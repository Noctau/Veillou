from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, InvalidDataError, UnauthorizedError
from app.core.security import (
    hash_password_async,
    hash_token,
    new_token,
    verify_password_async,
)
from app.core.time import now_utc
from app.models import User, UserSession
from app.services import login_guard
from app.services.users import get_user_by_email, validate_password

# Срок жизни сессии продлевается не чаще раза в сутки, чтобы не писать в БД на каждый запрос
RENEW_AFTER = timedelta(days=1)


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"
    message = "Неверный email или пароль"


@dataclass
class ActiveSession:
    user: User
    session: UserSession
    renewed: bool  # срок продлён -> cookie нужно переустановить


def session_ttl() -> timedelta:
    return timedelta(days=settings.SESSION_TTL_DAYS)


async def login(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[User, str]:
    """Проверяет пароль и создаёт сессию. Возвращает пользователя и токен для cookie.

    Перебор ограничен (`login_guard`): после серии ошибок — 429 без проверки пароля.
    """
    await login_guard.check(db, ip=ip, email=email)
    user = await get_user_by_email(db, email)
    # Соединение — обратно в пул: в очереди на argon2 запрос не должен его держать
    await db.commit()
    ok = await verify_password_async(password, user.password_hash if user else None)
    if not ok or user is None:
        await login_guard.record_failure(db, ip=ip, email=email)
        raise InvalidCredentialsError()
    await login_guard.clear_account(db, email)

    token = new_token()
    now = now_utc()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + session_ttl(),
            last_seen_at=now,
            user_agent=(user_agent or "")[:512] or None,
            ip=ip,
        )
    )
    await db.commit()
    return user, token


async def resolve_session(db: AsyncSession, token: str) -> ActiveSession | None:
    """Пользователь по токену сессии; None, если сессия не найдена, удалена или истекла."""
    now = now_utc()
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.token_hash == hash_token(token),
                UserSession.deleted_at.is_(None),
                UserSession.expires_at > now,
                User.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        return None

    session, user = row
    renewed = now - session.last_seen_at >= RENEW_AFTER
    if renewed:
        session.last_seen_at = now
        session.expires_at = now + session_ttl()
        await db.commit()
    return ActiveSession(user=user, session=session, renewed=renewed)


async def logout(db: AsyncSession, token: str) -> None:
    await db.execute(
        update(UserSession)
        .where(UserSession.token_hash == hash_token(token), UserSession.deleted_at.is_(None))
        .values(deleted_at=now_utc())
    )
    await db.commit()


class WrongPasswordError(AppError):
    # Не 401: сессия жива, просто неверный текущий пароль
    code = "wrong_password"
    message = "Текущий пароль неверный"


class SamePasswordError(AppError):
    code = "same_password"
    message = "Новый пароль совпадает с текущим"


async def change_password(
    db: AsyncSession,
    user: User,
    *,
    current: str,
    new: str,
    keep_token: str | None,
    ip: str | None = None,
) -> None:
    """Смена пароля из настроек: нужен текущий пароль.

    Перебор текущего пароля ограничен так же, как вход (`login_guard`). Остальные
    сессии закрываются (пароль мог утечь), текущая — остаётся. Коммитит.
    """
    try:
        validate_password(new)
    except ValueError as exc:
        raise InvalidDataError(str(exc)) from exc
    await login_guard.check(db, ip=ip, email=user.email)
    password_hash = user.password_hash
    await db.commit()  # соединение — в пул, пока argon2 в очереди
    if not await verify_password_async(current, password_hash):
        await login_guard.record_failure(db, ip=ip, email=user.email)
        raise WrongPasswordError()
    if current == new:
        raise SamePasswordError()
    user.password_hash = await hash_password_async(new)
    others = [UserSession.user_id == user.id, UserSession.deleted_at.is_(None)]
    if keep_token:
        others.append(UserSession.token_hash != hash_token(keep_token))
    await db.execute(update(UserSession).where(*others).values(deleted_at=now_utc()))
    await login_guard.clear_account(db, user.email)
    await db.commit()


# Сколько хранить истёкшие и закрытые сессии (для разбора «кто входил»)
KEEP_SESSIONS = timedelta(days=30)


async def prune_sessions(db: AsyncSession) -> None:
    """Ночная чистка: давно истёкшие и закрытые сессии удаляются."""
    cutoff = now_utc() - KEEP_SESSIONS
    await db.execute(
        delete(UserSession).where(
            or_(UserSession.expires_at < cutoff, UserSession.deleted_at < cutoff)
        )
    )
    await db.commit()
