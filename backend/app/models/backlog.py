"""Долгий ящик: дела без срока, которые постоянно откладываются (ТЗ §4.4)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import BacklogStatus
from app.models.base import UserOwnedMixin, UTCDateTime


class BacklogItem(UserOwnedMixin, Base):
    __tablename__ = "backlog_items"
    __table_args__ = (Index("ix_backlog_items_user_status", "user_id", "status"),)

    title: Mapped[str] = mapped_column(String(300))
    note: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    action_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("action_types.id", ondelete="SET NULL")
    )
    # Примерно: 15 мин / 1 ч / полдня (240)
    estimate_min: Mapped[int | None] = mapped_column(Integer)
    desired_by: Mapped[date | None] = mapped_column(Date)
    # Чипы BacklogCondition
    conditions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Своё окно (часы работы места); NULL — как у типа действия
    time_window: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(12), default=BacklogStatus.active)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
