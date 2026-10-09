"""M-05: ИИ-запросы ограничены — не больше N ждущих и дневная квота."""

from datetime import timedelta

import pytest
from aiogram.methods import EditMessageText
from aiogram.types import Update
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.time import now_utc
from app.domain.enums import JobKind, JobStatus
from app.models import Job, User

from .test_bot import linked, tg, tg_message
from .test_bot_ai import LONG

__all__ = ["linked", "tg"]
API = "/api/v1"


async def add_jobs(session: AsyncSession, user: User, n: int, **over) -> None:
    for _ in range(n):
        fields = {
            "user_id": user.id,
            "kind": JobKind.ai_parse,
            "payload": {},
            "status": JobStatus.pending,
            "run_at": now_utc(),
            **over,
        }
        session.add(Job(**fields))
    await session.commit()


async def parse(client: AsyncClient):
    return await client.post(f"{API}/quick-add/ai-parse", json={"text": "реферат"})


async def test_pending_limit(auth_client: AsyncClient, session: AsyncSession, user: User):
    await add_jobs(session, user, settings.AI_MAX_PENDING)
    resp = await parse(auth_client)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "ai_quota"


async def test_finished_and_other_jobs_do_not_block(
    auth_client: AsyncClient, session: AsyncSession, user: User
):
    await add_jobs(session, user, settings.AI_MAX_PENDING, status=JobStatus.done)
    await add_jobs(session, user, 10, kind=JobKind.reminders_sync)
    assert (await parse(auth_client)).status_code == 202


async def test_daily_limit(
    auth_client: AsyncClient, session: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_DAILY_LIMIT", 3)
    old = now_utc() - timedelta(hours=25)
    await add_jobs(session, user, 5, status=JobStatus.done, created_at=old)
    await add_jobs(session, user, 2, status=JobStatus.done)
    assert (await parse(auth_client)).status_code == 202
    resp = await parse(auth_client)
    assert resp.status_code == 429


async def test_bot_reports_quota_in_chat(tg, linked: User, session: AsyncSession):
    await add_jobs(session, linked, settings.AI_MAX_PENDING)
    await tg.dp.feed_update(tg.bot, Update(update_id=777_001, message=tg_message(LONG)))
    edits = [m for m in tg.session.sent if isinstance(m, EditMessageText)]
    assert edits
    assert "ИИ" in edits[-1].text


async def test_huge_photos_are_not_sent_to_vision_model(
    auth_client: AsyncClient, session: AsyncSession, user: User
):
    """L-06: фото больше MAX_IMAGE_BYTES в память воркера не читаются."""
    from app.models import Attachment, Task
    from app.services.ai_parse import MAX_IMAGE_BYTES

    task = Task(user_id=user.id, title="Задание с фото")
    session.add(task)
    await session.flush()
    session.add(
        Attachment(
            user_id=user.id,
            owner_type="task",
            owner_id=task.id,
            filename="big.jpg",
            mime="image/jpeg",
            size=MAX_IMAGE_BYTES + 1,
            sha256="0" * 64,
            storage_key="00/00/" + "0" * 64,
        )
    )
    await session.commit()
    resp = await auth_client.post(f"{API}/tasks/{task.id}/recognize")
    assert resp.status_code == 400
