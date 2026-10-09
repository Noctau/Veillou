"""Telegram-бот (long polling): python -m app.bot / make bot."""

import asyncio
import logging
import sys

from aiogram.types import BotCommand

from app.bot.app import create_bot, create_dispatcher
from app.core.config import settings
from app.core.db import engine
from app.heartbeat import beat

HEARTBEAT_SEC = 30.0


async def heartbeat_loop() -> None:
    while True:
        try:
            await beat("bot")
        except OSError:
            logging.exception("Heartbeat бота не записан")
        await asyncio.sleep(HEARTBEAT_SEC)


COMMANDS = [
    BotCommand(command="today", description="План на сегодня"),
    BotCommand(command="week", description="План на неделю"),
    BotCommand(command="add", description="Добавить дело: /add текст"),
    BotCommand(command="free", description="Есть N минут — что успеть"),
    BotCommand(command="help", description="Что я умею"),
]


async def main() -> None:
    if settings.TELEGRAM_BOT_TOKEN is None:
        sys.exit("TELEGRAM_BOT_TOKEN не задан в .env")
    bot = create_bot(settings.TELEGRAM_BOT_TOKEN.get_secret_value())
    dp = create_dispatcher()
    try:
        me = await bot.get_me()
        if settings.TELEGRAM_BOT_USERNAME and me.username != settings.TELEGRAM_BOT_USERNAME:
            logging.warning(
                "TELEGRAM_BOT_USERNAME=%s, а токен от @%s — ссылки привязки будут неверными",
                settings.TELEGRAM_BOT_USERNAME,
                me.username,
            )
        await bot.set_my_commands(COMMANDS)
        logging.info("Бот @%s запущен", me.username)
        pulse = asyncio.create_task(heartbeat_loop())
        # start_polling сам останавливается по SIGTERM/SIGINT
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        pulse.cancel()
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
