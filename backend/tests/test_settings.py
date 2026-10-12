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
    # Справочник засеян при создании пользователя: тип по умолчанию — «Самостоятельная учёба»
    assert data["default_action_type_id"] is not None
    assert {**data, "default_action_type_id": None} == UserSettings().model_dump(mode="json")
    # Сон, обед и рабочие часы — в режимах дня (M18), сводка и разбор — от них
    for key in ("sleep", "lunch", "work_hours"):
        assert key not in data
    assert data["schedule"]["morning_digest_after_wake_min"] == 30
    assert data["schedule"]["evening_review_before_sleep_min"] == 120
    # Дорога и «перед парой» — флаги типов занятости (M17), не настройки
    assert "travel_buffer_min" not in data
    assert "before_class" not in data["reminders"]
    assert data["reminders"]["subtask_start"]["enabled"] is False


async def test_patch_deep_merges(auth_client: AsyncClient, session: AsyncSession):
    resp = await auth_client.patch(
        URL,
        json={
            "schedule": {"morning_digest_after_wake_min": 0},
            "reminders": {"evening_review": {"channels": ["telegram"]}},
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["schedule"]["morning_digest_after_wake_min"] == 0
    assert data["schedule"]["evening_review_before_sleep_min"] == 120
    assert data["reminders"]["evening_review"] == {"enabled": True, "channels": ["telegram"]}
    assert data["reminders"]["deadlines"]["enabled"] is True

    # Второй PATCH не затирает первый
    resp = await auth_client.patch(URL, json={"deadline_buffer_days": 2})
    data = resp.json()
    assert data["deadline_buffer_days"] == 2
    assert data["schedule"]["morning_digest_after_wake_min"] == 0

    # В БД — только переопределения
    stored = dict(await session.scalar(select(User.settings)))
    assert stored.pop("default_action_type_id")
    assert stored == {
        "schedule": {"morning_digest_after_wake_min": 0},
        "reminders": {"evening_review": {"channels": ["telegram"]}},
        "deadline_buffer_days": 2,
    }
    assert (await auth_client.get(URL)).json() == data


async def test_null_resets_to_default(auth_client: AsyncClient):
    await auth_client.patch(URL, json={"quiet_hours": {"start": "21:00", "end": "07:00"}})
    resp = await auth_client.patch(URL, json={"quiet_hours": None})
    assert resp.json()["quiet_hours"] == {"start": "22:30", "end": "08:00"}


async def test_overnight_ranges_allowed_for_quiet_hours(auth_client: AsyncClient):
    resp = await auth_client.patch(URL, json={"quiet_hours": {"start": "23:00", "end": "07:00"}})
    assert resp.status_code == 200


async def test_old_day_settings_rejected(auth_client: AsyncClient):
    for body in [
        {"sleep": {"start": "00:30", "end": "08:30"}},
        {"work_hours": {"weekdays": {"end": "19:00"}}},
        {"schedule": {"morning_digest": "08:00"}},
    ]:
        resp = await auth_client.patch(URL, json=body)
        assert resp.status_code == 422, body


async def test_patch_validation(auth_client: AsyncClient):
    for body in [
        {"unknown_field": 1},
        {"quiet_hours": {"bogus": "10:00"}},
        {"deadline_buffer_days": 30},
        {"default_action_type_id": "nope"},
        {"reminders": {"deadlines": {"channels": ["sms"]}}},
        {"quiet_hours": {"start": "25:00"}},
        {"schedule": {"morning_digest_after_wake_min": 2000}},
        {"schedule": {"weekly_review_weekday": 8}},
    ]:
        resp = await auth_client.patch(URL, json=body)
        assert resp.status_code == 422, body


async def test_settings_are_per_user(auth_client: AsyncClient, client: AsyncClient, session):
    from app.services.users import create_user

    from .conftest import PASSWORD

    await auth_client.patch(URL, json={"deadline_buffer_days": 3})
    await create_user(session, email="other@example.com", password=PASSWORD)
    async with AsyncClient(transport=client._transport, base_url="http://test") as other:
        await other.post(
            "/api/v1/auth/login", json={"email": "other@example.com", "password": PASSWORD}
        )
        assert (await other.get(URL)).json()["deadline_buffer_days"] == 1


async def test_onboarding_flag(auth_client: AsyncClient):
    assert (await auth_client.get(URL)).json()["onboarding_done"] is False
    resp = await auth_client.patch(URL, json={"onboarding_done": True})
    assert resp.status_code == 200, resp.text
    assert (await auth_client.get(URL)).json()["onboarding_done"] is True
