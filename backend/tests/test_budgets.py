"""Лимиты нагрузки (M15.3): CRUD, состав, разовые лимиты дня."""

from datetime import date, timedelta

from .test_catalog import action_types
from .test_schedule_api import API, other_client

URL = f"{API}/load-budgets"


async def make_budget(client, **over) -> dict:
    resp = await client.post(URL, json={"name": "Учёба", "minutes_per_day": 300, **over})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_empty_by_default(auth_client):
    """Без лимитов — без ограничений: у нового пользователя их нет."""
    assert (await auth_client.get(URL)).json() == []


async def test_crud_and_members(auth_client):
    types = await action_types(auth_client)
    study, people = types["study"]["id"], types["people"]["id"]
    budget = await make_budget(auth_client, action_type_ids=[study, study])
    assert budget["action_type_ids"] == [study]
    assert budget["position"] == 0
    assert budget["overrides"] == []
    second = await make_budget(auth_client, name="Связь", minutes_per_day=60)
    assert second["position"] == 1

    url = f"{URL}/{budget['id']}"
    resp = await auth_client.patch(url, json={"action_type_ids": [people, study]})
    assert set(resp.json()["action_type_ids"]) == {study, people}
    resp = await auth_client.patch(url, json={"action_type_ids": [people], "minutes_per_day": 240})
    assert (resp.json()["action_type_ids"], resp.json()["minutes_per_day"]) == ([people], 240)
    assert (await auth_client.patch(url, json={"name": None})).status_code == 400
    for bad in ({"minutes_per_day": 0}, {"minutes_per_day": 2000}, {"name": ""}):
        assert (await auth_client.patch(url, json=bad)).status_code == 422, bad
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await auth_client.patch(url, json={"action_type_ids": [missing]})).status_code == 404

    assert (await auth_client.delete(url)).status_code == 204
    assert [b["name"] for b in (await auth_client.get(URL)).json()] == ["Связь"]
    assert (await auth_client.patch(url, json={"name": "X"})).status_code == 404


async def test_overrides(auth_client):
    budget = await make_budget(auth_client)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    url = f"{URL}/{budget['id']}/overrides/{tomorrow}"
    resp = await auth_client.put(url, json={"minutes": 480})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"budget_id": budget["id"], "date": tomorrow, "minutes": 480}
    # Повторный PUT — обновление, а не вторая строка
    await auth_client.put(url, json={"minutes": 0})
    (read,) = (await auth_client.get(URL)).json()
    assert read["overrides"] == [{"budget_id": budget["id"], "date": tomorrow, "minutes": 0}]
    # Прошедшие дни в списке не показываем
    past = (date.today() - timedelta(days=3)).isoformat()
    await auth_client.put(f"{URL}/{budget['id']}/overrides/{past}", json={"minutes": 60})
    assert len((await auth_client.get(URL)).json()[0]["overrides"]) == 1
    assert (await auth_client.put(url, json={"minutes": -1})).status_code == 422

    assert (await auth_client.delete(url)).status_code == 204
    assert (await auth_client.get(URL)).json()[0]["overrides"] == []


async def test_per_user(auth_client, session):
    budget = await make_budget(auth_client)
    async with other_client(auth_client, session) as other:
        assert (await other.get(URL)).json() == []
        assert (await other.patch(f"{URL}/{budget['id']}", json={"name": "X"})).status_code == 404
        day = date.today().isoformat()
        resp = await other.put(f"{URL}/{budget['id']}/overrides/{day}", json={"minutes": 60})
        assert resp.status_code == 404
        # Чужой тип действия в состав не добавить
        theirs = (await action_types(other))["study"]["id"]
        resp = await auth_client.patch(f"{URL}/{budget['id']}", json={"action_type_ids": [theirs]})
        assert resp.status_code == 404
