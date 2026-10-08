"""Экзамены, билеты и план подготовки (M12)."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import Field, StringConstraints

from app.domain.enums import ExamQuestionStatus, ExamSessionKind, ExamSessionStatus
from app.schemas.common import InputModel, Moment, ReadModel, UTCMoment

Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
QuestionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
Duration = Annotated[int, Field(ge=15, le=600, description="Длительность экзамена, мин")]
PrepDays = Annotated[int, Field(ge=1, le=60, description="Начать подготовку за N дней")]
LearnMin = Annotated[int, Field(ge=5, le=240, description="Выучить вопрос, мин")]
ReviewMin = Annotated[int, Field(ge=1, le=120, description="Повторить вопрос, мин")]
RunMin = Annotated[int, Field(ge=1, le=60, description="Общий прогон, мин на вопрос")]


class ExamCreate(InputModel):
    subject_id: uuid.UUID
    title: Title = Field(default="", description="Пусто — «Экзамен: <предмет>»")
    starts_at: Moment
    duration_min: Duration = 180
    location: Location | None = None
    note: str = Field(default="", max_length=5000)
    prep_days: PrepDays = 7
    learn_min: LearnMin = 45
    review_min: ReviewMin = 15
    run_min: RunMin = 5


class ExamUpdate(InputModel):
    title: Title | None = None
    starts_at: Moment | None = None
    duration_min: Duration | None = None
    location: Location | None = None
    note: str | None = Field(default=None, max_length=5000)
    prep_days: PrepDays | None = None
    learn_min: LearnMin | None = None
    review_min: ReviewMin | None = None
    run_min: RunMin | None = None


class ExamRead(ReadModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    title: str = Field(description="Готовое название (с предметом, если своё не задано)")
    starts_at: UTCMoment
    duration_min: int
    location: str | None
    note: str
    prep_days: int
    learn_min: int
    review_min: int
    run_min: int
    plan_enabled: bool
    questions_total: int = 0
    questions_learned: int = 0


class ExamQuestionRead(ReadModel):
    id: uuid.UUID
    number: int
    text: str
    status: ExamQuestionStatus
    learned_on: date | None
    reviews_done: int


class ExamSessionRead(ReadModel):
    """День плана подготовки и где он стоит в календаре (если уже стоит)."""

    id: uuid.UUID
    date: date
    kind: ExamSessionKind
    title: str
    numbers: list[int]
    minutes: int
    status: ExamSessionStatus
    start: UTCMoment | None = None
    end: UTCMoment | None = None


class ExamDetail(ExamRead):
    questions: list[ExamQuestionRead]
    sessions: list[ExamSessionRead]


class ExamQuestionsImport(InputModel):
    text: str = Field(
        min_length=1,
        max_length=50_000,
        description="Список вопросов: «1. …», «1) …» или по одному в строке",
    )


class ExamQuestionCreate(InputModel):
    text: QuestionText
    number: int | None = Field(default=None, ge=1, le=999, description="Пусто — следующий")


class ExamQuestionUpdate(InputModel):
    """status: learned — выучен (повторения от сегодня), review — «повторить»
    (цикл повторений заново), not_started — сбросить."""

    number: int | None = Field(default=None, ge=1, le=999)
    text: QuestionText | None = None
    status: ExamQuestionStatus | None = None
