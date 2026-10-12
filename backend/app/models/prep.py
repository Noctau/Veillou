"""Подготовка к событию (Part 2, M20; бывшие экзамены M12).

План подготовки крепится к событию (`event_id` — экзамен, выступление, собеседование:
жёсткое событие типа с `supports_prep`) или к сфере с датой. Пункты (`PrepItem`) —
билеты, темы, части выступления. Дни плана (`PrepSession`) строит стратегия
(domain/srs.py: `spaced` — выучить и повторить через +1/+3/+7, `even` — поровну по
дням); каждый день — гибкий блок `events.kind=prep` (`source_type=prep_session`),
его ставит в свободное окно своего дня планировщик.
"""

import datetime as dt
import uuid

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import PrepItemStatus, PrepSessionStatus, PrepStrategy
from app.models.base import UserOwnedMixin, UTCDateTime


class PrepPlan(UserOwnedMixin, Base):
    __tablename__ = "prep_plans"

    # К чему готовимся: событие или сфера с датой (одно из двух; у события сфера — его)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), index=True
    )
    area_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("areas.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[dt.date | None] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(300), default="")  # пусто — по событию / сфере
    strategy: Mapped[str] = mapped_column(String(10), default=PrepStrategy.spaced)
    # Начать за N дней (если событие ближе — с сегодняшнего дня)
    start_days_before: Mapped[int] = mapped_column(Integer, default=7)
    learn_min: Mapped[int] = mapped_column(Integer, default=45)  # выучить / пройти пункт
    review_min: Mapped[int] = mapped_column(Integer, default=15)  # повторить пункт (spaced)
    run_min: Mapped[int] = mapped_column(Integer, default=5)  # прогон накануне, на пункт; 0 — без
    note: Mapped[str] = mapped_column(Text, default="")
    # План построен (кнопка) — дальше пересобирается сам
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class PrepItem(UserOwnedMixin, Base):
    __tablename__ = "prep_items"
    __table_args__ = (Index("ix_prep_items_plan_number", "plan_id", "number"),)

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prep_plans.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default=PrepItemStatus.not_started)
    # Цикл повторений: от этого дня считаются +1 / +3 / +7
    learned_on: Mapped[dt.date | None] = mapped_column(Date)
    reviews_done: Mapped[int] = mapped_column(Integer, default=0)


class PrepSession(UserOwnedMixin, Base):
    """День плана. Ключ — (план, дата, вид): пересборка правит на месте."""

    __tablename__ = "prep_sessions"
    __table_args__ = (
        Index(
            "uq_prep_sessions_key",
            "plan_id",
            "date",
            "kind",
            unique=True,
            # Пропущенный день не мешает запланировать этот же день заново
            postgresql_where=text("deleted_at IS NULL AND status <> 'missed'"),
        ),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prep_plans.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[dt.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(10))  # PrepSessionKind
    item_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default=PrepSessionStatus.planned)
    done_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime)
