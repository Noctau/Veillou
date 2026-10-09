"""M-09: даты и длительности ограничены — без OverflowError и сотен тысяч вхождений."""

import pytest
from httpx import AsyncClient

from .test_schedule_api import SEMESTER, make_semester
from .test_tasks import make_task

API = "/api/v1"


@pytest.mark.parametrize(
    "over",
    [
        {"classes_end": "9999-12-31", "session_start": None, "session_end": None},
        {"start_date": "1900-09-01"},
        # Длиннее года
        {"classes_end": "2027-12-27", "session_start": "2028-01-09", "session_end": "2028-01-25"},
        {"session_end": "2027-12-25"},
    ],
)
async def test_semester_dates_are_bounded(auth_client: AsyncClient, over: dict):
    resp = await auth_client.post(f"{API}/semesters", json={**SEMESTER, **over})
    assert resp.status_code == 422, resp.text


async def test_semester_patch_is_bounded(auth_client: AsyncClient):
    sem = await make_semester(auth_client)
    resp = await auth_client.patch(
        f"{API}/semesters/{sem['id']}",
        json={"classes_end": "9999-12-01", "session_start": None, "session_end": None},
    )
    assert resp.status_code in (400, 422), resp.text


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("3000-01-01T10:00:00Z", "3000-01-01T11:00:00Z"),
        ("2026-10-20T10:00:00Z", "2026-12-20T10:00:00Z"),  # два месяца
    ],
)
async def test_event_is_bounded(auth_client: AsyncClient, start: str, end: str):
    resp = await auth_client.post(f"{API}/events", json={"title": "x", "start": start, "end": end})
    assert resp.status_code == 422, resp.text


async def test_event_patch_duration_is_bounded(auth_client: AsyncClient):
    ev = (
        await auth_client.post(
            f"{API}/events",
            json={"title": "x", "start": "2026-10-20T10:00:00Z", "end": "2026-10-20T11:00:00Z"},
        )
    ).json()
    resp = await auth_client.patch(f"{API}/events/{ev['id']}", json={"end": "2027-10-20T11:00:00Z"})
    assert resp.status_code == 400, resp.text


async def test_subtask_block_is_at_most_a_day(auth_client: AsyncClient):
    task = await make_task(auth_client, subtasks=[{"title": "Шаг"}])
    sub = task["subtasks"][0]
    resp = await auth_client.post(
        f"{API}/subtasks/{sub['id']}/schedule",
        json={"start": "2026-10-20T10:00:00Z", "end": "2026-10-22T10:00:00Z"},
    )
    assert resp.status_code == 422, resp.text


async def test_day_off_range_is_bounded(auth_client: AsyncClient):
    resp = await auth_client.post(
        f"{API}/days-off", json={"date_from": "2026-01-01", "date_to": "2028-01-01"}
    )
    assert resp.status_code == 422, resp.text


async def test_recurring_until_is_bounded(auth_client: AsyncClient):
    body = {
        "title": "Бассейн",
        "rrule": "FREQ=WEEKLY;BYDAY=TU",
        "start_date": "2026-10-01",
        "until": "9999-12-31",
        "start_time": "10:00",
        "end_time": "11:00",
    }
    resp = await auth_client.post(f"{API}/recurring-events", json=body)
    assert resp.status_code == 422, resp.text


async def test_normal_values_still_work(auth_client: AsyncClient):
    await make_semester(auth_client)
    resp = await auth_client.post(
        f"{API}/events",
        json={"title": "Поездка", "start": "2026-10-20T10:00:00Z", "end": "2026-10-25T10:00:00Z"},
    )
    assert resp.status_code == 201, resp.text


# ---------- L-13: длины полей ----------


async def test_event_note_is_limited(auth_client: AsyncClient):
    body = {"title": "x", "start": "2026-10-20T10:00:00Z", "end": "2026-10-20T11:00:00Z"}
    resp = await auth_client.post(f"{API}/events", json={**body, "note": "а" * 5001})
    assert resp.status_code == 422
    ev = (await auth_client.post(f"{API}/events", json=body)).json()
    resp = await auth_client.patch(f"{API}/events/{ev['id']}", json={"note": "а" * 5001})
    assert resp.status_code == 422


async def test_reminder_channels_are_limited(auth_client: AsyncClient):
    resp = await auth_client.patch(
        f"{API}/me/settings",
        json={"reminders": {"deadlines": {"channels": ["push"] * 1000}}},
    )
    assert resp.status_code in (400, 422)
    ok = await auth_client.patch(
        f"{API}/me/settings", json={"reminders": {"deadlines": {"channels": ["push", "push"]}}}
    )
    assert ok.status_code == 200
    assert ok.json()["reminders"]["deadlines"]["channels"] == ["push"]
