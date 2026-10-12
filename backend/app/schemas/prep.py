"""Подготовка к событию (Part 2, M20; бывшие экзамены M12): план, пункты, дни."""

import uuid
from datetime import date
from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from app.domain.enums import (
    EventStatus,
    PrepItemStatus,
    PrepSessionKind,
    PrepSessionStatus,
    PrepStrategy,
)
from app.schemas.common import InputModel, Moment, ReadModel, SaneDate, UTCMoment

Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
ItemText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Duration = Annotated[int, Field(ge=15, le=600, description="Длительность события, мин")]
DaysBefore = Annotated[int, Field(ge=1, le=60, description="Начать подготовку за N дней")]
LearnMin = Annotated[int, Field(ge=5, le=240, description="Выучить / пройти пункт, мин")]
ReviewMin = Annotated[int, Field(ge=1, le=120, description="Повторить пункт, мин")]
RunMin = Annotated[int, Field(ge=0, le=60, description="Прогон накануне, мин на пункт; 0 — без")]


class PrepEventIn(InputModel):
    """Событие, к которому готовимся, — создаётся вместе с планом."""

    event_type_id: uuid.UUID | None = Field(
        default=None, description="Тип занятости; null — первый тип с подготовкой"
    )
    title: Title = Field(default="", description="Пусто — «<тип>: <сфера>»")
    start: Moment
    duration_min: Duration = 180
    location: Location | None = None


class PrepPlanCreate(InputModel):
    area_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = Field(default=None, description="Готовиться к этому событию")
    event: PrepEventIn | None = Field(default=None, description="…или создать событие")
    date: SaneDate | None = Field(default=None, description="…или к дате (без события)")
    title: Title = ""
    strategy: PrepStrategy = PrepStrategy.spaced
    start_days_before: DaysBefore = 7
    learn_min: LearnMin = 45
    review_min: ReviewMin = 15
    run_min: RunMin = 5
    note: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def _target(self) -> Self:
        given = [x is not None for x in (self.event_id, self.event, self.date)]
        if sum(given) != 1:
            raise ValueError("Укажите событие, новое событие или дату (одно из трёх)")
        return self


class PrepPlanUpdate(InputModel):
    area_id: uuid.UUID | None = None
    date: SaneDate | None = Field(default=None, description="Только у плана без события")
    title: Title | None = None
    strategy: PrepStrategy | None = None
    start_days_before: DaysBefore | None = None
    learn_min: LearnMin | None = None
    review_min: ReviewMin | None = None
    run_min: RunMin | None = None
    note: str | None = Field(default=None, max_length=5000)


class PrepEventRead(ReadModel):
    id: uuid.UUID
    title: str
    start: UTCMoment
    end: UTCMoment
    location: str | None
    status: EventStatus
    event_type_id: uuid.UUID | None


class PrepPlanRead(ReadModel):
    id: uuid.UUID
    event_id: uuid.UUID | None
    area_id: uuid.UUID | None
    date: date | None
    title: str = Field(description="Готовое название (своё → событие → сфера)")
    strategy: PrepStrategy
    start_days_before: int
    learn_min: int
    review_min: int
    run_min: int
    note: str
    enabled: bool
    target: UTCMoment | None = Field(
        default=None, description="К какому моменту готовиться: начало события или дата"
    )
    event: PrepEventRead | None = None
    items_total: int = 0
    items_learned: int = 0


class PrepItemRead(ReadModel):
    id: uuid.UUID
    number: int
    text: str
    status: PrepItemStatus
    learned_on: date | None
    reviews_done: int


class PrepSessionRead(ReadModel):
    """День плана и где он стоит в календаре (если уже стоит)."""

    id: uuid.UUID
    date: date
    kind: PrepSessionKind
    title: str
    numbers: list[int]
    minutes: int
    status: PrepSessionStatus
    start: UTCMoment | None = None
    end: UTCMoment | None = None


class PrepPlanDetail(PrepPlanRead):
    items: list[PrepItemRead]
    sessions: list[PrepSessionRead]


class PrepItemsImport(InputModel):
    text: str = Field(
        min_length=1,
        max_length=50_000,
        description="Список пунктов: «1. …», «1) …» или по одному в строке",
    )


class PrepItemCreate(InputModel):
    text: ItemText
    number: int | None = Field(default=None, ge=1, le=999, description="Пусто — следующий")


class PrepItemUpdate(InputModel):
    """status: learned — пройден (повторения от сегодня), review — «повторить» (цикл
    повторений заново), not_started — сбросить."""

    number: int | None = Field(default=None, ge=1, le=999)
    text: ItemText | None = None
    status: PrepItemStatus | None = None
