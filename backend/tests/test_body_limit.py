"""M-01: большое тело отклоняется до аутентификации и разбора (413), загрузки — свой лимит."""

from collections.abc import AsyncIterator
from pathlib import Path

import anyio
import pytest
from httpx import AsyncClient

from app.core.body_limit import MIB, request_body_limit
from app.core.config import settings

from .test_tasks import make_task

API = "/api/v1"


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "STORAGE_DIR", tmp_path)
    return tmp_path


def big(size: int) -> bytes:
    return b"{" + b" " * (size - 2) + b"}"


async def chunks(size: int, chunk: int = 256 * 1024) -> AsyncIterator[bytes]:
    sent = 0
    while sent < size:
        yield b" " * min(chunk, size - sent)
        sent += chunk


def test_limits_by_path():
    assert request_body_limit(f"{API}/attachments") == (settings.MAX_UPLOAD_MB + 1) * MIB
    assert request_body_limit(f"{API}/attachments/abc/replace") > 100 * MIB
    assert request_body_limit(f"{API}/tasks") == settings.MAX_REQUEST_BODY_KB * 1024
    assert request_body_limit(f"{API}/attachments/order") == settings.MAX_REQUEST_BODY_KB * 1024


async def test_anonymous_big_json_rejected_before_auth(client: AsyncClient):
    resp = await client.post(
        f"{API}/tasks", content=big(3 * MIB), headers={"content-type": "application/json"}
    )
    assert resp.status_code == 413  # не 401: тело не читалось
    assert resp.json()["error"]["code"] == "request_too_large"


async def test_chunked_body_without_length_is_counted(client: AsyncClient):
    resp = await client.post(
        f"{API}/auth/login",
        content=chunks(3 * MIB),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 413


async def test_upload_has_its_own_limit(auth_client: AsyncClient, storage: Path):
    task = await make_task(auth_client)
    resp = await auth_client.post(
        f"{API}/attachments",
        data={"owner_type": "task", "owner_id": task["id"]},
        files={"file": ("big.pdf", b"%PDF" + b"0" * (3 * MIB), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text


async def test_upload_over_limit_rejected_before_parsing(
    auth_client: AsyncClient, storage: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    task = await make_task(auth_client)
    resp = await auth_client.post(
        f"{API}/attachments",
        data={"owner_type": "task", "owner_id": task["id"]},
        files={"file": ("big.pdf", b"0" * (3 * MIB), "application/pdf")},
    )
    assert resp.status_code == 413
    assert [p async for p in anyio.Path(storage).rglob("*.part")] == []


async def test_largest_json_still_fits(auth_client: AsyncClient):
    """Самый большой JSON — конспект на 200 000 символов кириллицы (~0.4 МБ UTF-8)."""
    body = {"title": "Лекция", "body_md": "текст\n" * 33_000}
    resp = await auth_client.post(f"{API}/notes", json=body)
    assert resp.status_code == 201, resp.text
