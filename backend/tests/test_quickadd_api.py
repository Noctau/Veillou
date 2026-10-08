from datetime import UTC, datetime

import pytest

from .test_schedule_api import API, make_semester, make_subject


@pytest.fixture
def frozen(monkeypatch):
    # Вторник 06.10.2026 15:00 МСК
    monkeypatch.setattr(
        "app.services.quickadd.now_utc", lambda: datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    )


async def test_parse_with_user_subjects(auth_client, frozen):
    sem = await make_semester(auth_client)
    subj = await make_subject(auth_client, sem["id"], synonyms=["климатуха"])
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
        "subject_id": subj["id"],
        "task_type": "essay",
        "action_type": "study",
        "kind_hint": "task",
        # Есть и срок, и предмет — ИИ не нужен
        "needs_ai": False,
    }


async def test_old_semester_subjects_do_not_clash(auth_client, frozen):
    old = await make_semester(
        auth_client,
        name="Весна 2026",
        start_date="2026-02-01",
        classes_end="2026-05-31",
        session_start="2026-06-01",
        session_end="2026-06-30",
    )
    await make_subject(auth_client, old["id"])
    sem = await make_semester(auth_client)
    current = await make_subject(auth_client, sem["id"])
    resp = await auth_client.post(f"{API}/quick-add/parse", json={"text": "дз клим"})
    assert resp.json()["subject_id"] == current["id"]


async def test_event_time(auth_client, frozen):
    resp = await auth_client.post(f"{API}/quick-add/parse", json={"text": "завтра в 14 врач"})
    body = resp.json()
    assert (body["kind_hint"], body["date"], body["time"]) == ("event", "2026-10-07", "14:00")


async def test_requires_auth(client):
    resp = await client.post(f"{API}/quick-add/parse", json={"text": "x"})
    assert resp.status_code == 401
