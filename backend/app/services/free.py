"""«У меня есть N минут» / `/free` (M11.4): кандидаты из БД → `domain/free.pick`.

Шаги заданий: несделанные, без невыполненных зависимостей, вхождения
регулярных — только сегодняшние; порядок — по ближайшему блоку в плане, потом
по дедлайну. Дела из ящика: сначала взятые на неделю, дальше по приоритету.
«Начать» ставит блок на «сейчас» закреплённым (у шага — переносит его блок).
"""

import uuid
from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc, wall_to_utc
from app.domain import backlog as box
from app.domain.calibration import calibrated
from app.domain.enums import (
    ActionTypeKey,
    BacklogCondition,
    BacklogStatus,
    EventKind,
    EventStatus,
    SourceType,
    SubtaskStatus,
    TaskStatus,
)
from app.domain.free import FreeCandidate, pick
from app.domain.planner import Window
from app.models import ActionType, BacklogItem, Event, Subtask, Task, User
from app.models.base import UserOwnedMixin
from app.schemas.review import FreeSuggestion
from app.schemas.task import SubtaskSchedule
from app.services.calibration import DEFAULT_ACTION, coefficients
from app.services.replan import windows_from_json
from app.services.settings import effective_settings
from app.services.tasks import TaskService

SOURCE_MODEL: dict[str, type[Task] | type[Subtask] | type[BacklogItem]] = {
    "subtask": Subtask,
    "task": Task,
    "backlog": BacklogItem,
}
SOURCE_TYPE = {
    "subtask": SourceType.subtask,
    "task": SourceType.task,
    "backlog": SourceType.backlog_item,
}


Kind = Literal["subtask", "task", "backlog"]
# Подпись (задание шага / «Из ящика»), id задания и его дедлайн
Meta = tuple[str | None, uuid.UUID | None, datetime | None]


class FreeService:
    def __init__(self, db: AsyncSession, user: User, now: datetime | None = None) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.now = now or now_utc()
        self.today = local_date(self.now, self.tz)

    async def _all[M: UserOwnedMixin](self, model: type[M], *where: ColumnElement[bool]) -> list[M]:
        stmt = select(model).where(
            model.user_id == self.user_id,
            model.deleted_at.is_(None),
            *where,
        )
        return list(await self.db.scalars(stmt))

    async def candidates(self) -> tuple[list[FreeCandidate], dict[tuple[Kind, uuid.UUID], Meta]]:
        action_types = {a.id: a for a in await self._all(ActionType)}
        by_key = {a.key: a for a in action_types.values() if a.key}
        coefs = await coefficients(self.db, self.user_id)
        tasks = {t.id: t for t in await self._all(Task, Task.status == TaskStatus.active)}
        subtasks = await self._all(Subtask, Subtask.task_id.in_(tasks))
        status = {str(st.id): st.status for st in subtasks}
        subs_by_task: dict[uuid.UUID, list[Subtask]] = defaultdict(list)
        for st in subtasks:
            subs_by_task[st.task_id].append(st)
        next_block: dict[uuid.UUID, datetime] = {}
        for e in await self._all(
            Event,
            Event.status == EventStatus.planned,
            Event.start >= self.now,
            Event.source_type.in_([SourceType.subtask, SourceType.task]),
        ):
            if e.source_id is None:
                continue
            if e.source_id not in next_block or e.start < next_block[e.source_id]:
                next_block[e.source_id] = e.start

        def type_of(type_id: uuid.UUID | None) -> ActionType | None:
            return action_types.get(type_id) if type_id else None

        result: list[FreeCandidate] = []
        meta: dict[tuple[Kind, uuid.UUID], Meta] = {}
        for task in tasks.values():
            subs = subs_by_task.get(task.id, [])
            items: list[tuple[Literal["subtask", "task"], uuid.UUID, Subtask | None, int]] = []
            if subs:
                for st in subs:
                    if st.status != SubtaskStatus.todo:
                        continue
                    if st.occurrence_date is not None and st.occurrence_date != self.today:
                        continue
                    if any(status.get(d) == SubtaskStatus.todo for d in st.depends_on):
                        continue
                    items.append(("subtask", st.id, st, st.estimate_min))
            elif task.estimate_min:
                items.append(("task", task.id, None, task.estimate_min))
            for kind, id, sub, estimate in items:
                at = type_of((sub.action_type_id if sub else None) or task.action_type_id)
                if sub is not None and sub.time_window:
                    windows = windows_from_json(sub.time_window)
                elif task.time_window:
                    windows = windows_from_json(task.time_window)
                else:
                    windows = windows_from_json(at.windows) if at else ()
                key = (task.task_type, at.key if at and at.key else DEFAULT_ACTION)
                planned = next_block.get(id)
                rank = (
                    planned is None,
                    planned.timestamp() if planned else 0,
                    task.deadline.timestamp() if task.deadline else float("inf"),
                )
                result.append(
                    FreeCandidate(
                        kind,
                        id,
                        sub.title if sub else task.title,
                        calibrated(estimate, coefs.get(key, 1.0)),
                        windows,
                        rank=rank,
                    )
                )
                meta[(kind, id)] = (task.title if sub else None, task.id, task.deadline)

        s = effective_settings(self.user)
        work = (
            Window(
                frozenset({1, 2, 3, 4, 5}), s.work_hours.weekdays.start, s.work_hours.weekdays.end
            ),
            Window(frozenset({6, 7}), s.work_hours.weekends.start, s.work_hours.weekends.end),
        )
        institution = by_key.get(ActionTypeKey.institutions)
        inst_windows = windows_from_json(institution.windows) if institution else ()
        classes_today = await self._classes_today()
        week = box.week_start(self.today)
        for item in await self._all(BacklogItem, BacklogItem.status == BacklogStatus.active):
            at = type_of(item.action_type_id)
            base = (
                windows_from_json(item.time_window)
                if item.time_window
                else (windows_from_json(at.windows) if at else ()) or work
            )
            days = None
            if BacklogCondition.on_class_days in item.conditions:
                days = frozenset({self.today}) if classes_today else frozenset()
            created = local_date(item.created_at, self.tz)
            result.append(
                FreeCandidate(
                    "backlog",
                    item.id,
                    item.title,
                    item.estimate_min or box.DEFAULT_ESTIMATE_MIN,
                    box.condition_windows(base, item.conditions, inst_windows),
                    days,
                    rank=(
                        item.planned_week is None or item.planned_week < week,
                        -box.priority(created, item.desired_by, self.today),
                        created,
                    ),
                )
            )
            meta[("backlog", item.id)] = ("Из ящика", None, None)
        return result, meta

    async def _classes_today(self) -> bool:
        start = wall_to_utc(self.today, time(0), self.tz)
        rows = await self._all(
            Event,
            Event.kind == EventKind.class_,
            Event.status != EventStatus.cancelled,
            Event.start >= start,
            Event.start < start + timedelta(days=1),
        )
        return bool(rows)

    async def suggest(self, minutes: int) -> list[FreeSuggestion]:
        candidates, meta = await self.candidates()
        result = []
        for c in pick(candidates, minutes, self.now, self.tz):
            subtitle, task_id, deadline = meta[(c.kind, c.id)]
            result.append(
                FreeSuggestion(
                    kind=c.kind,
                    id=c.id,
                    title=c.title,
                    minutes=c.minutes,
                    subtitle=subtitle,
                    task_id=task_id,
                    deadline=deadline,
                )
            )
        return result

    async def _lock_source(self, kind: str, id: uuid.UUID) -> Task | Subtask | BacklogItem:
        """Источник блока под блокировкой: второе «Начать» ждёт первое."""
        model = SOURCE_MODEL[kind]
        obj: Task | Subtask | BacklogItem | None = await self.db.scalar(
            select(model)
            .where(model.id == id, model.user_id == self.user_id, model.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if obj is None:
            raise InvalidDataError("Это дело уже нельзя взять — обновите список")
        return obj

    async def _started_block(self, kind: str, id: uuid.UUID, start: datetime) -> Event | None:
        return await self.db.scalar(
            select(Event).where(
                Event.user_id == self.user_id,
                Event.deleted_at.is_(None),
                Event.source_type == SOURCE_TYPE[kind],
                Event.source_id == id,
                Event.status == EventStatus.planned,
                Event.start == start,
            )
        )

    async def start(self, kind: str, id: uuid.UUID) -> Event:
        """Поставить блок на «сейчас», закреплённым. Коммитит.

        Повторное «Начать» в ту же минуту (двойное нажатие) возвращает тот же блок."""
        if kind not in SOURCE_MODEL:
            raise InvalidDataError("Это дело уже нельзя взять — обновите список")
        source = await self._lock_source(kind, id)
        start = self.now.replace(second=0, microsecond=0)
        if (already := await self._started_block(kind, id, start)) is not None:
            return already
        candidates, _ = await self.candidates()
        found = next((c for c in candidates if c.kind == kind and c.id == id), None)
        if found is None:
            raise InvalidDataError("Это дело уже нельзя взять — обновите список")
        end = start + timedelta(minutes=found.minutes)
        if isinstance(source, Subtask):
            await TaskService(self.db, self.user).schedule(
                id, SubtaskSchedule(start=start, end=end)
            )
            event = await self._started_block(kind, id, start)
            if event is None:
                raise RuntimeError(f"Блок подзадачи {id} не поставлен")
            return event
        if isinstance(source, Task):
            event = Event(
                user_id=self.user_id,
                kind=EventKind.subtask,
                title=source.title,
                subject_id=source.subject_id,
                source_type=SourceType.task,
                source_id=id,
            )
        else:
            event = Event(
                user_id=self.user_id,
                kind=EventKind.backlog,
                title=source.title,
                source_type=SourceType.backlog_item,
                source_id=id,
            )
        event.start, event.end = start, end
        event.is_fixed, event.is_pinned, event.status = False, True, EventStatus.planned
        self.db.add(event)
        await self.db.commit()
        return event
