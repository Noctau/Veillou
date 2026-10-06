from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.recurring_tasks import roll_all_recurring_tasks

from .test_catalog import action_types, categories
from .test_schedule_api import API, other_client
from .test_tasks import get_task, make_task

# Вторник 06.10.2026 15:00 МСК
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    state = {"now": NOW}
    monkeypatch.setattr("app.services.tasks.now_utc", lambda: state["now"])
    return state


async def make_project(client, **over) -> dict:
    resp = await client.post(f"{API}/projects", json={"title": "ВКР", **over})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def add_milestone(client, project_id: str, **over) -> dict:
    resp = await client.post(
        f"{API}/projects/{project_id}/milestones", json={"title": "Этап", **over}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------- проекты и этапы ----------


async def test_project_crud_and_progress(auth_client):
    cats = await categories(auth_client)
    project = await make_project(
        auth_client,
        deadline="2027-06-15",
        contacts=[{"name": "Петров П. П.", "role": "научный руководитель", "contact": "p@msu.ru"}],
    )
    assert project["category_id"] == cats["study"]["id"]
    assert project["contacts"][0]["role"] == "научный руководитель"
    assert project["milestones"] == [] and project["next_milestone"] is None

    topic = await add_milestone(
        auth_client, project["id"], title="Тема согласована", date="2026-10-20"
    )
    review = await add_milestone(
        auth_client, project["id"], title="Обзор литературы", date="2026-12-01"
    )
    await add_milestone(auth_client, project["id"], title="Защита")  # без даты — в конце

    t1 = await make_task(auth_client, title="Найти статьи", project_id=project["id"])
    await make_task(auth_client, title="Написать введение", milestone_id=review["id"])
    await auth_client.patch(f"{API}/tasks/{t1['id']}", json={"status": "done"})
    await auth_client.patch(f"{API}/milestones/{topic['id']}", json={"status": "done"})

    detail = (await auth_client.get(f"{API}/projects/{project['id']}")).json()
    assert [m["title"] for m in detail["milestones"]] == [
        "Тема согласована",
        "Обзор литературы",
        "Защита",
    ]
    assert detail["milestones"][0]["done_at"] is not None
    assert (detail["tasks_total"], detail["tasks_done"]) == (2, 1)
    assert (detail["milestones_total"], detail["milestones_done"]) == (3, 1)
    assert detail["next_milestone"]["id"] == review["id"]

    listed = (await auth_client.get(f"{API}/projects")).json()
    assert [p["id"] for p in listed] == [project["id"]]
    resp = await auth_client.get(f"{API}/tasks", params={"project_id": project["id"]})
    assert len(resp.json()) == 2


async def test_milestone_sets_project_and_must_match(auth_client):
    vkr = await make_project(auth_client)
    other = await make_project(auth_client, title="Магистратура")
    stage = await add_milestone(auth_client, vkr["id"])
    task = await make_task(auth_client, milestone_id=stage["id"])
    assert task["project_id"] == vkr["id"]

    resp = await auth_client.post(
        f"{API}/tasks", json={"title": "x", "project_id": other["id"], "milestone_id": stage["id"]}
    )
    assert resp.status_code == 400
    # Перенос задания в другой проект отвязывает этап старого
    resp = await auth_client.patch(f"{API}/tasks/{task['id']}", json={"project_id": other["id"]})
    assert resp.json()["milestone_id"] is None


async def test_single_work_default(auth_client):
    a = await make_project(auth_client, is_work_default=True)
    b = await make_project(auth_client, title="Другой", is_work_default=True)
    projects = {p["id"]: p for p in (await auth_client.get(f"{API}/projects")).json()}
    assert not projects[a["id"]]["is_work_default"] and projects[b["id"]]["is_work_default"]
    resp = await auth_client.patch(f"{API}/projects/{a['id']}", json={"is_work_default": True})
    assert resp.json()["is_work_default"]
    projects = {p["id"]: p for p in (await auth_client.get(f"{API}/projects")).json()}
    assert not projects[b["id"]]["is_work_default"]


async def test_delete_project_keeps_tasks(auth_client):
    project = await make_project(auth_client)
    stage = await add_milestone(auth_client, project["id"])
    task = await make_task(auth_client, milestone_id=stage["id"])
    assert (await auth_client.delete(f"{API}/projects/{project['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/projects/{project['id']}")).status_code == 404
    kept = await get_task(auth_client, task["id"])
    assert kept["project_id"] is None and kept["milestone_id"] is None


async def test_delete_milestone_unlinks_tasks(auth_client):
    project = await make_project(auth_client)
    stage = await add_milestone(auth_client, project["id"])
    task = await make_task(auth_client, milestone_id=stage["id"])
    assert (await auth_client.delete(f"{API}/milestones/{stage['id']}")).status_code == 204
    kept = await get_task(auth_client, task["id"])
    assert kept["project_id"] == project["id"] and kept["milestone_id"] is None


async def test_project_task_inherits_category(auth_client):
    cats = await categories(auth_client)
    project = await make_project(auth_client, category_id=cats["work"]["id"])
    task = await make_task(auth_client, project_id=project["id"])
    assert task["category_id"] == cats["work"]["id"]


async def test_projects_are_per_user(auth_client, session):
    project = await make_project(auth_client)
    async with other_client(auth_client, session) as other:
        assert (await other.get(f"{API}/projects")).json() == []
        assert (await other.get(f"{API}/projects/{project['id']}")).status_code == 404
        resp = await other.post(f"{API}/tasks", json={"title": "x", "project_id": project["id"]})
        assert resp.status_code == 404


# ---------- задания с работы ----------


async def test_work_task_defaults(auth_client):
    cats = await categories(auth_client)
    vkr = await make_project(auth_client, is_work_default=True)
    resp = await auth_client.post(f"{API}/tasks/work", json={"title": "Обработать данные ERA5"})
    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["category_id"] == cats["work"]["id"]
    assert task["project_id"] == vkr["id"]
    assert task["issued_at"] == "2026-10-06"
    assert task["deadline"] == "2026-10-20T20:59:00Z"  # 20.10 23:59 МСК

    resp = await auth_client.post(
        f"{API}/tasks/work",
        json={"title": "Отчёт", "issued_at": "2026-10-01", "no_project": True},
    )
    task = resp.json()
    assert task["project_id"] is None
    assert task["deadline"] == "2026-10-15T20:59:00Z"


async def test_work_task_without_default_project(auth_client):
    resp = await auth_client.post(f"{API}/tasks/work", json={"title": "x"})
    assert resp.json()["project_id"] is None


# ---------- регулярные задания ----------


async def test_recurring_meetings_materialize(auth_client, session: AsyncSession, clock):
    types = await action_types(auth_client)
    project = await make_project(auth_client)
    task = await make_task(
        auth_client,
        title="Встреча с научруком",
        task_type="other",
        project_id=project["id"],
        action_type_id=types["people"]["id"],
        recurrence="FREQ=WEEKLY;BYDAY=TH",
        estimate_min=60,
    )
    assert task["recurrence_start"] == "2026-10-06"
    dates = [s["occurrence_date"] for s in task["subtasks"]]
    # Четверги с 08.10 по 05.12 (60 дней)
    assert dates[0] == "2026-10-08" and dates[-1] == "2026-12-03"
    assert len(dates) == 9
    first = task["subtasks"][0]
    assert first["title"] == "Встреча с научруком" and first["estimate_min"] == 60
    assert task["action_type_id"] == types["people"]["id"]
    # Регулярное не входит в прогресс проекта
    detail = (await auth_client.get(f"{API}/projects/{project['id']}")).json()
    assert detail["tasks_total"] == 0

    # Сделанное вхождение не трогается при смене правила
    await auth_client.patch(f"{API}/subtasks/{first['id']}", json={"status": "done"})
    resp = await auth_client.patch(
        f"{API}/tasks/{task['id']}", json={"recurrence": "FREQ=WEEKLY;BYDAY=TU", "title": "Созвон"}
    )
    subtasks = resp.json()["subtasks"]
    by_date = {s["occurrence_date"]: s for s in subtasks}
    assert by_date["2026-10-08"]["status"] == "done"
    assert by_date["2026-10-08"]["title"] == "Встреча с научруком"
    todo = [s for s in subtasks if s["status"] == "todo"]
    assert {date.fromisoformat(s["occurrence_date"]).isoweekday() for s in todo} == {2}
    assert all(s["title"] == "Созвон" for s in todo)

    # Ночная докатка через неделю добавляет новые вхождения
    week_later = datetime(2026, 10, 13, 0, 30, tzinfo=UTC)
    created = await roll_all_recurring_tasks(session, now=week_later)
    assert created == 1

    # Снятие регулярности убирает будущие несделанные
    resp = await auth_client.patch(f"{API}/tasks/{task['id']}", json={"recurrence": None})
    left = resp.json()["subtasks"]
    assert [s["status"] for s in left] == ["done"]


async def test_recurring_rule_validated(auth_client):
    for bad in ("FREQ=HOURLY", "garbage", "DTSTART:20260101T000000\nRRULE:FREQ=DAILY"):
        resp = await auth_client.post(f"{API}/tasks", json={"title": "x", "recurrence": bad})
        assert resp.status_code == 422, bad
