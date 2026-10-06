"""Push-подписки, напоминания и кнопки уведомлений."""

import uuid
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.domain.enums import ReminderAction, ReminderKind
from app.schemas.common import InputModel, ReadModel, UTCMoment
from app.schemas.settings import Channel

Key = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PushKeys(InputModel):
    p256dh: Key
    auth: Key


class PushSubscriptionCreate(InputModel):
    """То, что отдаёт `PushSubscription.toJSON()` в браузере (+ имя устройства)."""

    endpoint: Annotated[str, StringConstraints(pattern=r"^https://", max_length=2000)]
    keys: PushKeys
    device_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""


class PushUnsubscribe(InputModel):
    endpoint: Annotated[str, StringConstraints(max_length=2000)]


class PushSubscriptionRead(ReadModel):
    id: uuid.UUID
    device_name: str
    created_at: UTCMoment
    last_used_at: UTCMoment | None


class PushConfig(BaseModel):
    """Публичный VAPID-ключ для `pushManager.subscribe`. null — push не настроен на сервере."""

    vapid_public_key: str | None
    subscriptions: list[PushSubscriptionRead]


class ChannelState(BaseModel):
    channel: Channel
    ready: bool
    reason: str | None = None


class NotificationTestResult(BaseModel):
    """Проверочное уведомление поставлено в очередь, воркер пришлёт его в течение ~10 с."""

    channels: list[ChannelState]


class ReminderRead(BaseModel):
    id: uuid.UUID
    kind: ReminderKind
    fire_at: UTCMoment
    channels: list[Channel]
    label: str = Field(description="О чём напоминание — для списка в Настройках")


class ReminderActionRequest(InputModel):
    token: Annotated[str, StringConstraints(min_length=10, max_length=200)]
    action: ReminderAction


class ReminderActionResult(BaseModel):
    message: str
    url: str | None
