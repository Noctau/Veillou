"""Отправка готовых напоминаний.

Цикл воркера:
1. Захват: `FOR UPDATE SKIP LOCKED` по `due_at <= now`, аренда на `LEASE`,
   коммит. Параллельный воркер эти строки уже не видит.
2. Доставка: напоминания одного пользователя склеиваются в одно сообщение на
   канал. Успешно доставленные каналы запоминаются в `sent_channels`, так что
   ретрай не дублирует их.
3. Итог: всё доставлено → sent; ошибка → ретрай с паузой, после
   `MAX_ATTEMPTS` → failed.

Если воркер упал между захватом и итогом, аренда истекает и напоминание
досылается следующим циклом — после рестарта ничего не теряется. Отправленное
(`status=sent`) повторно не захватывается.
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_token, new_token
from app.core.time import now_utc
from app.domain.enums import ReminderStatus
from app.models import Reminder, User
from app.notify.message import Message, combine
from app.notify.notifier import DeliveryStatus, Notifier
from app.services.notify_render import render

log = logging.getLogger(__name__)

LEASE = timedelta(minutes=2)
BATCH = 100
MAX_ATTEMPTS = 5
RETRY_DELAYS = (
    timedelta(seconds=30),
    timedelta(minutes=2),
    timedelta(minutes=10),
    timedelta(minutes=30),
)
DEFAULT_TTL = 24 * 3600


async def claim_due(db: AsyncSession, now: datetime, limit: int = BATCH) -> list[uuid.UUID]:
    rows = list(
        await db.scalars(
            select(Reminder)
            .where(
                Reminder.status == ReminderStatus.pending,
                Reminder.deleted_at.is_(None),
                Reminder.due_at <= now,
                or_(Reminder.locked_until.is_(None), Reminder.locked_until < now),
            )
            .order_by(Reminder.due_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for r in rows:
        r.locked_until = now + LEASE
        r.attempts += 1
    await db.commit()
    return [r.id for r in rows]


async def next_due_at(db: AsyncSession) -> datetime | None:
    """Когда ближайшее неотправленное — чтобы воркер не спал дольше нужного.

    Захваченное (аренда ещё идёт) раньше конца аренды не взять — иначе после
    упавшей доставки воркер две минуты опрашивал бы базу каждые полсекунды.
    """
    ready_at = func.greatest(Reminder.due_at, func.coalesce(Reminder.locked_until, Reminder.due_at))
    return await db.scalar(
        select(ready_at)
        .where(Reminder.status == ReminderStatus.pending, Reminder.deleted_at.is_(None))
        .order_by(ready_at)
        .limit(1)
    )


def _ttl(items: list[Reminder], now: datetime) -> int:
    limits = [int((r.expires_at - now).total_seconds()) for r in items if r.expires_at]
    return max(60, min(limits)) if limits else DEFAULT_TTL


def _finish(r: Reminder, now: datetime, error: str | None) -> None:
    r.locked_until = None
    if set(r.channels) <= set(r.sent_channels):
        r.status = ReminderStatus.sent
        r.sent_at = now
        r.last_error = error
        return
    r.last_error = error or "не доставлено"
    if r.attempts >= MAX_ATTEMPTS:
        r.status = ReminderStatus.failed
    else:
        r.due_at = now + RETRY_DELAYS[min(r.attempts, len(RETRY_DELAYS)) - 1]


async def deliver_user(
    db: AsyncSession, notifier: Notifier, user_id: uuid.UUID, ids: list[uuid.UUID], now: datetime
) -> None:
    reminders = list(
        await db.scalars(select(Reminder).where(Reminder.id.in_(ids)).order_by(Reminder.fire_at))
    )
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        for r in reminders:
            r.status, r.locked_until = ReminderStatus.skipped, None
        await db.commit()
        return

    ready: list[tuple[Reminder, Message]] = []
    errors: dict[uuid.UUID, str] = {}
    for r in reminders:
        if r.expires_at is not None and now >= r.expires_at:
            r.status, r.locked_until, r.last_error = ReminderStatus.skipped, None, "опоздало"
            continue
        try:
            msg = await render(db, user, r, now)
        except Exception as exc:
            log.exception("Не удалось собрать напоминание %s", r.id)
            errors[r.id] = f"render: {exc}"
            continue
        if msg is None:
            r.status, r.locked_until, r.last_error = ReminderStatus.skipped, None, "устарело"
            continue
        ready.append((r, msg))

    channels = list(dict.fromkeys(ch for r, _ in ready for ch in r.channels))
    # Один токен на напоминание на весь цикл: иначе следующий канал перезапишет хэш
    # и кнопки уже отправленного пуша перестанут работать
    tokens: dict[uuid.UUID, str] = {}
    for channel in channels:
        items = [
            (r, m) for r, m in ready if channel in r.channels and channel not in r.sent_channels
        ]
        if not items:
            continue
        msg = combine([m for _, m in items])
        if len(items) == 1 and msg.actions:
            # Кнопки пуша: одноразовый токен на это напоминание
            r = items[0][0]
            if r.id not in tokens:
                tokens[r.id] = new_token()
                r.action_token_hash = hash_token(tokens[r.id])
                r.action_used_at = None
            msg = replace(msg, action_token=tokens[r.id])
        delivery = await notifier.send(db, user, channel, msg, _ttl([r for r, _ in items], now))
        if delivery.status == DeliveryStatus.failed:
            log.warning("Канал %s: %s", channel, delivery.error)
            for r, _ in items:
                errors[r.id] = delivery.error or "ошибка канала"
            continue
        if delivery.status == DeliveryStatus.skipped:
            log.info("Канал %s пропущен для %s: %s", channel, user.id, delivery.error)
        for r, _ in items:
            r.sent_channels = [*r.sent_channels, channel]

    for r, _ in ready:
        _finish(r, now, errors.get(r.id))
    for r in reminders:
        if r.id in errors and r.status == ReminderStatus.pending and r.locked_until is not None:
            _finish(r, now, errors[r.id])
    await db.commit()


async def dispatch_due(
    factory: async_sessionmaker[AsyncSession], notifier: Notifier, now: datetime | None = None
) -> int:
    """Отправляет всё, что пора. Возвращает число захваченных напоминаний."""
    now = now or now_utc()
    async with factory() as db:
        ids = await claim_due(db, now)
        if not ids:
            return 0
        owners = {
            row[0]: row[1]
            for row in await db.execute(
                select(Reminder.id, Reminder.user_id).where(Reminder.id.in_(ids))
            )
        }
    by_user: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for rid in ids:
        by_user[owners[rid]].append(rid)
    for user_id, user_ids in by_user.items():
        async with factory() as db:
            try:
                await deliver_user(db, notifier, user_id, user_ids, now)
            except Exception:
                # Аренда истечёт, и следующий цикл попробует снова
                log.exception("Доставка напоминаний пользователю %s упала", user_id)
    return len(ids)
