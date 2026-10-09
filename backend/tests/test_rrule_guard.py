"""L-01: правило без единого вхождения отклоняется, и перебор дат идёт не в event loop."""

import threading

import pytest
from httpx import AsyncClient

from app.domain import recurrence

API = "/api/v1"
IMPOSSIBLE = "FREQ=DAILY;BYMONTH=2;BYMONTHDAY=30"


def test_has_occurrences():
    assert recurrence.has_occurrences("FREQ=WEEKLY;BYDAY=TU")
    assert recurrence.has_occurrences("FREQ=DAILY;BYMONTH=2;BYMONTHDAY=29")  # високосные
    assert not recurrence.has_occurrences(IMPOSSIBLE)


async def test_recurring_event_with_impossible_rule(auth_client: AsyncClient):
    body = {
        "title": "Никогда",
        "rrule": IMPOSSIBLE,
        "start_date": "2026-10-01",
        "start_time": "10:00",
        "end_time": "11:00",
    }
    resp = await auth_client.post(f"{API}/recurring-events", json=body)
    assert resp.status_code == 400
    assert "ни одного" in resp.json()["error"]["message"]


async def test_recurring_task_with_impossible_rule(auth_client: AsyncClient):
    resp = await auth_client.post(f"{API}/tasks", json={"title": "x", "recurrence": IMPOSSIBLE})
    assert resp.status_code == 400
    task = (await auth_client.post(f"{API}/tasks", json={"title": "x"})).json()
    resp = await auth_client.patch(f"{API}/tasks/{task['id']}", json={"recurrence": IMPOSSIBLE})
    assert resp.status_code == 400


async def test_check_runs_in_thread(auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    loop_thread = threading.get_ident()
    seen: list[int] = []
    original = recurrence.has_occurrences

    def spy(value: str) -> bool:
        seen.append(threading.get_ident())
        return original(value)

    monkeypatch.setattr(recurrence, "has_occurrences", spy)
    resp = await auth_client.post(
        f"{API}/tasks", json={"title": "x", "recurrence": "FREQ=WEEKLY;BYDAY=TH"}
    )
    assert resp.status_code == 201
    assert seen
    assert loop_thread not in seen
