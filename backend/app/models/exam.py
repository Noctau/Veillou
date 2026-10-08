"""Экзамены и билеты (ТЗ §4.1, M12).

План подготовки — дни `ExamSession`: «выучить №1–4», «повторить №1–3, 7»,
«общий прогон». Их строит `domain/srs.py` по статусам вопросов; каждый день —
гибкий блок `events.kind=exam_prep` (`source_type=exam_session`), который
планировщик ставит в свободное окно своего дня.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import ExamQuestionStatus, ExamSessionStatus
from app.models.base import UserOwnedMixin, UTCDateTime


class Exam(UserOwnedMixin, Base):
    __tablename__ = "exams"

    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), default="")  # пусто — «Экзамен»
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime)
    duration_min: Mapped[int] = mapped_column(Integer, default=180)
    location: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(Text, default="")
    # Начать подготовку за N дней (если экзамен ближе — с сегодняшнего дня)
    prep_days: Mapped[int] = mapped_column(Integer, default=7)
    learn_min: Mapped[int] = mapped_column(Integer, default=45)  # выучить вопрос
    review_min: Mapped[int] = mapped_column(Integer, default=15)  # повторить вопрос
    run_min: Mapped[int] = mapped_column(Integer, default=5)  # общий прогон, на вопрос
    # План подготовки построен (кнопка) — дальше он пересобирается сам
    plan_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class ExamQuestion(UserOwnedMixin, Base):
    __tablename__ = "exam_questions"
    __table_args__ = (Index("ix_exam_questions_exam_number", "exam_id", "number"),)

    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default=ExamQuestionStatus.not_started)
    # Цикл повторений: от этого дня считаются +1 / +3 / +7
    learned_on: Mapped[date | None] = mapped_column(Date)
    reviews_done: Mapped[int] = mapped_column(Integer, default=0)


class ExamSession(UserOwnedMixin, Base):
    """День плана подготовки. Ключ — (экзамен, дата, вид): пересборка правит на месте."""

    __tablename__ = "exam_sessions"
    __table_args__ = (
        Index(
            "uq_exam_sessions_key",
            "exam_id",
            "date",
            "kind",
            unique=True,
            # Пропущенный день не мешает запланировать этот же день заново
            postgresql_where=text("deleted_at IS NULL AND status <> 'missed'"),
        ),
    )

    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(10))  # ExamSessionKind
    question_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default=ExamSessionStatus.planned)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
