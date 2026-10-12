"""Всё, что видно в календаре, — строка в `events`.

Вхождения правил расписания материализуются сюда с `template_type/template_id`
и ключом `occurrence_date` — локальной датой, на которую вхождение приходится по
правилу. Ключ не меняется при переносе, поэтому перенесённое вручную вхождение
(`detached=true`) не создаётся заново на старом месте.

`kind` — поведение в планировщике (EventKind): жёсткое `busy` со своим типом
занятости или гибкие блоки. Смысл жёсткого события задаёт `event_type_id`.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import EventStatus
from app.models.base import UserOwnedMixin, UTCDateTime


class Event(UserOwnedMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_user_start", "user_id", "start"),
        Index("ix_events_template", "template_type", "template_id"),
        Index("ix_events_source", "source_type", "source_id"),
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

    area_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("areas.id", ondelete="SET NULL"), index=True
    )
    location: Mapped[str | None] = mapped_column(String(200))
    color: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")

    # Тип занятости жёсткого события; NULL — просто занято (без буферов и напоминаний)
    event_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_types.id", ondelete="SET NULL"), index=True
    )
    # Значения полей типа занятости: {field_id: value}
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Номер слота сетки (бывший номер пары)
    slot: Mapped[int | None] = mapped_column(SmallInteger)
