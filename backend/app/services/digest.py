"""Утренняя сводка и планы для бота: /today, /week.

Сводка v2 (M11.6): пары с аудиториями, план на день (шаги заданий и подготовка
к экзаменам — из плана), дело из ящика (поставленное на сегодня, иначе самое
старое), прочие события, просроченное, дедлайны и экзамены недели. Если план
ждёт подтверждения — напоминание открыть приложение.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import day_bounds_utc, get_tz, local_date, now_utc
from app.domain.enums import (
    BacklogStatus,
    ClassType,
    EventKind,
    EventStatus,
    PlanRevisionStatus,
    ReminderKind,
    SourceType,
    SubtaskStatus,
    TaskStatus,
)
from app.domain.tasks import progress
from app.models import BacklogItem, Event, PlanRevision, Subtask, Task, User
from app.notify.message import (
    Message,
    Section,
    fmt_day,
    fmt_day_full,
    fmt_range,
    plural,
)

# Просроченных в сводке — не больше, остальные «…и ещё N»
OVERDUE_LIMIT = 5

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


def event_line(e: Event, tz: ZoneInfo, context: str | None = None) -> str:
    mark = "✓ " if e.status == EventStatus.done else ""
    loc = f" · {e.location}" if e.location else ""
    ctx = f" — {context}" if context and context != e.title else ""
    return f"{mark}{fmt_range(e.start, e.end, tz)} {e.title}{ctx}{loc}"


PLAN_KINDS = frozenset({EventKind.subtask, EventKind.exam_prep, EventKind.project})


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
        live = [e for e in events if e.status != EventStatus.cancelled]
        classes = [e for e in events if e.kind == EventKind.class_]
        plan = [e for e in live if e.kind in PLAN_KINDS and e.status != EventStatus.missed]
        box = [e for e in live if e.kind == EventKind.backlog and e.status != EventStatus.missed]
        others = [
            e
            for e in live
            if e.kind not in PLAN_KINDS | {EventKind.class_, EventKind.backlog}
            and e.status != EventStatus.missed
        ]
        sections = []
        if classes:
            sections.append(Section("Пары", tuple(class_line(e, self.tz) for e in classes)))
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
            sections.append(Section("В календаре", tuple(event_line(e, self.tz) for e in others)))
        return sections, bool(box)

    async def _exam_section(self, start: datetime, end: datetime) -> list[Section]:
        from app.services.exams import days_until, upcoming_exams

        exams = await upcoming_exams(self.db, self.user, start, end)
        if not exams:
            return []
        lines = []
        for exam, title in exams:
            n = days_until(exam, self.today, self.tz)
            when = fmt_day(local_date(exam.starts_at, self.tz), self.today)
            left = f" · через {n} {plural(n, 'день', 'дня', 'дней')}" if n > 1 else ""
            room = f" · ауд. {exam.location}" if exam.location else ""
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
            sections.append(Section(None, ("Пар и дел в календаре нет.",)))
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
