"""Утренняя сводка (M6.4) и планы для бота: /today, /week.

Сводка v1: пары с аудиториями, события дня, дедлайны недели и одно самое
старое дело из ящика. План подзадач появится в v2 (M11.6).
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import day_bounds_utc, get_tz, local_date, now_utc
from app.domain.enums import (
    BacklogStatus,
    ClassType,
    EventKind,
    EventStatus,
    ReminderKind,
    SubtaskStatus,
    TaskStatus,
)
from app.domain.tasks import progress
from app.models import BacklogItem, Event, Subtask, Task, User
from app.notify.message import (
    Message,
    Section,
    fmt_day,
    fmt_day_full,
    fmt_range,
    plural,
)

CLASS_TYPE_SHORT = {
    ClassType.lecture: "лекция",
    ClassType.seminar: "семинар",
    ClassType.lab: "лаба",
}


def class_line(e: Event, tz: ZoneInfo) -> str:
    parts = [f"{fmt_range(e.start, e.end, tz)} {e.title}"]
    if e.class_type and (label := CLASS_TYPE_SHORT.get(ClassType(e.class_type))):
        parts[0] += f" ({label})"
    if e.location:
        parts.append(f"ауд. {e.location}")
    line = " · ".join(parts)
    return f"{line} — отменена" if e.status == EventStatus.cancelled else line


def event_line(e: Event, tz: ZoneInfo) -> str:
    mark = "✓ " if e.status == EventStatus.done else ""
    loc = f" · {e.location}" if e.location else ""
    return f"{mark}{fmt_range(e.start, e.end, tz)} {e.title}{loc}"


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
    assert t.deadline is not None
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

    async def _deadline_section(self, start: datetime, end: datetime, title: str) -> list[Section]:
        tasks = await self._deadlines(start, end)
        if not tasks:
            return []
        shares = await task_progress(self.db, tasks)
        return [
            Section(
                title,
                tuple(deadline_line(t, shares[t.id], self.tz, self.today) for t in tasks),
            )
        ]

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

    def _day_sections(self, events: list[Event]) -> list[Section]:
        classes = [e for e in events if e.kind == EventKind.class_]
        others = [
            e for e in events if e.kind != EventKind.class_ and e.status != EventStatus.cancelled
        ]
        sections = []
        if classes:
            sections.append(Section("Пары", tuple(class_line(e, self.tz) for e in classes)))
        if others:
            sections.append(Section("В календаре", tuple(event_line(e, self.tz) for e in others)))
        return sections

    async def day(self, day: date, *, morning: bool = False) -> Message:
        """Сводка на день: утренняя (morning) или ответ на /today."""
        start, end = day_bounds_utc(day, self.tz)
        sections = self._day_sections(await self._events(start, end))
        if not sections:
            sections.append(Section(None, ("Пар и дел в календаре нет.",)))
        sections += await self._deadline_section(
            start, start + timedelta(days=7), "Дедлайны недели"
        )
        if item := await self._oldest_backlog():
            waiting = (self.today - local_date(item.created_at, self.tz)).days
            age = f" — ждёт {waiting} {plural(waiting, 'день', 'дня', 'дней')}" if waiting else ""
            sections.append(Section("Из долгого ящика", (f"{item.title}{age}",)))
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
        sections = []
        for i in range(7):
            d = first + timedelta(days=i)
            day_events = [
                e
                for e in by_day.get(d, [])
                if not (e.kind != EventKind.class_ and e.status == EventStatus.cancelled)
            ]
            if not day_events:
                continue
            items = tuple(
                class_line(e, self.tz) if e.kind == EventKind.class_ else event_line(e, self.tz)
                for e in day_events
            )
            sections.append(Section(fmt_day(d, self.today).capitalize(), items))
        if not sections:
            sections.append(Section(None, ("На неделе в календаре пусто.",)))
        sections += await self._deadline_section(start, end, "Дедлайны")
        last = first + timedelta(days=6)
        return Message(
            title=f"Неделя: {fmt_day(first)} — {fmt_day(last)}", sections=tuple(sections)
        )
