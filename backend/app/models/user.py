from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.db import Base
from app.models.base import EntityMixin


class User(EntityMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)  # в нижнем регистре
    password_hash: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(
        String(64), default=settings.DEFAULT_TIMEZONE, server_default=settings.DEFAULT_TIMEZONE
    )
    # Только переопределения пользователя; дефолты — в schemas.settings.UserSettings
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
