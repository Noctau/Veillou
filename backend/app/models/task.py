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

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import Priority, SubtaskStatus, TaskStatus, TaskType
from app.models.base import UserOwnedMixin, UTCDateTime


class Task(UserOwnedMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_user_status_deadline", "user_id", "status", "deadline"),)

    title: Mapped[str] = mapped_column(String(300))
    task_type: Mapped[str] = mapped_column(String(20), default=TaskType.other)
    description: Mapped[str] = mapped_column(Text, default="")
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
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
    # Дата выдачи (задания с работы: дедлайн = выдача + 14 дней)
    issued_at: Mapped[date | None] = mapped_column(Date)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL")
    )
    # Регулярное задание («встреча с научруком по чт»): вхождения — подзадачи с датой
    recurrence: Mapped[str | None] = mapped_column(String(500))
    recurrence_start: Mapped[date | None] = mapped_column(Date)


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
