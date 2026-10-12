"""Материализация правил расписания в events: серия пересобирается, ручные правки живут."""

from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
from app.services.schedule_sync import HORIZON_DAYS, roll_all_users

from .test_schedule_api import (
    API,
    BELLS,
    class_type,
    make_area,
    make_class_rule,
    make_event_type,
    make_grid,
    make_period,
    make_rule,
)

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
    sem = await make_period(auth_client)
    grid = await make_grid(auth_client, sem["id"])
    subj = await make_area(auth_client, sem["id"], color="#10b981")
    kind_f = (await class_type(auth_client))["fields"][0]["id"]
    rule = await make_class_rule(
        auth_client,
        sem,
        subj,
        weekday=4,
        slot=2,
        grid=grid,
        location="1801",
        fields={kind_f: "семинар"},
    )
    return {"semester": sem, "subject": subj, "rule": rule, "grid": grid, "kind_f": kind_f}


async def test_rule_materializes_from_today(setup, session: AsyncSession):
    events = await live_events(session)
    assert [e.occurrence_date for e in events] == THURSDAYS
    first = events[0]
    assert first.kind == "busy"
    assert str(first.event_type_id) == setup["rule"]["event_type_id"]
    assert first.is_fixed
    assert first.title == "Климатология"
    assert first.color == "#10b981"
    assert first.location == "1801"
    assert first.fields == {setup["kind_f"]: "семинар"}
    assert first.slot == 2
    assert first.start == datetime(2026, 10, 8, 7, 45, tzinfo=UTC)  # 10:45 МСК
    assert str(first.template_id) == setup["rule"]["id"]


async def test_series_edit_keeps_manually_moved_class(
    setup, auth_client: AsyncClient, session: AsyncSession
):
    """DoD M2.3 (на правилах расписания, M17.4): правка серии не затирает вручную
    перенесённое вхождение."""
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
        f"{API}/schedule-rules/{setup['rule']['id']}", json={"location": "2105", "slot_from": 1}
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
    assert updated.location == "2105"
    assert updated.slot == 1
    assert updated.start == datetime(2026, 10, 22, 6, 0, tzinfo=UTC)  # 09:00 МСК


async def test_cancelled_class_not_resurrected(
    setup, auth_client: AsyncClient, session: AsyncSession
):
    target = (await live_events(session))[0]
    assert (await auth_client.delete(f"{API}/events/{target.id}")).status_code == 204
    await auth_client.patch(f"{API}/schedule-rules/{setup['rule']['id']}", json={"location": "9"})
    events = await live_events(session)
    assert len(events) == 12
    cancelled = next(e for e in events if e.id == target.id)
    assert cancelled.status == "cancelled"
    assert cancelled.detached


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
    assert date(2026, 11, 5) not in dates
    assert len(dates) == 11

    await auth_client.delete(f"{API}/days-off/{day_off['id']}")
    assert [e.occurrence_date for e in await live_events(session)] == THURSDAYS


async def test_bells_change_moves_times(setup, auth_client: AsyncClient, session: AsyncSession):
    bells = [{**b, "start": "11:00", "end": "12:35"} if b["number"] == 2 else b for b in BELLS]
    thursday = [{"number": 2, "start": "12:00", "end": "13:30"}]
    await auth_client.put(
        f"{API}/slot-grids",
        json={
            "period_id": setup["semester"]["id"],
            "name": "Звонки",
            "schedules": [{"weekday": None, "slots": bells}, {"weekday": 4, "slots": thursday}],
        },
    )
    first = (await live_events(session))[0]
    assert first.start == datetime(2026, 10, 8, 9, 0, tzinfo=UTC)  # 12:00 МСК по четвергам


async def test_period_shortened_drops_tail(setup, auth_client: AsyncClient, session: AsyncSession):
    resp = await auth_client.patch(
        f"{API}/periods/{setup['semester']['id']}", json={"end_date": "2026-10-31", "pauses": []}
    )
    assert resp.status_code == 200, resp.text
    assert [e.occurrence_date for e in await live_events(session)] == THURSDAYS[:4]


async def test_subject_rename_updates_titles(
    setup, auth_client: AsyncClient, session: AsyncSession
):
    target = (await live_events(session))[0]
    await auth_client.patch(f"{API}/events/{target.id}", json={"location": "А-4"})
    await auth_client.patch(
        f"{API}/areas/{setup['subject']['id']}", json={"name": "Климат", "color": "#ef4444"}
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

    resp = await auth_client.delete(f"{API}/schedule-rules/{setup['rule']['id']}")
    assert resp.status_code == 204
    # Остались только прошедшие; будущие удалены, включая правленную вручную
    assert [e.occurrence_date for e in await live_events(session)] == THURSDAYS[:3]


async def test_past_occurrences_not_touched_by_series_edit(
    setup, auth_client: AsyncClient, session: AsyncSession, clock
):
    clock["now"] = datetime(2026, 10, 20, 4, 0, tzinfo=UTC)
    await auth_client.patch(f"{API}/schedule-rules/{setup['rule']['id']}", json={"location": "9"})
    events = await live_events(session)
    assert [e.location for e in events[:2]] == ["1801", "1801"]
    assert {e.location for e in events[2:]} == {"9"}


async def test_rule_created_mid_period_starts_today(
    setup, auth_client: AsyncClient, session: AsyncSession
):
    # Вторник 06.10 — «сегодня», 1-й слот уже прошёл по времени, но день текущий
    await make_class_rule(
        auth_client,
        setup["semester"],
        setup["subject"],
        weekday=2,
        slot=1,
        mask=[2],
        grid=setup["grid"],
    )
    tuesdays = sorted(e.occurrence_date for e in await live_events(session) if e.slot == 1)
    # Неделя 05.10 — 6-я от начала периода (1-я — неделя цикла 1) -> неделя 2
    assert tuesdays[:3] == [date(2026, 10, 6), date(2026, 10, 20), date(2026, 11, 3)]


async def test_reset_past_occurrence(setup, auth_client: AsyncClient, session: AsyncSession, clock):
    # Пару перенесли, день прошёл — «Как в расписании» всё равно возвращает время и аудиторию
    target = (await live_events(session))[0]
    await auth_client.patch(
        f"{API}/events/{target.id}",
        json={
            "start": "2026-10-09T12:00:00+03:00",
            "end": "2026-10-09T13:35:00+03:00",
            "location": "А-4",
        },
    )
    clock["now"] = datetime(2026, 10, 20, 4, 0, tzinfo=UTC)
    resp = await auth_client.post(f"{API}/events/{target.id}/reset")
    data = resp.json()
    assert data["detached"] is False
    assert data["location"] == "1801"
    assert data["start"] == "2026-10-08T07:45:00Z"


# ---------- правила без периода, смены, исключения ----------


async def test_rule_without_period_rolls_90_days(
    auth_client: AsyncClient, session: AsyncSession, clock
):
    personal = await make_event_type(auth_client, name="Личное", fields=[], buffer_before_min=0)
    await make_rule(
        auth_client,
        event_type_id=personal["id"],
        title="Бассейн",
        pattern={"kind": "weekly", "weekdays": [2, 4]},
        start_time="19:00",
        end_time="20:30",
    )
    today = date(2026, 10, 6)
    dates = [e.occurrence_date for e in await live_events(session)]
    assert dates[0] == today
    assert dates[-1] <= today + timedelta(days=HORIZON_DAYS)
    count = len(dates)

    # Через неделю ночная джоба докатывает окно
    clock["now"] = NOW + timedelta(days=7)
    assert await roll_all_users(session, now=clock["now"]) == 2
    assert len(await live_events(session)) == count + 2


async def test_shift_cycle_materializes(auth_client: AsyncClient, session: AsyncSession, clock):
    shift = await make_event_type(
        auth_client, name="Смена", fields=[], buffer_before_min=40, remind_before_min=60
    )
    await make_rule(
        auth_client,
        event_type_id=shift["id"],
        pattern={"kind": "day_cycle", "on": 2, "off": 2, "anchor": "2026-10-06"},
        start_time="20:00",
        end_time="08:00",
    )
    events = await live_events(session)
    assert [e.occurrence_date for e in events[:4]] == [
        date(2026, 10, 6),
        date(2026, 10, 7),
        date(2026, 10, 10),
        date(2026, 10, 11),
    ]
    # Название — по типу занятости; ночная смена кончается утром следующего дня
    assert events[0].title == "Смена"
    assert events[0].end - events[0].start == timedelta(hours=12)

    await auth_client.patch(f"{API}/event-types/{shift['id']}", json={"name": "Дежурство"})
    assert {e.title for e in await live_events(session)} == {"Дежурство"}


async def test_days_off_only_for_period_rules(
    setup, auth_client: AsyncClient, session: AsyncSession
):
    personal = await make_event_type(auth_client, name="Личное", fields=[])
    await make_rule(
        auth_client,
        event_type_id=personal["id"],
        title="Бассейн",
        pattern={"kind": "weekly", "weekdays": [4]},
        start_time="19:00",
        end_time="20:00",
    )
    other = await make_period(auth_client, name="Другой")
    # Исключение чужого периода не трогает правила этого
    await auth_client.post(
        f"{API}/days-off",
        json={"period_id": other["id"], "date_from": "2026-10-15", "date_to": "2026-10-15"},
    )
    by_title = {}
    for e in await live_events(session):
        by_title.setdefault(e.title, []).append(e.occurrence_date)
    assert date(2026, 10, 15) in by_title["Климатология"]

    # Общее исключение — у правила периода вхождения нет, у правила без периода — есть
    await auth_client.post(
        f"{API}/days-off", json={"date_from": "2026-10-15", "date_to": "2026-10-15"}
    )
    by_title = {}
    for e in await live_events(session):
        by_title.setdefault(e.title, []).append(e.occurrence_date)
    assert date(2026, 10, 15) not in by_title["Климатология"]
    assert date(2026, 10, 15) in by_title["Бассейн"]


async def test_period_pause_skips(setup, auth_client: AsyncClient, session: AsyncSession):
    await auth_client.patch(
        f"{API}/periods/{setup['semester']['id']}",
        json={
            "pauses": [
                {"from": "2026-11-02", "to": "2026-11-08", "title": "Каникулы"},
                {"from": "2026-12-28", "to": "2027-01-25", "title": "Сессия"},
            ]
        },
    )
    dates = [e.occurrence_date for e in await live_events(session)]
    assert date(2026, 11, 5) not in dates
    assert len(dates) == 11
