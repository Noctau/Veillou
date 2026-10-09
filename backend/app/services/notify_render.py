"""Текст напоминания — собирается в момент отправки по актуальной сущности.

None — напоминание устарело (пару отменили или перенесли, задание сделано или
дедлайн сдвинут): отправитель его пропускает, а пересборка уже создала новое.
"""

from dataclasses import replace
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import day_bounds_utc, get_tz, local_date
from app.domain.enums import (
    ClassType,
    EventKind,
    EventStatus,
    ReminderAction,
    ReminderKind,
    SourceType,
    SubtaskStatus,
    TaskStatus,
)
from app.models import Event, Reminder, Subject, Subtask, Task, User
from app.notify.message import Message, Section, fmt_moment, fmt_range, lines, plural
from app.services.digest import CLASS_TYPE_SHORT, Digest, deadline_line, task_progress

ACTIONS = (ReminderAction.done, ReminderAction.snooze, ReminderAction.tomorrow)


async def _event(db: AsyncSession, r: Reminder) -> Event | None:
    if r.entity_id is None:
        return None
    e = await db.get(Event, r.entity_id)
    if e is None or e.user_id != r.user_id or e.deleted_at is not None:
        return None
    if e.status != EventStatus.planned:
        return None
    if r.payload.get("start") and e.start != datetime.fromisoformat(r.payload["start"]):
        return None
    return e


async def _task(db: AsyncSession, r: Reminder) -> Task | None:
    if r.entity_id is None:
        return None
    t = await db.get(Task, r.entity_id)
    if t is None or t.user_id != r.user_id or t.deleted_at is not None:
        return None
    if t.status != TaskStatus.active or t.deadline is None:
        return None
    if r.payload.get("deadline") and t.deadline != datetime.fromisoformat(r.payload["deadline"]):
        return None
    return t


async def _before_class(db: AsyncSession, user: User, r: Reminder, now: datetime) -> Message | None:
    e = await _event(db, r)
    if e is None or e.kind != EventKind.class_:
        return None
    tz = get_tz(user.timezone)
    minutes = round((e.start - now).total_seconds() / 60)
    if minutes <= 0:
        when = "Сейчас"
    elif minutes < 60:
        when = f"Через {minutes} мин"
    else:
        when = f"В {e.start.astimezone(tz):%H:%M}"

    kind = CLASS_TYPE_SHORT.get(ClassType(e.class_type)) if e.class_type else None
    where = f"ауд. {e.location}" if e.location else None
    head = " · ".join(p for p in (fmt_range(e.start, e.end, tz), kind, where) if p)
    info = lines(head, f"Преподаватель: {e.teacher}" if e.teacher else None)
    sections = [Section(None, info)]
    if e.note.strip():
        sections.append(Section("Взять / подготовить", tuple(e.note.strip().splitlines())))

    if e.subject_id is not None:
        # Что сдавать по предмету до конца завтрашнего дня
        day = local_date(e.start, tz)
        _, until = day_bounds_utc(day + timedelta(days=1), tz)
        tasks = list(
            await db.scalars(
                select(Task)
                .where(
                    Task.user_id == user.id,
                    Task.deleted_at.is_(None),
                    Task.status == TaskStatus.active,
                    Task.subject_id == e.subject_id,
                    Task.deadline >= now,
                    Task.deadline < until,
                )
                .order_by(Task.deadline)
            )
        )
        if tasks:
            shares = await task_progress(db, tasks)
            sections.append(
                Section("Сдать", tuple(deadline_line(t, shares[t.id], tz, day) for t in tasks))
            )
    url = f"/subjects/{e.subject_id}" if e.subject_id else "/calendar"
    return Message(
        title=f"{when}: {e.title}",
        sections=tuple(sections),
        url=url,
        kind=ReminderKind.before_class,
        tag=f"class-{e.id}",
    )


def _deadline_title(days_before: int) -> str:
    if days_before == 0:
        return "Сегодня дедлайн"
    if days_before == 1:
        return "Завтра дедлайн"
    return f"Дедлайн через {days_before} {plural(days_before, 'день', 'дня', 'дней')}"


async def _deadline(db: AsyncSession, user: User, r: Reminder, now: datetime) -> Message | None:
    t = await _task(db, r)
    if t is None or t.deadline is None:  # срок сняли — напоминание устарело
        return None
    tz = get_tz(user.timezone)
    today = local_date(now, tz)
    days_before = (local_date(t.deadline, tz) - today).days
    share = (await task_progress(db, [t]))[t.id]
    subject = await db.get(Subject, t.subject_id) if t.subject_id else None
    info = lines(
        f"Сдать: {fmt_moment(t.deadline, tz, today)}",
        f"Готово {round(share * 100)}%" if share > 0 else None,
        subject.name if subject and subject.deleted_at is None else None,
    )
    return Message(
        title=f"{_deadline_title(max(days_before, 0))}: {t.title}",
        sections=(Section(None, info),),
        url=f"/tasks/{t.id}",
        actions=ACTIONS,
        kind=ReminderKind.deadline,
        tag=f"task-{t.id}",
    )


async def _subtask_start(
    db: AsyncSession, user: User, r: Reminder, now: datetime
) -> Message | None:
    e = await _event(db, r)
    if e is None or e.source_type != SourceType.subtask or e.source_id is None:
        return None
    st = await db.get(Subtask, e.source_id)
    if st is None or st.deleted_at is not None or st.status != SubtaskStatus.todo:
        return None
    task = await db.get(Task, st.task_id)
    if task is None or task.deleted_at is not None:
        return None
    tz = get_tz(user.timezone)
    info = lines(fmt_range(e.start, e.end, tz), task.title if task.title != st.title else None)
    return Message(
        title=f"Пора: {st.title}",
        sections=(Section(None, info),),
        url=f"/tasks/{task.id}",
        actions=ACTIONS,
        kind=ReminderKind.subtask_start,
        tag=f"block-{e.id}",
    )


async def _digest(db: AsyncSession, user: User, r: Reminder, now: datetime) -> Message | None:
    day = date.fromisoformat(r.payload["date"])
    return await Digest(db, user, now).day(day, morning=True)


def _minutes(total: int) -> str:
    h, m = divmod(total, 60)
    return f"{h} ч {m} мин" if h and m else (f"{h} ч" if h else f"{m} мин")


async def _evening(db: AsyncSession, user: User, r: Reminder, now: datetime) -> Message | None:
    """Вечерний разбор. Всё отмечено — не присылаем."""
    from app.services.review import ReviewService

    day = date.fromisoformat(r.payload["date"])
    items, done = await ReviewService(db, user, now).evening_items(day)
    if not items:
        return None
    tz = get_tz(user.timezone)
    head = f"Сделано: {done}. " if done else ""
    hint = "Перенести невыполненное? Остальное сдвинется, предупрежу, если дедлайн под угрозой."
    return Message(
        title=f"Вечерний разбор: не отмечено {len(items)}",
        sections=(
            Section(None, tuple(f"{fmt_range(e.start, e.end, tz)} {e.title}" for e in items)),
            Section(None, (head + hint,)),
        ),
        url="/review",
        actions=(ReminderAction.reschedule, ReminderAction.pick),
        kind=ReminderKind.evening_review,
        tag=f"evening-{day.isoformat()}",
    )


async def _weekly(db: AsyncSession, user: User, r: Reminder, now: datetime) -> Message | None:
    """Недельный разбор: итоги и дела из ящика на неделю."""
    from app.services.review import ReviewService

    review = await ReviewService(db, user, now).weekly()
    st = review.stats
    if not st.blocks_planned and not review.suggestions and not review.planned:
        return None
    sections = []
    if st.blocks_planned or st.tasks_done or st.backlog_done:
        summary = lines(
            f"Сделано блоков: {st.blocks_done} из {st.blocks_planned}"
            + (f" ({_minutes(st.done_minutes)})" if st.done_minutes else ""),
            f"Не сделано: {st.blocks_missed}" if st.blocks_missed else None,
            f"Заданий сдано: {st.tasks_done}" if st.tasks_done else None,
            f"Дел из ящика закрыто: {st.backlog_done}" if st.backlog_done else None,
        )
        sections.append(Section("Итоги недели", summary))
    if review.planned:
        sections.append(Section("Уже на неделе", tuple(i.title for i in review.planned)))
    if review.suggestions:
        sections.append(
            Section("Из ящика на неделю", tuple(f"• {i.title}" for i in review.suggestions))
        )
    return Message(
        title="Разбор недели",
        sections=tuple(sections),
        url="/review/week",
        actions=(ReminderAction.accept,) if review.suggestions else (),
        kind=ReminderKind.weekly_review,
        tag=f"weekly-{review.week_start.isoformat()}",
    )


def _test(*_: object) -> Message:
    return Message(
        title="Уведомления работают",
        sections=(Section(None, ("Так будут приходить напоминания.",)),),
        url="/settings",
        kind=ReminderKind.test,
    )


async def render(db: AsyncSession, user: User, r: Reminder, now: datetime) -> Message | None:
    kind = ReminderKind(r.kind)
    if kind == ReminderKind.before_class:
        msg = await _before_class(db, user, r, now)
    elif kind == ReminderKind.deadline:
        msg = await _deadline(db, user, r, now)
    elif kind == ReminderKind.subtask_start:
        msg = await _subtask_start(db, user, r, now)
    elif kind == ReminderKind.morning_digest:
        msg = await _digest(db, user, r, now)
    elif kind == ReminderKind.evening_review:
        msg = await _evening(db, user, r, now)
    elif kind == ReminderKind.weekly_review:
        msg = await _weekly(db, user, r, now)
    else:
        msg = _test()
    return None if msg is None else replace(msg, reminder_id=r.id)
