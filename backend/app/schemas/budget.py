"""Лимиты нагрузки (M15.3): «не больше N минут в день» на группу типов действий
и типов занятости (M17)."""

import uuid
from datetime import date

from pydantic import Field, field_validator

from app.schemas.catalog import CatalogName
from app.schemas.common import InputModel, ReadModel

BudgetMinutes = Field(ge=15, le=1440, description="Минут в день")


def _unique_ids(value: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
    return list(dict.fromkeys(value)) if value is not None else None


class LoadBudgetCreate(InputModel):
    name: CatalogName
    minutes_per_day: int = BudgetMinutes
    action_type_ids: list[uuid.UUID] = Field(
        default_factory=list, max_length=50, description="Типы действий, которые идут в лимит"
    )
    event_type_ids: list[uuid.UUID] = Field(
        default_factory=list, max_length=50, description="Типы занятости, которые идут в лимит"
    )

    _ids = field_validator("action_type_ids", "event_type_ids")(_unique_ids)


class LoadBudgetUpdate(InputModel):
    name: CatalogName | None = None
    minutes_per_day: int | None = Field(default=None, ge=15, le=1440)
    action_type_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    event_type_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    position: int | None = Field(default=None, ge=0, le=1000)

    _ids = field_validator("action_type_ids", "event_type_ids")(_unique_ids)


class BudgetOverridePut(InputModel):
    minutes: int = Field(ge=0, le=1440)


class BudgetOverrideRead(ReadModel):
    budget_id: uuid.UUID
    date: date
    minutes: int


class LoadBudgetRead(ReadModel):
    id: uuid.UUID
    name: str
    minutes_per_day: int
    position: int
    action_type_ids: list[uuid.UUID]
    event_type_ids: list[uuid.UUID]
    overrides: list[BudgetOverrideRead] = Field(
        default_factory=list, description="Разовые лимиты на сегодня и дальше"
    )
