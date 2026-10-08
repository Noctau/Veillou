"""Очередь фоновых джоб в Postgres (`jobs`).

Воркер берёт джобу через `FOR UPDATE SKIP LOCKED`, «арендует» её на
`LEASE` и выполняет обработчик по `kind`. Ошибка → ретрай с паузой, после
`max_attempts` — failed. Если воркер упал посреди джобы, аренда истекает и
джобу подхватывает следующий цикл.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable, Collection
from datetime import datetime, timedelta
from enum import StrEnum
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
# То же для пересчёта превью плана (солвер дороже — ждём дольше)
PLAN_DEBOUNCE = timedelta(seconds=5)

Handler = Callable[[AsyncSession, Job], Awaitable[None]]


class JobOutcome(StrEnum):
    done = "done"
    failed = "failed"  # в т. ч. ушла на ретрай после ошибки
    deferred = "deferred"  # ресурс недоступен — джоба ждёт в очереди


class JobDeferredError(Exception):
    """Нужный ресурс сейчас недоступен (ИИ выключен): джоба остаётся в очереди и
    будет выполнена позже. Попытка не засчитывается; `message` — для пользователя.
    Джоба старше `max_wait` всё же падает."""

    def __init__(
        self,
        message: str,
        *,
        delay: timedelta = timedelta(minutes=1),
        max_wait: timedelta | None = None,
        expired_message: str | None = None,
    ) -> None:
        self.message = message
        self.delay = delay
        self.max_wait = max_wait
        self.expired_message = expired_message or message
        super().__init__(message)


class JobFailedError(Exception):
    """Ошибка, которую повтор не исправит (ИИ ответил не по схеме, задание удалили):
    джоба сразу `failed`, `message` — для пользователя (GET /jobs/{id})."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _insert(
    kind: str,
    *,
    user_id: uuid.UUID | None,
    payload: dict[str, Any] | None,
    run_at: datetime,
    dedupe_key: str | None,
    max_attempts: int = 3,
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
            max_attempts=max_attempts,
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
    max_attempts: int = 3,
) -> uuid.UUID | None:
    """Ставит джобу. С `dedupe_key` — не больше одной ожидающей на ключ. Не коммитит.

    Возвращает id новой джобы; None — такая уже ждёт (схлопнулась по ключу).
    """
    return await db.scalar(
        _insert(
            kind,
            user_id=user_id,
            payload=payload,
            run_at=run_at or now_utc(),
            dedupe_key=dedupe_key,
            max_attempts=max_attempts,
        ).returning(Job.id)
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


def plan_preview_key(user_id: uuid.UUID) -> str:
    return f"{JobKind.plan_preview}:{user_id}"


def enqueue_plan_preview_sync(conn: Connection, user_id: uuid.UUID, reason: str) -> None:
    """Пересчитать превью плана (из обработчика after_flush)."""
    conn.execute(
        _insert(
            JobKind.plan_preview,
            user_id=user_id,
            payload={"reasons": [reason]},
            run_at=now_utc() + PLAN_DEBOUNCE,
            dedupe_key=plan_preview_key(user_id),
        )
    )


async def _claim(
    db: AsyncSession,
    now: datetime,
    *,
    kinds: Collection[str] | None = None,
    exclude: Collection[str] | None = None,
    fifo: bool = False,
) -> Job | None:
    """Готовая джоба. `kinds` / `exclude` — фильтр по виду; `fifo` — по времени
    постановки (очередь ИИ: что раньше попросили, то раньше и получат)."""
    stmt = select(Job).where(
        Job.status.in_([JobStatus.pending, JobStatus.running]),
        Job.run_at <= now,
        or_(Job.locked_until.is_(None), Job.locked_until < now),
    )
    if kinds is not None:
        stmt = stmt.where(Job.kind.in_(list(kinds)))
    if exclude:
        stmt = stmt.where(Job.kind.not_in(list(exclude)))
    order = [Job.created_at, Job.id] if fifo else [Job.run_at]
    job = await db.scalar(stmt.order_by(*order).limit(1).with_for_update(skip_locked=True))
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
    *,
    kinds: Collection[str] | None = None,
    exclude: Collection[str] | None = None,
    fifo: bool = False,
) -> JobOutcome | None:
    """Берёт и выполняет одну готовую джобу. None — очередь пуста."""
    now = now or now_utc()
    async with factory() as db:
        job = await _claim(db, now, kinds=kinds, exclude=exclude, fifo=fifo)
        if job is None:
            return None
        # После rollback атрибуты истекают — берём заранее
        job_id, kind = job.id, job.kind
        handler = handlers.get(kind)
        try:
            if handler is None:
                raise RuntimeError(f"Нет обработчика для {kind!r}")
            await handler(db, job)
        except JobDeferredError as exc:
            await db.rollback()
            log.info("Джоба %s (%s) ждёт: %s", job_id, kind, exc.message)
            return await _defer(db, job_id, exc)
        except JobFailedError as exc:
            await db.rollback()
            log.warning("Джоба %s (%s) не выполнена: %s", job_id, kind, exc.message)
            await _fail(db, job_id, exc)
            return JobOutcome.failed
        except Exception as exc:
            await db.rollback()
            log.exception("Джоба %s (%s) упала", job_id, kind)
            await _fail(db, job_id, exc)
            return JobOutcome.failed
        job.status = JobStatus.done
        job.finished_at = now_utc()
        job.locked_until = None
        await db.commit()
    return JobOutcome.done


async def _defer(db: AsyncSession, job_id: uuid.UUID, exc: JobDeferredError) -> JobOutcome:
    job = await db.get(Job, job_id)
    if job is None:
        return JobOutcome.deferred
    now = now_utc()
    if exc.max_wait is not None and job.created_at < now - exc.max_wait:
        await _fail(db, job_id, JobFailedError(exc.expired_message))
        return JobOutcome.failed
    # Ожидание — не неудачная попытка
    job.attempts = max(0, job.attempts - 1)
    job.status = JobStatus.pending
    job.locked_until = None
    job.run_at = now + exc.delay
    job.last_error = exc.message[:2000]
    job.result = {**(job.result or {}), "waiting": exc.message}
    await db.commit()
    return JobOutcome.deferred


async def _fail(db: AsyncSession, job_id: uuid.UUID, exc: Exception) -> None:
    job = await db.get(Job, job_id)
    if job is None:
        return
    job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
    job.locked_until = None
    if isinstance(exc, JobFailedError):
        job.result = {**(job.result or {}), "error": exc.message}
    if isinstance(exc, JobFailedError) or job.attempts >= job.max_attempts:
        job.status = JobStatus.failed
        job.finished_at = now_utc()
    else:
        job.status = JobStatus.pending
        job.run_at = now_utc() + RETRY_DELAYS[min(job.attempts, len(RETRY_DELAYS)) - 1]
    await db.commit()


async def run_ready(
    factory: async_sessionmaker[AsyncSession],
    handlers: dict[str, Handler],
    limit: int = 100,
    **filters: Any,
) -> int:
    done = 0
    while done < limit and await run_one(factory, handlers, **filters):
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
