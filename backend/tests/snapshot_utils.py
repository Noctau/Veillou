"""Снимки (M14.1): сравнение текста с файлом в tests/snapshots/ и нормализация.

Перезаписать снимки: `make snapshots-update` (UPDATE_SNAPSHOTS=1). Снимок меняется
только осознанно — с пометкой в коммите, почему поменялось поведение.

Нормализация убирает то, что меняется от прогона к прогону или от миграции к
миграции, но не поведение: UUID заменяются метками сущностей (`‹Климатология›`),
моменты — местным временем пользователя.
"""

import dataclasses
import difflib
import json
import os
import re
import uuid
from collections.abc import Iterable
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActionType,
    Area,
    AreaType,
    BacklogItem,
    Category,
    ClassRule,
    DayOff,
    Event,
    Exam,
    ExamQuestion,
    ExamSession,
    LoadBudget,
    Milestone,
    Note,
    Project,
    RecurringEvent,
    Semester,
    Source,
    Subtask,
    Task,
    TaskType,
)

SNAPSHOTS = Path(__file__).parent / "snapshots"
UPDATE = os.environ.get("UPDATE_SNAPSHOTS") == "1"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class Snapshots:
    """Копит расхождения со снимками, `verify()` роняет тест со всеми диффами сразу."""

    def __init__(self, folder: str) -> None:
        self.dir = SNAPSHOTS / folder
        self.failures: list[str] = []

    def check(self, name: str, content: str) -> None:
        path = self.dir / name
        content = content.rstrip() + "\n"
        if UPDATE:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            return
        if not path.exists():
            self.failures.append(f"{name}: снимка нет — make snapshots-update")
            return
        expected = path.read_text()
        if expected != content:
            diff = difflib.unified_diff(
                expected.splitlines(),
                content.splitlines(),
                f"snapshots/{path.relative_to(SNAPSHOTS)}",
                "сейчас",
                lineterm="",
                n=2,
            )
            self.failures.append("\n".join(diff))

    def verify(self) -> None:
        if self.failures:
            pytest.fail(
                "Поведение разошлось со снимком. Если так и задумано — make snapshots-update "
                "и пометка в коммите.\n\n" + "\n\n".join(self.failures),
                pytrace=False,
            )


class Labels:
    """UUID → понятная метка сущности; неизвестные — `‹?N›` в порядке появления."""

    def __init__(self, tz: ZoneInfo) -> None:
        self.tz = tz
        self.names: dict[str, str] = {}
        self.unknown: dict[str, str] = {}

    def _add(self, id: uuid.UUID, label: str) -> None:
        taken = set(self.names.values())
        unique, n = label, 2
        while unique in taken:
            unique, n = f"{label} #{n}", n + 1
        self.names[str(id)] = unique

    def local(self, moment: datetime) -> str:
        local = moment.astimezone(self.tz)
        return local.strftime("%Y-%m-%d %H:%M" + (":%S" if local.second else ""))

    async def load(self, db: AsyncSession, user_id: uuid.UUID) -> None:
        async def rows[M](model: type[M]) -> list[M]:
            stmt = select(model).where(model.user_id == user_id)  # type: ignore[attr-defined]
            return list(await db.scalars(stmt.order_by(model.created_at, model.id)))  # type: ignore[attr-defined]

        areas = {a.id: a.name for a in await rows(Area)}
        tasks = {t.id: t.title for t in await rows(Task)}
        exams = {e.id: f"Экзамен {areas.get(e.area_id, '?')}" for e in await rows(Exam)}
        simple: list[tuple[Iterable[Any], str]] = [
            (await rows(Semester), "name"),
            (await rows(AreaType), "name"),
            (await rows(Area), "name"),
            (await rows(DayOff), "title"),
            (await rows(RecurringEvent), "title"),
            (await rows(Category), "name"),
            (await rows(ActionType), "name"),
            (await rows(TaskType), "name"),
            (await rows(Task), "title"),
            (await rows(Project), "title"),
            (await rows(Milestone), "title"),
            (await rows(BacklogItem), "title"),
            (await rows(Note), "title"),
            (await rows(Source), "title"),
        ]
        for items, attr in simple:
            for item in items:
                self._add(item.id, getattr(item, attr))
        for exam_id, label in exams.items():
            self._add(exam_id, label)
        for budget in await rows(LoadBudget):
            self._add(budget.id, f"лимит {budget.name}")
        for r in await rows(ClassRule):
            when = f"пара {r.pair_number}" if r.pair_number else f"{r.start_time:%H:%M}"
            parity = f" {r.parity}" if r.parity != "all" else ""
            self._add(r.id, f"{areas.get(r.area_id)} д{r.weekday} {when}{parity}")
        for st in await rows(Subtask):
            occ = f" {st.occurrence_date:%d.%m}" if st.occurrence_date else ""
            self._add(st.id, f"{tasks.get(st.task_id)} / {st.title}{occ}")
        for q in await rows(ExamQuestion):
            self._add(q.id, f"{exams.get(q.exam_id)} / вопрос {q.number}")
        for x in await rows(ExamSession):
            self._add(x.id, f"{exams.get(x.exam_id)} / {x.kind} {x.date:%d.%m}")
        for e in await rows(Event):
            self._add(e.id, f"{e.title} {e.start.astimezone(self.tz):%d.%m %H:%M}")

    def _sub(self, m: re.Match[str]) -> str:
        key = m.group(0)
        if key in self.names:
            return f"‹{self.names[key]}›"
        if key not in self.unknown:
            self.unknown[key] = f"?{len(self.unknown) + 1}"
        return f"‹{self.unknown[key]}›"

    def text(self, value: str) -> str:
        return UUID_RE.sub(self._sub, value)

    def plain(self, value: Any) -> Any:
        """Значение → JSON-совместимое, без UUID и с местным временем."""
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {f.name: self.plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
        if isinstance(value, Enum):
            return self.plain(value.value)
        if isinstance(value, datetime):
            return self.local(value)
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, time):
            return value.strftime("%H:%M")
        if isinstance(value, ZoneInfo):
            return value.key
        if isinstance(value, uuid.UUID):
            return self.text(str(value))
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {str(self.plain(k)): self.plain(v) for k, v in value.items()}
        if isinstance(value, (set, frozenset)):
            return sorted((self.plain(v) for v in value), key=_sort_key)
        if isinstance(value, (list, tuple)):
            return [self.plain(v) for v in value]
        return value

    def json(self, value: Any) -> str:
        return dump(self.plain(value))

    def inline(self, value: Any) -> str:
        """Значение в одну строку: моменты ISO-строкой — в местное время, переводы строк — ⏎."""
        if isinstance(value, str):
            try:
                moment = datetime.fromisoformat(value)
            except ValueError:
                moment = None
            if moment is not None and moment.tzinfo is not None:
                return self.local(moment)
            return self.text(value).replace("\n", "⏎")
        plain = self.plain(value)
        if isinstance(plain, str):
            return plain.replace("\n", "⏎")
        return json.dumps(plain, ensure_ascii=False)


def dump(value: Any, indent: str = "") -> str:
    """JSON с отступами, но списки скаляров — в одну строку (окна, дни недели)."""
    inner = indent + " "
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [
            f"{inner}{json.dumps(k, ensure_ascii=False)}: {dump(v, inner)}"
            for k, v in value.items()
        ]
        return "{\n" + ",\n".join(items) + f"\n{indent}}}"
    if isinstance(value, list):
        if all(not isinstance(v, (dict, list)) for v in value):
            return json.dumps(value, ensure_ascii=False)
        return "[\n" + ",\n".join(inner + dump(v, inner) for v in value) + f"\n{indent}]"
    return json.dumps(value, ensure_ascii=False)


def _sort_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
