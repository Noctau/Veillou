"""Категории, типы действий, типы задач и окна времени (ТЗ §4.8, M15)."""

import uuid
from typing import Annotated, Any, Literal, Self

from pydantic import (
    Discriminator,
    Field,
    StringConstraints,
    Tag,
    field_validator,
    model_validator,
)

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

TypeWindows = Annotated[list[TimeWindow], Field(min_length=1, max_length=14)]


class ActionTypeCreate(InputModel):
    name: CatalogName
    windows: TypeWindows
    default_category_id: uuid.UUID | None = None
    prefer_morning: bool = False


class ActionTypeUpdate(InputModel):
    name: CatalogName | None = None
    windows: TypeWindows | None = None
    default_category_id: uuid.UUID | None = None
    prefer_morning: bool | None = None
    position: int | None = Field(default=None, ge=0, le=1000)


class ActionTypeRead(ReadModel):
    id: uuid.UUID
    key: ActionTypeKey | None = Field(description="Ключ сида; у своих типов — null")
    name: str
    default_category_id: uuid.UUID | None
    windows: list[TimeWindow]
    prefer_morning: bool = Field(description="Лёгкое предпочтение утра в плане")
    position: int


# ---------- типы задач ----------

Synonym = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class DeadlineDays(InputModel):
    """Срок = дата выдачи (или сегодня) + N дней, 23:59."""

    kind: Literal["days"] = "days"
    days: int = Field(ge=1, le=365)


class DeadlineNextOccurrence(InputModel):
    """Срок = начало ближайшего будущего вхождения правила расписания той же сферы
    («к следующему уроку»); пересчитывается при изменении расписания."""

    kind: Literal["next_occurrence"] = "next_occurrence"


def _deadline_kind(value: Any) -> str | None:
    """Без `kind` — «+N дней» (так правило записывалось до M19)."""
    if isinstance(value, dict):
        return str(value.get("kind", "days"))
    return getattr(value, "kind", None)


DeadlineRule = Annotated[
    Annotated[DeadlineDays, Tag("days")]
    | Annotated[DeadlineNextOccurrence, Tag("next_occurrence")],
    Discriminator(_deadline_kind),
]


def _unique_words(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    seen: dict[str, str] = {}
    for word in value:
        seen.setdefault(word.lower(), word)
    return list(seen.values())


class TaskTypeCreate(InputModel):
    name: CatalogName
    icon: CategoryIcon = CategoryIcon.tag
    synonyms: list[Synonym] = Field(default_factory=list, max_length=30)
    default_action_type_id: uuid.UUID | None = None
    default_category_id: uuid.UUID | None = None
    default_estimate_min: int | None = Field(default=None, ge=5, le=10_000)
    deadline_rule: DeadlineRule | None = Field(
        default=None, description="Как вывести срок; тип с правилом — «быстрый тип» в ＋"
    )
    default_project_id: uuid.UUID | None = None
    default_template_id: uuid.UUID | None = None

    _synonyms = field_validator("synonyms")(_unique_words)


class TaskTypeUpdate(InputModel):
    name: CatalogName | None = None
    icon: CategoryIcon | None = None
    synonyms: list[Synonym] | None = Field(default=None, max_length=30)
    default_action_type_id: uuid.UUID | None = None
    default_category_id: uuid.UUID | None = None
    default_estimate_min: int | None = Field(default=None, ge=5, le=10_000)
    deadline_rule: DeadlineRule | None = None
    default_project_id: uuid.UUID | None = None
    default_template_id: uuid.UUID | None = None
    position: int | None = Field(default=None, ge=0, le=1000)

    _synonyms = field_validator("synonyms")(_unique_words)


class TaskTypeRead(ReadModel):
    id: uuid.UUID
    name: str
    icon: CategoryIcon
    synonyms: list[str]
    default_action_type_id: uuid.UUID | None
    default_category_id: uuid.UUID | None
    default_estimate_min: int | None
    deadline_rule: DeadlineRule | None
    default_project_id: uuid.UUID | None
    default_template_id: uuid.UUID | None
    position: int
