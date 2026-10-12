"""Утренняя сводка и планы для бота: /today, /week.

Сводка v2 (M11.6, M17.5): секции типов занятости с «Сейчас / Дальше» (заголовок —
название типа во множественном, строка — время · название · поля · место), план на
день (шаги заданий и подготовка — из плана), дело из ящика (поставленное на
сегодня, иначе самое старое), прочие события, просроченное, дедлайны и экзамены
недели. Если план ждёт подтверждения — напоминание открыть приложение.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import day_bounds_utc, get_tz, local_date, now_utc
from app.domain.enums import (
    BacklogStatus,
    EventKind,
    EventStatus,
    PlanRevisionStatus,
    ReminderKind,
    SourceType,
    SubtaskStatus,
    TaskStatus,
)
from app.domain.tasks import progress
from app.models import BacklogItem, Event, EventType, PlanRevision, Subtask, Task, User
from app.notify.message import (
    Message,
    Section,
    fmt_day,
    fmt_day_full,
    fmt_range,
    plural,
)
from app.services.event_text import busy_line, place
from app.services.event_types import event_types_by_id

# Просроченных в сводке — не больше, остальные «…и ещё N»
OVERDUE_LIMIT = 5


def event_line(
    e: Event, tz: ZoneInfo, context: str | None = None, event_type: EventType | None = None
) -> str:
    mark = "✓ " if e.status == EventStatus.done else ""
    where = place(e, event_type)
    loc = f" · {where}" if where else ""
    ctx = f" — {context}" if context and context != e.title else ""
    return f"{mark}{fmt_range(e.start, e.end, tz)} {e.title}{ctx}{loc}"


PLAN_KINDS = frozenset({EventKind.subtask, EventKind.prep, EventKind.project})


async def task_progress(db: AsyncSession, tasks: list[Task]) -> dict[object, float]:
    if not tasks:
        return {}
    rows = await db.execute(
        select(
            Subtask.task_id,
            func.count(),
            func.count().filter(Subtask.status == SubtaskStatus.done),
        )
        .where(Subtask.task_id.in_([t.id for t in tasks]), Subtask.deleted_at.is_(None))
        .group_by(Subtask.task_id)
    )
    counts = {task_id: (done, total) for task_id, total, done in rows}
    return {
        t.id: progress(*counts.get(t.id, (0, 0)), task_done=t.status == TaskStatus.done)
        for t in tasks
    }


def deadline_line(t: Task, share: float, tz: ZoneInfo, today: date) -> str:
    if t.deadline is None:  # в секции дедлайнов — только задания со сроком
        return t.title
    local = t.deadline.astimezone(tz)
    when = fmt_day(local.date(), today)
    if local.strftime("%H:%M") != "23:59":
        when += f" {local.strftime('%H:%M')}"
    pct = f" · {round(share * 100)}%" if share > 0 else ""
    return f"{when} — {t.title}{pct}"


class Digest:
    def __init__(self, db: AsyncSession, user: User, now: datetime | None = None) -> None:
        self.db = db
        self.user = user
        self.tz = get_tz(user.timezone)
        self.now = now or now_utc()
        self.today = local_date(self.now, self.tz)
        self._types: dict[uuid.UUID, EventType] | None = None

    async def types(self) -> dict[uuid.UUID, EventType]:
        if self._types is None:
            self._types = await event_types_by_id(self.db, self.user.id)
        return self._types

    async def _sectioned(self, e: Event) -> EventType | None:
        """Тип события, если у него своя секция («Сейчас / Дальше»)."""
        if e.kind != EventKind.busy or e.event_type_id is None:
            return None
        t = (await self.types()).get(e.event_type_id)
        return t if t is not None and t.show_now_next else None

    async def _events(self, start: datetime, end: datetime) -> list[Event]:
        return list(
            await self.db.scalars(
                select(Event)
                .where(
                    Event.user_id == self.user.id,
                    Event.deleted_at.is_(None),
                    Event.start < end,
                    Event.end > start,
                )
                .order_by(Event.start, Event.title)
            )
        )

    async def _deadlines(self, start: datetime, end: datetime) -> list[Task]:
        return list(
            await self.db.scalars(
                select(Task)
                .where(
                    Task.user_id == self.user.id,
                    Task.deleted_at.is_(None),
                    Task.status == TaskStatus.active,
                    Task.deadline >= start,
                    Task.deadline < end,
                )
                .order_by(Task.deadline)
            )
        )

    async def _deadline_section(
        self, start: datetime, end: datetime, title: str, limit: int | None = None
    ) -> list[Section]:
        tasks = await self._deadlines(start, end)
        if not tasks:
            return []
        shown = tasks[:limit] if limit else tasks
        shares = await task_progress(self.db, shown)
        lines = [deadline_line(t, shares[t.id], self.tz, self.today) for t in shown]
        if rest := len(tasks) - len(shown):
            lines.append(f"…и ещё {rest}")
        return [Section(title, tuple(lines))]

    async def _oldest_backlog(self) -> BacklogItem | None:
        return await self.db.scalar(
            select(BacklogItem)
            .where(
                BacklogItem.user_id == self.user.id,
                BacklogItem.deleted_at.is_(None),
                BacklogItem.status == BacklogStatus.active,
            )
            .order_by(BacklogItem.created_at)
            .limit(1)
        )

    async def _task_titles(self, events: list[Event]) -> dict[object, str]:
        """Блок шага → название задания (для строки «шаг — задание»)."""
        ids = [e.source_id for e in events if e.source_type == SourceType.subtask]
        if not ids:
            return {}
        rows = await self.db.execute(
            select(Subtask.id, Task.title)
            .join(Task, Task.id == Subtask.task_id)
            .where(Subtask.id.in_(ids), Subtask.user_id == self.user.id)
        )
        return dict(rows.all())

    async def _day_sections(self, events: list[Event]) -> tuple[list[Section], bool]:
        """Разделы дня и есть ли в нём дело из ящика."""
        types = await self.types()
        live = [e for e in events if e.status != EventStatus.cancelled]
        by_type: dict[uuid.UUID, list[Event]] = defaultdict(list)
        for e in events:
            if (t := await self._sectioned(e)) is not None:
                by_type[t.id].append(e)
        sectioned = {e.id for group in by_type.values() for e in group}
        plan = [e for e in live if e.kind in PLAN_KINDS and e.status != EventStatus.missed]
        box = [e for e in live if e.kind == EventKind.backlog and e.status != EventStatus.missed]
        others = [
            e
            for e in live
            if e.kind not in PLAN_KINDS | {EventKind.backlog}
            and e.id not in sectioned
            and e.status != EventStatus.missed
        ]
        sections = []
        for t in sorted((types[i] for i in by_type), key=lambda t: (t.position, t.name)):
            lines = tuple(busy_line(e, t, self.tz) for e in by_type[t.id])
            sections.append(Section(t.name_plural, lines))
        if plan:
            tasks = await self._task_titles(plan)
            sections.append(
                Section(
                    "План на день",
                    tuple(event_line(e, self.tz, tasks.get(e.source_id)) for e in plan),
                )
            )
        if box:
            sections.append(Section("Из долгого ящика", tuple(event_line(e, self.tz) for e in box)))
        if others:
            lines = tuple(
                event_line(e, self.tz, event_type=types.get(e.event_type_id))  # type: ignore[arg-type]
                for e in others
            )
            sections.append(Section("В календаре", lines))
        return sections, bool(box)

    async def _exam_section(self, start: datetime, end: datetime) -> list[Section]:
        from app.services.exams import days_until, upcoming_exams

        exams = await upcoming_exams(self.db, self.user, start, end)
        if not exams:
            return []
        # Подпись места — по типу занятости события экзамена
        types = await self.types()
        labels = {
            source_id: types[type_id].location_label
            for source_id, type_id in await self.db.execute(
                select(Event.source_id, Event.event_type_id).where(
                    Event.user_id == self.user.id,
                    Event.deleted_at.is_(None),
                    Event.source_type == SourceType.exam,
                    Event.source_id.in_([exam.id for exam, _ in exams]),
                )
            )
            if type_id in types
        }
        lines = []
        for exam, title in exams:
            n = days_until(exam, self.today, self.tz)
            when = fmt_day(local_date(exam.starts_at, self.tz), self.today)
            left = f" · через {n} {plural(n, 'день', 'дня', 'дней')}" if n > 1 else ""
            label = labels.get(exam.id)
            room = f" · {label} {exam.location}" if label else f" · {exam.location}"
            room = room if exam.location else ""
            lines.append(f"{when} {exam.starts_at.astimezone(self.tz):%H:%M} — {title}{room}{left}")
        return [Section("Экзамены", tuple(lines))]

    async def _pending_plan(self) -> list[Section]:
        rev = await self.db.scalar(
            select(PlanRevision).where(
                PlanRevision.user_id == self.user.id,
                PlanRevision.deleted_at.is_(None),
                PlanRevision.status == PlanRevisionStatus.proposed,
            )
        )
        if rev is None:
            return []
        risky = {r.get("group_title") or r.get("task_title") for r in rev.at_risk}
        text = "План ждёт подтверждения — откройте приложение"
        if risky:
            text += f" (под угрозой: {', '.join(sorted(t for t in risky if t))})"
        return [Section(None, (text,))]

    async def day(self, day: date, *, morning: bool = False) -> Message:
        """Сводка на день: утренняя (morning) или ответ на /today."""
        start, end = day_bounds_utc(day, self.tz)
        sections, has_box = await self._day_sections(await self._events(start, end))
        if not sections:
            sections.append(Section(None, ("Событий и дел в календаре нет.",)))
        # Несданное к сроку не пропадает из сводки, пока его не закроют
        sections += await self._deadline_section(
            datetime.min.replace(tzinfo=UTC), self.now, "Просрочено", limit=OVERDUE_LIMIT
        )
        sections += await self._deadline_section(
            max(start, self.now), start + timedelta(days=7), "Дедлайны недели"
        )
        sections += await self._exam_section(max(start, self.now), start + timedelta(days=8))
        if not has_box and (item := await self._oldest_backlog()):
            waiting = (self.today - local_date(item.created_at, self.tz)).days
            age = f" — ждёт {waiting} {plural(waiting, 'день', 'дня', 'дней')}" if waiting else ""
            sections.append(Section("Из долгого ящика", (f"{item.title}{age}",)))
        if morning:
            sections = await self._pending_plan() + sections
        title = fmt_day_full(day)
        if morning:
            title = f"Доброе утро! {title}"
        return Message(
            title=title,
            sections=tuple(sections),
            url="/",
            kind=ReminderKind.morning_digest,
            tag=f"digest-{day.isoformat()}",
        )

    async def week(self, first: date) -> Message:
        """План на 7 дней начиная с `first` (/week)."""
        start, _ = day_bounds_utc(first, self.tz)
        _, end = day_bounds_utc(first + timedelta(days=6), self.tz)
        events = await self._events(start, end)
        by_day: dict[date, list[Event]] = {}
        for e in events:
            by_day.setdefault(local_date(e.start, self.tz), []).append(e)
        types = await self.types()
        sections = []
        for i in range(7):
            items = []
            for e in by_day.get(first + timedelta(days=i), []):
                t = await self._sectioned(e)
                if t is not None:
                    items.append(busy_line(e, t, self.tz))
                elif e.status != EventStatus.cancelled:
                    items.append(event_line(e, self.tz, event_type=types.get(e.event_type_id)))  # type: ignore[arg-type]
            if items:
                day = first + timedelta(days=i)
                sections.append(Section(fmt_day(day, self.today).capitalize(), tuple(items)))
        if not sections:
            sections.append(Section(None, ("На неделе в календаре пусто.",)))
        sections += await self._deadline_section(start, end, "Дедлайны")
        last = first + timedelta(days=6)
        return Message(
            title=f"Неделя: {fmt_day(first)} — {fmt_day(last)}", sections=tuple(sections)
        )
