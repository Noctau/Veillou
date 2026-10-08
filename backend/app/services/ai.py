"""Вызов ИИ из джоб: провайдер из настроек, каждая попытка — строка `ai_log`.

Журнал коммитится сразу после вызова — и при успехе, и при ошибке (тогда
обработчик джобы откатит свои правки, а журнал останется).
"""

import uuid
from collections.abc import Sequence
from datetime import timedelta

from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import Attempt, Image, LLMError, LLMUnavailableError, Message, get_provider
from app.core.config import settings
from app.core.time import now_utc
from app.domain.enums import AIPurpose
from app.models import AILog
from app.services.jobs import JobDeferredError, JobFailedError

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


async def prune_log(db: AsyncSession) -> None:
    cutoff = now_utc() - timedelta(days=settings.AI_LOG_KEEP_DAYS)
    await db.execute(delete(AILog).where(AILog.created_at < cutoff))
    await db.commit()
