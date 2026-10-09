from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from aiogram.types import User as TgUser

from app.core.db import session_factory
from app.services import telegram

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


def _is_link_attempt(update: Update) -> bool:
    """`/start <код>` в личке — единственное, что принимается от непривязанных."""
    msg = update.message
    if msg is None or msg.text is None:
        return False
    parts = msg.text.split(maxsplit=1)
    return len(parts) == 2 and parts[0].split("@")[0] == "/start"


class AccessMiddleware(BaseMiddleware):
    """Outer-middleware на Update.

    - работает только в личных чатах;
    - даёт обработчикам `db` (AsyncSession) и `user` (привязанный User или None);
    - апдейты от чужих tg_user_id молча игнорируются, кроме попытки привязки.
    """

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(
            event, Update
        ):  # middleware висит на dp.update — сюда приходят только они
            return await handler(event, data)
        tg_user: TgUser | None = data.get("event_from_user")
        chat = data.get("event_chat")
        if tg_user is None or tg_user.is_bot or chat is None or chat.type != "private":
            return None

        async with session_factory() as db:
            user = await telegram.get_user_by_tg(db, tg_user.id)
            if user is None and not _is_link_attempt(event):
                return None
            data["db"] = db
            data["user"] = user
            return await handler(event, data)
