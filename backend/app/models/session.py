from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import EntityMixin, UserOwnedMixin, UTCDateTime


class UserSession(UserOwnedMixin, Base):
    """Сессия входа. В cookie — случайный токен, здесь — только его sha256."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip: Mapped[str | None] = mapped_column(String(64))


class LoginFailure(EntityMixin, Base):
    """Неудачный вход: ключ — адрес (`ip:…`) или аккаунт (`email:…`). Служебная таблица,
    старше окна LOGIN_WINDOW_MIN чистится ночной джобой."""

    __tablename__ = "login_failures"
    __table_args__ = (Index("ix_login_failures_key_created", "key", "created_at"),)

    key: Mapped[str] = mapped_column(String(400))
