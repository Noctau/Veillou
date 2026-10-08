"""M12: экзамены, билеты, план подготовки (сценарий 8)."""

from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.core.db import session_factory
from app.core.time import get_tz, local_date, now_utc, wall_to_utc
from app.domain.enums import EventKind, EventStatus, ExamSessionKind, ExamSessionStatus
from app.models import Event, ExamSession, User
from app.services.exams import ExamService, sync_all
from app.services.replan import ReplanService

from .test_ai import make_subject
from .test_schedule_api import other_client

API = "/api/v1"
TZ = get_tz("Europe/Moscow")
QUESTIONS = (
    "Вопросы к экзамену:\n1. Циклоны\n2. Антициклоны\n3. Фронты\n4. Туманы\n5. Грозы\n6. Ветер"
)


@pytest.fixture(autouse=True)
def _fast_solver(monkeypatch):
    monkeypatch.setattr(ReplanService, "time_limit_s", 0.4)


def in_days(n: int, h: int = 10) -> datetime:
    return wall_to_utc(local_date(now_utc(), TZ) + timedelta(days=n), time(h), TZ)


async def make_exam(client, subject_id: str, days: int = 5, **over) -> dict:
    body = {"subject_id": subject_id, "starts_at": in_days(days).isoformat(), **over}
    resp = await client.post(f"{API}/exams", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def subject(client) -> dict:
    return await make_subject(client, "Климатология", "клим")


async def calendar(client, kind: str | None = None) -> list[dict]:
    resp = await client.get(
        f"{API}/calendar",
        params={"from": now_utc().isoformat(), "to": (now_utc() + timedelta(days=30)).isoformat()},
    )
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    return [e for e in events if kind is None or e["kind"] == kind]


async def test_create_exam_puts_it_in_calendar(auth_client):
    subj = await subject(auth_client)
    exam = await make_exam(auth_client, subj["id"], location="1801")
    assert exam["title"] == "Экзамен: Климатология"
    assert (exam["learn_min"], exam["review_min"], exam["run_min"], exam["prep_days"]) == (
        45,
        15,
        5,
        7,
    )
    [event] = await calendar(auth_client, "exam")
    assert event["is_fixed"] and event["location"] == "1801"
    assert event["title"] == "Экзамен: Климатология"

    new_start = in_days(6, 9)
    resp = await auth_client.patch(
        f"{API}/exams/{exam['id']}", json={"starts_at": new_start.isoformat()}
    )
    assert resp.status_code == 200
    [event] = await calendar(auth_client, "exam")
    assert datetime.fromisoformat(event["start"]) == new_start

    resp = await auth_client.get(f"{API}/exams", params={"subject_id": subj["id"]})
    assert [e["id"] for e in resp.json()] == [exam["id"]]
    assert (await auth_client.delete(f"{API}/exams/{exam['id']}")).status_code == 204
    assert await calendar(auth_client, "exam") == []


async def test_import_questions(auth_client):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"])
    resp = await auth_client.post(
        f"{API}/exams/{exam['id']}/questions/import", json={"text": QUESTIONS}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [(q["number"], q["text"]) for q in body["questions"]][:2] == [
        (1, "Циклоны"),
        (2, "Антициклоны"),
    ]
    assert body["questions_total"] == 6
    # Ненумерованные — дописываются в конец
    resp = await auth_client.post(
        f"{API}/exams/{exam['id']}/questions/import", json={"text": "Радиация\nАльбедо"}
    )
    assert [q["number"] for q in resp.json()["questions"]][-2:] == [7, 8]
    resp = await auth_client.post(
        f"{API}/exams/{exam['id']}/questions/import", json={"text": " \n "}
    )
    assert resp.status_code in (400, 422)


async def test_build_plan_and_schedule(auth_client, user):
    """Сценарий 8: экзамен + дата + билеты → план подготовки по дням до экзамена."""
    exam = await make_exam(auth_client, (await subject(auth_client))["id"], days=5)
    await auth_client.post(f"{API}/exams/{exam['id']}/questions/import", json={"text": QUESTIONS})
    resp = await auth_client.post(f"{API}/exams/{exam['id']}/plan")
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["plan_enabled"]
    sessions = detail["sessions"]
    kinds = [s["kind"] for s in sessions]
    assert "learn" in kinds and "run" in kinds
    run = next(s for s in sessions if s["kind"] == "run")
    assert run["date"] == (local_date(now_utc(), TZ) + timedelta(days=4)).isoformat()
    assert run["numbers"] == [1, 2, 3, 4, 5, 6]
    learned = sorted(n for s in sessions if s["kind"] == "learn" for n in s["numbers"])
    assert learned == [1, 2, 3, 4, 5, 6]
    assert next(s for s in sessions if s["kind"] == "learn")["title"].startswith("клим: выучить №")

    # Превью уже посчитано: блоки подготовки встают по своим дням
    state = (await auth_client.get(f"{API}/plan")).json()
    proposal = state["proposal"]
    assert proposal is not None
    adds = [c for c in proposal["changes"] if c["op"] == "add"]
    assert adds and all(c["kind"] == "exam_prep" for c in adds)
    resp = await auth_client.post(f"{API}/plan/revisions/{proposal['id']}/apply")
    assert resp.status_code == 200, resp.text
    prep = await calendar(auth_client, "exam_prep")
    by_session = {e["source_id"]: e for e in prep}
    for s in sessions:
        if s["id"] in by_session:
            start = datetime.fromisoformat(by_session[s["id"]]["start"])
            assert start.astimezone(TZ).date().isoformat() == s["date"]
    exam_start = datetime.fromisoformat(exam["starts_at"])
    assert all(datetime.fromisoformat(e["end"]) <= exam_start for e in prep)


async def test_session_done_marks_questions_learned(auth_client, user):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"], days=5)
    await auth_client.post(f"{API}/exams/{exam['id']}/questions/import", json={"text": QUESTIONS})
    detail = (await auth_client.post(f"{API}/exams/{exam['id']}/plan")).json()
    proposal = (await auth_client.get(f"{API}/plan")).json()["proposal"]
    await auth_client.post(f"{API}/plan/revisions/{proposal['id']}/apply")
    first_learn = next(s for s in detail["sessions"] if s["kind"] == "learn")
    [event] = [
        e for e in await calendar(auth_client, "exam_prep") if e["source_id"] == first_learn["id"]
    ]

    resp = await auth_client.patch(f"{API}/events/{event['id']}", json={"status": "done"})
    assert resp.status_code == 200
    detail = (await auth_client.get(f"{API}/exams/{exam['id']}")).json()
    learned = {q["number"] for q in detail["questions"] if q["status"] == "learned"}
    assert learned == set(first_learn["numbers"])
    assert next(s for s in detail["sessions"] if s["id"] == first_learn["id"])["status"] == "done"
    assert detail["questions_learned"] == len(learned)

    # Сняли отметку — вопросы снова не выучены
    await auth_client.patch(f"{API}/events/{event['id']}", json={"status": "planned"})
    detail = (await auth_client.get(f"{API}/exams/{exam['id']}")).json()
    assert all(q["status"] == "not_started" for q in detail["questions"])


async def test_review_status_returns_question_to_cycle(auth_client):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"], days=10)
    await auth_client.post(
        f"{API}/exams/{exam['id']}/questions/import", json={"text": "1. A\n2. B"}
    )
    detail = (await auth_client.post(f"{API}/exams/{exam['id']}/plan")).json()
    q = detail["questions"][0]
    resp = await auth_client.patch(f"{API}/exam-questions/{q['id']}", json={"status": "review"})
    assert resp.status_code == 200
    assert resp.json()["learned_on"] == local_date(now_utc(), TZ).isoformat()
    detail = (await auth_client.get(f"{API}/exams/{exam['id']}")).json()
    tomorrow = (local_date(now_utc(), TZ) + timedelta(days=1)).isoformat()
    reviews = [s for s in detail["sessions"] if s["kind"] == "review" and s["date"] == tomorrow]
    assert reviews and 1 in reviews[0]["numbers"]
    learn = [n for s in detail["sessions"] if s["kind"] == "learn" for n in s["numbers"]]
    assert 1 not in learn


async def test_disable_plan_removes_future_sessions(auth_client, user):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"])
    await auth_client.post(
        f"{API}/exams/{exam['id']}/questions/import", json={"text": "1. A\n2. B"}
    )
    await auth_client.post(f"{API}/exams/{exam['id']}/plan")
    resp = await auth_client.delete(f"{API}/exams/{exam['id']}/plan")
    assert resp.json()["sessions"] == [] and not resp.json()["plan_enabled"]


async def test_plan_requires_questions(auth_client):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"])
    resp = await auth_client.post(f"{API}/exams/{exam['id']}/plan")
    assert resp.status_code == 400


async def test_other_user_cannot_see_exam(auth_client, session):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"])
    async with other_client(auth_client, session) as other:
        assert (await other.get(f"{API}/exams/{exam['id']}")).status_code == 404
        assert (await other.get(f"{API}/exams")).json() == []


async def test_nightly_marks_missed_and_redistributes(auth_client, user):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"], days=4, prep_days=7)
    await auth_client.post(f"{API}/exams/{exam['id']}/questions/import", json={"text": QUESTIONS})
    await auth_client.post(f"{API}/exams/{exam['id']}/plan")
    tomorrow = now_utc() + timedelta(days=1)
    async with session_factory() as db:
        u = await db.get(User, user.id)
        await sync_all(db, u, tomorrow)
        rows = list(await db.scalars(select(ExamSession).where(ExamSession.deleted_at.is_(None))))
    today = local_date(now_utc(), TZ)
    missed = [x for x in rows if x.status == ExamSessionStatus.missed]
    assert missed and all(x.date == today for x in missed)
    # Вопросы невыученного дня ушли на следующие дни
    planned = [x for x in rows if x.status == ExamSessionStatus.planned]
    learn_ids = {q for x in planned if x.kind == ExamSessionKind.learn for q in x.question_ids}
    assert len(learn_ids) == 6


async def test_exam_in_past_has_no_plan(auth_client, user):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"], days=2)
    await auth_client.post(f"{API}/exams/{exam['id']}/questions/import", json={"text": "1. A"})
    await auth_client.post(f"{API}/exams/{exam['id']}/plan")
    async with session_factory() as db:
        u = await db.get(User, user.id)
        svc = ExamService(db, u, now_utc() + timedelta(days=3))
        await sync_all(db, u, now_utc() + timedelta(days=3))
        detail = await svc.get_detail(exam["id"])
    assert detail.sessions == []


async def test_exam_blocks_are_busy_for_planner(auth_client, user):
    subj = await subject(auth_client)
    await make_exam(auth_client, subj["id"], days=1)
    async with session_factory() as db:
        u = await db.get(User, user.id)
        snap = await ReplanService(db, u).snapshot()
        events = list(await db.scalars(select(Event).where(Event.kind == EventKind.exam)))
    assert events and events[0].status == EventStatus.planned
    assert any(b.start == events[0].start for b in snap.inp.busy)
