"""Лимиты нагрузки (Part 2, M15.3): «не больше N минут в день» на группу дел.

В лимит засчитываются гибкие блоки по типу действия (`load_budget_members`),
а также закреплённое и сделанное сегодня. Блок, чей тип действия входит в два
лимита, считается в обоих. Нет лимитов — нет и ограничений.
Жёсткие события войдут в лимиты по типу занятости (M17).
"""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UserOwnedMixin


class LoadBudget(UserOwnedMixin, Base):
    __tablename__ = "load_budgets"

    name: Mapped[str] = mapped_column(String(100))
    minutes_per_day: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)


class LoadBudgetMember(UserOwnedMixin, Base):
    """Что засчитывается в лимит. Состав правится целиком: старые строки — удалённые."""

    __tablename__ = "load_budget_members"
    __table_args__ = (
        Index(
            "uq_load_budget_members_action_type",
            "budget_id",
            "action_type_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    budget_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("load_budgets.id", ondelete="CASCADE"), index=True
    )
    action_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("action_types.id", ondelete="CASCADE")
    )


class BudgetDayOverride(UserOwnedMixin, Base):
    """Разовый лимит на день («в чт можно 8 ч») — вариант при угрозе плана."""

    __tablename__ = "budget_day_overrides"
    __table_args__ = (
        Index(
            "uq_budget_day_overrides_budget_date",
            "budget_id",
            "date",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    budget_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("load_budgets.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    minutes: Mapped[int] = mapped_column(Integer)
