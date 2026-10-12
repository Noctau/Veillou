"""Занятость и расписание (Part 2, M17): типы занятости, периоды, сетки слотов,
исключения и правила расписания.

Время в правилах — «настенное» в TZ пользователя. В календарь правила попадают
через материализацию в `events` (services/schedule_sync.py), генерация вхождений —
domain/recurrence.py. Справочники не засеваются: у пользователей Part 1 типы
«Пара», «Личное», «Отдых», «Экзамен» создала миграция.
"""

import uuid
from datetime import date, time
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, SmallInteger, String, Text, Time, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UserOwnedMixin


class EventType(UserOwnedMixin, Base):
    """Тип занятости — только жёсткие события. Поведение задают флаги, а не название."""

    __tablename__ = "event_types"
    __table_args__ = (
        Index(
            "uq_event_types_user_key",
            "user_id",
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND key IS NOT NULL"),
        ),
    )

    # Только для сида и миграций (class, personal, rest, exam); логику по нему не ветвят
    key: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))  # «Смена»
    name_plural: Mapped[str] = mapped_column(String(100))  # «Смены» — заголовок секции сводки
    icon: Mapped[str] = mapped_column(String(40), default="calendar")
    color: Mapped[str] = mapped_column(String(16), default="#64748b")
    # Дорога: вычитается до и после события; со склейкой — до первого и после
    # последнего события дня с тем же типом и местом
    buffer_before_min: Mapped[int] = mapped_column(SmallInteger, default=0)
    buffer_after_min: Mapped[int] = mapped_column(SmallInteger, default=0)
    merge_buffers: Mapped[bool] = mapped_column(Boolean, default=False)
    # Напоминание за N минут до начала; NULL — не напоминать
    remind_before_min: Mapped[int | None] = mapped_column(SmallInteger)
    remind_channels: Mapped[list[str]] = mapped_column(JSONB, default=list)
    show_now_next: Mapped[bool] = mapped_column(Boolean, default=False)  # «Сейчас / Дальше»
    is_rest: Mapped[bool] = mapped_column(Boolean, default=False)  # защищённый отдых
    supports_prep: Mapped[bool] = mapped_column(Boolean, default=False)  # подготовка к событию
    # Подпись перед местом в текстах («ауд.» → «ауд. 1801»); пусто — место как есть
    location_label: Mapped[str] = mapped_column(String(20), default="")
    default_area_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("area_types.id", ondelete="SET NULL")
    )
    # Список FieldDef (domain/fields.py) — поля событий этого типа
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)


class Period(UserOwnedMixin, Base):
    """Период (бывший семестр): границы правил, цикл недель и паузы."""

    __tablename__ = "periods"

    name: Mapped[str] = mapped_column(String(100))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    # Цикл недель: 1 — без цикла; неделя start_date получает first_cycle_week,
    # дальше номера идут по неделям Пн–Вс
    cycle_weeks: Mapped[int] = mapped_column(SmallInteger, default=1)
    first_cycle_week: Mapped[int] = mapped_column(SmallInteger, default=1)
    # [{"from": "2027-01-09", "to": "2027-01-25", "title": "Сессия"}] — правила периода
    # в паузы не генерируются
    pauses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class SlotGrid(UserOwnedMixin, Base):
    """Сетка слотов (бывшие звонки). Сетка — группа строк с одним (period_id, name):
    общая строка (weekday = NULL) и переопределения дней (ISO 1–7). Правило ссылается
    на общую строку; переопределение заменяет общие слоты в свой день целиком."""

    __tablename__ = "slot_grids"
    __table_args__ = (
        Index(
            "uq_slot_grids_group_weekday",
            "user_id",
            text("coalesce(period_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "name",
            text("coalesce(weekday, 0)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    period_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("periods.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), default="")
    weekday: Mapped[int | None] = mapped_column(SmallInteger)
    # [{"number": 1, "start": "09:00", "end": "10:35"}, ...]
    slots: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class DayOff(UserOwnedMixin, Base):
    """Исключение: дни без правил периода. period_id = NULL — во всех периодах.
    Диапазон дат включительно. Правила без периода исключения не трогают."""

    __tablename__ = "days_off"

    period_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("periods.id", ondelete="CASCADE"), index=True
    )
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(200), default="")


class ScheduleRule(UserOwnedMixin, Base):
    """Правило расписания: тип занятости × паттерн × время (или слоты).

    Материализуется в `events` до конца периода, без периода — на скользящие 90 дней
    (ночная джоба докатывает окно).
    """

    __tablename__ = "schedule_rules"

    event_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("event_types.id", ondelete="CASCADE"), index=True
    )
    area_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("areas.id", ondelete="CASCADE"), index=True
    )
    period_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("periods.id", ondelete="CASCADE"), index=True
    )
    slot_grid_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("slot_grids.id", ondelete="SET NULL")
    )
    # Дискриминированное объединение (schemas/schedule.Pattern)
    pattern: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Настенное время (end <= start — через полночь) или слоты сетки
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    slot_from: Mapped[int | None] = mapped_column(SmallInteger)
    slot_to: Mapped[int | None] = mapped_column(SmallInteger)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    # Название вхождений; NULL — название сферы, без сферы — типа занятости
    title: Mapped[str | None] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(200))
    color: Mapped[str | None] = mapped_column(String(16))
    # Значения полей типа занятости: {field_id: value}
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
