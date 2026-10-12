"""Автозадачи от событий (Part 2, M19): правило у типа занятости или у правила
расписания — «до» или «после» каждого вхождения создаётся задача.

Материализация — services/event_tasks.py: задача хранит `origin_event_id` и
`origin_rule_id`, окно (`Task.earliest` / `deadline`) следует за вхождением.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import EventRuleWhen
from app.models.base import UserOwnedMixin


class EventRule(UserOwnedMixin, Base):
    __tablename__ = "event_rules"

    # Ровно одно из двух: все события типа или вхождения одного правила расписания
    event_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_types.id", ondelete="CASCADE"), index=True
    )
    schedule_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedule_rules.id", ondelete="CASCADE"), index=True
    )
    when: Mapped[str] = mapped_column(String(10), default=EventRuleWhen.before)
    # «Подготовить урок — {area}»: {area}, {event}, {field:<id или подпись>}
    title_template: Mapped[str] = mapped_column(String(300))
    estimate_min: Mapped[int] = mapped_column(Integer, default=30)
    action_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("action_types.id", ondelete="SET NULL")
    )
    task_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_types.id", ondelete="SET NULL")
    )
    # «До»: закончить за N минут до начала
    offset_min: Mapped[int] = mapped_column(Integer, default=0)
    # «После»: не позже конца + N дней (NULL — без этого срока)
    within_days: Mapped[int | None] = mapped_column(SmallInteger)
    # «После»: до начала следующего вхождения той же серии
    until_next: Mapped[bool] = mapped_column(Boolean, default=False)
    # Предлагать в вечернем разборе, а не создавать сразу
    confirm: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
