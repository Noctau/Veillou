"""L-03: ошибка у одного пользователя не прерывает ночные/ежечасные циклы для остальных."""

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import session_factory
from app.models import Task, User
from app.services import recurring_tasks, reminders, replan, schedule_sync
from app.services.users import create_user

from .conftest import PASSWORD


@pytest.fixture
async def two_users(session: AsyncSession, user: User) -> tuple[uuid.UUID, uuid.UUID]:
    other = await create_user(session, email="b@example.com", password=PASSWORD)
    return user.id, other.id


async def test_nightly_replan_continues_after_failure(
    two_users: tuple[uuid.UUID, uuid.UUID], monkeypatch: pytest.MonkeyPatch
):
    bad, good = two_users
    done: list[uuid.UUID] = []

    async def preview(self: Any, *args: Any, **kwargs: Any) -> None:
        if self.user_id == bad:
            raise RuntimeError("сломался")
        done.append(self.user_id)

    monkeypatch.setattr(replan.ReplanService, "preview", preview)
    async with session_factory() as db:
        await replan.nightly_replan(db)
    assert done == [good]


async def test_sync_all_users_continues_after_failure(
    two_users: tuple[uuid.UUID, uuid.UUID], monkeypatch: pytest.MonkeyPatch
):
    bad, good = two_users
    done: list[uuid.UUID] = []
    original = reminders.sync_user_reminders

    async def sync(db: AsyncSession, user_id: uuid.UUID, now: Any = None) -> Any:
        if user_id == bad:
            raise RuntimeError("сломался")
        done.append(user_id)
        return await original(db, user_id, now)

    monkeypatch.setattr(reminders, "sync_user_reminders", sync)
    async with session_factory() as db:
        await reminders.sync_all_users(db)
    assert done == [good]


async def test_roll_all_users_continues_after_failure(
    two_users: tuple[uuid.UUID, uuid.UUID], monkeypatch: pytest.MonkeyPatch
):
    bad, good = two_users
    done: list[uuid.UUID] = []

    async def roll(self: Any) -> int:
        if self.user_id == bad:
            raise RuntimeError("сломался")
        done.append(self.user_id)
        return 0

    monkeypatch.setattr(schedule_sync.SeriesSync, "roll_recurring", roll)
    async with session_factory() as db:
        await schedule_sync.roll_all_users(db)
    assert done == [good]


async def test_roll_recurring_tasks_continues_after_failure(
    two_users: tuple[uuid.UUID, uuid.UUID], session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    bad, good = two_users
    for owner in (bad, good):
        session.add(Task(user_id=owner, title="Встреча", recurrence="FREQ=WEEKLY"))
    await session.commit()
    done: list[uuid.UUID] = []

    async def sync(db: AsyncSession, task: Task, today: Any) -> int:
        if task.user_id == bad:
            raise RuntimeError("сломался")
        done.append(task.user_id)
        return 1

    monkeypatch.setattr(recurring_tasks, "sync_recurring_task", sync)
    async with session_factory() as db:
        created = await recurring_tasks.roll_all_recurring_tasks(db)
    assert done == [good]
    assert created == 1
