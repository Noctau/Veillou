"""M12, M20: подготовка к событию — экзамен с билетами (spaced), выступление (even)."""

from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.core.db import session_factory
from app.core.time import get_tz, local_date, now_utc, wall_to_utc
from app.domain.enums import EventKind, EventStatus, PrepSessionKind, PrepSessionStatus
from app.models import Event, PrepSession, User
from app.services.prep import PrepService, sync_all
from app.services.replan import ReplanService

from .test_ai import make_area
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


async def exam_type(client) -> dict:
    """Тип «Экзамен» (подготовка) пользователя; нет — создаёт."""
    from .test_schedule_api import make_event_type

    for t in (await client.get(f"{API}/event-types")).json():
        if t["name"] == "Экзамен":
            return t
    return await make_event_type(
        client, name="Экзамен", name_plural="Экзамены", supports_prep=True, fields=[]
    )


async def make_exam(
    client, area_id: str, days: int = 5, location: str | None = None, **over
) -> dict:
    """Экзамен: событие типа «Экзамен» + план подготовки к нему."""
    await exam_type(client)
    body = {
        "area_id": area_id,
        "event": {"start": in_days(days).isoformat(), "location": location},
        **over,
    }
    resp = await client.post(f"{API}/prep-plans", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def subject(client) -> dict:
    return await make_area(client, "Климатология", "клим")


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
    assert exam["strategy"] == "spaced"
    assert (exam["learn_min"], exam["review_min"], exam["run_min"], exam["start_days_before"]) == (
        45,
        15,
        5,
        7,
    )
    [event] = await calendar(auth_client, "busy")
    assert event["is_fixed"]
    assert event["location"] == "1801"
    assert event["title"] == "Экзамен: Климатология"
    assert event["event_type_id"] == (await exam_type(auth_client))["id"]
    assert exam["event"]["id"] == event["id"]

    # Событие переносят в календаре — срок плана следует за ним
    new_start = in_days(6, 9)
    resp = await auth_client.patch(
        f"{API}/events/{event['id']}",
        json={"start": new_start.isoformat(), "end": (new_start + timedelta(hours=3)).isoformat()},
    )
    assert resp.status_code == 200
    detail = (await auth_client.get(f"{API}/prep-plans/{exam['id']}")).json()
    assert datetime.fromisoformat(detail["target"]) == new_start

    resp = await auth_client.get(f"{API}/prep-plans", params={"area_id": subj["id"]})
    assert [e["id"] for e in resp.json()] == [exam["id"]]
    resp = await auth_client.get(f"{API}/prep-plans", params={"event_id": event["id"]})
    assert [e["id"] for e in resp.json()] == [exam["id"]]
    url = f"{API}/prep-plans/{exam['id']}"
    assert (await auth_client.delete(url, params={"with_event": True})).status_code == 204
    assert await calendar(auth_client, "busy") == []


async def test_import_questions(auth_client):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"])
    resp = await auth_client.post(
        f"{API}/prep-plans/{exam['id']}/items/import", json={"text": QUESTIONS}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [(q["number"], q["text"]) for q in body["items"]][:2] == [
        (1, "Циклоны"),
        (2, "Антициклоны"),
    ]
    assert body["items_total"] == 6
    # Ненумерованные — дописываются в конец
    resp = await auth_client.post(
        f"{API}/prep-plans/{exam['id']}/items/import", json={"text": "Радиация\nАльбедо"}
    )
    assert [q["number"] for q in resp.json()["items"]][-2:] == [7, 8]
    resp = await auth_client.post(
        f"{API}/prep-plans/{exam['id']}/items/import", json={"text": " \n "}
    )
    assert resp.status_code in (400, 422)


async def test_build_plan_and_schedule(auth_client, user):
    """Сценарий 8: экзамен + дата + билеты → план подготовки по дням до экзамена."""
    exam = await make_exam(auth_client, (await subject(auth_client))["id"], days=5)
    await auth_client.post(f"{API}/prep-plans/{exam['id']}/items/import", json={"text": QUESTIONS})
    resp = await auth_client.post(f"{API}/prep-plans/{exam['id']}/enable")
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["enabled"]
    sessions = detail["sessions"]
    kinds = [s["kind"] for s in sessions]
    assert "learn" in kinds
    assert "run" in kinds
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
    assert adds
    assert all(c["kind"] == "prep" for c in adds)
    resp = await auth_client.post(f"{API}/plan/revisions/{proposal['id']}/apply")
    assert resp.status_code == 200, resp.text
    prep = await calendar(auth_client, "prep")
    by_session = {e["source_id"]: e for e in prep}
    for s in sessions:
        if s["id"] in by_session:
            start = datetime.fromisoformat(by_session[s["id"]]["start"])
            assert start.astimezone(TZ).date().isoformat() == s["date"]
    exam_start = datetime.fromisoformat(exam["target"])
    assert all(datetime.fromisoformat(e["end"]) <= exam_start for e in prep)


async def test_session_done_marks_questions_learned(auth_client, user):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"], days=5)
    await auth_client.post(f"{API}/prep-plans/{exam['id']}/items/import", json={"text": QUESTIONS})
    detail = (await auth_client.post(f"{API}/prep-plans/{exam['id']}/enable")).json()
    proposal = (await auth_client.get(f"{API}/plan")).json()["proposal"]
    await auth_client.post(f"{API}/plan/revisions/{proposal['id']}/apply")
    first_learn = next(s for s in detail["sessions"] if s["kind"] == "learn")
    [event] = [
        e for e in await calendar(auth_client, "prep") if e["source_id"] == first_learn["id"]
    ]

    resp = await auth_client.patch(f"{API}/events/{event['id']}", json={"status": "done"})
    assert resp.status_code == 200
    detail = (await auth_client.get(f"{API}/prep-plans/{exam['id']}")).json()
    learned = {q["number"] for q in detail["items"] if q["status"] == "learned"}
    assert learned == set(first_learn["numbers"])
    assert next(s for s in detail["sessions"] if s["id"] == first_learn["id"])["status"] == "done"
    assert detail["items_learned"] == len(learned)

    # Сняли отметку — вопросы снова не выучены
    await auth_client.patch(f"{API}/events/{event['id']}", json={"status": "planned"})
    detail = (await auth_client.get(f"{API}/prep-plans/{exam['id']}")).json()
    assert all(q["status"] == "not_started" for q in detail["items"])


async def test_review_status_returns_question_to_cycle(auth_client):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"], days=10)
    await auth_client.post(
        f"{API}/prep-plans/{exam['id']}/items/import", json={"text": "1. A\n2. B"}
    )
    detail = (await auth_client.post(f"{API}/prep-plans/{exam['id']}/enable")).json()
    q = detail["items"][0]
    resp = await auth_client.patch(f"{API}/prep-items/{q['id']}", json={"status": "review"})
    assert resp.status_code == 200
    assert resp.json()["learned_on"] == local_date(now_utc(), TZ).isoformat()
    detail = (await auth_client.get(f"{API}/prep-plans/{exam['id']}")).json()
    tomorrow = (local_date(now_utc(), TZ) + timedelta(days=1)).isoformat()
    reviews = [s for s in detail["sessions"] if s["kind"] == "review" and s["date"] == tomorrow]
    assert reviews
    assert 1 in reviews[0]["numbers"]
    learn = [n for s in detail["sessions"] if s["kind"] == "learn" for n in s["numbers"]]
    assert 1 not in learn


async def test_disable_plan_removes_future_sessions(auth_client, user):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"])
    await auth_client.post(
        f"{API}/prep-plans/{exam['id']}/items/import", json={"text": "1. A\n2. B"}
    )
    await auth_client.post(f"{API}/prep-plans/{exam['id']}/enable")
    resp = await auth_client.post(f"{API}/prep-plans/{exam['id']}/disable")
    assert resp.json()["sessions"] == []
    assert not resp.json()["enabled"]


async def test_plan_requires_questions(auth_client):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"])
    resp = await auth_client.post(f"{API}/prep-plans/{exam['id']}/enable")
    assert resp.status_code == 400


async def test_other_user_cannot_see_exam(auth_client, session):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"])
    async with other_client(auth_client, session) as other:
        assert (await other.get(f"{API}/prep-plans/{exam['id']}")).status_code == 404
        assert (await other.get(f"{API}/prep-plans")).json() == []


async def test_nightly_marks_missed_and_redistributes(auth_client, user):
    exam = await make_exam(
        auth_client, (await subject(auth_client))["id"], days=4, start_days_before=7
    )
    await auth_client.post(f"{API}/prep-plans/{exam['id']}/items/import", json={"text": QUESTIONS})
    await auth_client.post(f"{API}/prep-plans/{exam['id']}/enable")
    tomorrow = now_utc() + timedelta(days=1)
    async with session_factory() as db:
        u = await db.get(User, user.id)
        await sync_all(db, u, tomorrow)
        rows = list(await db.scalars(select(PrepSession).where(PrepSession.deleted_at.is_(None))))
    today = local_date(now_utc(), TZ)
    missed = [x for x in rows if x.status == PrepSessionStatus.missed]
    assert missed
    assert all(x.date == today for x in missed)
    # Вопросы невыученного дня ушли на следующие дни
    planned = [x for x in rows if x.status == PrepSessionStatus.planned]
    learn_ids = {q for x in planned if x.kind == PrepSessionKind.learn for q in x.item_ids}
    assert len(learn_ids) == 6


async def test_exam_in_past_has_no_plan(auth_client, user):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"], days=2)
    await auth_client.post(f"{API}/prep-plans/{exam['id']}/items/import", json={"text": "1. A"})
    await auth_client.post(f"{API}/prep-plans/{exam['id']}/enable")
    async with session_factory() as db:
        u = await db.get(User, user.id)
        svc = PrepService(db, u, now_utc() + timedelta(days=3))
        await sync_all(db, u, now_utc() + timedelta(days=3))
        detail = await svc.get_detail(exam["id"])
    assert detail.sessions == []


async def test_exam_blocks_are_busy_for_planner(auth_client, user):
    subj = await subject(auth_client)
    await make_exam(auth_client, subj["id"], days=1)
    async with session_factory() as db:
        u = await db.get(User, user.id)
        snap = await ReplanService(db, u).snapshot()
        events = list(await db.scalars(select(Event).where(Event.kind == EventKind.busy)))
    assert events
    assert events[0].status == EventStatus.planned
    assert any(b.start == events[0].start for b in snap.inp.busy)


async def test_exam_event_gets_prep_event_type(auth_client):
    from .test_schedule_api import make_event_type

    await make_event_type(auth_client, name="Смена", fields=[])
    await make_exam(auth_client, (await subject(auth_client))["id"])
    [event] = await calendar(auth_client, "busy")
    assert event["event_type_id"] == (await exam_type(auth_client))["id"]


# ---------- M20: план к готовому событию, к дате, стратегия even ----------


async def test_talk_even_strategy_builds_blocks_before_date(auth_client, user):
    """«Выступление» со стратегией even: части поровну по дням, накануне прогон, блоки
    подготовки встают до начала выступления."""
    from .test_schedule_api import make_event_type

    talk_type = await make_event_type(
        auth_client, name="Выступление", name_plural="Выступления", supports_prep=True, fields=[]
    )
    start = in_days(5, 15)
    event = (
        await auth_client.post(
            f"{API}/events",
            json={
                "title": "Доклад на конференции",
                "start": start.isoformat(),
                "end": (start + timedelta(hours=1)).isoformat(),
                "event_type_id": talk_type["id"],
            },
        )
    ).json()
    resp = await auth_client.post(
        f"{API}/prep-plans",
        json={"event_id": event["id"], "strategy": "even", "learn_min": 30, "run_min": 10},
    )
    assert resp.status_code == 201, resp.text
    plan = resp.json()
    assert plan["title"] == "Доклад на конференции"
    await auth_client.post(
        f"{API}/prep-plans/{plan['id']}/items/import",
        json={"text": "Вступление\nРезультаты\nМетод\nВыводы"},
    )
    detail = (await auth_client.post(f"{API}/prep-plans/{plan['id']}/enable")).json()
    kinds = [s["kind"] for s in detail["sessions"]]
    assert "review" not in kinds
    assert kinds.count("run") == 1
    learned = sorted(n for s in detail["sessions"] if s["kind"] == "learn" for n in s["numbers"])
    assert learned == [1, 2, 3, 4]
    run = next(s for s in detail["sessions"] if s["kind"] == "run")
    assert run["date"] == (local_date(now_utc(), TZ) + timedelta(days=4)).isoformat()
    assert run["minutes"] == 40

    proposal = (await auth_client.get(f"{API}/plan")).json()["proposal"]
    assert proposal is not None
    await auth_client.post(f"{API}/plan/revisions/{proposal['id']}/apply")
    prep = await calendar(auth_client, "prep")
    assert prep
    assert all(datetime.fromisoformat(e["end"]) <= start for e in prep)


async def test_plan_for_area_date_without_event(auth_client):
    subj = await subject(auth_client)
    day = (local_date(now_utc(), TZ) + timedelta(days=6)).isoformat()
    resp = await auth_client.post(
        f"{API}/prep-plans", json={"area_id": subj["id"], "date": day, "strategy": "even"}
    )
    assert resp.status_code == 201, resp.text
    plan = resp.json()
    assert (plan["event"], plan["title"]) == (None, "Подготовка: Климатология")
    await auth_client.post(f"{API}/prep-plans/{plan['id']}/items/import", json={"text": "A\nB"})
    detail = (await auth_client.post(f"{API}/prep-plans/{plan['id']}/enable")).json()
    assert detail["sessions"]
    assert all(s["date"] < day for s in detail["sessions"])
    for bad in ({"area_id": subj["id"]}, {"date": day, "event": {"start": in_days(2).isoformat()}}):
        assert (await auth_client.post(f"{API}/prep-plans", json=bad)).status_code == 422


async def test_cancelled_event_drops_sessions(auth_client, user):
    exam = await make_exam(auth_client, (await subject(auth_client))["id"], days=5)
    await auth_client.post(f"{API}/prep-plans/{exam['id']}/items/import", json={"text": QUESTIONS})
    await auth_client.post(f"{API}/prep-plans/{exam['id']}/enable")
    await auth_client.patch(f"{API}/events/{exam['event']['id']}", json={"status": "cancelled"})
    async with session_factory() as db:
        u = await db.get(User, user.id)
        await sync_all(db, u)
    detail = (await auth_client.get(f"{API}/prep-plans/{exam['id']}")).json()
    assert (detail["target"], detail["sessions"]) == (None, [])
