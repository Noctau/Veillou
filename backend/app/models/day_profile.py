"""Режимы дня (Part 2, M18): подъём, отбой, обед, общие рабочие окна, флаги отдыха —
и правила, какой режим у какой даты (domain/dayprofile.py).

Новым пользователям засеваются «Будни» и «Выходные» (services/day_profiles.py),
у пользователей Part 1 их создала миграция из `work_hours`, `sleep`, `lunch`.
"""

import uuid
from datetime import date, time
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, SmallInteger, String, Time, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UserOwnedMixin


class DayProfile(UserOwnedMixin, Base):
    __tablename__ = "day_profiles"
    __table_args__ = (
        Index(
            "uq_day_profiles_user_key",
            "user_id",
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND key IS NOT NULL"),
        ),
    )

    # Только для сида и миграций (weekdays, weekends); логику по нему не ветвят
    key: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    wake: Mapped[time] = mapped_column(Time)
    # Отбой; не позже подъёма — после полуночи
    sleep: Mapped[time] = mapped_column(Time)
    lunch_start: Mapped[time | None] = mapped_column(Time)
    lunch_end: Mapped[time | None] = mapped_column(Time)
    # [{"start": "09:00", "end": "21:00"}] — когда вообще можно ставить дела
    work_windows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    rest_evening_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    rest_halfday_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_follows_sleep: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)


class DayProfileRule(UserOwnedMixin, Base):
    """Правило назначения: `kind` + свои параметры (остальные — NULL / пусто)."""

    __tablename__ = "day_profile_rules"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("day_profiles.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))  # DayRuleKind
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    event_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_types.id", ondelete="CASCADE")
    )
    weekdays: Mapped[list[int]] = mapped_column(JSONB, default=list)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
