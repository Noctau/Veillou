"""Режимы дня и правила назначения (Part 2, M18).

`*Update` — частичные: сервис накладывает их на текущие значения и валидирует
итог через `*Create`, так что межполевые проверки работают и при PATCH.
"""

import uuid
from datetime import date, time
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from app.domain.enums import DayRuleKind
from app.schemas.catalog import CatalogName
from app.schemas.common import InputModel, ReadModel, SaneDate, WallTime, Weekday

MAX_WINDOWS = 6
MAX_RULE_DAYS = 366


class Span(InputModel):
    """Интервал внутри суток; `end <= start` — до следующего дня (рабочее окно совы)."""

    start: WallTime
    end: WallTime

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.start == self.end:
            raise ValueError("Начало и конец совпадают")
        return self


class Lunch(Span):
    @model_validator(mode="after")
    def _order(self) -> Self:
        if self.end <= self.start:
            raise ValueError("Обед: конец должен быть позже начала")
        return self


Windows = Annotated[list[Span], Field(max_length=MAX_WINDOWS)]


class DayProfileCreate(InputModel):
    name: CatalogName
    wake: WallTime = Field(default=time(7, 30), description="Подъём")
    sleep: WallTime = Field(
        default=time(23, 30), description="Отбой; не позже подъёма — после полуночи"
    )
    lunch: Lunch | None = Field(default=None, description="Обед; null — без обеда")
    work_windows: Windows = Field(
        default_factory=lambda: [Span(start=time(9), end=time(21))],
        description="Когда вообще можно ставить дела",
    )
    rest_evening_ok: bool = Field(default=True, description="Может быть свободным вечером")
    rest_halfday_ok: bool = Field(default=False, description="Может быть половиной выходного")
    quiet_follows_sleep: bool = Field(
        default=True, description="Тихие часы — сон режима (иначе — тихие часы из настроек)"
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.wake == self.sleep:
            raise ValueError("Подъём и отбой совпадают")
        return self


class DayProfileUpdate(InputModel):
    name: CatalogName | None = None
    wake: WallTime | None = None
    sleep: WallTime | None = None
    lunch: Lunch | None = Field(default=None, description="null — без обеда")
    work_windows: Windows | None = None
    rest_evening_ok: bool | None = None
    rest_halfday_ok: bool | None = None
    quiet_follows_sleep: bool | None = None
    position: int | None = Field(default=None, ge=0, le=1000)


class SpanRead(ReadModel):
    start: WallTime
    end: WallTime


class DayProfileRead(ReadModel):
    id: uuid.UUID
    key: str | None = Field(description="Ключ сида/миграции; у своих режимов — null")
    name: str
    wake: WallTime
    sleep: WallTime
    lunch: SpanRead | None
    work_windows: list[SpanRead]
    rest_evening_ok: bool
    rest_halfday_ok: bool
    quiet_follows_sleep: bool
    position: int


# ---------- правила ----------


class DayProfileRuleCreate(InputModel):
    profile_id: uuid.UUID
    kind: DayRuleKind
    date_from: SaneDate | None = Field(default=None, description="dates: с (включительно)")
    date_to: SaneDate | None = Field(default=None, description="dates: по (включительно)")
    event_type_id: uuid.UUID | None = Field(default=None, description="event_day / day_after")
    weekdays: list[Weekday] = Field(default_factory=list, max_length=7, description="weekdays")

    @field_validator("weekdays")
    @classmethod
    def _unique(cls, value: list[int]) -> list[int]:
        return sorted(set(value))

    @model_validator(mode="after")
    def _by_kind(self) -> Self:
        if self.kind == DayRuleKind.dates:
            if self.date_from is None:
                raise ValueError("Укажите дату")
            if self.date_to is None:
                self.date_to = self.date_from
            if self.date_to < self.date_from:
                raise ValueError("Конец раньше начала")
            if (self.date_to - self.date_from).days >= MAX_RULE_DAYS:
                raise ValueError(f"Не длиннее {MAX_RULE_DAYS} дней")
            self.event_type_id, self.weekdays = None, []
        elif self.kind in (DayRuleKind.event_day, DayRuleKind.day_after):
            if self.event_type_id is None:
                raise ValueError("Укажите тип занятости")
            self.date_from = self.date_to = None
            self.weekdays = []
        else:
            if not self.weekdays:
                raise ValueError("Укажите дни недели")
            self.date_from = self.date_to = None
            self.event_type_id = None
        return self


class DayProfileRuleUpdate(InputModel):
    profile_id: uuid.UUID | None = None
    kind: DayRuleKind | None = None
    date_from: SaneDate | None = None
    date_to: SaneDate | None = None
    event_type_id: uuid.UUID | None = None
    weekdays: list[Weekday] | None = Field(default=None, max_length=7)
    position: int | None = Field(default=None, ge=0, le=1000)


class DayProfileRuleRead(ReadModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    kind: DayRuleKind
    date_from: date | None
    date_to: date | None
    event_type_id: uuid.UUID | None
    weekdays: list[int]
    position: int


class DayProfileDayPut(InputModel):
    """Режим одной даты в одно касание («сегодня — выходной»); null — по правилам."""

    profile_id: uuid.UUID | None


class DayProfileDay(ReadModel):
    date: date
    profile_id: uuid.UUID | None = Field(description="null — встроенный режим (своих нет)")
    name: str
    # Правило «на эту дату» — его можно снять
    pinned: bool
