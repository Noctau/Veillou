"""Литература по предмету: учебник, статья, сайт (ТЗ §4.1).

Файл источника — вложение с `owner_type=source`; из источника одной кнопкой
создаётся задание чтения (services/sources.py).
"""

import uuid
from typing import Any

from sqlalchemy import Boolean, Computed, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import SourceKind, SourceStatus
from app.models.base import UserOwnedMixin

SOURCE_SEARCH = (
    "setweight(to_tsvector('russian', replace(lower(title), 'ё', 'е')), 'A') || "
    "setweight(to_tsvector('russian', replace(lower(author), 'ё', 'е')), 'B') || "
    "setweight(to_tsvector('russian', replace(lower(note), 'ё', 'е')), 'C')"
)


class Source(UserOwnedMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_search", "search", postgresql_using="gin"),)

    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(300), default="")
    kind: Mapped[str] = mapped_column(String(12), default=SourceKind.textbook)
    url: Mapped[str | None] = mapped_column(String(2000))
    # Обязательная или дополнительная литература
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(12), default=SourceStatus.to_read)
    note: Mapped[str] = mapped_column(Text, default="")
    search: Mapped[Any] = mapped_column(
        TSVECTOR, Computed(SOURCE_SEARCH, persisted=True), deferred=True
    )
