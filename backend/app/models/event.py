"""Всё, что видно в календаре, — строка в `events`.

Вхождения шаблонов (пары, личные повторы) материализуются сюда с
`template_type/template_id` и ключом `occurrence_date` — локальной датой, на
которую вхождение приходится по шаблону. Ключ не меняется при переносе, поэтому
перенесённая вручную пара (`detached=true`) не создаётся заново на старом месте.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Index, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import EventStatus
from app.models.base import UserOwnedMixin, UTCDateTime


class Event(UserOwnedMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_user_start", "user_id", "start"),
        Index("ix_events_template", "template_type", "template_id"),
        # Одно живое вхождение шаблона на дату
        Index(
            "uq_events_template_occurrence",
            "template_type",
            "template_id",
            "occurrence_date",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND template_id IS NOT NULL"),
        ),
    )

    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    start: Mapped[datetime] = mapped_column(UTCDateTime)
    end: Mapped[datetime] = mapped_column(UTCDateTime)
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default=EventStatus.planned)

    template_type: Mapped[str | None] = mapped_column(String(20))
    template_id: Mapped[uuid.UUID | None] = mapped_column()
    occurrence_date: Mapped[date | None] = mapped_column(Date)
    detached: Mapped[bool] = mapped_column(Boolean, default=False)

    # Сущность-источник гибкого блока (subtask, backlog_item, exam_question…)
    source_type: Mapped[str | None] = mapped_column(String(30))
    source_id: Mapped[uuid.UUID | None] = mapped_column()

    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )
    location: Mapped[str | None] = mapped_column(String(200))
    color: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")

    # Только для пар
    class_type: Mapped[str | None] = mapped_column(String(20))
    pair_number: Mapped[int | None] = mapped_column(SmallInteger)
    teacher: Mapped[str | None] = mapped_column(String(200))
