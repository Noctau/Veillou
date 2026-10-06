"""Материализация пар в events: серия пересобирается, ручные правки живут."""

from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event

from .test_schedule_api import API, BELLS, make_semester, make_subject

# «Сейчас» — вторник 06.10.2026, 07:00 МСК
NOW = datetime(2026, 10, 6, 4, 0, tzinfo=UTC)
THURSDAYS = [
    date(2026, 10, 8) + (date(2026, 10, 15) - date(2026, 10, 8)) * i for i in range(12)
]  # 08.10 … 24.12


@pytest.fixture
def clock(monkeypatch):
    state = {"now": NOW}
    monkeypatch.setattr("app.services.schedule_sync.now_utc", lambda: state["now"])
    return state


async def live_events(session: AsyncSession) -> list[Event]:
    rows = await session.scalars(
        select(Event)
        .where(Event.deleted_at.is_(None))
        .order_by(Event.start)
        .execution_options(populate_existing=True)
    )
    return list(rows)


@pytest.fixture
async def setup(auth_client: AsyncClient, clock):
    sem = await make_semester(auth_client)
    await auth_client.put(
        f"{API}/semesters/{sem['id']}/bells",
        json={"schedules": [{"weekday": None, "slots": BELLS}]},
    )
    subj = await make_subject(auth_client, sem["id"], color="#10b981")
    resp = await auth_client.post(
        f"{API}/class-rules",
        json={
            "semester_id": sem["id"],
            "subject_id": subj["id"],
            "weekday": 4,
            "pair_number": 2,
            "location": "1801",
            "class_type": "seminar",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"semester": sem, "subject": subj, "rule": resp.json()}


async def test_rule_materializes_from_today(setup, session: AsyncSession):
    events = await live_events(session)
    assert [e.occurrence_date for e in events] == THURSDAYS
    first = events[0]
    assert first.kind == "class" and first.is_fixed
    assert first.title == "Климатология" and first.color == "#10b981"
    assert first.location == "1801" and first.class_type == "seminar" and first.pair_number == 2
    assert first.start == datetime(2026, 10, 8, 7, 45, tzinfo=UTC)  # 10:45 МСК
    assert str(first.template_id) == setup["rule"]["id"]


async def test_series_edit_keeps_manually_moved_class(
    setup, auth_client: AsyncClient, session: AsyncSession
):
    """DoD M2.3: правка серии не затирает вручную перенесённую пару."""
    events = await live_events(session)
    moved, other = events[1], events[2]  # 15.10 и 22.10
    ids_before = {e.id for e in events}

    # Переносим 15.10 на пятницу 16.10, 3-я пара, другая аудитория
    resp = await auth_client.patch(
        f"{API}/events/{moved.id}",
        json={
            "start": "2026-10-16T13:00:00+03:00",
            "end": "2026-10-16T14:35:00+03:00",
            "location": "А-4",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["detached"] is True

    # Правим серию: другая аудитория и 1-я пара
    resp = await auth_client.patch(
        f"{API}/class-rules/{setup['rule']['id']}", json={"location": "2105", "pair_number": 1}
    )
    assert resp.status_code == 200

    events = await live_events(session)
    by_id = {e.id: e for e in events}
    # Ничего не пересоздано: id те же, лишней пары на 15.10 не появилось
    assert {e.id for e in events} == ids_before
    assert sorted(e.occurrence_date for e in events) == THURSDAYS

    kept = by_id[moved.id]
    assert kept.location == "А-4"
    assert kept.start == datetime(2026, 10, 16, 10, 0, tzinfo=UTC)

    updated = by_id[other.id]
    assert updated.location == "2105" and updated.pair_number == 1
    assert updated.start == datetime(2026, 10, 22, 6, 0, tzinfo=UTC)  # 09:00 МСК


async def test_cancelled_class_not_resurrected(
    setup, auth_client: AsyncClient, session: AsyncSession
):
    target = (await live_events(session))[0]
    assert (await auth_client.delete(f"{API}/events/{target.id}")).status_code == 204
    await auth_client.patch(f"{API}/class-rules/{setup['rule']['id']}", json={"location": "9"})
    events = await live_events(session)
    assert len(events) == 12
    cancelled = next(e for e in events if e.id == target.id)
    assert cancelled.status == "cancelled" and cancelled.detached


async def test_reset_returns_to_series(setup, auth_client: AsyncClient, session: AsyncSession):
    target = (await live_events(session))[0]
    await auth_client.patch(f"{API}/events/{target.id}", json={"location": "А-4"})
    resp = await auth_client.post(f"{API}/events/{target.id}/reset")
    assert resp.status_code == 200
    assert resp.json()["detached"] is False
    assert resp.json()["location"] == "1801"


async def test_day_off_removes_and_restores(setup, auth_client: AsyncClient, session: AsyncSession):
    resp = await auth_client.post(
        f"{API}/days-off", json={"date_from": "2026-11-02", "date_to": "2026-11-08"}
    )
    day_off = resp.json()
    dates = [e.occurrence_date for e in await live_events(session)]
    assert date(2026, 11, 5) not in dates and len(dates) == 11

    await auth_client.delete(f"{API}/days-off/{day_off['id']}")
    assert [e.occurrence_date for e in await live_events(session)] == THURSDAYS


async def test_bells_change_moves_times(setup, auth_client: AsyncClient, session: AsyncSession):
    bells = [{**b, "start": "11:00", "end": "12:35"} if b["number"] == 2 else b for b in BELLS]
    thursday = [{"number": 2, "start": "12:00", "end": "13:30"}]
    await auth_client.put(
        f"{API}/semesters/{setup['semester']['id']}/bells",
        json={"schedules": [{"weekday": None, "slots": bells}, {"weekday": 4, "slots": thursday}]},
    )
    first = (await live_events(session))[0]
    assert first.start == datetime(2026, 10, 8, 9, 0, tzinfo=UTC)  # 12:00 МСК по четвергам


async def test_semester_shortened_drops_tail(
    setup, auth_client: AsyncClient, session: AsyncSession
):
    await auth_client.patch(
        f"{API}/semesters/{setup['semester']['id']}", json={"classes_end": "2026-10-31"}
    )
    assert [e.occurrence_date for e in await live_events(session)] == THURSDAYS[:4]


async def test_subject_rename_updates_titles(
    setup, auth_client: AsyncClient, session: AsyncSession
):
    target = (await live_events(session))[0]
    await auth_client.patch(f"{API}/events/{target.id}", json={"location": "А-4"})
    await auth_client.patch(
        f"{API}/subjects/{setup['subject']['id']}", json={"name": "Климат", "color": "#ef4444"}
    )
    events = await live_events(session)
    assert {(e.title, e.color) for e in events} == {("Климат", "#ef4444")}


async def test_delete_rule_keeps_past(
    setup, auth_client: AsyncClient, session: AsyncSession, clock
):
    # Прошло три недели: 08/15/22.10 — в прошлом
    clock["now"] = datetime(2026, 10, 27, 4, 0, tzinfo=UTC)
    moved = (await live_events(session))[5]
    await auth_client.patch(f"{API}/events/{moved.id}", json={"location": "А-4"})

    assert (await auth_client.delete(f"{API}/class-rules/{setup['rule']['id']}")).status_code == 204
    # Остались только прошедшие; будущие удалены, включая правленную вручную
    assert [e.occurrence_date for e in await live_events(session)] == THURSDAYS[:3]


async def test_past_occurrences_not_touched_by_series_edit(
    setup, auth_client: AsyncClient, session: AsyncSession, clock
):
    clock["now"] = datetime(2026, 10, 20, 4, 0, tzinfo=UTC)
    await auth_client.patch(f"{API}/class-rules/{setup['rule']['id']}", json={"location": "9"})
    events = await live_events(session)
    assert [e.location for e in events[:2]] == ["1801", "1801"]
    assert {e.location for e in events[2:]} == {"9"}


async def test_rule_created_mid_semester_starts_today(
    setup, auth_client: AsyncClient, session: AsyncSession
):
    # Вторник 06.10 — «сегодня», 1-я пара уже прошла по времени, но день текущий
    await auth_client.post(
        f"{API}/class-rules",
        json={
            "semester_id": setup["semester"]["id"],
            "subject_id": setup["subject"]["id"],
            "weekday": 2,
            "pair_number": 1,
            "parity": "even",
        },
    )
    tuesdays = sorted(e.occurrence_date for e in await live_events(session) if e.pair_number == 1)
    # Неделя 05.10 — 6-я от начала семестра (1-я — числитель) -> знаменатель
    assert tuesdays[:3] == [date(2026, 10, 6), date(2026, 10, 20), date(2026, 11, 3)]
