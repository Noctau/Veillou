"""Push-подписки, проверочное уведомление и список ближайших напоминаний."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.time import now_utc
from app.domain.enums import ReminderKind, ReminderStatus
from app.models import Event, PushSubscription, Reminder, Task, User
from app.schemas.notify import ChannelState, PushSubscriptionCreate, ReminderRead
from app.schemas.settings import Channel
from app.services.reminders import upcoming


def push_configured() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


async def list_subscriptions(db: AsyncSession, user: User) -> list[PushSubscription]:
    return list(
        await db.scalars(
            select(PushSubscription)
            .where(PushSubscription.user_id == user.id, PushSubscription.deleted_at.is_(None))
            .order_by(PushSubscription.created_at)
        )
    )


async def subscribe(db: AsyncSession, user: User, data: PushSubscriptionCreate) -> None:
    """Upsert по endpoint: тот же браузер после перелогина переходит к новому пользователю."""
    values = {
        "user_id": user.id,
        "p256dh": data.keys.p256dh,
        "auth": data.keys.auth,
        "device_name": data.device_name,
        "deleted_at": None,
    }
    await db.execute(
        insert(PushSubscription)
        .values(id=uuid.uuid4(), endpoint=data.endpoint, **values)
        .on_conflict_do_update(
            index_elements=["endpoint"], set_={**values, "updated_at": now_utc()}
        )
    )
    await db.commit()


async def unsubscribe(db: AsyncSession, user: User, endpoint: str) -> None:
    sub = await db.scalar(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id, PushSubscription.endpoint == endpoint
        )
    )
    if sub is not None:
        await db.delete(sub)
        await db.commit()


async def channel_states(db: AsyncSession, user: User) -> list[ChannelState]:
    subs = await list_subscriptions(db, user)
    push_reason = None
    if not push_configured():
        push_reason = "Push не настроен на сервере (VAPID-ключи)"
    elif not subs:
        push_reason = "Это устройство не подписано на push"
    tg_reason = None
    if settings.TELEGRAM_BOT_TOKEN is None:
        tg_reason = "Бот не настроен на сервере"
    elif user.tg_user_id is None:
        tg_reason = "Telegram не привязан"
    return [
        ChannelState(channel=Channel.push, ready=push_reason is None, reason=push_reason),
        ChannelState(channel=Channel.telegram, ready=tg_reason is None, reason=tg_reason),
    ]


async def send_test(db: AsyncSession, user: User) -> list[ChannelState]:
    """Ставит проверочное напоминание «прямо сейчас» во все готовые каналы."""
    states = await channel_states(db, user)
    channels = [str(s.channel) for s in states if s.ready]
    if channels:
        now = now_utc()
        db.add(
            Reminder(
                user_id=user.id,
                kind=ReminderKind.test,
                fire_at=now,
                due_at=now,
                channels=channels,
                payload={},
                dedupe_key=f"test:{uuid.uuid4().hex}",
                is_auto=False,
                status=ReminderStatus.pending,
                sent_channels=[],
                attempts=0,
            )
        )
        await db.commit()
    return states


KIND_LABEL = {
    ReminderKind.morning_digest: "Утренняя сводка",
    ReminderKind.before_class: "Перед парой",
    ReminderKind.deadline: "Дедлайн",
    ReminderKind.subtask_start: "Начало",
    ReminderKind.evening_review: "Вечерний разбор",
    ReminderKind.weekly_review: "Разбор недели",
    ReminderKind.test: "Проверка",
}


async def upcoming_read(db: AsyncSession, user: User, limit: int = 20) -> list[ReminderRead]:
    rows = await upcoming(db, user, limit)
    event_ids = [r.entity_id for r in rows if r.entity_type == "event" and r.entity_id]
    task_ids = [r.entity_id for r in rows if r.entity_type == "task" and r.entity_id]
    titles: dict[uuid.UUID, str] = {}
    if event_ids:
        titles |= {
            row[0]: row[1]
            for row in await db.execute(
                select(Event.id, Event.title).where(Event.id.in_(event_ids))
            )
        }
    if task_ids:
        titles |= {
            row[0]: row[1]
            for row in await db.execute(select(Task.id, Task.title).where(Task.id.in_(task_ids)))
        }

    result = []
    for r in rows:
        kind = ReminderKind(r.kind)
        label = KIND_LABEL[kind]
        if r.entity_id and (title := titles.get(r.entity_id)):
            label = f"{label}: {title}"
        result.append(
            ReminderRead(
                id=r.id,
                kind=kind,
                fire_at=r.fire_at,
                channels=[Channel(c) for c in r.channels],
                label=label,
            )
        )
    return result
