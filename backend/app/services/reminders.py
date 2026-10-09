"""Пересборка будущих напоминаний пользователя.

Собирает из БД пары, дедлайны и блоки, считает желаемый набор через
`notify.builder` и сверяет его с таблицей `reminders` по `dedupe_key`:
недостающие создаёт, изменившиеся двигает, лишние удаляет.

Трогаются только будущие неотправленные автоматические напоминания. Уже
просроченные, но не отправленные (воркер лежал) остаются отправителю — он
досылает их или пропускает как устаревшие.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import get_tz, local_date, now_utc
from app.domain.enums import (
    EventKind,
    EventStatus,
    ReminderKind,
    ReminderStatus,
    SourceType,
    TaskStatus,
)
from app.models import ActionType, Event, Job, Reminder, Subtask, Task, User
from app.notify import builder
from app.notify.builder import Candidate, Planned, TimeRange, Window, windows_from_json
from app.schemas.settings import ReminderRule, UserSettings
from app.services.settings import effective_settings

log = logging.getLogger(__name__)

# На сколько вперёд держим напоминания (окно докатывает периодическая пересборка)
HORIZON = timedelta(days=8)
# Не трогаем то, что вот-вот заберёт отправитель
FREEZE = timedelta(seconds=30)


@dataclass
class SyncStats:
    created: int = 0
    updated: int = 0
    deleted: int = 0


def quiet_range(s: UserSettings) -> TimeRange:
    return TimeRange(s.quiet_hours.start, s.quiet_hours.end)


def _channels(rule: ReminderRule) -> list[str] | None:
    if not rule.enabled or not rule.channels:
        return None
    return [str(c) for c in rule.channels]


class _Collector:
    def __init__(self, db: AsyncSession, user: User, s: UserSettings, now: datetime) -> None:
        self.db = db
        self.user = user
        self.s = s
        self.now = now
        self.tz = get_tz(user.timezone)
        self.horizon = now + HORIZON
        self._windows: dict[uuid.UUID, tuple[Window, ...]] | None = None

    async def windows_by_type(self) -> dict[uuid.UUID, tuple[Window, ...]]:
        if self._windows is None:
            rows = await self.db.scalars(
                select(ActionType).where(
                    ActionType.user_id == self.user.id, ActionType.deleted_at.is_(None)
                )
            )
            self._windows = {a.id: windows_from_json(a.windows) for a in rows}
        return self._windows

    async def task_windows(self, task: Task, subtask: Subtask | None = None) -> tuple[Window, ...]:
        """Своё окно подзадачи → своё окно задания → окно типа действия."""
        if subtask is not None and subtask.time_window:
            return windows_from_json(subtask.time_window)
        if task.time_window:
            return windows_from_json(task.time_window)
        type_id = (subtask.action_type_id if subtask else None) or task.action_type_id
        if type_id is None:
            return ()
        return (await self.windows_by_type()).get(type_id, ())

    async def classes(self, channels: list[str]) -> list[Candidate]:
        rows = await self.db.scalars(
            select(Event).where(
                Event.user_id == self.user.id,
                Event.deleted_at.is_(None),
                Event.kind == EventKind.class_,
                Event.status == EventStatus.planned,
                Event.start > self.now,
                Event.start <= self.horizon,
            )
        )
        infos = [builder.ClassInfo(e.id, e.start) for e in rows]
        return builder.class_candidates(
            infos, self.s.reminders.before_class.minutes_before, channels
        )

    async def deadlines(self, channels: list[str]) -> list[Candidate]:
        days = self.s.reminders.deadlines.days_before
        if not days:
            return []
        rows = await self.db.scalars(
            select(Task).where(
                Task.user_id == self.user.id,
                Task.deleted_at.is_(None),
                Task.status == TaskStatus.active,
                Task.deadline > self.now,
                Task.deadline <= self.horizon + timedelta(days=max(days) + 1),
            )
        )
        infos = [
            builder.DeadlineInfo(t.id, t.deadline, await self.task_windows(t))
            for t in rows
            if t.deadline is not None
        ]
        return builder.deadline_candidates(
            infos, days, self.s.schedule.morning_digest, self.tz, channels
        )

    def digests(self, channels: list[str]) -> list[Candidate]:
        today = local_date(self.now, self.tz)
        days = [today + timedelta(days=i) for i in range(HORIZON.days)]
        return builder.digest_candidates(days, self.s.schedule.morning_digest, self.tz, channels)

    def reviews(self) -> list[Candidate]:
        r, at = self.s.reminders, self.s.schedule
        today = local_date(self.now, self.tz)
        days = [today + timedelta(days=i) for i in range(HORIZON.days)]
        result: list[Candidate] = []
        if ch := _channels(r.evening_review):
            result += builder.review_candidates(
                ReminderKind.evening_review,
                days,
                at.evening_review,
                self.tz,
                ch,
                builder.EVENING_TTL,
            )
        if ch := _channels(r.weekly_review):
            result += builder.review_candidates(
                ReminderKind.weekly_review,
                [d for d in days if d.isoweekday() == at.weekly_review_weekday],
                at.weekly_review,
                self.tz,
                ch,
                builder.WEEKLY_TTL,
            )
        return result

    async def subtask_blocks(self, channels: list[str]) -> list[Candidate]:
        rows = (
            await self.db.execute(
                select(Event, Subtask, Task)
                .join(Subtask, Subtask.id == Event.source_id)
                .join(Task, Task.id == Subtask.task_id)
                .where(
                    Event.user_id == self.user.id,
                    Event.deleted_at.is_(None),
                    Event.source_type == SourceType.subtask,
                    Event.status == EventStatus.planned,
                    Event.start > self.now,
                    Event.start <= self.horizon,
                    Subtask.deleted_at.is_(None),
                    Task.deleted_at.is_(None),
                )
            )
        ).all()
        infos = [
            builder.BlockInfo(e.id, e.start, e.end, await self.task_windows(t, st))
            for e, st, t in rows
        ]
        return builder.subtask_candidates(infos, channels)

    async def candidates(self) -> list[Candidate]:
        r = self.s.reminders
        result: list[Candidate] = []
        if ch := _channels(r.before_class):
            result += await self.classes(ch)
        if ch := _channels(r.deadlines):
            result += await self.deadlines(ch)
        if ch := _channels(r.morning_digest):
            result += self.digests(ch)
        if ch := _channels(r.subtask_start):
            result += await self.subtask_blocks(ch)
        result += self.reviews()
        return result


async def desired_reminders(
    db: AsyncSession, user: User, now: datetime | None = None
) -> list[Planned]:
    now = now or now_utc()
    s = effective_settings(user)
    candidates = await _Collector(db, user, s, now).candidates()
    return builder.build(candidates, quiet_range(s), get_tz(user.timezone))


def _fields(p: Planned) -> dict[str, Any]:
    return {
        "kind": str(p.kind),
        "fire_at": p.fire_at,
        "due_at": p.fire_at,
        "expires_at": p.expires_at,
        "channels": list(p.channels),
        "payload": p.payload,
        "entity_type": p.entity_type,
        "entity_id": p.entity_id,
    }


async def sync_user_reminders(
    db: AsyncSession, user_id: uuid.UUID, now: datetime | None = None
) -> SyncStats:
    """Сверяет будущие напоминания пользователя с желаемыми. Коммитит."""
    now = now or now_utc()
    stats = SyncStats()
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        return stats
    frozen_until = now + FREEZE
    desired: dict[str, Planned] = {}
    for p in await desired_reminders(db, user, now):
        if p.fire_at > frozen_until:
            desired[p.key] = p
        elif p.kind == ReminderKind.morning_digest and p.expires_at and p.expires_at > now:
            # Время сводки сдвинули на уже прошедшее (8:00 → 7:00 в 7:30) — сегодняшняя
            # уходит сейчас, а не теряется. Уже отправленную не продублирует dedupe_key.
            desired[p.key] = replace(p, fire_at=now)

    existing = {
        r.dedupe_key: r
        for r in await db.scalars(
            select(Reminder)
            .where(
                Reminder.user_id == user_id,
                Reminder.deleted_at.is_(None),
                Reminder.is_auto.is_(True),
                Reminder.status == ReminderStatus.pending,
                Reminder.fire_at > frozen_until,
            )
            .with_for_update(skip_locked=True)
        )
    }

    stale = [r.id for key, r in existing.items() if key not in desired]
    if stale:
        await db.execute(delete(Reminder).where(Reminder.id.in_(stale)))
        stats.deleted = len(stale)

    for key, p in desired.items():
        fields = _fields(p)
        if (row := existing.get(key)) is not None:
            changed = False
            for name, value in fields.items():
                if getattr(row, name) != value:
                    setattr(row, name, value)
                    changed = True
            stats.updated += changed
            continue
        result = await db.execute(
            insert(Reminder)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                dedupe_key=key,
                is_auto=True,
                status=ReminderStatus.pending,
                sent_channels=[],
                attempts=0,
                **fields,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "dedupe_key"],
                index_where=Reminder.deleted_at.is_(None),
            )
        )
        stats.created += cast(CursorResult[Any], result).rowcount or 0
    await db.commit()
    return stats


async def handle_sync_job(db: AsyncSession, job: Job) -> None:
    if job.user_id is not None:
        await sync_user_reminders(db, job.user_id)


async def sync_all_users(db: AsyncSession, now: datetime | None = None) -> int:
    """Периодическая пересборка: окно напоминаний сдвигается вперёд."""
    ids: Sequence[uuid.UUID] = list(
        await db.scalars(select(User.id).where(User.deleted_at.is_(None)))
    )
    for user_id in ids:
        try:
            await sync_user_reminders(db, user_id, now)
        except Exception:
            log.exception("Пересборка напоминаний пользователя %s упала", user_id)
            await db.rollback()
    return len(ids)


async def upcoming(db: AsyncSession, user: User, limit: int = 20) -> list[Reminder]:
    return list(
        await db.scalars(
            select(Reminder)
            .where(
                Reminder.user_id == user.id,
                Reminder.deleted_at.is_(None),
                Reminder.status == ReminderStatus.pending,
            )
            .order_by(Reminder.fire_at)
            .limit(limit)
        )
    )
