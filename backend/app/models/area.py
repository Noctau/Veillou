"""Сферы и их типы (Part 2, M16.2; бывшие предметы).

Сфера — контейнер, к которому крепятся занятия, задачи, заметки, материалы,
проекты и подготовка: предмет, ученик, клиент, место работы, секция. Тип сферы
задаёт названия, поля (domain/fields.py) и разделы страницы.
Справочник не засевается: у пользователей Part 1 тип «Предмет» создала миграция.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UserOwnedMixin, UTCDateTime


class AreaType(UserOwnedMixin, Base):
    __tablename__ = "area_types"
    __table_args__ = (
        Index(
            "uq_area_types_user_key",
            "user_id",
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND key IS NOT NULL"),
        ),
    )

    # Только для сида и миграций (subject — «Предмет» Part 1); логику по нему не ветвят
    key: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))  # «Ученик»
    name_plural: Mapped[str] = mapped_column(String(100))  # «Ученики»
    icon: Mapped[str] = mapped_column(String(40), default="tag")
    color: Mapped[str] = mapped_column(String(16), default="#3b82f6")
    # Список FieldDef (domain/fields.py), удалённые поля — с deleted=true
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Разделы страницы сферы по порядку (AreaSection)
    sections: Mapped[list[str]] = mapped_column(JSONB, default=list)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)


class Area(UserOwnedMixin, Base):
    __tablename__ = "areas"

    area_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("area_types.id", ondelete="CASCADE"), index=True
    )
    # Период, в котором сфера живёт; NULL — всегда
    period_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("periods.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str | None] = mapped_column(String(50))
    color: Mapped[str] = mapped_column(String(16), default="#3b82f6")
    # Другие названия для быстрого ввода («клим», «климат»)
    synonyms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Значения полей типа: {field_id: value}
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    # В архиве: не предлагается в быстром вводе и выборе, данные на месте
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
