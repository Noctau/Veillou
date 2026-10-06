from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.storage import LocalStorage, get_storage
from app.main import app

from .test_schedule_api import API, make_semester, make_subject, other_client


@pytest.fixture(autouse=True)
def storage(tmp_path: Path):
    app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    yield tmp_path
    app.dependency_overrides.pop(get_storage, None)


async def make_source(client: AsyncClient, subject_id: str, **over) -> dict:
    body = {"subject_id": subject_id, "title": "Курс общей метеорологии", **over}
    resp = await client.post(f"{API}/sources", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def subject(auth_client: AsyncClient) -> dict:
    sem = await make_semester(auth_client)
    return await make_subject(auth_client, sem["id"])


async def test_requires_auth(client: AsyncClient):
    assert (await client.get(f"{API}/sources")).status_code == 401


async def test_source_crud_and_order(auth_client: AsyncClient, subject):
    book = await make_source(auth_client, subject["id"], author="Матвеев Л. Т.")
    assert (book["kind"], book["status"], book["required"]) == ("textbook", "to_read", True)
    extra = await make_source(
        auth_client,
        subject["id"],
        title="Статья про циклоны",
        kind="article",
        required=False,
        url="https://elibrary.ru/item.asp?id=1",
    )
    site = await make_source(auth_client, subject["id"], title="Сайт", kind="website")

    resp = await auth_client.patch(f"{API}/sources/{site['id']}", json={"status": "reading"})
    assert resp.json()["status"] == "reading"
    resp = await auth_client.patch(f"{API}/sources/{site['id']}", json={"title": None})
    assert resp.status_code == 400

    listed = (await auth_client.get(f"{API}/sources", params={"subject_id": subject["id"]})).json()
    # Обязательные первыми, «читаю» выше «прочитать»; дополнительные — в конце
    assert [s["id"] for s in listed] == [site["id"], book["id"], extra["id"]]
    assert listed[2]["url"] == "https://elibrary.ru/item.asp?id=1"

    assert (await auth_client.delete(f"{API}/sources/{book['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/sources/{book['id']}")).status_code == 404


async def test_source_file(auth_client: AsyncClient, subject):
    source = await make_source(auth_client, subject["id"])
    resp = await auth_client.post(
        f"{API}/attachments",
        data={"owner_type": "source", "owner_id": source["id"]},
        files={"file": ("учебник.pdf", b"%PDF-1.4 book", "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    assert (await auth_client.get(f"{API}/sources/{source['id']}")).json()["files_count"] == 1


async def test_reading_task(auth_client: AsyncClient, subject):
    source = await make_source(
        auth_client, subject["id"], author="Матвеев Л. Т.", url="https://example.com/book"
    )
    resp = await auth_client.post(
        f"{API}/sources/{source['id']}/reading-task",
        json={"chapters": "главы 3–5", "deadline": "2026-10-15T23:59:00+03:00"},
    )
    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["title"] == "Прочитать главы 3–5 — Курс общей метеорологии"
    assert task["task_type"] == "reading"
    assert task["subject_id"] == subject["id"]
    assert (
        task["description"] == "Матвеев Л. Т. — Курс общей метеорологии\nhttps://example.com/book"
    )
    assert task["deadline"] == "2026-10-15T20:59:00Z"

    tasks = (await auth_client.get(f"{API}/tasks", params={"subject_id": subject["id"]})).json()
    assert [t["id"] for t in tasks] == [task["id"]]

    resp = await auth_client.post(f"{API}/sources/{source['id']}/reading-task", json={})
    assert resp.json()["title"] == "Прочитать: Курс общей метеорологии"


async def test_isolation(auth_client: AsyncClient, session, subject):
    source = await make_source(auth_client, subject["id"])
    async with other_client(auth_client, session) as other:
        assert (await other.get(f"{API}/sources")).json() == []
        assert (await other.get(f"{API}/sources/{source['id']}")).status_code == 404
        resp = await other.post(f"{API}/sources/{source['id']}/reading-task", json={})
        assert resp.status_code == 404
        resp = await other.post(
            f"{API}/sources", json={"subject_id": subject["id"], "title": "Чужой"}
        )
        assert resp.status_code == 404
