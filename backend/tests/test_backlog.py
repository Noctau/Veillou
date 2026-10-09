from .test_catalog import action_types, categories
from .test_schedule_api import API, other_client


async def make_item(client, **over) -> dict:
    resp = await client.post(f"{API}/backlog", json={"title": "Записаться к стоматологу", **over})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def listing(client, status: str = "active") -> list[str]:
    resp = await client.get(f"{API}/backlog", params={"status": status})
    assert resp.status_code == 200, resp.text
    return [i["title"] for i in resp.json()]


async def test_create_guesses_action_type_and_category(auth_client):
    types = await action_types(auth_client)
    cats = await categories(auth_client)
    item = await make_item(auth_client)
    assert item["action_type_id"] == types["institutions"]["id"]
    assert item["category_id"] == cats["home"]["id"]
    assert item["status"] == "active"
    assert item["conditions"] == []

    unknown = await make_item(auth_client, title="Что-то своё")
    assert unknown["action_type_id"] is None
    assert unknown["category_id"] is None

    personal = cats["personal"]["id"]
    explicit = await make_item(auth_client, title="Купить подарок", category_id=personal)
    assert explicit["category_id"] == personal
    assert explicit["action_type_id"] == types["outside"]["id"]


async def test_fields_and_validation(auth_client):
    item = await make_item(
        auth_client,
        estimate_min=60,
        desired_by="2026-10-31",
        conditions=["weekday_daytime", "institution_hours", "weekday_daytime"],
        time_window=[{"weekdays": [1, 2, 3, 4, 5], "start": "08:00", "end": "20:00"}],
    )
    assert item["conditions"] == ["weekday_daytime", "institution_hours"]
    assert item["desired_by"] == "2026-10-31"
    for bad in ({"conditions": ["in_city"]}, {"estimate_min": 0}, {"title": " "}):
        resp = await auth_client.post(f"{API}/backlog", json={"title": "x", **bad})
        assert resp.status_code == 422, bad
    resp = await auth_client.patch(f"{API}/backlog/{item['id']}", json={"conditions": None})
    assert resp.status_code == 400


async def test_order_desired_first_then_oldest(auth_client):
    await make_item(auth_client, title="Старое")
    await make_item(auth_client, title="Новое")
    await make_item(auth_client, title="К концу месяца", desired_by="2026-10-31")
    await make_item(auth_client, title="К пятнице", desired_by="2026-10-09")
    assert await listing(auth_client) == ["К пятнице", "К концу месяца", "Старое", "Новое"]


async def test_done_archive_and_restore(auth_client):
    item = await make_item(auth_client)
    url = f"{API}/backlog/{item['id']}"
    resp = await auth_client.patch(url, json={"status": "archived"})
    assert resp.json()["archived_at"] is not None
    assert await listing(auth_client) == []
    assert await listing(auth_client, "archived") == ["Записаться к стоматологу"]

    resp = await auth_client.patch(url, json={"status": "active"})
    assert resp.json()["archived_at"] is None
    assert resp.json()["done_at"] is None
    resp = await auth_client.patch(url, json={"status": "done"})
    assert resp.json()["done_at"] is not None
    assert await listing(auth_client, "done") == ["Записаться к стоматологу"]

    assert (await auth_client.delete(url)).status_code == 204
    assert await listing(auth_client, "done") == []


async def test_backlog_is_per_user(auth_client, session):
    item = await make_item(auth_client)
    async with other_client(auth_client, session) as other:
        assert await listing(other) == []
        resp = await other.patch(f"{API}/backlog/{item['id']}", json={"title": "x"})
        assert resp.status_code == 404
