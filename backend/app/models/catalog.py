"""Справочники: категории дел и типы действий (ТЗ §4.8).

У каждого пользователя свой набор, засеянный дефолтами (services/catalog.py).
Окна типа действия — «настенное» время в TZ пользователя.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UserOwnedMixin


class Category(UserOwnedMixin, Base):
    """Что это за дело: Учёба · Работа · Быт · Личное (+ свои). Задаёт цвет и иконку."""

    __tablename__ = "categories"
    __table_args__ = (
        Index(
            "uq_categories_user_key",
            "user_id",
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND key IS NOT NULL"),
        ),
    )

    # Системная категория (study/work/home/personal); у своих — NULL
    key: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(16))
    icon: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(SmallInteger, default=0)


class ActionType(UserOwnedMixin, Base):
    """Когда дело уместно делать. Окно типа важнее общих рабочих часов."""

    __tablename__ = "action_types"
    __table_args__ = (
        Index(
            "uq_action_types_user_key",
            "user_id",
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    key: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    default_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    # [{"weekdays": [1,2,3,4,5], "start": "09:00", "end": "19:00"}]; end <= start — через полночь
    windows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
