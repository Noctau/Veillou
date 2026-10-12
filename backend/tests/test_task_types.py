"""Справочник типов задач (M15.1): CRUD, умолчания типа при создании задачи,
«быстрые типы» с правилом срока (бывшее «задание с работы»)."""

from datetime import UTC, datetime

import pytest

from .test_catalog import action_types, categories
from .test_schedule_api import API, other_client
from .test_tasks import get_task, make_task, make_task_type

# Вторник 06.10.2026 15:00 МСК
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr("app.services.tasks.now_utc", lambda: NOW)


async def make_project(client, **over) -> dict:
    resp = await client.post(f"{API}/projects", json={"title": "ВКР", **over})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_empty_for_new_user(auth_client):
    """Типы задач не засеваются: пустой справочник — нормальное состояние."""
    assert (await auth_client.get(f"{API}/task-types")).json() == []
    task = await make_task(auth_client)
    assert task["task_type_id"] is None


async def test_crud(auth_client):
    essay = await make_task_type(auth_client, synonyms=["реферат", "Реферат", "эссе"])
    assert essay["synonyms"] == ["реферат", "эссе"]
    assert essay["position"] == 0
    assert essay["deadline_rule"] is None
    lab = await make_task_type(auth_client, name="Лабораторная", icon="flask-conical")
    assert lab["position"] == 1

    url = f"{API}/task-types/{essay['id']}"
    resp = await auth_client.patch(url, json={"name": "Эссе", "deadline_rule": {"days": 7}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deadline_rule"] == {"kind": "days", "days": 7}
    assert (await auth_client.patch(url, json={"name": None})).status_code == 400
    for bad in (
        {"deadline_rule": {"kind": "days", "days": 0}},
        {"deadline_rule": {"kind": "weeks", "days": 1}},
        {"icon": "nope"},
        {"key": "essay"},
    ):
        assert (await auth_client.patch(url, json=bad)).status_code == 422, bad
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await auth_client.patch(url, json={"default_project_id": missing})).status_code == 404

    task = await make_task(auth_client, task_type_id=essay["id"])
    assert task["task_type_id"] == essay["id"]
    assert (await auth_client.delete(url)).status_code == 204
    names = [t["name"] for t in (await auth_client.get(f"{API}/task-types")).json()]
    assert names == ["Лабораторная"]
    # Задачи удалённого типа остаются — без типа
    assert (await get_task(auth_client, task["id"]))["task_type_id"] is None
    resp = await auth_client.post(f"{API}/tasks", json={"title": "x", "task_type_id": essay["id"]})
    assert resp.status_code == 404


async def test_per_user(auth_client, session):
    essay = await make_task_type(auth_client)
    async with other_client(auth_client, session) as other:
        assert (await other.get(f"{API}/task-types")).json() == []
        resp = await other.patch(f"{API}/task-types/{essay['id']}", json={"name": "X"})
        assert resp.status_code == 404
        resp = await other.post(f"{API}/tasks", json={"title": "x", "task_type_id": essay["id"]})
        assert resp.status_code == 404


async def test_type_defaults_fill_empty_fields(auth_client):
    """«Задание с работы»: срок = выдача + 14 дней, проект и категория типа."""
    cats = await categories(auth_client)
    types = await action_types(auth_client)
    vkr = await make_project(auth_client)
    work = await make_task_type(
        auth_client,
        name="Задание с работы",
        deadline_rule={"kind": "days", "days": 14},
        default_project_id=vkr["id"],
        default_category_id=cats["work"]["id"],
        default_action_type_id=types["home"]["id"],
        default_estimate_min=90,
    )
    task = await make_task(auth_client, title="Обработать данные ERA5", task_type_id=work["id"])
    assert task["category_id"] == cats["work"]["id"]
    assert task["project_id"] == vkr["id"]
    assert task["action_type_id"] == types["home"]["id"]
    assert task["estimate_min"] == 90
    assert task["issued_at"] == "2026-10-06"
    assert task["deadline"] == "2026-10-20T20:59:00Z"  # 20.10 23:59 МСК

    # Своя дата выдачи, явный «без проекта», свои поля важнее умолчаний
    task = await make_task(
        auth_client,
        title="Отчёт",
        task_type_id=work["id"],
        issued_at="2026-10-01",
        project_id=None,
        category_id=cats["study"]["id"],
        estimate_min=30,
    )
    assert task["project_id"] is None
    assert task["deadline"] == "2026-10-15T20:59:00Z"
    assert task["category_id"] == cats["study"]["id"]
    assert task["estimate_min"] == 30
    task = await make_task(
        auth_client, task_type_id=work["id"], deadline="2026-11-01T12:00:00+03:00"
    )
    assert task["deadline"] == "2026-11-01T09:00:00Z"
    assert task["issued_at"] is None

    # Удалённый проект типа не подставляется
    assert (await auth_client.delete(f"{API}/projects/{vkr['id']}")).status_code == 204
    task = await make_task(auth_client, task_type_id=work["id"])
    assert task["project_id"] is None


async def test_type_template_gives_steps(auth_client):
    types = await action_types(auth_client)
    resp = await auth_client.post(
        f"{API}/breakdown-templates",
        json={
            "name": "Реферат",
            "steps": [
                {"title": "Найти источники", "estimate_min": 60},
                {
                    "title": "Написать",
                    "estimate_min": 120,
                    "action_type_id": types["people"]["id"],
                    "depends_on": [0],
                },
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    template = resp.json()
    essay = await make_task_type(auth_client, default_template_id=template["id"])
    task = await make_task(auth_client, task_type_id=essay["id"])
    steps = task["subtasks"]
    assert [s["title"] for s in steps] == ["Найти источники", "Написать"]
    assert steps[1]["depends_on"] == [steps[0]["id"]]
    assert steps[1]["action_type_id"] == types["people"]["id"]
    # Свои шаги важнее шаблона
    task = await make_task(auth_client, task_type_id=essay["id"], subtasks=[{"title": "Своё"}])
    assert [s["title"] for s in task["subtasks"]] == ["Своё"]
