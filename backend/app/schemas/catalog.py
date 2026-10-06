"""Категории, типы действий и окна времени (ТЗ §4.8)."""

import uuid
from typing import Annotated, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.domain.enums import ActionTypeKey, CategoryIcon, CategoryKey
from app.schemas.common import HexColor, InputModel, ReadModel, WallTime, Weekday

CatalogName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class TimeWindow(InputModel):
    """Когда можно: дни недели × интервал. `end <= start` — до следующего дня (ночь)."""

    weekdays: list[Weekday] = Field(min_length=1, max_length=7)
    start: WallTime
    end: WallTime

    @field_validator("weekdays")
    @classmethod
    def _unique_sorted(cls, value: list[int]) -> list[int]:
        return sorted(set(value))

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.start == self.end:
            raise ValueError("Конец окна должен отличаться от начала")
        return self


# Своё окно у задания / подзадачи / дела: null — как у типа действия
Windows = Annotated[list[TimeWindow], Field(max_length=14)]


# ---------- категории ----------


class CategoryCreate(InputModel):
    name: CatalogName
    color: HexColor
    icon: CategoryIcon = CategoryIcon.tag


class CategoryUpdate(InputModel):
    name: CatalogName | None = None
    color: HexColor | None = None
    icon: CategoryIcon | None = None
    position: int | None = Field(default=None, ge=0, le=1000)


class CategoryRead(ReadModel):
    id: uuid.UUID
    key: CategoryKey | None
    name: str
    color: str
    icon: CategoryIcon
    position: int


# ---------- типы действий ----------


class ActionTypeUpdate(InputModel):
    """Набор типов фиксирован; правятся название, окна и категория по умолчанию."""

    name: CatalogName | None = None
    windows: Annotated[list[TimeWindow], Field(min_length=1, max_length=14)] | None = None
    default_category_id: uuid.UUID | None = None


class ActionTypeRead(ReadModel):
    id: uuid.UUID
    key: ActionTypeKey
    name: str
    default_category_id: uuid.UUID | None
    windows: list[TimeWindow]
    position: int
