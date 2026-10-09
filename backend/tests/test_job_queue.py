"""L-05: джоба, на которой воркер падал max_attempts раз, не забирается снова бесконечно."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import session_factory
from app.core.time import now_utc
from app.domain.enums import JobStatus
from app.models import Job, User
from app.services import jobs


async def test_crashed_job_with_exhausted_attempts_is_failed(session: AsyncSession, user: User):
    past = now_utc() - timedelta(minutes=10)
    session.add(
        Job(
            user_id=user.id,
            kind="ai.photo",
            payload={},
            status=JobStatus.running,  # воркер упал посреди выполнения
            run_at=past,
            locked_until=past,
            attempts=3,
            max_attempts=3,
        )
    )
    await session.commit()
    called = []

    async def handler(db: AsyncSession, job: Job) -> None:
        called.append(job.id)

    assert await jobs.run_one(session_factory, {"ai.photo": handler}) is None
    assert called == []
    session.expire_all()
    # Не первая попавшаяся: создание пользователя ставит ещё и reminders.sync
    job = await session.scalar(select(Job).where(Job.kind == "ai.photo"))
    assert job is not None
    assert job.status == JobStatus.failed
    assert job.finished_at is not None
    assert job.result == {"error": "Не получилось — попробуйте ещё раз"}


async def test_crashed_job_with_attempts_left_is_retried(session: AsyncSession, user: User):
    past = now_utc() - timedelta(minutes=10)
    session.add(
        Job(
            user_id=user.id,
            kind="x",
            payload={},
            status=JobStatus.running,
            run_at=past,
            locked_until=past,
            attempts=1,
            max_attempts=3,
        )
    )
    await session.commit()
    called = []

    async def handler(db: AsyncSession, job: Job) -> None:
        called.append(job.id)

    assert await jobs.run_one(session_factory, {"x": handler}) == jobs.JobOutcome.done
    assert len(called) == 1
