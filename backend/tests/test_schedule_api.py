from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import AsyncClient

from .conftest import PASSWORD

API = "/api/v1"

SEMESTER = {
    "name": "Осень 2026",
    "start_date": "2026-09-01",
    "classes_end": "2026-12-27",
    "session_start": "2027-01-09",
    "session_end": "2027-01-25",
    "first_week_parity": "odd",
}

BELLS = [
    {"number": 1, "start": "09:00", "end": "10:35"},
    {"number": 2, "start": "10:45", "end": "12:20"},
    {"number": 3, "start": "13:00", "end": "14:35"},
]


async def make_semester(client: AsyncClient, **over) -> dict:
    resp = await client.post(f"{API}/semesters", json={**SEMESTER, **over})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def make_subject(client: AsyncClient, semester_id: str, **over) -> dict:
    body = {"semester_id": semester_id, "name": "Климатология", "short_name": "клим", **over}
    resp = await client.post(f"{API}/subjects", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@asynccontextmanager
async def other_client(client: AsyncClient, session) -> AsyncIterator[AsyncClient]:
    from app.services.users import create_user

    await create_user(session, email="other@example.com", password=PASSWORD)
    async with AsyncClient(transport=client._transport, base_url="http://test") as other:
        await other.post(
            f"{API}/auth/login", json={"email": "other@example.com", "password": PASSWORD}
        )
        yield other


async def test_requires_auth(client: AsyncClient):
    for url in ("/semesters", "/subjects", "/class-rules", "/days-off"):
        assert (await client.get(API + url)).status_code == 401


# ---------- семестр ----------


async def test_semester_crud(auth_client: AsyncClient):
    sem = await make_semester(auth_client)
    assert sem["first_week_parity"] == "odd"

    resp = await auth_client.patch(
        f"{API}/semesters/{sem['id']}", json={"first_week_parity": "even"}
    )
    assert resp.status_code == 200
    assert resp.json()["first_week_parity"] == "even"
    assert resp.json()["classes_end"] == SEMESTER["classes_end"]

    assert [s["id"] for s in (await auth_client.get(f"{API}/semesters")).json()] == [sem["id"]]
    assert (await auth_client.delete(f"{API}/semesters/{sem['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/semesters")).json() == []


async def test_semester_validation(auth_client: AsyncClient):
    resp = await auth_client.post(
        f"{API}/semesters", json={**SEMESTER, "classes_end": "2026-08-01"}
    )
    assert resp.status_code == 422
    resp = await auth_client.post(f"{API}/semesters", json={**SEMESTER, "session_end": None})
    assert resp.status_code == 422

    sem = await make_semester(auth_client)
    # PATCH валидирует итог: конец занятий раньше начала
    resp = await auth_client.patch(
        f"{API}/semesters/{sem['id']}", json={"start_date": "2027-02-01"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_data"


# ---------- звонки ----------


async def test_bells_replace(auth_client: AsyncClient):
    sem = await make_semester(auth_client)
    url = f"{API}/semesters/{sem['id']}/bells"
    saturday = [{"number": 1, "start": "09:30", "end": "11:00"}]
    body = {"schedules": [{"weekday": None, "slots": BELLS}, {"weekday": 6, "slots": saturday}]}
    resp = await auth_client.put(url, json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json() == [{"weekday": None, "slots": BELLS}, {"weekday": 6, "slots": saturday}]

    # Повторная замена: старые уходят
    resp = await auth_client.put(url, json={"schedules": [{"weekday": None, "slots": BELLS[:1]}]})
    assert resp.status_code == 200
    assert (await auth_client.get(url)).json() == [{"weekday": None, "slots": BELLS[:1]}]


async def test_bells_validation(auth_client: AsyncClient):
    sem = await make_semester(auth_client)
    url = f"{API}/semesters/{sem['id']}/bells"
    overlap = [
        {"number": 1, "start": "09:00", "end": "10:35"},
        {"number": 2, "start": "10:00", "end": "11:00"},
    ]
    for schedules in (
        [{"weekday": None, "slots": overlap}],
        [{"weekday": None, "slots": BELLS}, {"weekday": None, "slots": BELLS}],
        [{"weekday": None, "slots": [{"number": 1, "start": "10:00", "end": "09:00"}]}],
        [{"weekday": 8, "slots": BELLS}],
    ):
        resp = await auth_client.put(url, json={"schedules": schedules})
        assert resp.status_code == 422, schedules


# ---------- выходные ----------


async def test_days_off(auth_client: AsyncClient):
    resp = await auth_client.post(
        f"{API}/days-off", json={"date_from": "2026-11-04", "date_to": "2026-11-04", "title": "ДНЕ"}
    )
    assert resp.status_code == 201
    day = resp.json()
    resp = await auth_client.patch(f"{API}/days-off/{day['id']}", json={"date_to": "2026-11-01"})
    assert resp.status_code == 400
    assert (await auth_client.delete(f"{API}/days-off/{day['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/days-off")).json() == []


# ---------- предметы ----------


async def test_subject_crud(auth_client: AsyncClient):
    sem = await make_semester(auth_client)
    subj = await make_subject(
        auth_client,
        sem["id"],
        color="#10b981",
        control_form="graded_credit",
        teachers=[{"name": "Иванова А. П.", "role": "лектор"}],
        links=[{"title": "Курс", "url": "https://example.com/course"}],
        synonyms=["климат"],
    )
    assert subj["teachers"] == [{"name": "Иванова А. П.", "role": "лектор", "contact": ""}]
    assert subj["links"] == [{"title": "Курс", "url": "https://example.com/course"}]

    resp = await auth_client.patch(f"{API}/subjects/{subj['id']}", json={"short_name": None})
    assert resp.status_code == 200
    assert resp.json()["short_name"] is None
    assert resp.json()["synonyms"] == ["климат"]

    resp = await auth_client.patch(f"{API}/subjects/{subj['id']}", json={"color": "red"})
    assert resp.status_code == 400

    listed = await auth_client.get(f"{API}/subjects", params={"semester_id": sem["id"]})
    assert [s["id"] for s in listed.json()] == [subj["id"]]
    assert (await auth_client.delete(f"{API}/subjects/{subj['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/subjects/{subj['id']}")).status_code == 404


async def test_subject_link_must_be_url(auth_client: AsyncClient):
    resp = await auth_client.post(
        f"{API}/subjects", json={"name": "X", "links": [{"url": "not a url"}]}
    )
    assert resp.status_code == 422


# ---------- правила пар ----------


async def test_class_rule_crud(auth_client: AsyncClient):
    sem = await make_semester(auth_client)
    subj = await make_subject(auth_client, sem["id"])
    body = {
        "semester_id": sem["id"],
        "subject_id": subj["id"],
        "weekday": 2,
        "pair_number": 3,
        "parity": "odd",
        "class_type": "seminar",
        "location": "1801",
    }
    resp = await auth_client.post(f"{API}/class-rules", json=body)
    assert resp.status_code == 201, resp.text
    rule = resp.json()
    assert rule["start_time"] is None

    resp = await auth_client.patch(
        f"{API}/class-rules/{rule['id']}", json={"start_time": "18:30", "end_time": "20:00"}
    )
    assert resp.status_code == 200
    assert (resp.json()["start_time"], resp.json()["end_time"]) == ("18:30", "20:00")

    # Только начало без конца -> итог невалиден
    resp = await auth_client.patch(f"{API}/class-rules/{rule['id']}", json={"end_time": None})
    assert resp.status_code == 400

    # Удаление предмета удаляет его пары
    await auth_client.delete(f"{API}/subjects/{subj['id']}")
    assert (await auth_client.get(f"{API}/class-rules")).json() == []


async def test_class_rule_validation(auth_client: AsyncClient):
    sem = await make_semester(auth_client)
    subj = await make_subject(auth_client, sem["id"])
    base = {"semester_id": sem["id"], "subject_id": subj["id"], "weekday": 1}
    resp = await auth_client.post(f"{API}/class-rules", json=base)
    assert resp.status_code == 422  # ни номера пары, ни времени
    resp = await auth_client.post(
        f"{API}/class-rules", json={**base, "pair_number": 1, "weekday": 0}
    )
    assert resp.status_code == 422


async def test_other_users_data_invisible(auth_client: AsyncClient, client: AsyncClient, session):
    sem = await make_semester(auth_client)
    subj = await make_subject(auth_client, sem["id"])
    async with other_client(client, session) as other:
        assert (await other.get(f"{API}/semesters")).json() == []
        assert (await other.get(f"{API}/subjects/{subj['id']}")).status_code == 404
        assert (await other.patch(f"{API}/semesters/{sem['id']}", json={})).status_code == 404
        # Нельзя повесить пару на чужой семестр/предмет
        other_sem = await make_semester(other)
        resp = await other.post(
            f"{API}/class-rules",
            json={
                "semester_id": other_sem["id"],
                "subject_id": subj["id"],
                "weekday": 1,
                "pair_number": 1,
            },
        )
        assert resp.status_code == 404


# ---------- события ----------


async def test_personal_event_crud(auth_client: AsyncClient):
    body = {
        "title": "Бассейн",
        "start": "2026-10-07T18:00:00+03:00",
        "end": "2026-10-07T19:00:00+03:00",
    }
    resp = await auth_client.post(f"{API}/events", json=body)
    assert resp.status_code == 201, resp.text
    event = resp.json()
    assert event["kind"] == "personal"
    assert event["is_fixed"] is True
    assert event["start"] == "2026-10-07T15:00:00Z"

    resp = await auth_client.patch(f"{API}/events/{event['id']}", json={"status": "done"})
    assert resp.json()["status"] == "done"
    assert resp.json()["detached"] is False  # разовое событие — не вхождение шаблона

    resp = await auth_client.patch(
        f"{API}/events/{event['id']}", json={"end": "2026-10-07T17:00:00+03:00"}
    )
    assert resp.status_code == 400

    assert (await auth_client.delete(f"{API}/events/{event['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/events/{event['id']}")).status_code == 404


async def test_event_rejects_naive_and_class_kind(auth_client: AsyncClient):
    naive = {"title": "x", "start": "2026-10-07T18:00:00", "end": "2026-10-07T19:00:00"}
    assert (await auth_client.post(f"{API}/events", json=naive)).status_code == 422
    cls = {
        "kind": "class",
        "title": "x",
        "start": "2026-10-07T18:00:00Z",
        "end": "2026-10-07T19:00:00Z",
    }
    assert (await auth_client.post(f"{API}/events", json=cls)).status_code == 422
