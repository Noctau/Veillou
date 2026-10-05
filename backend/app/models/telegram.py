from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UserOwnedMixin, UTCDateTime


class TelegramLinkCode(UserOwnedMixin, Base):
    """Одноразовый код для `/start <код>`. Хранится только sha256."""

    __tablename__ = "telegram_link_codes"

    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
