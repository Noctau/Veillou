from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.schemas.notify import (
    NotificationTestResult,
    PushConfig,
    PushSubscriptionCreate,
    PushSubscriptionRead,
    PushUnsubscribe,
    ReminderActionRequest,
    ReminderActionResult,
    ReminderRead,
)
from app.services import push, reminder_actions

router = APIRouter(prefix="/me", tags=["notifications"])
actions_router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/push")
async def get_push_config(user: CurrentUser, db: SessionDep) -> PushConfig:
    subs = await push.list_subscriptions(db, user)
    return PushConfig(
        vapid_public_key=settings.VAPID_PUBLIC_KEY if push.push_configured() else None,
        subscriptions=[PushSubscriptionRead.model_validate(s) for s in subs],
    )


@router.post("/push/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe_push(data: PushSubscriptionCreate, user: CurrentUser, db: SessionDep) -> None:
    await push.subscribe(db, user, data)


@router.post("/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_push(data: PushUnsubscribe, user: CurrentUser, db: SessionDep) -> None:
    await push.unsubscribe(db, user, data.endpoint)


@router.post("/notifications/test")
async def send_test_notification(user: CurrentUser, db: SessionDep) -> NotificationTestResult:
    return NotificationTestResult(channels=await push.send_test(db, user))


@router.get("/reminders")
async def list_upcoming_reminders(user: CurrentUser, db: SessionDep) -> list[ReminderRead]:
    """Ближайшие запланированные напоминания."""
    return await push.upcoming_read(db, user)


@actions_router.post("/action")
async def reminder_action(data: ReminderActionRequest, db: SessionDep) -> ReminderActionResult:
    """Кнопка Android-пуша. Без сессии: доступ по одноразовому токену из пуша."""
    result = await reminder_actions.perform_by_token(db, data.token, data.action)
    return ReminderActionResult(message=result.message, url=result.url)
