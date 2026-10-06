"""Регулярные задания: вхождения RRULE → подзадачи с `occurrence_date`.

Как личные повторы в календаре, но вместо событий — подзадачи (их потом
раскладывает планировщик). Окно — 60 дней вперёд, ночная джоба докатывает.

Синхронизация с сегодняшнего дня (локального):
- вхождение есть в правиле, но нет подзадачи → создаётся;
- подзадача есть, а в правиле дня больше нет → удаляется (если ещё не сделана);
- у будущих несделанных название и оценка следуют за заданием.
Прошлое и сделанное не трогается.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import get_tz, now_utc
from app.domain.enums import EventStatus, SourceType, SubtaskStatus, TaskStatus
from app.domain.recurrence import DateRange, rrule_dates
from app.models import Event, Subtask, Task, User

HORIZON_DAYS = 60
DEFAULT_ESTIMATE_MIN = 30


async def sync_recurring_task(db: AsyncSession, task: Task, today: date) -> int:
    """Приводит подзадачи-вхождения задания к его правилу. Не коммитит.

    Возвращает число созданных подзадач.
    """
    rows = await db.scalars(
        select(Subtask).where(
            Subtask.task_id == task.id,
            Subtask.deleted_at.is_(None),
            Subtask.occurrence_date.is_not(None),
        )
    )
    existing = {s.occurrence_date: s for s in rows}

    wanted: list[date] = []
    if task.recurrence and task.status == TaskStatus.active and task.deleted_at is None:
        wanted = rrule_dates(
            task.recurrence,
            dtstart=task.recurrence_start or today,
            window=DateRange(today, today + timedelta(days=HORIZON_DAYS)),
        )
    wanted_set = set(wanted)
    estimate = task.estimate_min or DEFAULT_ESTIMATE_MIN

    dropped: list[uuid.UUID] = []
    for day, subtask in existing.items():
        if day is None or day < today or subtask.status != SubtaskStatus.todo:
            continue
        if day in wanted_set:
            subtask.title = task.title
            subtask.estimate_min = estimate
        else:
            subtask.deleted_at = now_utc()
            dropped.append(subtask.id)
    if dropped:
        events = await db.scalars(
            select(Event).where(
                Event.source_type == SourceType.subtask,
                Event.source_id.in_(dropped),
                Event.status == EventStatus.planned,
                Event.deleted_at.is_(None),
            )
        )
        for event in events:
            event.deleted_at = now_utc()

    created = 0
    for day in wanted:
        if day in existing:
            continue
        db.add(
            Subtask(
                user_id=task.user_id,
                task_id=task.id,
                title=task.title,
                estimate_min=estimate,
                position=0,
                depends_on=[],
                status=SubtaskStatus.todo,
                note="",
                occurrence_date=day,
            )
        )
        created += 1
    return created


async def roll_all_recurring_tasks(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Ночная джоба: докатывает окно регулярных заданий у всех пользователей."""
    now = now or now_utc()
    rows = await db.execute(
        select(Task, User.timezone)
        .join(User, User.id == Task.user_id)
        .where(
            Task.deleted_at.is_(None),
            Task.recurrence.is_not(None),
            Task.status == TaskStatus.active,
            User.deleted_at.is_(None),
        )
    )
    created = 0
    for task, timezone in rows.all():
        today = now.astimezone(get_tz(timezone)).date()
        created += await sync_recurring_task(db, task, today)
    await db.commit()
    return created
