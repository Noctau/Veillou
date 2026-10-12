import asyncio

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActionType, Category
from app.services.catalog import ensure_defaults

from .test_schedule_api import API, other_client


async def action_types(client: AsyncClient) -> dict[str, dict]:
    resp = await client.get(f"{API}/action-types")
    assert resp.status_code == 200, resp.text
    return {a["key"] or a["name"]: a for a in resp.json()}


async def categories(client: AsyncClient) -> dict[str | None, dict]:
    resp = await client.get(f"{API}/categories")
    assert resp.status_code == 200, resp.text
    return {c["key"] or c["name"]: c for c in resp.json()}


async def test_defaults_seeded_for_new_user(auth_client):
    cats = await categories(auth_client)
    assert [c["name"] for c in cats.values()] == ["Учёба", "Работа", "Быт", "Личное"]
    types = await action_types(auth_client)
    assert list(types) == ["people", "institutions", "study", "outside", "home", "personal"]
    people = types["people"]
    assert people["name"] == "Связь с людьми"
    assert people["windows"] == [{"weekdays": [1, 2, 3, 4, 5], "start": "09:00", "end": "19:00"}]
    assert people["default_category_id"] == cats["work"]["id"]
    # Нейтральный сид (M21.1): слова без студенческих, тип по умолчанию — «Сосредоточенная работа»
    assert "позвонить" in people["synonyms"]
    assert not {"научрук", "деканат"} & {w for t in types.values() for w in t["synonyms"]}
    assert types["study"]["name"] == "Сосредоточенная работа"
    assert types["study"]["synonyms"] == []
    # Сосредоточенная работа — до 01:00 следующего дня
    assert types["study"]["windows"] == [
        {"weekdays": [1, 2, 3, 4, 5, 6, 7], "start": "07:00", "end": "01:00"}
    ]
    assert [k for k, t in types.items() if t["prefer_morning"]] == ["people"]
    # Тип по умолчанию — «Сосредоточенная работа»
    settings = (await auth_client.get(f"{API}/me/settings")).json()
    assert settings["default_action_type_id"] == types["study"]["id"]


async def test_ensure_defaults_idempotent_and_backfills(session: AsyncSession, user):
    # Пользователь, созданный до M4.1: справочников нет
    await session.execute(ActionType.__table__.delete())
    await session.execute(Category.__table__.delete())
    await session.commit()
    results = await asyncio.gather(*(_ensure_in_new_session(user.id) for _ in range(3)))
    assert any(results)
    assert not await ensure_defaults(session, user.id)
    count = await session.scalar(select(func.count()).select_from(ActionType))
    assert count == 6
    assert await session.scalar(select(func.count()).select_from(Category)) == 4


async def _ensure_in_new_session(user_id) -> bool:
    from app.core.db import session_factory

    async with session_factory() as db:
        added = await ensure_defaults(db, user_id)
        await db.commit()
        return added


async def test_update_and_reset_action_type_windows(auth_client):
    people = (await action_types(auth_client))["people"]
    url = f"{API}/action-types/{people['id']}"
    body = {
        "windows": [
            {"weekdays": [4, 2, 2], "start": "10:00", "end": "17:00"},
            {"weekdays": [6], "start": "22:00", "end": "02:00"},
        ]
    }
    resp = await auth_client.patch(url, json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["windows"][0] == {"weekdays": [2, 4], "start": "10:00", "end": "17:00"}

    for bad in (
        {"windows": []},
        {"windows": [{"weekdays": [], "start": "10:00", "end": "11:00"}]},
        {"windows": [{"weekdays": [8], "start": "10:00", "end": "11:00"}]},
        {"windows": [{"weekdays": [1], "start": "10:00", "end": "10:00"}]},
        {"key": "study"},
    ):
        assert (await auth_client.patch(url, json=bad)).status_code == 422, bad
    assert (await auth_client.patch(url, json={"windows": None})).status_code == 400

    resp = await auth_client.post(f"{url}/reset")
    assert resp.json()["windows"] == people["windows"]


async def test_categories_crud(auth_client):
    resp = await auth_client.post(
        f"{API}/categories", json={"name": "Здоровье", "color": "#ef4444", "icon": "stethoscope"}
    )
    assert resp.status_code == 201, resp.text
    health = resp.json()
    assert health["key"] is None
    assert health["position"] == 4

    resp = await auth_client.patch(f"{API}/categories/{health['id']}", json={"name": "Врачи"})
    assert resp.json()["name"] == "Врачи"
    assert (
        await auth_client.post(
            f"{API}/categories", json={"name": "X", "color": "#ef4444", "icon": "nope"}
        )
    ).status_code == 422

    study = (await categories(auth_client))["study"]
    resp = await auth_client.delete(f"{API}/categories/{study['id']}")
    assert resp.status_code == 409
    resp = await auth_client.patch(f"{API}/categories/{study['id']}", json={"name": "Универ"})
    assert resp.json()["name"] == "Универ"

    assert (await auth_client.delete(f"{API}/categories/{health['id']}")).status_code == 204
    assert "Врачи" not in await categories(auth_client)


async def test_catalog_is_per_user(auth_client, session):
    people = (await action_types(auth_client))["people"]
    async with other_client(auth_client, session) as other:
        theirs = await action_types(other)
        assert theirs["people"]["id"] != people["id"]
        resp = await other.patch(f"{API}/action-types/{people['id']}", json={"name": "X"})
        assert resp.status_code == 404


# ---------- свои типы действий (M15.2) ----------


WINDOWS = [{"weekdays": [1, 2, 3, 4, 5], "start": "15:00", "end": "20:00"}]


async def test_create_own_action_type(auth_client):
    resp = await auth_client.post(
        f"{API}/action-types", json={"name": "Уроки", "windows": WINDOWS, "prefer_morning": True}
    )
    assert resp.status_code == 201, resp.text
    lessons = resp.json()
    assert lessons["key"] is None
    assert lessons["prefer_morning"]
    assert lessons["position"] == 6
    assert list(await action_types(auth_client))[-1] == "Уроки"
    # Свой тип «по умолчанию» не сбрасывается
    resp = await auth_client.post(f"{API}/action-types/{lessons['id']}/reset")
    assert resp.status_code == 400
    resp = await auth_client.patch(
        f"{API}/action-types/{lessons['id']}", json={"prefer_morning": False}
    )
    assert resp.json()["prefer_morning"] is False
    bad = {"name": "X", "windows": []}
    assert (await auth_client.post(f"{API}/action-types", json=bad)).status_code == 422


async def test_delete_action_type_reassigns_to_default(auth_client):
    from .test_tasks import add_subtask, get_task, make_task

    types = await action_types(auth_client)
    people, study = types["people"]["id"], types["study"]["id"]
    task = await make_task(auth_client, action_type_id=people)
    sub = await add_subtask(auth_client, task["id"], action_type_id=people)
    item = (
        await auth_client.post(
            f"{API}/backlog",
            json={"title": "Позвонить", "action_type_id": people, "hours_action_type_id": people},
        )
    ).json()
    budget = (
        await auth_client.post(
            f"{API}/load-budgets",
            json={"name": "Люди", "minutes_per_day": 60, "action_type_ids": [people, study]},
        )
    ).json()

    assert (await auth_client.delete(f"{API}/action-types/{people}")).status_code == 204
    assert "people" not in await action_types(auth_client)
    detail = await get_task(auth_client, task["id"])
    assert detail["action_type_id"] == study
    assert detail["subtasks"][0]["id"] == sub["id"]
    assert detail["subtasks"][0]["action_type_id"] == study
    item = next(
        i for i in (await auth_client.get(f"{API}/backlog")).json() if i["id"] == item["id"]
    )
    assert (item["action_type_id"], item["hours_action_type_id"]) == (study, None)
    budgets = (await auth_client.get(f"{API}/load-budgets")).json()
    assert budgets[0]["id"] == budget["id"]
    assert budgets[0]["action_type_ids"] == [study]


async def test_delete_default_action_type_clears_default(auth_client):
    from .test_tasks import make_task

    study = (await action_types(auth_client))["study"]["id"]
    task = await make_task(auth_client)
    assert task["action_type_id"] == study
    assert (await auth_client.delete(f"{API}/action-types/{study}")).status_code == 204
    settings = (await auth_client.get(f"{API}/me/settings")).json()
    assert settings["default_action_type_id"] is None
    # Без типа по умолчанию задачи создаются без типа действия, всё работает
    task = await make_task(auth_client, title="Без типа")
    assert task["action_type_id"] is None
    # Удалённое не засевается заново
    assert "study" not in await action_types(auth_client)


async def test_default_action_type_setting(auth_client, session):
    types = await action_types(auth_client)
    home = types["home"]["id"]
    resp = await auth_client.patch(f"{API}/me/settings", json={"default_action_type_id": home})
    assert resp.status_code == 200, resp.text
    from .test_tasks import make_task

    assert (await make_task(auth_client))["action_type_id"] == home
    resp = await auth_client.patch(
        f"{API}/me/settings",
        json={"default_action_type_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 400
    async with other_client(auth_client, session) as other:
        resp = await other.patch(f"{API}/me/settings", json={"default_action_type_id": home})
        assert resp.status_code == 400
