from datetime import UTC, datetime

import pytest

from .test_catalog import action_types
from .test_schedule_api import API, make_area, make_period
from .test_tasks import make_task_type


@pytest.fixture
def frozen(monkeypatch):
    # Вторник 06.10.2026 15:00 МСК
    monkeypatch.setattr(
        "app.services.quickadd.now_utc", lambda: datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    )


async def test_parse_with_user_subjects(auth_client, frozen, session):
    types = await action_types(auth_client)
    # Словарь — названия и синонимы справочника (M21.1)
    essay = await make_task_type(auth_client)
    sem = await make_period(auth_client)
    subj = await make_area(auth_client, sem["id"], synonyms=["климатуха"])
    resp = await auth_client.post(
        f"{API}/quick-add/parse", json={"text": "реферат по климатухе до 15 окт"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "title": "Реферат",
        "date": "2026-10-15",
        "time": None,
        "end_time": None,
        "duration_min": None,
        "deadline": "2026-10-15T20:59:00Z",
        "is_deadline": True,
        "area_id": subj["id"],
        "task_type_id": essay["id"],
        # Похоже на задачу — тип действия по умолчанию
        "action_type_id": types["study"]["id"],
        "event_type_id": None,
        "kind_hint": "task",
        # Есть и срок, и предмет — ИИ не нужен
        "needs_ai": False,
    }


async def test_old_period_areas_do_not_clash(auth_client, frozen):
    old = await make_period(
        auth_client,
        name="Весна 2026",
        start_date="2026-02-01",
        end_date="2026-06-30",
        pauses=[{"from": "2026-06-01", "to": "2026-06-30", "title": "Сессия"}],
    )
    await make_area(auth_client, old["id"])
    sem = await make_period(auth_client)
    current = await make_area(auth_client, sem["id"])
    resp = await auth_client.post(f"{API}/quick-add/parse", json={"text": "дз клим"})
    assert resp.json()["area_id"] == current["id"]


async def test_event_time(auth_client, frozen):
    resp = await auth_client.post(f"{API}/quick-add/parse", json={"text": "завтра в 14 врач"})
    body = resp.json()
    assert (body["kind_hint"], body["date"], body["time"]) == ("event", "2026-10-07", "14:00")


async def test_requires_auth(client):
    resp = await client.post(f"{API}/quick-add/parse", json={"text": "x"})
    assert resp.status_code == 401


# ---------- словарь пользователя (M21.1) ----------


async def test_schoolkid_one_line_homework_due_next_lesson(auth_client, user):
    """Сценарий 4: «алгебра №245» — ДЗ по сфере со сроком к следующему уроку."""
    from datetime import datetime as dt

    from app.core.db import session_factory
    from app.models import User
    from app.services.quickadd import create_from_text

    from .test_event_tasks import _ok, lessons, tutor

    t = await tutor(auth_client)
    await _ok(await auth_client.patch(f"{API}/areas/{t['area']['id']}", json={"name": "Алгебра"}))
    hw = await _ok(
        await auth_client.post(
            f"{API}/task-types",
            json={
                "name": "ДЗ",
                "synonyms": ["дз", "№"],
                "deadline_rule": {"kind": "next_occurrence"},
            },
        )
    )
    parsed = (
        await auth_client.post(f"{API}/quick-add/parse", json={"text": "алгебра №245"})
    ).json()
    assert (parsed["area_id"], parsed["task_type_id"]) == (t["area"]["id"], hw["id"])
    assert parsed["kind_hint"] == "task"
    async with session_factory() as db:
        u = await db.get(User, user.id)
        assert u is not None
        created = await create_from_text(db, u, "алгебра №245")
    task = await _ok(await auth_client.get(f"{API}/tasks/{created.id}"))
    assert task["title"] == "№245"
    assert dt.fromisoformat(task["deadline"]) == (await lessons(user))[0].start


async def test_office_call_creates_event_of_type(auth_client, frozen):
    """Сценарий 5/6: «созвон с клиентом в пт 15:00» — событие типа «Встреча», без ИИ."""
    meeting = (
        await auth_client.post(
            f"{API}/event-types", json={"name": "Встреча", "synonyms": ["созвон", "стендап"]}
        )
    ).json()
    resp = await auth_client.post(
        f"{API}/quick-add/parse", json={"text": "созвон с клиентом в пт 15:00"}
    )
    data = resp.json()
    assert (data["kind_hint"], data["event_type_id"]) == ("event", meeting["id"])
    assert data["time"] == "15:00"
    assert data["needs_ai"] is False


async def test_task_without_area_is_sure_when_user_has_no_areas(auth_client, frozen):
    """Нулевая настройка: задача со сроком без сферы — ИИ не нужен."""
    resp = await auth_client.post(f"{API}/quick-add/parse", json={"text": "сдать отчёт к пятнице"})
    data = resp.json()
    assert (data["kind_hint"], data["area_id"], data["needs_ai"]) == ("task", None, False)
