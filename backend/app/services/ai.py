"""Вызов ИИ из джоб: провайдер из настроек, каждая попытка — строка `ai_log`.

Журнал коммитится сразу после вызова — и при успехе, и при ошибке (тогда
обработчик джобы откатит свои правки, а журнал останется).
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import (
    Attempt,
    Image,
    LLMError,
    LLMRejectedError,
    LLMUnavailableError,
    Message,
    get_provider,
)
from app.core.config import settings
from app.core.exceptions import TooManyRequestsError
from app.core.time import now_utc
from app.domain.enums import AI_JOB_KINDS, AIPurpose, JobKind, JobStatus
from app.models import AILog, Job
from app.services import jobs
from app.services.jobs import JobDeferredError, JobFailedError

log = logging.getLogger(__name__)

WAITING = "ИИ сейчас недоступен — запрос в очереди, выполню, как только он появится"
EXPIRED = "ИИ так и не стал доступен — попробуйте ещё раз"


def _rows(
    user_id: uuid.UUID, purpose: AIPurpose, attempts: Sequence[Attempt], job_id: uuid.UUID | None
) -> list[AILog]:
    return [
        AILog(
            user_id=user_id,
            purpose=purpose,
            provider=a.provider,
            model=a.model[:100],
            ok=a.ok,
            error=a.error,
            latency_ms=a.latency_ms,
            prompt_tokens=a.prompt_tokens,
            completion_tokens=a.completion_tokens,
            request=a.request,
            response=a.response,
            job_id=job_id,
        )
        for a in attempts
    ]


async def call_llm[T: BaseModel](
    db: AsyncSession,
    user_id: uuid.UUID,
    purpose: AIPurpose,
    messages: Sequence[Message],
    schema: type[T],
    *,
    images: Sequence[Image] | None = None,
    job_id: uuid.UUID | None = None,
) -> T:
    """Ответ ИИ по схеме.

    Ни один провайдер не ответил — `JobDeferredError`: запрос ждёт в очереди, пока ИИ
    не появится (не дольше LLM_QUEUE_MAX_HOURS). Ответил, но не по схеме —
    `JobFailedError` с текстом для пользователя: повтор того же не поможет.
    """
    try:
        completion = await get_provider().complete_json(messages, schema, images)
    except LLMError as exc:
        db.add_all(_rows(user_id, purpose, exc.attempts, job_id))
        await db.commit()
        if isinstance(exc, LLMRejectedError):
            log.error(
                "ИИ отклонил запрос (%s): %s",
                purpose,
                exc.attempts[-1].error if exc.attempts else exc,
            )
        if isinstance(exc, LLMUnavailableError):
            raise JobDeferredError(
                WAITING,
                max_wait=timedelta(hours=settings.LLM_QUEUE_MAX_HOURS),
                expired_message=EXPIRED,
            ) from exc
        raise JobFailedError(exc.message) from exc
    db.add_all(_rows(user_id, purpose, completion.attempts, job_id))
    await db.commit()
    return completion.value


class AIQuotaError(TooManyRequestsError):
    code = "ai_quota"


async def _ai_jobs(db: AsyncSession, user_id: uuid.UUID, *where: Any) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.user_id == user_id, Job.kind.in_(list(AI_JOB_KINDS)), *where)
        )
        or 0
    )


async def enqueue_ai(
    db: AsyncSession, kind: JobKind, *, user_id: uuid.UUID, payload: dict[str, Any]
) -> uuid.UUID:
    """Ставит ИИ-джобу в пределах квоты (429 сверх неё). Не коммитит."""
    pending = await _ai_jobs(db, user_id, Job.status.in_([JobStatus.pending, JobStatus.running]))
    if pending >= settings.AI_MAX_PENDING:
        raise AIQuotaError(
            f"Уже ждут ответа ИИ запросов: {pending} — дождитесь их и попробуйте снова"
        )
    today = await _ai_jobs(db, user_id, Job.created_at > now_utc() - timedelta(days=1))
    if today >= settings.AI_DAILY_LIMIT:
        raise AIQuotaError("Запросы к ИИ на сегодня закончились — попробуйте завтра")
    job_id = await jobs.enqueue(db, kind, user_id=user_id, payload=payload, max_attempts=1)
    if job_id is None:  # без dedupe_key новая строка вставляется всегда
        raise RuntimeError("ИИ-джоба не поставлена")
    return job_id


async def prune_log(db: AsyncSession) -> None:
    cutoff = now_utc() - timedelta(days=settings.AI_LOG_KEEP_DAYS)
    await db.execute(delete(AILog).where(AILog.created_at < cutoff))
    await db.commit()
