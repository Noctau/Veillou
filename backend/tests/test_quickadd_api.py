import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from app.models import TaskType

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
    essay = await make_task_type(auth_client)
    # Словарь быстрого ввода Part 1 отдаёт ключи сида: у мигрированных типов есть key
    await session.execute(
        update(TaskType).where(TaskType.id == uuid.UUID(essay["id"])).values(key="essay")
    )
    await session.commit()
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
