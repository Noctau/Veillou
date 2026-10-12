"""Задания и подзадачи (ТЗ §4.2, §4.8).

Регулярное задание (`recurrence` — RRULE) материализуется подзадачами с
`occurrence_date` на 60 дней вперёд (services/recurring_tasks.py).

Категория, тип действия и своё окно (`time_window`) есть и у задания, и у
подзадачи: у подзадачи NULL значит «как у задания». В календарь подзадача
попадает событием `events.kind=subtask` с `source_type=subtask`.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import Priority, SubtaskStatus, TaskStatus
from app.models.base import UserOwnedMixin, UTCDateTime


class Task(UserOwnedMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_user_status_deadline", "user_id", "status", "deadline"),
        # Одна живая автозадача на (правило, вхождение)
        Index(
            "uq_tasks_origin",
            "origin_rule_id",
            "origin_event_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND origin_rule_id IS NOT NULL"),
        ),
    )

    title: Mapped[str] = mapped_column(String(300))
    # NULL — без типа
    task_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_types.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[str] = mapped_column(Text, default="")
    area_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("areas.id", ondelete="SET NULL"), index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    # Тип действия по умолчанию для подзадач
    action_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("action_types.id", ondelete="SET NULL")
    )
    # Своё окно: [{"weekdays": [4], "start": "10:00", "end": "17:00"}]; NULL — как у типа
    time_window: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    deadline: Mapped[datetime | None] = mapped_column(UTCDateTime)
    priority: Mapped[str] = mapped_column(String(10), default=Priority.normal)
    status: Mapped[str] = mapped_column(String(12), default=TaskStatus.active)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Оценка всего задания, пока нет подзадач
    estimate_min: Mapped[int | None] = mapped_column(Integer)
    # Свой «закончить за N дней до дедлайна» (сдвинутый внутренний срок); NULL — из настроек
    deadline_buffer_days: Mapped[int | None] = mapped_column(Integer)
    # Дата выдачи (тип с правилом срока: дедлайн = выдача + N дней)
    issued_at: Mapped[date | None] = mapped_column(Date)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL")
    )
    # Регулярное задание («созвон с руководителем по чт»): вхождения — подзадачи с датой
    recurrence: Mapped[str | None] = mapped_column(String(500))
    recurrence_start: Mapped[date | None] = mapped_column(Date)
    # Не раньше этого момента (окно автозадачи «после события»)
    earliest: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Срок посчитан по правилу типа «к следующему вхождению» — пересчитывается сам,
    # пока его не поправили руками
    deadline_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    # Автозадача (M19): от какого вхождения и по какому правилу
    origin_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), index=True
    )
    origin_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_rules.id", ondelete="SET NULL"), index=True
    )


class Subtask(UserOwnedMixin, Base):
    __tablename__ = "subtasks"
    __table_args__ = (
        Index(
            "uq_subtasks_task_occurrence",
            "task_id",
            "occurrence_date",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND occurrence_date IS NOT NULL"),
        ),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    estimate_min: Mapped[int] = mapped_column(Integer, default=30)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # id подзадач того же задания, которые должны быть сделаны раньше
    depends_on: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(12), default=SubtaskStatus.todo)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    actual_feel: Mapped[str | None] = mapped_column(String(10))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    action_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("action_types.id", ondelete="SET NULL")
    )
    time_window: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    note: Mapped[str] = mapped_column(Text, default="")
    # Вхождение регулярного задания: к какому дню относится
    occurrence_date: Mapped[date | None] = mapped_column(Date)
