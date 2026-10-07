from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.bot.handlers import create_router
from app.bot.middleware import AccessMiddleware


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.update.outer_middleware(AccessMiddleware())
    dp.include_router(create_router())
    return dp


def create_bot(token: str) -> Bot:
    return Bot(token, default=DefaultBotProperties(link_preview_is_disabled=True))
