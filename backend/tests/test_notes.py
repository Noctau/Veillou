from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.storage import LocalStorage, get_storage
from app.main import app

from .test_attachments import PNG
from .test_schedule_api import API, BELLS, make_semester, make_subject, other_client

# Вторник 06.10.2026 15:00 МСК
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr("app.services.notes.now_utc", lambda: NOW)


@pytest.fixture(autouse=True)
def storage(tmp_path: Path):
    app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    yield tmp_path
    app.dependency_overrides.pop(get_storage, None)


async def make_note(client: AsyncClient, **over) -> dict:
    resp = await client.post(f"{API}/notes", json=over)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def class_event(client: AsyncClient, day: str = "2026-10-06") -> tuple[dict, dict]:
    """Предмет и вхождение его пары (1 пара по вторникам) на `day`."""
    sem = await make_semester(client)
    subject = await make_subject(client, sem["id"])
    resp = await client.put(
        f"{API}/semesters/{sem['id']}/bells",
        json={"schedules": [{"weekday": None, "slots": BELLS}]},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{API}/class-rules",
        json={
            "semester_id": sem["id"],
            "subject_id": subject["id"],
            "weekday": 2,
            "pair_number": 1,
            "location": "1801",
        },
    )
    assert resp.status_code == 201, resp.text
    cal = await client.get(
        f"{API}/calendar", params={"from": f"{day}T00:00:00+03:00", "to": f"{day}T23:59:00+03:00"}
    )
    (event,) = [e for e in cal.json()["events"] if e["kind"] == "class"]
    return subject, event


async def test_requires_auth(client: AsyncClient):
    assert (await client.get(f"{API}/notes")).status_code == 401


async def test_text_note_crud(auth_client: AsyncClient):
    sem = await make_semester(auth_client)
    subject = await make_subject(auth_client, sem["id"])
    note = await make_note(
        auth_client,
        subject_id=subject["id"],
        body_md="# Лекция 3\n\nУравнение $p = \\rho R T$",
    )
    # Название и дата по умолчанию
    assert note["title"] == "Климатология · 6 окт"
    assert note["class_date"] == "2026-10-06"
    assert note["kind"] == "text"
    assert note["excerpt"] == "Лекция 3 Уравнение …"
    assert note["event"] is None and note["attachments_count"] == 0

    resp = await auth_client.patch(
        f"{API}/notes/{note['id']}", json={"title": "Термодинамика", "body_md": "новое"}
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["title"], resp.json()["body_md"]) == ("Термодинамика", "новое")

    resp = await auth_client.patch(f"{API}/notes/{note['id']}", json={"title": None})
    assert resp.status_code == 400

    listed = (await auth_client.get(f"{API}/notes", params={"subject_id": subject["id"]})).json()
    assert [n["id"] for n in listed] == [note["id"]]
    assert "body_md" not in listed[0]

    assert (await auth_client.delete(f"{API}/notes/{note['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/notes/{note['id']}")).status_code == 404
    assert (await auth_client.get(f"{API}/notes")).json() == []


async def test_note_without_subject(auth_client: AsyncClient):
    note = await make_note(
        auth_client, title="Мысли", kind="link", url="https://disk.yandex.ru/d/x"
    )
    assert note["subject_id"] is None
    assert note["url"] == "https://disk.yandex.ru/d/x"
    resp = await auth_client.patch(f"{API}/notes/{note['id']}", json={"url": None})
    assert resp.json()["url"] is None
    resp = await auth_client.post(f"{API}/notes", json={"url": "не ссылка"})
    assert resp.status_code == 422


async def test_note_to_class_event(auth_client: AsyncClient):
    subject, event = await class_event(auth_client)
    note = await make_note(auth_client, event_id=event["id"])
    assert note["subject_id"] == subject["id"]
    assert note["class_date"] == "2026-10-06"
    assert note["title"] == "Климатология · 6 окт"
    assert note["event"]["location"] == "1801"
    assert note["event"]["pair_number"] == 1

    listed = (await auth_client.get(f"{API}/notes", params={"event_id": event["id"]})).json()
    assert [n["id"] for n in listed] == [note["id"]]


async def test_relink_to_other_event(auth_client: AsyncClient):
    subject, _ = await class_event(auth_client)
    note = await make_note(auth_client, title="Без пары")
    assert note["class_date"] == "2026-10-06"
    cal = await auth_client.get(
        f"{API}/calendar",
        params={"from": "2026-10-13T00:00:00+03:00", "to": "2026-10-14T00:00:00+03:00"},
    )
    (next_week,) = cal.json()["events"]
    resp = await auth_client.patch(f"{API}/notes/{note['id']}", json={"event_id": next_week["id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["subject_id"] == subject["id"]
    assert resp.json()["class_date"] == "2026-10-13"


async def test_cover_and_attachments_deleted_with_note(auth_client: AsyncClient):
    note = await make_note(auth_client, kind="photo")
    resp = await auth_client.post(
        f"{API}/attachments",
        data={"owner_type": "note", "owner_id": note["id"]},
        files={"file": ("стр1.png", PNG, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    page = resp.json()

    listed = (await auth_client.get(f"{API}/notes")).json()
    assert listed[0]["attachments_count"] == 1
    assert listed[0]["cover_url"].startswith(f"{API}/files/{page['id']}?")
    assert listed[0]["cover_url"].endswith(page["url"][page["url"].index("&v=") :])

    await auth_client.delete(f"{API}/notes/{note['id']}")
    resp = await auth_client.get(
        f"{API}/attachments", params={"owner_type": "note", "owner_id": note["id"]}
    )
    assert resp.status_code == 404  # владельца больше нет


async def test_isolation(auth_client: AsyncClient, session):
    _, event = await class_event(auth_client)
    note = await make_note(auth_client)
    async with other_client(auth_client, session) as other:
        assert (await other.get(f"{API}/notes/{note['id']}")).status_code == 404
        assert (await other.get(f"{API}/notes")).json() == []
        resp = await other.post(f"{API}/notes", json={"event_id": event["id"]})
        assert resp.status_code == 404
        resp = await other.patch(f"{API}/notes/{note['id']}", json={"title": "x"})
        assert resp.status_code == 404


async def test_note_for_event_get_or_create(auth_client: AsyncClient):
    subject, event = await class_event(auth_client)
    url = f"{API}/notes/for-event/{event['id']}"
    resp = await auth_client.post(url, params={"kind": "photo"})
    assert resp.status_code == 201, resp.text
    note = resp.json()
    assert (note["event_id"], note["subject_id"], note["kind"]) == (
        event["id"],
        subject["id"],
        "photo",
    )

    # Второе нажатие открывает тот же конспект
    resp = await auth_client.post(url)
    assert resp.status_code == 200
    assert resp.json()["id"] == note["id"]

    resp = await auth_client.post(f"{API}/notes/for-event/{subject['id']}")
    assert resp.status_code == 404


async def test_reorder_and_replace_pages(auth_client: AsyncClient):
    note = await make_note(auth_client, kind="photo")
    pages = []
    for i in range(3):
        resp = await auth_client.post(
            f"{API}/attachments",
            data={"owner_type": "note", "owner_id": note["id"]},
            files={"file": (f"{i}.png", PNG + bytes([i]), "image/png")},
        )
        pages.append(resp.json())
    ids = [p["id"] for p in pages]
    order = {"owner_type": "note", "owner_id": note["id"]}

    resp = await auth_client.put(
        f"{API}/attachments/order", json={**order, "ids": [ids[2], ids[0], ids[1]]}
    )
    assert resp.status_code == 200, resp.text
    listed = (await auth_client.get(f"{API}/attachments", params=order)).json()
    assert [a["id"] for a in listed] == [ids[2], ids[0], ids[1]]

    # Неполный список или чужой id — ошибка
    resp = await auth_client.put(f"{API}/attachments/order", json={**order, "ids": ids[:2]})
    assert resp.status_code == 400
    resp = await auth_client.put(
        f"{API}/attachments/order", json={**order, "ids": [ids[0], ids[0], ids[1]]}
    )
    assert resp.status_code == 400

    # Повёрнутая страница: то же место, новый файл и новая ссылка
    rotated = PNG + b"rotated"
    resp = await auth_client.post(
        f"{API}/attachments/{ids[0]}/replace",
        files={"file": ("0.jpg", rotated, "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    replaced = resp.json()
    assert (replaced["id"], replaced["position"]) == (ids[0], 1)
    assert (replaced["size"], replaced["mime"]) == (len(rotated), "image/jpeg")
    assert replaced["url"] != pages[0]["url"]
    async with AsyncClient(transport=auth_client._transport, base_url="http://test") as anon:
        assert (await anon.get(replaced["url"])).content == rotated


async def test_pdf_viewable_inline(auth_client: AsyncClient):
    note = await make_note(auth_client, kind="file")
    resp = await auth_client.post(
        f"{API}/attachments",
        data={"owner_type": "note", "owner_id": note["id"]},
        files={"file": ("лекция.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    att = resp.json()
    async with AsyncClient(transport=auth_client._transport, base_url="http://test") as anon:
        resp = await anon.get(att["url"])
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.headers["content-disposition"].startswith("inline")
        assert "content-security-policy" not in resp.headers
        # На скачивание — как обычно, в песочнице
        resp = await anon.get(att["download_url"])
        assert resp.headers["content-security-policy"] == "sandbox"
