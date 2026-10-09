from httpx import AsyncClient

from .test_catalog import action_types, categories
from .test_schedule_api import API, make_semester, make_subject, other_client


async def make_task(client: AsyncClient, **over) -> dict:
    body = {"title": "Реферат", "task_type": "essay", **over}
    resp = await client.post(f"{API}/tasks", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def add_subtask(client: AsyncClient, task_id: str, **over) -> dict:
    resp = await client.post(f"{API}/tasks/{task_id}/subtasks", json={"title": "Шаг", **over})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def get_task(client: AsyncClient, task_id: str) -> dict:
    resp = await client.get(f"{API}/tasks/{task_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_create_task_with_defaults(auth_client):
    task = await make_task(
        auth_client,
        deadline="2026-10-15T23:59:00+03:00",
        subtasks=[{"title": "Найти источники", "estimate_min": 60}, {"title": "Написать"}],
    )
    types = await action_types(auth_client)
    cats = await categories(auth_client)
    # Без явных значений: «Самостоятельная учёба» и её категория «Учёба»
    assert task["action_type_id"] == types["study"]["id"]
    assert task["category_id"] == cats["study"]["id"]
    assert task["deadline"] == "2026-10-15T20:59:00Z"
    assert task["status"] == "active"
    assert task["priority"] == "normal"
    assert [s["title"] for s in task["subtasks"]] == ["Найти источники", "Написать"]
    assert [s["position"] for s in task["subtasks"]] == [0, 1]
    assert task["subtasks"][1]["estimate_min"] == 30
    assert task["subtasks_total"] == 2
    assert task["progress"] == 0


async def test_category_follows_action_type(auth_client):
    types = await action_types(auth_client)
    cats = await categories(auth_client)
    home_id = types["home"]["id"]
    task = await make_task(auth_client, title="Записаться в МФЦ", action_type_id=home_id)
    assert task["category_id"] == cats["home"]["id"]


async def test_progress_and_done_sync(auth_client):
    task = await make_task(auth_client, subtasks=[{"title": "a"}, {"title": "b"}, {"title": "c"}])
    first = task["subtasks"][0]
    resp = await auth_client.patch(
        f"{API}/subtasks/{first['id']}", json={"status": "done", "actual_feel": "slower"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["done_at"] is not None
    task = await get_task(auth_client, task["id"])
    assert task["subtasks_done"] == 1
    assert round(task["progress"], 2) == 0.33

    # Снятие отметки сбрасывает и оценку «как прошло»
    resp = await auth_client.patch(f"{API}/subtasks/{first['id']}", json={"status": "todo"})
    assert resp.json()["actual_feel"] is None
    assert resp.json()["done_at"] is None

    resp = await auth_client.patch(f"{API}/tasks/{task['id']}", json={"status": "done"})
    assert resp.json()["done_at"] is not None


async def test_task_without_subtasks_progress(auth_client):
    task = await make_task(auth_client)
    assert task["progress"] == 0
    resp = await auth_client.patch(f"{API}/tasks/{task['id']}", json={"status": "done"})
    assert resp.json()["progress"] == 1


async def test_dependencies_validated(auth_client):
    task = await make_task(auth_client, subtasks=[{"title": "a"}, {"title": "b"}])
    a, b = task["subtasks"]
    c = await add_subtask(auth_client, task["id"], depends_on=[a["id"], a["id"]])
    assert c["depends_on"] == [a["id"]]
    assert c["position"] == 2

    url = f"{API}/subtasks/{a['id']}"
    assert (await auth_client.patch(url, json={"depends_on": [a["id"]]})).status_code == 400
    # a → c → a — цикл
    assert (await auth_client.patch(url, json={"depends_on": [c["id"]]})).status_code == 400
    assert (await auth_client.patch(url, json={"depends_on": [b["id"]]})).status_code == 200

    other = await make_task(auth_client, title="Другое", subtasks=[{"title": "x"}])
    resp = await auth_client.patch(url, json={"depends_on": [other["subtasks"][0]["id"]]})
    assert resp.status_code == 400

    # Удаление подзадачи убирает её из зависимостей остальных
    assert (await auth_client.delete(f"{API}/subtasks/{a['id']}")).status_code == 204
    task = await get_task(auth_client, task["id"])
    assert all(a["id"] not in s["depends_on"] for s in task["subtasks"])


async def test_reorder(auth_client):
    task = await make_task(auth_client, subtasks=[{"title": "a"}, {"title": "b"}, {"title": "c"}])
    ids = [s["id"] for s in task["subtasks"]]
    url = f"{API}/tasks/{task['id']}/subtasks/order"
    resp = await auth_client.put(url, json={"ids": [ids[2], ids[0], ids[1]]})
    assert [s["title"] for s in resp.json()["subtasks"]] == ["c", "a", "b"]
    assert (await auth_client.put(url, json={"ids": ids[:2]})).status_code == 400
    assert (await auth_client.put(url, json={"ids": [ids[0], *ids[:2]]})).status_code == 400


async def test_list_filters_and_deadline_order(auth_client):
    sem = await make_semester(auth_client)
    subj = await make_subject(auth_client, sem["id"])
    late = await make_task(auth_client, title="Поздно", deadline="2026-11-01T12:00:00Z")
    soon = await make_task(
        auth_client, title="Скоро", deadline="2026-10-08T12:00:00Z", subject_id=subj["id"]
    )
    await make_task(auth_client, title="Без срока")
    done = await make_task(auth_client, title="Готово", deadline="2026-10-07T12:00:00Z")
    await auth_client.patch(f"{API}/tasks/{done['id']}", json={"status": "done"})

    resp = await auth_client.get(f"{API}/tasks", params={"status": "active"})
    assert [t["title"] for t in resp.json()] == ["Скоро", "Поздно", "Без срока"]

    resp = await auth_client.get(
        f"{API}/tasks", params={"status": "active", "due_before": "2026-10-20T00:00:00Z"}
    )
    assert [t["id"] for t in resp.json()] == [soon["id"]]

    resp = await auth_client.get(f"{API}/tasks", params={"subject_id": subj["id"]})
    assert [t["id"] for t in resp.json()] == [soon["id"]]
    resp = await auth_client.get(f"{API}/tasks", params=[("status", "active"), ("status", "done")])
    assert len(resp.json()) == 4
    assert late["id"] in {t["id"] for t in resp.json()}


async def test_schedule_subtask_and_calendar_sync(auth_client):
    cats = await categories(auth_client)
    task = await make_task(auth_client, subtasks=[{"title": "Глава 1", "estimate_min": 90}])
    sub = task["subtasks"][0]
    url = f"{API}/subtasks/{sub['id']}/schedule"
    resp = await auth_client.post(url, json={"start": "2026-10-07T18:00:00+03:00"})
    assert resp.status_code == 200, resp.text
    [block] = resp.json()["events"]
    assert block["start"] == "2026-10-07T15:00:00Z"
    assert block["end"] == "2026-10-07T16:30:00Z"
    assert block["is_pinned"]

    cal = await auth_client.get(
        f"{API}/calendar", params={"from": "2026-10-07T00:00:00Z", "to": "2026-10-08T00:00:00Z"}
    )
    [event] = cal.json()["events"]
    assert event["kind"] == "subtask"
    assert not event["is_fixed"]
    assert event["source_type"] == "subtask"
    assert event["source_id"] == sub["id"]
    assert event["title"] == "Глава 1"
    assert event["color"] == cats["study"]["color"]

    # Перенос — тот же блок
    resp = await auth_client.post(url, json={"start": "2026-10-08T10:00:00+03:00"})
    assert [e["id"] for e in resp.json()["events"]] == [event["id"]]

    # «Сделано» в календаре закрывает подзадачу, и наоборот
    await auth_client.patch(f"{API}/events/{event['id']}", json={"status": "done"})
    assert (await auth_client.get(f"{API}/subtasks/{sub['id']}")).json()["status"] == "done"
    await auth_client.patch(f"{API}/subtasks/{sub['id']}", json={"status": "todo"})
    ev = (await auth_client.get(f"{API}/events/{event['id']}")).json()
    assert ev["status"] == "planned"

    # Переименование подзадачи переименовывает блок
    await auth_client.patch(f"{API}/subtasks/{sub['id']}", json={"title": "Глава первая"})
    assert (await auth_client.get(f"{API}/events/{event['id']}")).json()["title"] == "Глава первая"

    resp = await auth_client.delete(url)
    assert resp.json()["events"] == []


async def test_dragging_flexible_block_pins_it(auth_client):
    task = await make_task(auth_client, subtasks=[{"title": "x"}])
    sub = task["subtasks"][0]
    resp = await auth_client.post(
        f"{API}/subtasks/{sub['id']}/schedule", json={"start": "2026-10-07T10:00:00Z"}
    )
    event_id = resp.json()["events"][0]["id"]
    await auth_client.patch(f"{API}/events/{event_id}", json={"is_pinned": False})
    resp = await auth_client.patch(
        f"{API}/events/{event_id}",
        json={"start": "2026-10-07T12:00:00Z", "end": "2026-10-07T12:30:00Z"},
    )
    assert resp.json()["is_pinned"] is True


async def test_delete_task_removes_planned_blocks(auth_client):
    task = await make_task(auth_client, subtasks=[{"title": "x"}])
    sub = task["subtasks"][0]
    resp = await auth_client.post(
        f"{API}/subtasks/{sub['id']}/schedule", json={"start": "2026-10-07T10:00:00Z"}
    )
    event_id = resp.json()["events"][0]["id"]
    assert (await auth_client.delete(f"{API}/tasks/{task['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/tasks/{task['id']}")).status_code == 404
    assert (await auth_client.get(f"{API}/subtasks/{sub['id']}")).status_code == 404
    assert (await auth_client.get(f"{API}/events/{event_id}")).status_code == 404


async def test_validation(auth_client):
    for bad in (
        {"title": ""},
        {"title": "x", "task_type": "nope"},
        {"title": "x", "deadline": "2026-10-15T23:59:00"},  # без TZ
        {"title": "x", "subtasks": [{"title": "a", "estimate_min": 1}]},
        {"title": "x", "time_window": [{"weekdays": [], "start": "10:00", "end": "11:00"}]},
    ):
        assert (await auth_client.post(f"{API}/tasks", json=bad)).status_code == 422, bad
    task = await make_task(auth_client)
    resp = await auth_client.patch(f"{API}/tasks/{task['id']}", json={"title": None})
    assert resp.status_code == 400
    resp = await auth_client.patch(
        f"{API}/tasks/{task['id']}", json={"category_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert resp.status_code == 404


async def test_time_window_roundtrip(auth_client):
    window = [{"weekdays": [4], "start": "10:00", "end": "17:00"}]
    task = await make_task(auth_client, time_window=window)
    assert task["time_window"] == window
    resp = await auth_client.patch(f"{API}/tasks/{task['id']}", json={"time_window": None})
    assert resp.json()["time_window"] is None


async def test_deleted_category_unlinked(auth_client):
    resp = await auth_client.post(
        f"{API}/categories", json={"name": "Здоровье", "color": "#ef4444", "icon": "stethoscope"}
    )
    cat = resp.json()
    task = await make_task(auth_client, category_id=cat["id"])
    await auth_client.delete(f"{API}/categories/{cat['id']}")
    assert (await get_task(auth_client, task["id"]))["category_id"] is None


async def test_tasks_are_per_user(auth_client, session):
    task = await make_task(auth_client, subtasks=[{"title": "x"}])
    async with other_client(auth_client, session) as other:
        assert (await other.get(f"{API}/tasks/{task['id']}")).status_code == 404
        assert (await other.get(f"{API}/tasks")).json() == []
        sub_id = task["subtasks"][0]["id"]
        resp = await other.patch(f"{API}/subtasks/{sub_id}", json={"title": "y"})
        assert resp.status_code == 404
