"""Фоновый процесс: python -m app.worker / make worker.

Цикл (раз в WORKER_POLL_SEC, но не позже ближайшего напоминания):
- джобы из `jobs` (пересборка напоминаний после правок);
- отправка готовых напоминаний из `reminders` (push + Telegram);
- раз в час — пересборка напоминаний всех пользователей (окно едет вперёд);
- джобы превью плана (после правок заданий, расписания, «не сделано»);
- в 3:00 по DEFAULT_TIMEZONE — докатка повторов и регулярных заданий, чистка очередей,
  прошедшие неотмеченные блоки → missed и превью плана к утру.

При старте сразу выполняется ночная джоба и пересборка: окна не отстают,
а неотправленное за время простоя досылается в первом же цикле.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta

from aiogram import Bot
from sqlalchemy import delete

from app.core.config import settings
from app.core.db import engine, session_factory
from app.core.time import get_tz, now_utc
from app.domain.enums import JobKind, ReminderStatus
from app.models import Reminder
from app.notify.notifier import Notifier, Sender, TelegramSender, WebPushSender
from app.services import jobs
from app.services.dispatch import dispatch_due, next_due_at
from app.services.recurring_tasks import roll_all_recurring_tasks
from app.services.reminders import handle_sync_job, sync_all_users
from app.services.replan import handle_preview_job, nightly_replan
from app.services.schedule_sync import roll_all_users

log = logging.getLogger("app.worker")
NIGHTLY_AT = time(3, 0)
RESYNC_EVERY = timedelta(hours=1)
KEEP_REMINDERS = timedelta(days=30)

HANDLERS: dict[str, jobs.Handler] = {
    JobKind.reminders_sync: handle_sync_job,
    JobKind.plan_preview: handle_preview_job,
}


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
        subtasks = await roll_all_recurring_tasks(db)
        await jobs.prune(db)
        await db.execute(
            delete(Reminder).where(
                Reminder.status != ReminderStatus.pending,
                Reminder.updated_at < now_utc() - KEEP_REMINDERS,
            )
        )
        await db.commit()
    log.info(
        "Ночная докатка: %d вхождений повторов, %d подзадач регулярных заданий",
        created,
        subtasks,
    )
    async with session_factory() as db:
        users = await nightly_replan(db)
    log.info("Ночное перепланирование: %d польз.", users)


async def resync_all() -> None:
    async with session_factory() as db:
        users = await sync_all_users(db)
    log.info("Напоминания пересобраны для %d польз.", users)


async def safely(name: str, coro_fn: Callable[[], Awaitable[object]]) -> None:
    """Ошибка шага (например, БД ещё не поднялась) не должна ронять воркер."""
    try:
        await coro_fn()
    except Exception:
        log.exception("%s: ошибка", name)


def build_notifier() -> tuple[Notifier, list[Bot]]:
    senders: dict[str, Sender] = {}
    closers: list[Bot] = []
    if settings.TELEGRAM_BOT_TOKEN is not None:
        from app.bot.app import create_bot

        bot = create_bot(settings.TELEGRAM_BOT_TOKEN.get_secret_value())
        senders["telegram"] = TelegramSender(bot, settings.APP_URL)
        closers.append(bot)
    else:
        log.warning("TELEGRAM_BOT_TOKEN не задан — напоминания в Telegram не уходят")
    if settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY:
        senders["push"] = WebPushSender(
            settings.VAPID_PUBLIC_KEY,
            settings.VAPID_PRIVATE_KEY.get_secret_value(),
            settings.VAPID_SUBJECT,
        )
    else:
        log.warning("VAPID-ключи не заданы — push не уходит (make vapid-keys)")
    return Notifier(senders), closers


async def tick(notifier: Notifier) -> None:
    await jobs.run_ready(session_factory, HANDLERS)
    await dispatch_due(session_factory, notifier)


async def sleep_time() -> float:
    poll = settings.WORKER_POLL_SEC
    async with session_factory() as db:
        due = await next_due_at(db)
    if due is None:
        return poll
    return min(poll, max(0.5, (due - now_utc()).total_seconds()))


async def main() -> None:
    notifier, closers = build_notifier()
    try:
        await safely("Ночная джоба", nightly)
        await safely("Пересборка напоминаний", resync_all)
        loop = asyncio.get_running_loop()
        next_nightly = loop.time() + seconds_until(NIGHTLY_AT, now_utc())
        next_resync = loop.time() + RESYNC_EVERY.total_seconds()
        while True:
            await safely("Цикл очередей", lambda: tick(notifier))
            if loop.time() >= next_nightly:
                await safely("Ночная джоба", nightly)
                next_nightly = loop.time() + seconds_until(NIGHTLY_AT, now_utc())
            if loop.time() >= next_resync:
                await safely("Пересборка напоминаний", resync_all)
                next_resync = loop.time() + RESYNC_EVERY.total_seconds()
            try:
                pause = await sleep_time()
            except Exception:
                log.exception("Не удалось узнать время ближайшего напоминания")
                pause = settings.WORKER_POLL_SEC
            await asyncio.sleep(pause)
    finally:
        for bot in closers:
            await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
