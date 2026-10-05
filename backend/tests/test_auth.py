from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.time import now_utc
from app.models import User, UserSession
from app.services import auth, users

from .conftest import PASSWORD

API = "/api/v1"
COOKIE = settings.SESSION_COOKIE_NAME


async def login(client: AsyncClient, email: str = "student@example.com", password: str = PASSWORD):
    return await client.post(f"{API}/auth/login", json={"email": email, "password": password})


async def test_me_without_session_is_401(client: AsyncClient):
    resp = await client.get(f"{API}/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_me_with_garbage_cookie_is_401(client: AsyncClient):
    client.cookies.set(COOKIE, "garbage")
    resp = await client.get(f"{API}/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "session_expired"


async def test_login_sets_httponly_cookie(client: AsyncClient, user: User):
    resp = await login(client, email="STUDENT@example.com")
    assert resp.status_code == 200
    assert resp.json() == {
        "id": str(user.id),
        "email": "student@example.com",
        "timezone": "Europe/Moscow",
    }

    set_cookie = resp.headers["set-cookie"].lower()
    assert f"{COOKIE}=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert f"max-age={settings.SESSION_TTL_DAYS * 86400}" in set_cookie


async def test_session_token_is_stored_hashed(
    client: AsyncClient, user: User, session: AsyncSession
):
    await login(client)
    token = client.cookies[COOKIE]
    stored = await session.scalar(
        select(UserSession.token_hash).where(UserSession.user_id == user.id)
    )
    assert stored is not None and stored != token and len(stored) == 64


async def test_login_wrong_password_or_unknown_email(client: AsyncClient, user: User):
    for email, password in [
        ("student@example.com", "wrong-password"),
        ("nobody@example.com", PASSWORD),
    ]:
        resp = await login(client, email=email, password=password)
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_credentials"
        assert COOKIE not in client.cookies


async def test_login_validation(client: AsyncClient):
    resp = await client.post(f"{API}/auth/login", json={"email": "", "password": "x"})
    assert resp.status_code == 422
    # Произвольная строка — просто «неверный логин», без подсказок о формате
    resp = await client.post(f"{API}/auth/login", json={"email": "not-an-email", "password": "x"})
    assert resp.status_code == 401


async def test_me_with_session(auth_client: AsyncClient):
    resp = await auth_client.get(f"{API}/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "student@example.com"


async def test_logout_invalidates_session(auth_client: AsyncClient):
    token = auth_client.cookies[COOKIE]
    resp = await auth_client.post(f"{API}/auth/logout")
    assert resp.status_code == 204
    assert COOKIE not in auth_client.cookies

    # Старый токен больше не работает, даже если его кто-то сохранил
    auth_client.cookies.set(COOKIE, token)
    assert (await auth_client.get(f"{API}/me")).status_code == 401


async def test_logout_without_session_is_ok(client: AsyncClient):
    assert (await client.post(f"{API}/auth/logout")).status_code == 204


async def test_expired_session_is_401(auth_client: AsyncClient, session: AsyncSession):
    await session.execute(update(UserSession).values(expires_at=now_utc() - timedelta(seconds=1)))
    await session.commit()
    assert (await auth_client.get(f"{API}/me")).status_code == 401


async def test_deleted_user_session_is_401(auth_client: AsyncClient, session: AsyncSession):
    await session.execute(update(User).values(deleted_at=now_utc()))
    await session.commit()
    assert (await auth_client.get(f"{API}/me")).status_code == 401


async def test_session_is_renewed_after_a_day(auth_client: AsyncClient, session: AsyncSession):
    old = now_utc() - timedelta(days=2)
    await session.execute(
        update(UserSession).values(last_seen_at=old, expires_at=old + timedelta(days=3))
    )
    await session.commit()

    resp = await auth_client.get(f"{API}/me")
    assert resp.status_code == 200
    assert COOKIE in resp.headers.get("set-cookie", "")

    session.expire_all()
    expires_at = await session.scalar(select(UserSession.expires_at))
    assert expires_at > now_utc() + auth.session_ttl() - timedelta(minutes=1)


async def test_fresh_session_is_not_renewed(auth_client: AsyncClient):
    resp = await auth_client.get(f"{API}/me")
    assert "set-cookie" not in resp.headers


async def test_create_user_rules(session: AsyncSession, user: User):
    with pytest.raises(ConflictError):
        await users.create_user(session, email="student@EXAMPLE.com", password=PASSWORD)
    with pytest.raises(ValueError, match="короче"):
        await users.create_user(session, email="b@example.com", password="short")
    with pytest.raises(ValueError, match="Некорректный email"):
        await users.create_user(session, email="dev@veillou.test", password=PASSWORD)
    with pytest.raises(ValueError, match="часовой пояс"):
        await users.create_user(
            session, email="b@example.com", password=PASSWORD, timezone="Nope/Nope"
        )


async def test_set_password(client: AsyncClient, session: AsyncSession, user: User):
    await users.set_password(session, user, "another-password")
    assert (await login(client)).status_code == 401
    assert (await login(client, password="another-password")).status_code == 200
