from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.schedule_sync import roll_all_users
from app.worker.__main__ import NIGHTLY_AT, seconds_until

from .test_schedule_api import API, other_client
from .test_schedule_sync import NOW, live_events

GYM = {
    "kind": "rest",
    "title": "Бассейн",
    "rrule": "FREQ=WEEKLY;BYDAY=TU,TH",
    "start_date": "2026-10-01",
    "start_time": "19:00",
    "end_time": "20:30",
}


@pytest.fixture
def clock(monkeypatch):
    state = {"now": NOW}
    monkeypatch.setattr("app.services.schedule_sync.now_utc", lambda: state["now"])
    return state


async def create_recurring(client: AsyncClient, **over) -> dict:
    resp = await client.post(f"{API}/recurring-events", json={**GYM, **over})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------- личные повторы ----------


async def test_recurring_materializes_90_days(auth_client, session: AsyncSession, clock):
    rec = await create_recurring(auth_client)
    assert rec["rrule"] == "FREQ=WEEKLY;BYDAY=TU,TH"
    events = await live_events(session)
    dates = [e.occurrence_date for e in events]
    # С сегодня (вт 06.10) до 04.01.2027 включительно: 13 вт + 13 чт
    assert dates[0] == date(2026, 10, 6)
    assert dates[-1] <= date(2027, 1, 4)
    assert len(dates) == 26
    first = events[0]
    assert first.kind == "rest" and first.is_fixed and first.title == "Бассейн"
    assert first.start == datetime(2026, 10, 6, 16, 0, tzinfo=UTC)
    assert first.end == datetime(2026, 10, 6, 17, 30, tzinfo=UTC)


async def test_recurring_validation(auth_client, clock):
    for over in (
        {"rrule": "FREQ=HOURLY"},
        {"rrule": "garbage"},
        {"until": "2026-09-01"},
        {"end_time": "19:00"},
        {"kind": "class"},
    ):
        resp = await auth_client.post(f"{API}/recurring-events", json={**GYM, **over})
        assert resp.status_code == 422, over


async def test_series_edit_keeps_detached_occurrence(auth_client, session: AsyncSession, clock):
    rec = await create_recurring(auth_client)
    moved = (await live_events(session))[0]
    await auth_client.patch(
        f"{API}/events/{moved.id}",
        json={"start": "2026-10-06T20:00:00+03:00", "end": "2026-10-06T21:00:00+03:00"},
    )
    resp = await auth_client.patch(
        f"{API}/recurring-events/{rec['id']}", json={"start_time": "18:00", "end_time": "19:00"}
    )
    assert resp.status_code == 200
    events = {e.id: e for e in await live_events(session)}
    assert events[moved.id].start == datetime(2026, 10, 6, 17, 0, tzinfo=UTC)  # 20:00 МСК
    others = [e for e in events.values() if e.id != moved.id]
    assert {e.start.astimezone(UTC).hour for e in others} == {15}  # 18:00 МСК
    assert len(events) == 26


async def test_rrule_change_and_delete(auth_client, session: AsyncSession, clock):
    rec = await create_recurring(auth_client)
    await auth_client.patch(
        f"{API}/recurring-events/{rec['id']}", json={"rrule": "FREQ=WEEKLY;BYDAY=SA"}
    )
    dates = [e.occurrence_date for e in await live_events(session)]
    assert all(d.isoweekday() == 6 for d in dates) and len(dates) == 13

    resp = await auth_client.delete(f"{API}/recurring-events/{rec['id']}")
    assert resp.status_code == 204
    assert await live_events(session) == []
    assert (await auth_client.get(f"{API}/recurring-events")).json() == []


async def test_nightly_roll_extends_window(auth_client, session: AsyncSession, clock):
    await create_recurring(auth_client, until=None)
    before = await live_events(session)

    later = datetime(2026, 11, 5, 0, 0, tzinfo=UTC)  # через месяц
    clock["now"] = later
    created = await roll_all_users(session, now=later)
    after = await live_events(session)

    assert created > 0
    assert {e.id for e in before} <= {e.id for e in after}  # старые не пересозданы
    assert max(e.occurrence_date for e in after) > max(e.occurrence_date for e in before)
    # Повторный прогон ничего не дублирует
    assert await roll_all_users(session, now=later) == 0


async def test_reset_recurring_occurrence(auth_client, session: AsyncSession, clock):
    await create_recurring(auth_client)
    target = (await live_events(session))[0]
    await auth_client.patch(f"{API}/events/{target.id}", json={"title": "Тренажёрка"})
    resp = await auth_client.post(f"{API}/events/{target.id}/reset")
    assert resp.json()["title"] == "Бассейн" and resp.json()["detached"] is False


# ---------- календарь ----------


async def test_calendar_range(auth_client, clock):
    await create_recurring(auth_client)
    await auth_client.post(
        f"{API}/events",
        json={
            "title": "Врач",
            "start": "2026-10-07T23:30:00+03:00",
            "end": "2026-10-08T00:30:00+03:00",
        },
    )
    await auth_client.post(
        f"{API}/days-off", json={"date_from": "2026-11-04", "date_to": "2026-11-04", "title": "ДНЕ"}
    )
    # Неделя 05.10–12.10 по Москве
    resp = await auth_client.get(
        f"{API}/calendar",
        params={"from": "2026-10-04T21:00:00Z", "to": "2026-10-11T21:00:00Z"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert [e["title"] for e in data["events"]] == ["Бассейн", "Врач", "Бассейн"]
    assert data["events"][0]["start"] == "2026-10-06T16:00:00Z"
    assert data["days_off"] == []

    # Событие через полночь попадает в оба дня
    resp = await auth_client.get(
        f"{API}/calendar",
        params={"from": "2026-10-07T21:00:00Z", "to": "2026-10-08T21:00:00Z"},
    )
    assert [e["title"] for e in resp.json()["events"]] == ["Врач", "Бассейн"]

    resp = await auth_client.get(
        f"{API}/calendar",
        params={"from": "2026-11-01T00:00:00+03:00", "to": "2026-11-08T00:00:00+03:00"},
    )
    assert [d["title"] for d in resp.json()["days_off"]] == ["ДНЕ"]


async def test_calendar_cancelled_class_included(auth_client, session: AsyncSession, clock):
    rec = await create_recurring(auth_client)
    target = (await live_events(session))[0]
    await auth_client.delete(f"{API}/events/{target.id}")
    resp = await auth_client.get(
        f"{API}/calendar", params={"from": "2026-10-06T00:00:00Z", "to": "2026-10-07T00:00:00Z"}
    )
    (event,) = resp.json()["events"]
    assert event["status"] == "cancelled" and event["template_id"] == rec["id"]


async def test_calendar_validation(auth_client):
    url = f"{API}/calendar"
    assert (await auth_client.get(url, params={"from": "2026-10-01T00:00:00"})).status_code == 422
    resp = await auth_client.get(
        url, params={"from": "2026-10-02T00:00:00Z", "to": "2026-10-01T00:00:00Z"}
    )
    assert resp.status_code == 400
    resp = await auth_client.get(
        url, params={"from": "2026-01-01T00:00:00Z", "to": "2027-06-01T00:00:00Z"}
    )
    assert resp.status_code == 400


async def test_calendar_is_per_user(auth_client, client, session, clock):
    await create_recurring(auth_client)
    params = {"from": "2026-10-01T00:00:00Z", "to": "2026-11-01T00:00:00Z"}
    assert (await auth_client.get(f"{API}/calendar", params=params)).json()["events"]
    async with other_client(client, session) as other:
        assert (await other.get(f"{API}/calendar", params=params)).json()["events"] == []


# ---------- воркер ----------


def test_worker_waits_until_3am_moscow():
    # 06.10 01:00 МСК -> до 03:00 два часа
    assert seconds_until(NIGHTLY_AT, datetime(2026, 10, 5, 22, 0, tzinfo=UTC)) == 2 * 3600
    # 06.10 04:00 МСК -> до завтрашних 03:00 23 часа
    assert seconds_until(NIGHTLY_AT, datetime(2026, 10, 6, 1, 0, tzinfo=UTC)) == 23 * 3600


async def test_calendar_day_off_on_next_day_not_included(auth_client, clock):
    # Экран «Сегодня» запрашивает [00:00, 00:00 следующего дня) — выходной завтра не «сегодня»
    await auth_client.post(
        f"{API}/days-off", json={"date_from": "2026-11-04", "date_to": "2026-11-04", "title": "ДНЕ"}
    )
    resp = await auth_client.get(
        f"{API}/calendar",
        params={"from": "2026-11-03T00:00:00+03:00", "to": "2026-11-04T00:00:00+03:00"},
    )
    assert resp.json()["days_off"] == []
    resp = await auth_client.get(
        f"{API}/calendar",
        params={"from": "2026-11-04T00:00:00+03:00", "to": "2026-11-05T00:00:00+03:00"},
    )
    assert [d["title"] for d in resp.json()["days_off"]] == ["ДНЕ"]


async def test_mark_done_does_not_detach(auth_client, session: AsyncSession, clock):
    # «Сделано» — не ручная правка: серия по-прежнему обновляет вхождение
    await create_recurring(auth_client, kind="personal")
    target = (await live_events(session))[0]
    resp = await auth_client.patch(f"{API}/events/{target.id}", json={"status": "done"})
    assert resp.json()["status"] == "done" and resp.json()["detached"] is False
    # Отмена — ручная правка
    resp = await auth_client.patch(f"{API}/events/{target.id}", json={"status": "cancelled"})
    assert resp.json()["detached"] is True


async def test_reset_when_series_no_longer_has_day(auth_client, session: AsyncSession, clock):
    rec = await create_recurring(auth_client)
    target = (await live_events(session))[0]  # вт 06.10
    await auth_client.patch(f"{API}/events/{target.id}", json={"title": "Тренажёрка"})
    # Серия теперь только по четвергам; правленный вторник остаётся (detached)
    await auth_client.patch(
        f"{API}/recurring-events/{rec['id']}", json={"rrule": "FREQ=WEEKLY;BYDAY=TH"}
    )
    assert (await auth_client.get(f"{API}/events/{target.id}")).status_code == 200
    resp = await auth_client.post(f"{API}/events/{target.id}/reset")
    assert resp.status_code == 200
    assert (await auth_client.get(f"{API}/events/{target.id}")).status_code == 404


async def test_worker_survives_failing_job(monkeypatch):
    from app.worker import __main__ as worker

    async def boom() -> None:
        raise ConnectionError("db down")

    logged: list[str] = []
    monkeypatch.setattr(worker.log, "exception", lambda msg, *a: logged.append(msg % a))
    await worker.safely("Ночная джоба", boom)  # не бросает
    assert logged == ["Ночная джоба: ошибка"]
