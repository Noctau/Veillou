import time
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.storage import LocalStorage, get_storage
from app.main import app

from .test_schedule_api import API, other_client
from .test_tasks import make_task

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 2048


@pytest.fixture(autouse=True)
def storage(tmp_path: Path):
    app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    yield tmp_path
    app.dependency_overrides.pop(get_storage, None)


async def upload(
    client: AsyncClient,
    owner_id: str,
    content: bytes = PNG,
    filename: str = "доска.png",
    mime: str = "image/png",
):
    return await client.post(
        f"{API}/attachments",
        data={"owner_type": "task", "owner_id": owner_id},
        files={"file": (filename, content, mime)},
    )


def stored_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and "tmp" not in p.parts]


async def test_upload_list_and_download(auth_client, storage):
    task = await make_task(auth_client)
    resp = await upload(auth_client, task["id"])
    assert resp.status_code == 201, resp.text
    att = resp.json()
    assert (att["filename"], att["mime"], att["size"]) == ("доска.png", "image/png", len(PNG))
    assert att["url"].startswith(f"{API}/files/{att['id']}?exp=")

    listed = (
        await auth_client.get(
            f"{API}/attachments", params={"owner_type": "task", "owner_id": task["id"]}
        )
    ).json()
    assert [a["id"] for a in listed] == [att["id"]]

    # Ссылка работает без cookie
    async with AsyncClient(transport=auth_client._transport, base_url="http://test") as anon:
        resp = await anon.get(att["url"])
        assert resp.status_code == 200
        assert resp.content == PNG
        assert resp.headers["content-type"] == "image/png"
        assert resp.headers["content-disposition"].startswith("inline;")
        resp = await anon.get(att["download_url"])
        assert resp.headers["content-disposition"].startswith("attachment;")


async def test_dedupe_by_content(auth_client, storage):
    first = await make_task(auth_client, title="Первое")
    second = await make_task(auth_client, title="Второе")
    a = (await upload(auth_client, first["id"])).json()
    b = (await upload(auth_client, second["id"], filename="копия.png")).json()
    again = (await upload(auth_client, first["id"])).json()
    assert a["id"] != b["id"]
    assert again["id"] == a["id"]  # тот же файл к тому же заданию — не дублируется
    assert len(stored_files(storage)) == 1


async def test_bad_signature_and_expired_link(auth_client, storage, monkeypatch):
    task = await make_task(auth_client)
    att = (await upload(auth_client, task["id"])).json()
    tampered = att["url"].replace("sig=", "sig=0")
    assert (await auth_client.get(tampered)).status_code == 403
    other_id = att["url"].replace(att["id"], "00000000-0000-0000-0000-000000000000")
    assert (await auth_client.get(other_id)).status_code == 403

    future = time.time() + settings.FILE_URL_TTL_MIN * 60 + 5
    monkeypatch.setattr("app.services.attachments.time.time", lambda: future)
    assert (await auth_client.get(att["url"])).status_code == 403


async def test_dangerous_types_are_not_inline(auth_client, storage):
    task = await make_task(auth_client)
    html = b"<script>alert(1)</script>"
    att = (await upload(auth_client, task["id"], html, "x.html", "text/html")).json()
    resp = await auth_client.get(att["url"])
    assert resp.headers["content-disposition"].startswith("attachment;")
    assert resp.headers["content-type"] == "application/octet-stream"
    assert resp.headers["content-security-policy"] == "sandbox"


async def test_size_limit_and_empty(auth_client, storage, monkeypatch):
    task = await make_task(auth_client)
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0)
    resp = await upload(auth_client, task["id"])
    assert resp.status_code == 413
    assert stored_files(storage) == []
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    assert (await upload(auth_client, task["id"], b"")).status_code == 400


async def test_filename_sanitized_and_rename(auth_client, storage):
    task = await make_task(auth_client)
    att = (await upload(auth_client, task["id"], filename="../../etc/passwd")).json()
    assert att["filename"] == "passwd"
    resp = await auth_client.patch(f"{API}/attachments/{att['id']}", json={"filename": "фото.png"})
    assert resp.json()["filename"] == "фото.png"


async def test_delete_and_owner_checks(auth_client, storage, session):
    task = await make_task(auth_client)
    att = (await upload(auth_client, task["id"])).json()
    resp = await upload(auth_client, "00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404

    async with other_client(auth_client, session) as other:
        assert (await upload(other, task["id"])).status_code == 404
        assert (await other.delete(f"{API}/attachments/{att['id']}")).status_code == 404

    # Удаление задания убирает его вложения, ссылка перестаёт работать
    await auth_client.delete(f"{API}/tasks/{task['id']}")
    assert (await auth_client.get(att["url"])).status_code == 404
