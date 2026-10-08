"""Перепланирование (M9): ревизии плана, разовые лимиты дня, калибровка.

Ревизия — это и превью (`proposed`), и применённое изменение (`applied`):
`ops` — что сделать с событиями, `undo` — как вернуть после применения.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, Float, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import PlanRevisionStatus
from app.models.base import UserOwnedMixin, UTCDateTime


class PlanRevision(UserOwnedMixin, Base):
    __tablename__ = "plan_revisions"
    __table_args__ = (
        Index("ix_plan_revisions_user_status", "user_id", "status"),
        # Одно ожидающее превью на пользователя
        Index(
            "uq_plan_revisions_user_proposed",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'proposed' AND deleted_at IS NULL"),
        ),
    )

    status: Mapped[str] = mapped_column(String(12), default=PlanRevisionStatus.proposed)
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Хэш входа планировщика (без «сейчас»): изменился — превью устарело
    fingerprint: Mapped[str] = mapped_column(String(64))
    # Хэш предложения (ops + at_risk): одинаковые превью не плодим
    content_hash: Mapped[str] = mapped_column(String(64))
    ops: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    at_risk: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Состояние событий до и после применения — для отката
    undo: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    undone_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class StudyDayLimit(UserOwnedMixin, Base):
    """Разовый лимит учёбы на день («в чт можно 8 ч») — вариант при at_risk."""

    __tablename__ = "study_day_limits"
    __table_args__ = (
        Index(
            "uq_study_day_limits_user_date",
            "user_id",
            "date",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    date: Mapped[date] = mapped_column(Date)
    minutes: Mapped[int] = mapped_column(Integer)


class Calibration(UserOwnedMixin, Base):
    """Коэффициент оценок по (тип задания, тип действия) — пересчитывается по истории
    отметок «быстрее / ок / дольше» после `reset_at`."""

    __tablename__ = "calibrations"
    __table_args__ = (
        Index(
            "uq_calibrations_user_key",
            "user_id",
            "task_type",
            "action_type",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    task_type: Mapped[str] = mapped_column(String(20))
    action_type: Mapped[str] = mapped_column(String(20))  # ActionTypeKey
    coef: Mapped[float] = mapped_column(Float, default=1.0)
    samples: Mapped[int] = mapped_column(Integer, default=0)
    reset_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
