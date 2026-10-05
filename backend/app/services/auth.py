from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import hash_token, new_token, verify_password
from app.core.time import now_utc
from app.models import User, UserSession
from app.services.users import get_user_by_email

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
    """Проверяет пароль и создаёт сессию. Возвращает пользователя и токен для cookie."""
    user = await get_user_by_email(db, email)
    if not verify_password(password, user.password_hash if user else None) or user is None:
        raise InvalidCredentialsError()

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
