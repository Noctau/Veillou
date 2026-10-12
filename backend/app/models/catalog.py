"""Справочники: категории дел, типы действий и типы задач (ТЗ §4.8, Part 2 M15).

Категории и типы действий засеваются дефолтами (services/catalog.py), типы задач —
только миграцией у пользователей Part 1: пустой справочник — нормальное состояние.
`key` нужен только для идемпотентного сида и миграций — логику по нему не ветвят.
Окна типа действия — «настенное» время в TZ пользователя.
"""

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, SmallInteger, String, text
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
            postgresql_where=text("deleted_at IS NULL AND key IS NOT NULL"),
        ),
    )

    # Ключ сида (people/institutions/study/…); у своих — NULL
    key: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    default_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    # [{"weekdays": [1,2,3,4,5], "start": "09:00", "end": "19:00"}]; end <= start — через полночь
    windows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Слова быстрого ввода и ИИ: «врач», «мфц»
    synonyms: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # Лёгкое предпочтение утра в планировщике (бывшая логика на ключе people)
    prefer_morning: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    position: Mapped[int] = mapped_column(SmallInteger, default=0)


class TaskType(UserOwnedMixin, Base):
    """Тип задачи: подставляет умолчания при создании и задаёт ключ калибровки.

    `deadline_rule` — как вывести срок, если его не дали:
    `{"kind": "days", "days": 14}` — дата выдачи + N дней (23:59).
    Типы с правилом срока — «быстрые типы» в интерфейсе.
    """

    __tablename__ = "task_types"
    __table_args__ = (
        Index(
            "uq_task_types_user_key",
            "user_id",
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND key IS NOT NULL"),
        ),
    )

    key: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    icon: Mapped[str] = mapped_column(String(40), default="tag")
    # Слова быстрого ввода и ИИ: «реферат», «эссе»
    synonyms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    default_action_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("action_types.id", ondelete="SET NULL")
    )
    default_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    default_estimate_min: Mapped[int | None] = mapped_column(Integer)
    deadline_rule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    default_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL")
    )
    default_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("breakdown_templates.id", ondelete="SET NULL", use_alter=True)
    )
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
