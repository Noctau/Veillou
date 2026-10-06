import uuid

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.core.time import is_valid_tz
from app.models import User
from app.services.catalog import ensure_defaults

MIN_PASSWORD_LENGTH = 8


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(
        select(User).where(func.lower(User.email) == email.lower(), User.deleted_at.is_(None))
    )


def normalize_email(email: str) -> str:
    try:
        return validate_email(email.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError(f"Некорректный email: {exc}") from exc


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    timezone: str = settings.DEFAULT_TIMEZONE,
) -> User:
    email = normalize_email(email)
    validate_password(password)
    if not is_valid_tz(timezone):
        raise ValueError(f"Неизвестный часовой пояс: {timezone}")
    if await session.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise ConflictError("Пользователь с таким email уже есть", code="email_taken")

    user = User(email=email, password_hash=hash_password(password), timezone=timezone)
    session.add(user)
    await session.flush()
    await ensure_defaults(session, user.id)
    await session.commit()
    return user


async def set_password(session: AsyncSession, user: User, password: str) -> None:
    validate_password(password)
    user.password_hash = hash_password(password)
    await session.commit()
