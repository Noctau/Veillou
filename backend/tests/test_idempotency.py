"""M-06 / M-07: двойное нажатие (два параллельных запроса) не выполняет действие дважды."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.db import session_factory
from app.core.security import hash_token
from app.core.time import now_utc
from app.domain.enums import (
    MilestoneStatus,
    ReminderAction,
    ReminderKind,
    ReminderStatus,
    SubtaskStatus,
)
from app.models import BacklogItem, Event, Job, Milestone, Reminder, Subtask, Task, User
from app.schemas.ai import BreakdownApply, BreakdownStep, MilestonesApply, MilestoneSuggestion
from app.services import breakdown, reminder_actions
from app.services.breakdown import BreakdownService
from app.services.free import FreeService
from app.services.project_ai import ProjectAIService
from app.services.reminder_actions import perform_by_id
from app.services.replan import ReplanService

from .test_tasks import make_task

API = "/api/v1"


@pytest.fixture(autouse=True)
def _fast_solver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ReplanService, "time_limit_s", 0.4)


def slow_down(monkeypatch: pytest.MonkeyPatch, owner: Any, name: str) -> None:
    """Пауза после шага `owner.name`: оба запроса успевают пройти проверку до записи —
    гонка воспроизводится детерминированно."""
    original = getattr(owner, name)

    async def slowed(*args: Any, **kwargs: Any) -> Any:
        result = await original(*args, **kwargs)
        await asyncio.sleep(0.3)
        return result

    monkeypatch.setattr(owner, name, slowed)


async def twice(user: User, action: Callable[[Any, User], Awaitable[Any]]) -> list[str]:
    """Одно и то же действие из двух сессий одновременно; итог каждой — 'ok' или имя ошибки."""

    async def run() -> str:
        async with session_factory() as db:
            u = await db.get(User, user.id)
            assert u is not None
            try:
                await action(db, u)
            except Exception as exc:
                return type(exc).__name__
            return "ok"

    return list(await asyncio.gather(run(), run()))


async def count(model: Any, *where: Any) -> int:
    async with session_factory() as db:
        return int(await db.scalar(select(func.count()).select_from(model).where(*where)))


async def test_double_plan_apply_adds_blocks_once(
    auth_client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
):
    slow_down(monkeypatch, ReplanService, "snapshot")
    deadline = now_utc() + timedelta(days=5)
    await make_task(auth_client, title="Доклад", estimate_min=90, deadline=deadline.isoformat())
    proposal = (await auth_client.post(f"{API}/plan/preview")).json()["proposal"]
    rev_id = uuid.UUID(proposal["id"])

    results = await twice(user, lambda db, u: ReplanService(db, u).apply(rev_id))
    assert sorted(results) == ["PlanStaleError", "ok"]
    blocks = await count(
        Event, Event.user_id == user.id, Event.deleted_at.is_(None), Event.title == "Доклад"
    )
    assert blocks == 1


async def _deadline_reminder(user: User, token: str | None = None) -> Reminder:
    async with session_factory() as db:
        task_id = uuid.uuid4()
        deadline = now_utc() + timedelta(days=2)
        db.add(Task(id=task_id, user_id=user.id, title="Реферат", deadline=deadline))
        now = now_utc()
        r = Reminder(
            user_id=user.id,
            kind=ReminderKind.deadline,
            fire_at=now,
            due_at=now,
            expires_at=now + timedelta(days=2),
            channels=["push", "telegram"],
            payload={},
            entity_type="task",
            entity_id=task_id,
            dedupe_key=f"deadline:{task_id}",
            is_auto=True,
            status=ReminderStatus.sent,
            sent_channels=["push", "telegram"],
            attempts=1,
            action_token_hash=hash_token(token) if token else None,
        )
        db.add(r)
        await db.commit()
        return r


def _snoozed() -> Any:
    return Reminder.dedupe_key.like("%:snooze:%")


async def test_double_push_snooze_snoozes_once(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
):
    slow_down(monkeypatch, reminder_actions, "_task")
    token = "t" * 40
    await _deadline_reminder(user, token)
    body = {"token": token, "action": ReminderAction.snooze}
    codes = await asyncio.gather(
        *(client.post(f"{API}/notifications/action", json=body) for _ in range(2))
    )
    assert sorted(r.status_code for r in codes) == [200, 409]
    assert await count(Reminder, _snoozed()) == 1


async def test_double_telegram_button_acts_once(user: User, monkeypatch: pytest.MonkeyPatch):
    slow_down(monkeypatch, reminder_actions, "_task")
    r = await _deadline_reminder(user)
    results = await twice(user, lambda db, u: perform_by_id(db, u, r.id, ReminderAction.snooze))
    assert sorted(results) == ["ReminderActionError", "ok"]
    assert await count(Reminder, _snoozed()) == 1


async def test_double_breakdown_apply_keeps_one_set_of_steps(
    auth_client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
):
    slow_down(monkeypatch, breakdown, "load_catalog")
    task = await make_task(auth_client, title="Реферат")
    data = BreakdownApply(
        steps=[BreakdownStep(title="Найти источники", estimate_min=40)], plan=False
    )
    task_id = uuid.UUID(task["id"])
    results = await twice(user, lambda db, u: BreakdownService(db, u).apply(task_id, data))
    assert results == ["ok", "ok"]  # повтор — та же разбивка, не ошибка
    steps = await count(
        Subtask,
        Subtask.task_id == task_id,
        Subtask.deleted_at.is_(None),
        Subtask.status == SubtaskStatus.todo,
    )
    assert steps == 1


async def test_double_milestones_save_adds_once(
    auth_client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
):
    slow_down(monkeypatch, ProjectAIService, "_mark_applied")
    project = (await auth_client.post(f"{API}/projects", json={"title": "ВКР"})).json()
    project_id = uuid.UUID(project["id"])
    async with session_factory() as db:
        job = Job(
            user_id=user.id,
            kind="ai.milestones",
            payload={"project_id": str(project_id)},
            status="done",
            run_at=now_utc(),
            result={"project_id": str(project_id), "milestones": [], "warning": None},
        )
        db.add(job)
        await db.commit()
        job_id = job.id
    data = MilestonesApply(milestones=[MilestoneSuggestion(title="Обзор готов")], job_id=job_id)
    results = await twice(user, lambda db, u: ProjectAIService(db, u).apply(project_id, data))
    assert sorted(results) == ["ConflictError", "ok"]
    milestones = await count(
        Milestone,
        Milestone.project_id == project_id,
        Milestone.deleted_at.is_(None),
        Milestone.status == MilestoneStatus.planned,
    )
    assert milestones == 1


async def test_double_free_start_creates_one_block(
    auth_client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
):
    slow_down(monkeypatch, FreeService, "candidates")
    item = (await auth_client.post(f"{API}/backlog", json={"title": "Стоматолог"})).json()
    item_id = uuid.UUID(item["id"])
    now = now_utc().replace(hour=12, minute=0, second=0, microsecond=0)

    async def start(db: Any, u: User) -> Event:
        return await FreeService(db, u, now).start("backlog", item_id)

    results = await twice(user, start)
    assert results == ["ok", "ok"]  # второй «Начать» — тот же блок
    blocks = await count(
        Event,
        Event.source_id == item_id,
        Event.deleted_at.is_(None),
    )
    assert blocks == 1
    assert await count(BacklogItem, BacklogItem.id == item_id) == 1


async def test_parallel_day_limit_puts_do_not_fail(client: AsyncClient, user: User):
    """L-02: select → insert давал IntegrityError (500) примерно в половине случаев."""
    from httpx import ASGITransport

    from app.main import app

    from .conftest import PASSWORD

    clients = []
    for _ in range(2):
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        await c.post(
            f"{API}/auth/login", json={"email": "student@example.com", "password": PASSWORD}
        )
        clients.append(c)
    codes: list[int] = []
    for d in range(10, 20):
        resps = await asyncio.gather(
            *(c.put(f"{API}/plan/day-limits/2030-01-{d}", json={"minutes": 480}) for c in clients)
        )
        codes += [r.status_code for r in resps]
    for c in clients:
        await c.aclose()
    assert set(codes) == {200}


async def test_integrity_error_is_409():
    from fastapi import FastAPI
    from httpx import ASGITransport
    from sqlalchemy.exc import IntegrityError

    from app.core.exceptions import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/boom")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
