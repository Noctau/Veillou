"""Долгие проекты (ВКР, магистратура) и их этапы (ТЗ §4.9)."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import MilestoneStatus, ProjectStatus
from app.models.base import UserOwnedMixin, UTCDateTime


class Project(UserOwnedMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        # Не больше одного проекта «по умолчанию для заданий с работы»
        Index(
            "uq_projects_user_work_default",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND is_work_default"),
        ),
    )

    title: Mapped[str] = mapped_column(String(300))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    # Итоговый срок: защита, подача документов
    deadline: Mapped[dt.date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, default="")
    # [{"name": "...", "role": "научный руководитель", "contact": "..."}]
    contacts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # [{"title": "...", "url": "..."}]
    links: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Норма часов в неделю — планировщик резервирует (M13.1)
    weekly_norm_min: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default=ProjectStatus.active)
    # Сюда по умолчанию попадают «задания с работы»
    is_work_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Milestone(UserOwnedMixin, Base):
    __tablename__ = "milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    date: Mapped[dt.date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default=MilestoneStatus.planned)
    done_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
    position: Mapped[int] = mapped_column(Integer, default=0)
