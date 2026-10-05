import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import hash_token
from app.core.time import now_utc
from app.models import TelegramLinkCode, User


class LinkError(AppError):
    code = "telegram_link_failed"


@dataclass
class LinkCode:
    code: str
    expires_at: datetime
    deep_link: str | None


def _deep_link(code: str) -> str | None:
    if not settings.TELEGRAM_BOT_USERNAME:
        return None
    return f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={code}"


async def create_link_code(db: AsyncSession, user: User) -> LinkCode:
    """Новый одноразовый код; прежние неиспользованные коды пользователя гасятся."""
    now = now_utc()
    await db.execute(
        update(TelegramLinkCode)
        .where(
            TelegramLinkCode.user_id == user.id,
            TelegramLinkCode.used_at.is_(None),
            TelegramLinkCode.deleted_at.is_(None),
        )
        .values(deleted_at=now)
    )
    # 16 символов [A-Za-z0-9_-] — годится для deep link (лимит Telegram — 64)
    code = secrets.token_urlsafe(12)
    expires_at = now + timedelta(minutes=settings.TELEGRAM_LINK_CODE_TTL_MIN)
    db.add(TelegramLinkCode(user_id=user.id, code_hash=hash_token(code), expires_at=expires_at))
    await db.commit()
    return LinkCode(code=code, expires_at=expires_at, deep_link=_deep_link(code))


async def link_by_code(db: AsyncSession, code: str, tg_user_id: int) -> User:
    """Привязывает Telegram-аккаунт по коду. Код срабатывает один раз."""
    now = now_utc()
    row = (
        await db.execute(
            select(TelegramLinkCode, User)
            .join(User, User.id == TelegramLinkCode.user_id)
            .where(
                TelegramLinkCode.code_hash == hash_token(code.strip()),
                TelegramLinkCode.deleted_at.is_(None),
                TelegramLinkCode.used_at.is_(None),
                TelegramLinkCode.expires_at > now,
                User.deleted_at.is_(None),
            )
            .with_for_update(of=TelegramLinkCode)
        )
    ).first()
    if row is None:
        raise LinkError("Код недействителен или истёк. Получите новый в Настройках.")
    link_code, user = row

    owner = await get_user_by_tg(db, tg_user_id)
    if owner is not None and owner.id != user.id:
        raise LinkError("Этот Telegram уже привязан к другому аккаунту.")

    link_code.used_at = now
    user.tg_user_id = tg_user_id
    await db.commit()
    return user


async def get_user_by_tg(db: AsyncSession, tg_user_id: int) -> User | None:
    return await db.scalar(
        select(User).where(User.tg_user_id == tg_user_id, User.deleted_at.is_(None))
    )


async def unlink(db: AsyncSession, user: User) -> None:
    user.tg_user_id = None
    await db.commit()
