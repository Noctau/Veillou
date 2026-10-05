from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services import telegram

HELP = (
    "Я буду присылать напоминания и принимать дела в ящик.\n"
    "Скоро здесь появятся /today, /week и /add."
)


async def start_with_code(
    message: Message, command: CommandObject, db: AsyncSession, user: User | None
) -> None:
    assert message.from_user is not None and command.args is not None
    try:
        linked = await telegram.link_by_code(db, command.args, tg_user_id=message.from_user.id)
    except telegram.LinkError as exc:
        await message.answer(exc.message)
        return
    await message.answer(f"Готово, Telegram привязан к {linked.email}.\n\n{HELP}")


async def start(message: Message) -> None:
    # Сюда доходят только привязанные: остальных отсекает AccessMiddleware
    await message.answer(f"Привет! {HELP}")


async def fallback(message: Message) -> None:
    await message.answer(HELP)


def create_router() -> Router:
    """Новый роутер на каждый Dispatcher (aiogram не даёт подключить один дважды)."""
    router = Router(name="core")
    router.message.register(start_with_code, CommandStart(deep_link=True))
    router.message.register(start, CommandStart())
    router.message.register(fallback)
    return router
