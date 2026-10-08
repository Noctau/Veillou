"""Защита входа (H-01): перебор пароля ограничен, argon2 не блокирует event loop."""

import asyncio
import threading
import time
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.core.time import now_utc
from app.models import LoginFailure, User
from app.services import login_guard

from .conftest import PASSWORD

API = "/api/v1"


async def login(client: AsyncClient, password: str = PASSWORD, email: str = "student@example.com"):
    return await client.post(f"{API}/auth/login", json={"email": email, "password": password})


async def failures(session: AsyncSession, key: str) -> int:
    return await session.scalar(
        select(func.count()).select_from(LoginFailure).where(LoginFailure.key == key)
    )


async def test_password_check_runs_outside_event_loop(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
):
    loop_thread = threading.get_ident()
    seen: list[int] = []
    original = security._password_hash.verify

    def spy(password: str, hashed: str) -> bool:
        seen.append(threading.get_ident())
        return original(password, hashed)

    monkeypatch.setattr(security._password_hash, "verify", spy)
    assert (await login(client)).status_code == 200
    assert (await login(client, "wrong-password")).status_code == 401
    assert seen and loop_thread not in seen


async def test_concurrent_password_checks_are_bounded(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
):
    """argon2 съедает 64 МБ на проверку — одновременно их немного."""
    active = peak = 0
    lock = threading.Lock()

    def slow_verify(password: str, hashed: str) -> bool:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return False

    monkeypatch.setattr(security._password_hash, "verify", slow_verify)
    await asyncio.gather(*(login(client, "wrong") for _ in range(8)))
    assert 1 <= peak <= security.MAX_CONCURRENT_HASHES


async def test_too_many_failures_from_ip_are_rejected_without_hashing(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES_PER_IP", 3)
    for _ in range(3):
        assert (await login(client, "wrong-password")).status_code == 401

    calls = 0
    original = security._password_hash.verify

    def counting(password: str, hashed: str) -> bool:
        nonlocal calls
        calls += 1
        return original(password, hashed)

    monkeypatch.setattr(security._password_hash, "verify", counting)
    resp = await login(client)  # даже верный пароль — подождать
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "too_many_login_attempts"
    assert 0 < int(resp.headers["retry-after"]) <= settings.LOGIN_WINDOW_MIN * 60
    assert calls == 0


async def test_too_many_failures_for_account_from_any_ip(
    client: AsyncClient, user: User, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES_PER_ACCOUNT", 2)
    # Ошибки с других адресов тоже считаются для аккаунта
    for ip in ("10.0.0.1", "10.0.0.2"):
        session.add(LoginFailure(key=login_guard.ip_key(ip)))
        session.add(LoginFailure(key=login_guard.account_key("student@example.com")))
    await session.commit()
    resp = await login(client, email="Student@Example.com")
    assert resp.status_code == 429


async def test_old_failures_do_not_count(
    client: AsyncClient, user: User, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES_PER_IP", 2)
    long_ago = now_utc() - timedelta(minutes=settings.LOGIN_WINDOW_MIN + 1)
    for _ in range(5):
        session.add(LoginFailure(key=login_guard.ip_key("127.0.0.1"), created_at=long_ago))
    await session.commit()
    assert (await login(client)).status_code == 200


async def test_success_clears_account_failures(
    client: AsyncClient, user: User, session: AsyncSession
):
    for _ in range(2):
        await login(client, "wrong-password")
    key = login_guard.account_key("student@example.com")
    assert await failures(session, key) == 2
    assert (await login(client)).status_code == 200
    assert await failures(session, key) == 0


async def test_unknown_email_counts_as_failure(client: AsyncClient, session: AsyncSession):
    assert (await login(client, email="nobody@example.com")).status_code == 401
    assert await failures(session, login_guard.account_key("nobody@example.com")) == 1
    assert await failures(session, login_guard.ip_key("127.0.0.1")) == 1


async def test_password_length_is_limited(client: AsyncClient, user: User):
    resp = await login(client, "x" * 1025)
    assert resp.status_code == 422


async def test_prune_removes_expired_failures(session: AsyncSession):
    old = now_utc() - timedelta(minutes=settings.LOGIN_WINDOW_MIN + 1)
    session.add(LoginFailure(key="ip:1.1.1.1", created_at=old))
    session.add(LoginFailure(key="ip:1.1.1.1"))
    await session.commit()
    await login_guard.prune(session)
    assert await failures(session, "ip:1.1.1.1") == 1


async def test_password_check_does_not_hold_db_connection(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
):
    """В очереди на argon2 запрос не держит соединение пула — иначе флуд логинов
    выбирает весь пул и встаёт остальное API."""
    held: list[int] = []
    original = security._password_hash.verify

    def spy(password: str, hashed: str) -> bool:
        held.append(engine.pool.checkedout())
        return original(password, hashed)

    monkeypatch.setattr(security._password_hash, "verify", spy)
    assert (await login(client, "wrong-password")).status_code == 401
    assert (await login(client)).status_code == 200
    assert held == [0, 0]
