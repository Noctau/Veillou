"""Notifier: доставка сообщения по каналам `push` и `telegram`.

Каждый канал возвращает `Delivery`: sent — доставлено, skipped — канал не
настроен у пользователя (нет привязки или подписок; это не ошибка и не
ретраится), failed — временная ошибка, отправитель повторит.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import now_utc
from app.models import PushSubscription, User
from app.notify.message import ACTION_TITLES, TELEGRAM_ONLY, Message

log = logging.getLogger(__name__)


class DeliveryStatus(StrEnum):
    sent = "sent"
    skipped = "skipped"
    failed = "failed"


@dataclass(frozen=True)
class Delivery:
    status: DeliveryStatus
    error: str | None = None


SENT = Delivery(DeliveryStatus.sent)


def skipped(reason: str) -> Delivery:
    return Delivery(DeliveryStatus.skipped, reason)


def failed(reason: str) -> Delivery:
    return Delivery(DeliveryStatus.failed, reason)


class Sender(Protocol):
    async def send(self, db: AsyncSession, user: User, msg: Message, ttl: int) -> Delivery: ...


# ---------- Telegram ----------


def reminder_callback(action: str, reminder_id: object) -> str:
    """callback_data кнопки напоминания (лимит Telegram — 64 байта)."""
    return f"ra:{action}:{getattr(reminder_id, 'hex', reminder_id)}"


def telegram_markup(msg: Message, app_url: str | None) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    if msg.actions and msg.reminder_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text=ACTION_TITLES[a], callback_data=reminder_callback(a, msg.reminder_id)
                )
                for a in msg.actions
            ]
        )
    if app_url:
        rows.append([InlineKeyboardButton(text="Открыть", url=f"{app_url}{msg.url}")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


class TelegramSender:
    def __init__(self, bot: Bot, app_url: str | None = None) -> None:
        self.bot = bot
        self.app_url = app_url

    async def send(self, db: AsyncSession, user: User, msg: Message, ttl: int) -> Delivery:
        if user.tg_user_id is None:
            return skipped("Telegram не привязан")
        try:
            await self.bot.send_message(
                user.tg_user_id,
                msg.telegram_html(),
                parse_mode="HTML",
                reply_markup=telegram_markup(msg, self.app_url),
            )
        except TelegramForbiddenError as exc:
            # Бот заблокирован или чат удалён — повторять бессмысленно
            return skipped(str(exc))
        except TelegramAPIError as exc:
            return failed(f"telegram: {exc}")
        return SENT


# ---------- Web Push ----------


def push_payload(msg: Message) -> str:
    """То, что получает service worker в событии push."""
    data = {
        "title": msg.title,
        "body": msg.plain_body(),
        "url": msg.url,
        "tag": msg.tag,
        "actions": [
            {"action": a, "title": ACTION_TITLES[a]} for a in msg.actions if a not in TELEGRAM_ONLY
        ]
        if msg.action_token
        else [],
        "token": msg.action_token,
    }
    return json.dumps(data, ensure_ascii=False)


class WebPushSender:
    def __init__(self, public_key: str, private_key: str, subject: str) -> None:
        self.public_key = public_key
        self.private_key = private_key
        self.subject = subject

    def _post(self, sub: PushSubscription, data: str, ttl: int) -> None:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=data,
            vapid_private_key=self.private_key,
            vapid_claims={"sub": self.subject},
            ttl=ttl,
            headers={"Urgency": "high"},
            timeout=15,
        )

    async def send(self, db: AsyncSession, user: User, msg: Message, ttl: int) -> Delivery:
        subs = list(
            await db.scalars(
                select(PushSubscription).where(
                    PushSubscription.user_id == user.id, PushSubscription.deleted_at.is_(None)
                )
            )
        )
        if not subs:
            return skipped("Нет push-подписок")
        data = push_payload(msg)
        ok, errors = 0, []
        for sub in subs:
            try:
                await asyncio.to_thread(self._post, sub, data, ttl)
            except WebPushException as exc:
                code = exc.response.status_code if exc.response is not None else None
                if code in (404, 410):
                    # Подписка отозвана (браузер переустановлен, разрешение снято)
                    log.info("Push-подписка %s больше не действует (%s), удаляю", sub.id, code)
                    await db.delete(sub)
                    continue
                errors.append(f"{code}: {exc}")
            except Exception as exc:  # сеть, таймаут
                errors.append(f"{type(exc).__name__}: {exc}")
            else:
                ok += 1
                sub.last_used_at = now_utc()
        await db.commit()
        if ok:
            return SENT
        if errors:
            return failed("push: " + "; ".join(errors)[:500])
        return skipped("Все push-подписки устарели")


class Notifier:
    def __init__(self, senders: dict[str, Sender]) -> None:
        self.senders = senders

    async def send(
        self, db: AsyncSession, user: User, channel: str, msg: Message, ttl: int
    ) -> Delivery:
        sender = self.senders.get(channel)
        if sender is None:
            return skipped(f"Канал {channel} не настроен на сервере")
        return await sender.send(db, user, msg, ttl)
