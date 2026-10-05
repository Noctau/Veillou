from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.settings import UserSettings, deep_merge

URL = "/api/v1/me/settings"


# ---------- deep_merge ----------


def test_deep_merge_nested():
    base = {"a": {"b": 1, "c": 2}, "d": 3}
    assert deep_merge(base, {"a": {"b": 10}}) == {"a": {"b": 10, "c": 2}, "d": 3}
    assert base == {"a": {"b": 1, "c": 2}, "d": 3}  # исходник не мутирует


def test_deep_merge_lists_replaced():
    assert deep_merge({"x": [1, 2]}, {"x": [3]}) == {"x": [3]}


def test_deep_merge_none_removes_and_prunes_empty():
    assert deep_merge({"a": {"b": 1}, "c": 1}, {"a": {"b": None}}) == {"c": 1}
    assert deep_merge({"a": 1}, {"a": None, "z": None}) == {}
    assert deep_merge({}, {"a": {"b": None}}) == {}


# ---------- API ----------


async def test_settings_require_auth(client: AsyncClient):
    assert (await client.get(URL)).status_code == 401
    assert (await client.patch(URL, json={})).status_code == 401


async def test_defaults(auth_client: AsyncClient):
    resp = await auth_client.get(URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data == UserSettings().model_dump(mode="json")
    assert data["sleep"] == {"start": "23:30", "end": "07:30"}
    assert data["schedule"]["morning_digest"] == "08:00"
    assert data["reminders"]["before_class"]["minutes_before"] == 15
    assert data["reminders"]["subtask_start"]["enabled"] is False


async def test_patch_deep_merges(auth_client: AsyncClient, session: AsyncSession):
    resp = await auth_client.patch(
        URL,
        json={
            "work_hours": {"weekdays": {"end": "19:00"}},
            "reminders": {"before_class": {"minutes_before": 20, "channels": ["telegram"]}},
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["work_hours"]["weekdays"] == {"start": "09:00", "end": "19:00"}
    assert data["work_hours"]["weekends"] == {"start": "11:00", "end": "19:00"}
    assert data["reminders"]["before_class"] == {
        "enabled": True,
        "channels": ["telegram"],
        "minutes_before": 20,
    }
    assert data["reminders"]["deadlines"]["enabled"] is True

    # Второй PATCH не затирает первый
    resp = await auth_client.patch(URL, json={"study_limit_min_per_day": 300})
    data = resp.json()
    assert data["study_limit_min_per_day"] == 300
    assert data["work_hours"]["weekdays"]["end"] == "19:00"

    # В БД — только переопределения
    stored = await session.scalar(select(User.settings))
    assert stored == {
        "work_hours": {"weekdays": {"end": "19:00"}},
        "reminders": {"before_class": {"minutes_before": 20, "channels": ["telegram"]}},
        "study_limit_min_per_day": 300,
    }
    assert (await auth_client.get(URL)).json() == data


async def test_null_resets_to_default(auth_client: AsyncClient):
    await auth_client.patch(URL, json={"lunch": {"start": "12:00", "end": "12:30"}})
    resp = await auth_client.patch(URL, json={"lunch": None})
    assert resp.json()["lunch"] == {"start": "13:00", "end": "14:00"}


async def test_overnight_ranges_allowed_for_sleep(auth_client: AsyncClient):
    resp = await auth_client.patch(URL, json={"sleep": {"start": "00:30", "end": "08:30"}})
    assert resp.status_code == 200
    resp = await auth_client.patch(URL, json={"quiet_hours": {"start": "23:00", "end": "07:00"}})
    assert resp.status_code == 200


async def test_invalid_merged_result_rejected_and_not_saved(auth_client: AsyncClient):
    # Только конец обеда раньше дефолтного начала 13:00 -> итог невалиден
    resp = await auth_client.patch(URL, json={"lunch": {"end": "12:00"}})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_settings"
    assert (await auth_client.get(URL)).json()["lunch"]["end"] == "14:00"


async def test_patch_validation(auth_client: AsyncClient):
    for body in [
        {"unknown_field": 1},
        {"work_hours": {"weekdays": {"bogus": "10:00"}}},
        {"study_limit_min_per_day": 5},
        {"reminders": {"deadlines": {"channels": ["sms"]}}},
        {"sleep": {"start": "25:00"}},
        {"schedule": {"weekly_review_weekday": 8}},
    ]:
        resp = await auth_client.patch(URL, json=body)
        assert resp.status_code == 422, body


async def test_settings_are_per_user(auth_client: AsyncClient, client: AsyncClient, session):
    from app.services.users import create_user

    from .conftest import PASSWORD

    await auth_client.patch(URL, json={"travel_buffer_min": 30})
    await create_user(session, email="other@example.com", password=PASSWORD)
    async with AsyncClient(transport=client._transport, base_url="http://test") as other:
        await other.post(
            "/api/v1/auth/login", json={"email": "other@example.com", "password": PASSWORD}
        )
        assert (await other.get(URL)).json()["travel_buffer_min"] == 60
