"""Шаблоны расписания: семестр, звонки, выходные, предметы, правила пар.

Время в шаблонах — «настенное» в TZ пользователя. В календарь они попадают
через материализацию в `events` (services/schedule_sync.py).
"""

import uuid
from datetime import date, time
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, SmallInteger, String, Text, Time, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import ClassType, ControlForm, Parity, RuleParity
from app.models.base import UserOwnedMixin


class Semester(UserOwnedMixin, Base):
    __tablename__ = "semesters"

    name: Mapped[str] = mapped_column(String(100))
    start_date: Mapped[date] = mapped_column(Date)
    # Последний день занятий: пары генерируются в [start_date, classes_end]
    classes_end: Mapped[date] = mapped_column(Date)
    session_start: Mapped[date | None] = mapped_column(Date)
    session_end: Mapped[date | None] = mapped_column(Date)
    # Чётность недели, в которую попадает start_date; дальше чередуется
    first_week_parity: Mapped[str] = mapped_column(String(8), default=Parity.odd)


class BellSchedule(UserOwnedMixin, Base):
    """Звонки семестра. weekday = NULL — общие, иначе переопределение для дня (ISO 1–7)."""

    __tablename__ = "bell_schedules"
    __table_args__ = (
        Index(
            "uq_bell_schedules_semester_weekday",
            "semester_id",
            text("coalesce(weekday, 0)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semesters.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int | None] = mapped_column(SmallInteger)
    # [{"number": 1, "start": "09:00", "end": "10:35"}, ...]
    slots: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class DayOff(UserOwnedMixin, Base):
    """Праздник / день без пар. Диапазон дат включительно."""

    __tablename__ = "days_off"

    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(200), default="")


class Subject(UserOwnedMixin, Base):
    __tablename__ = "subjects"

    semester_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semesters.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str | None] = mapped_column(String(50))
    color: Mapped[str] = mapped_column(String(16), default="#3b82f6")
    control_form: Mapped[str] = mapped_column(String(20), default=ControlForm.exam)
    # [{"name": "...", "role": "лектор", "contact": "..."}]
    teachers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # [{"title": "...", "url": "..."}]
    links: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Другие названия для быстрого ввода («клим», «климат»)
    synonyms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


class ClassRule(UserOwnedMixin, Base):
    """Пара в сетке недели: день × номер пары × чётность."""

    __tablename__ = "class_rules"

    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semesters.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)  # ISO: 1 = Пн
    pair_number: Mapped[int | None] = mapped_column(SmallInteger)
    # Своё время вместо звонков (спецкурс в 18:30). Задаются вместе.
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    parity: Mapped[str] = mapped_column(String(8), default=RuleParity.all)
    class_type: Mapped[str] = mapped_column(String(20), default=ClassType.lecture)
    location: Mapped[str | None] = mapped_column(String(200))
    teacher: Mapped[str | None] = mapped_column(String(200))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
