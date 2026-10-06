"""Вложение: файл, приложенный к заданию / проекту / конспекту / источнику.

Сам файл лежит в Storage по ключу-хэшу; несколько вложений могут ссылаться на
один файл (дедупликация по sha256). Удаление вложения мягкое, файл остаётся.
"""

import uuid

from sqlalchemy import BigInteger, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UserOwnedMixin


class Attachment(UserOwnedMixin, Base):
    __tablename__ = "attachments"
    __table_args__ = (Index("ix_attachments_owner", "owner_type", "owner_id"),)

    owner_type: Mapped[str] = mapped_column(String(20))
    owner_id: Mapped[uuid.UUID] = mapped_column()
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(127))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(100))
    # Порядок (страницы фото-конспекта)
    position: Mapped[int] = mapped_column(Integer, default=0)
