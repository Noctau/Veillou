"""Время задания (п.1): без шагов — своё и его ставит планировщик; с шагами — сумма
шагов, и планировщик ставит шаги, а не задание."""

from sqlalchemy import select

from app.core.db import session_factory
from app.domain.enums import EventKind, EventStatus, SourceType
from app.domain.tasks import total_estimate
from app.models import Event

from .test_replan import FRI, at, call, snapshot
from .test_schedule_api import API
from .test_tasks import add_subtask, get_task, make_task


def test_total_estimate_rules():
    assert total_estimate(90, 0, 0) == 90
    assert total_estimate(None, 0, 0) is None
    assert total_estimate(90, 70, 2) == 70  # с шагами своё время не в счёт
    assert total_estimate(45, 300, 5, recurring=True) == 45  # время одного вхождения


async def test_own_time_without_steps(auth_client):
    task = await make_task(auth_client, estimate_min=90)
    assert task["estimate_min"] == 90
    assert task["total_estimate_min"] == 90
    listed = (await auth_client.get(f"{API}/tasks")).json()
    assert listed[0]["total_estimate_min"] == 90


async def test_time_is_sum_of_steps(auth_client):
    task = await make_task(auth_client, estimate_min=200)
    await add_subtask(auth_client, task["id"], estimate_min=40)
    step = await add_subtask(auth_client, task["id"], estimate_min=50)
    await auth_client.patch(f"{API}/subtasks/{step['id']}", json={"status": "done"})
    detail = await get_task(auth_client, task["id"])
    # Все шаги, сделанные тоже
    assert detail["total_estimate_min"] == 90
    listed = (await auth_client.get(f"{API}/tasks")).json()
    assert listed[0]["total_estimate_min"] == 90


async def test_own_time_rejected_when_task_has_steps(auth_client):
    task = await make_task(auth_client)
    await add_subtask(auth_client, task["id"], estimate_min=40)
    resp = await auth_client.patch(f"{API}/tasks/{task['id']}", json={"estimate_min": 60})
    assert resp.status_code == 400
    assert "шаг" in resp.json()["error"]["message"]


async def test_set_own_time_then_planned(auth_client, user):
    task = await make_task(auth_client, deadline=at(FRI, 23, 59).isoformat())
    snap = await snapshot(user)
    assert not [b for b in snap.inp.blocks if task["id"] in str(b.id)]

    resp = await auth_client.patch(f"{API}/tasks/{task['id']}", json={"estimate_min": 75})
    assert resp.status_code == 200
    assert resp.json()["total_estimate_min"] == 75
    snap = await snapshot(user)
    [block] = [b for b in snap.inp.blocks if b.id == f"task:{task['id']}"]
    assert block.duration_min == 75


async def test_task_with_steps_plans_steps_not_task(auth_client, user):
    task = await make_task(auth_client, estimate_min=120, deadline=at(FRI, 23, 59).isoformat())
    step = await add_subtask(auth_client, task["id"], estimate_min=30)
    ids = {str(b.id) for b in (await snapshot(user)).inp.blocks}
    assert f"subtask:{step['id']}" in ids
    assert f"task:{task['id']}" not in ids


async def test_first_step_drops_whole_task_blocks(auth_client, user):
    task = await make_task(auth_client, estimate_min=60, deadline=at(FRI, 23, 59).isoformat())
    rev = await call(user, "preview")
    await call(user, "apply", rev.id)
    async with session_factory() as db:
        blocks = list(
            await db.scalars(
                select(Event).where(
                    Event.source_type == SourceType.task, Event.deleted_at.is_(None)
                )
            )
        )
    assert blocks
    assert all(b.kind == EventKind.subtask for b in blocks)

    await add_subtask(auth_client, task["id"], estimate_min=30)
    async with session_factory() as db:
        left = list(
            await db.scalars(
                select(Event).where(
                    Event.source_type == SourceType.task,
                    Event.deleted_at.is_(None),
                    Event.status == EventStatus.planned,
                )
            )
        )
    assert left == []


async def test_quickadd_duration_becomes_task_time(auth_client, user):
    from app.services.quickadd import create_from_text
    from app.services.tasks import TaskService

    async with session_factory() as db:
        created = await create_from_text(db, user, "реферат до пятницы на 2 часа")
        detail = await TaskService(db, user).get_detail(created.id)
    assert detail.estimate_min == 120
