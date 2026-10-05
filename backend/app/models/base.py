import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Dialect, ForeignKey, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.time import to_utc


class UTCDateTime(TypeDecorator[datetime]):
    """timestamptz, который не принимает naive datetime и всегда отдаёт UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> datetime | None:
        return None if value is None else to_utc(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        return None if value is None else to_utc(value)


class EntityMixin:
    """id, created_at, updated_at, deleted_at — есть у всех таблиц."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class UserOwnedMixin(EntityMixin):
    """Всё, что принадлежит пользователю. Любой запрос фильтруется по user_id."""

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
