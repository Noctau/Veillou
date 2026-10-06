"""Литература по предмету: учебник, статья, сайт (ТЗ §4.1).

Файл источника — вложение с `owner_type=source`; из источника одной кнопкой
создаётся задание чтения (services/sources.py).
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import SourceKind, SourceStatus
from app.models.base import UserOwnedMixin


class Source(UserOwnedMixin, Base):
    __tablename__ = "sources"

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
