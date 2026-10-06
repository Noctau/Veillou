"""Конспект: текст (Markdown + LaTeX), фото тетради, файл или ссылка (ТЗ §4.1).

Привязан к предмету и, по желанию, к конкретной паре (`event_id`). Страницы
фото и файлы — вложения с `owner_type=note`, порядок — `Attachment.position`.
"""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import NoteKind
from app.models.base import UserOwnedMixin


class Note(UserOwnedMixin, Base):
    __tablename__ = "notes"

    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )
    # Пара, к которой конспект (вхождение events.kind=class)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), index=True
    )
    # Дата пары: из события или вручную. Остаётся, даже если вхождение пропадёт
    class_date: Mapped[date | None] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(10), default=NoteKind.text)
    body_md: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(String(2000))
