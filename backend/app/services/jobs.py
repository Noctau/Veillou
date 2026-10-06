"""Очередь фоновых джоб в Postgres (`jobs`).

Воркер берёт джобу через `FOR UPDATE SKIP LOCKED`, «арендует» её на
`LEASE` и выполняет обработчик по `kind`. Ошибка → ретрай с паузой, после
`max_attempts` — failed. Если воркер упал посреди джобы, аренда истекает и
джобу подхватывает следующий цикл.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, delete, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.time import now_utc
from app.domain.enums import JobKind, JobStatus
from app.models import Job

log = logging.getLogger(__name__)

LEASE = timedelta(minutes=5)
RETRY_DELAYS = (timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=10))
KEEP_FINISHED = timedelta(days=14)
# Пауза перед пересборкой напоминаний: серия правок схлопывается в одну джобу
REMINDERS_DEBOUNCE = timedelta(seconds=3)

Handler = Callable[[AsyncSession, Job], Awaitable[None]]


def _insert(
    kind: str,
    *,
    user_id: uuid.UUID | None,
    payload: dict[str, Any] | None,
    run_at: datetime,
    dedupe_key: str | None,
) -> Any:
    return (
        insert(Job)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            kind=kind,
            payload=payload or {},
            status=JobStatus.pending,
            run_at=run_at,
            attempts=0,
            max_attempts=3,
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing(
            index_elements=["dedupe_key"],
            # Литерал, а не параметры: иначе Postgres не сопоставит частичный индекс
            index_where=text("status = 'pending' AND dedupe_key IS NOT NULL"),
        )
    )


async def enqueue(
    db: AsyncSession,
    kind: str,
    *,
    user_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    run_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> None:
    """Ставит джобу. С `dedupe_key` — не больше одной ожидающей на ключ. Не коммитит."""
    await db.execute(
        _insert(
            kind,
            user_id=user_id,
            payload=payload,
            run_at=run_at or now_utc(),
            dedupe_key=dedupe_key,
        )
    )


def reminders_sync_key(user_id: uuid.UUID) -> str:
    return f"{JobKind.reminders_sync}:{user_id}"


async def request_reminders_sync(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Явный запрос пересборки — для массовых UPDATE, мимо которых проходит after_flush."""
    await enqueue(
        db,
        JobKind.reminders_sync,
        user_id=user_id,
        run_at=now_utc() + REMINDERS_DEBOUNCE,
        dedupe_key=reminders_sync_key(user_id),
    )


def enqueue_reminders_sync_sync(conn: Connection, user_ids: set[uuid.UUID]) -> None:
    """То же из синхронного контекста (обработчик after_flush)."""
    run_at = now_utc() + REMINDERS_DEBOUNCE
    for user_id in user_ids:
        conn.execute(
            _insert(
                JobKind.reminders_sync,
                user_id=user_id,
                payload=None,
                run_at=run_at,
                dedupe_key=reminders_sync_key(user_id),
            )
        )


async def _claim(db: AsyncSession, now: datetime) -> Job | None:
    job = await db.scalar(
        select(Job)
        .where(
            Job.status.in_([JobStatus.pending, JobStatus.running]),
            Job.run_at <= now,
            or_(Job.locked_until.is_(None), Job.locked_until < now),
        )
        .order_by(Job.run_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = JobStatus.running
    job.locked_until = now + LEASE
    job.attempts += 1
    # Новые правки должны ставить новую ожидающую джобу, а не схлопываться с этой
    job.dedupe_key = None
    await db.commit()
    return job


async def run_one(
    factory: async_sessionmaker[AsyncSession],
    handlers: dict[str, Handler],
    now: datetime | None = None,
) -> bool:
    """Берёт и выполняет одну готовую джобу. False — очередь пуста."""
    now = now or now_utc()
    async with factory() as db:
        job = await _claim(db, now)
        if job is None:
            return False
        handler = handlers.get(job.kind)
        try:
            if handler is None:
                raise RuntimeError(f"Нет обработчика для {job.kind!r}")
            await handler(db, job)
        except Exception as exc:
            await db.rollback()
            log.exception("Джоба %s (%s) упала", job.id, job.kind)
            await _fail(db, job.id, exc)
            return True
        job.status = JobStatus.done
        job.finished_at = now_utc()
        job.locked_until = None
        await db.commit()
    return True


async def _fail(db: AsyncSession, job_id: uuid.UUID, exc: Exception) -> None:
    job = await db.get(Job, job_id)
    if job is None:
        return
    job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
    job.locked_until = None
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.failed
        job.finished_at = now_utc()
    else:
        job.status = JobStatus.pending
        job.run_at = now_utc() + RETRY_DELAYS[min(job.attempts, len(RETRY_DELAYS)) - 1]
    await db.commit()


async def run_ready(
    factory: async_sessionmaker[AsyncSession], handlers: dict[str, Handler], limit: int = 100
) -> int:
    done = 0
    while done < limit and await run_one(factory, handlers):
        done += 1
    return done


async def prune(db: AsyncSession, now: datetime | None = None) -> None:
    """Удаляет давно завершённые джобы."""
    cutoff = (now or now_utc()) - KEEP_FINISHED
    await db.execute(
        delete(Job).where(
            Job.status.in_([JobStatus.done, JobStatus.failed]), Job.finished_at < cutoff
        )
    )
    await db.commit()
