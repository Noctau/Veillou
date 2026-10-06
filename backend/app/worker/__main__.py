"""Фоновый процесс: python -m app.worker / make worker.

Пока только ночная джоба (3:00 по DEFAULT_TIMEZONE): докатка личных повторов
на 90 дней вперёд. Очередь jobs/reminders с SKIP LOCKED появится в M6.1.
"""

import asyncio
import logging
from datetime import datetime, time, timedelta

from app.core.config import settings
from app.core.db import engine, session_factory
from app.core.time import get_tz, now_utc
from app.services.schedule_sync import roll_all_users

log = logging.getLogger("app.worker")
NIGHTLY_AT = time(3, 0)


def seconds_until(at: time, now: datetime) -> float:
    """Сколько ждать до ближайшего `at` по DEFAULT_TIMEZONE."""
    tz = get_tz(settings.DEFAULT_TIMEZONE)
    local = now.astimezone(tz)
    target = datetime.combine(local.date(), at, tzinfo=tz)
    if target <= local:
        target = datetime.combine(local.date() + timedelta(days=1), at, tzinfo=tz)
    return (target - local).total_seconds()


async def nightly() -> None:
    async with session_factory() as db:
        created = await roll_all_users(db)
    log.info("Ночная докатка повторов: создано %d вхождений", created)


async def run_nightly_safely() -> None:
    """Ошибка джобы (например, БД ещё не поднялась) не должна ронять воркер."""
    try:
        await nightly()
    except Exception:
        log.exception("Ночная джоба упала")


async def main() -> None:
    try:
        await run_nightly_safely()  # после рестарта — сразу, чтобы окно не отставало
        while True:
            await asyncio.sleep(seconds_until(NIGHTLY_AT, now_utc()))
            await run_nightly_safely()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
