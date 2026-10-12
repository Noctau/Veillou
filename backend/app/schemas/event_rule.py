"""Автозадачи от событий (Part 2, M19). `EventRuleUpdate` частичный: сервис накладывает
его на текущие значения и валидирует итог через `EventRuleCreate`."""

import uuid
from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from app.domain.enums import EventRuleWhen
from app.schemas.common import InputModel, ReadModel

Template = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
OffsetMin = Annotated[int, Field(ge=0, le=60 * 24 * 14, description="Минут до начала")]
WithinDays = Annotated[int, Field(ge=0, le=60, description="Дней после конца")]
EstimateMin = Annotated[int, Field(ge=5, le=24 * 60)]


class EventRuleCreate(InputModel):
    event_type_id: uuid.UUID | None = Field(default=None, description="Все события типа")
    schedule_rule_id: uuid.UUID | None = Field(
        default=None, description="Вхождения одного правила расписания"
    )
    when: EventRuleWhen = EventRuleWhen.before
    title_template: Template = Field(
        description="Подстановки: {area}, {event}, {field:<id или подпись поля>}"
    )
    estimate_min: EstimateMin = 30
    action_type_id: uuid.UUID | None = None
    task_type_id: uuid.UUID | None = None
    offset_min: OffsetMin = Field(default=0, description="«До»: закончить за N минут")
    within_days: WithinDays | None = Field(
        default=None, description="«После»: не позже конца + N дней"
    )
    until_next: bool = Field(default=False, description="«После»: до следующего вхождения")
    confirm: bool = Field(default=False, description="Предлагать в вечернем разборе")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.event_type_id is None) == (self.schedule_rule_id is None):
            raise ValueError("Укажите тип занятости или правило расписания (одно из двух)")
        if self.when == EventRuleWhen.before:
            self.within_days, self.until_next = None, False
        else:
            self.offset_min = 0
        return self


class EventRuleUpdate(InputModel):
    when: EventRuleWhen | None = None
    title_template: Template | None = None
    estimate_min: EstimateMin | None = None
    action_type_id: uuid.UUID | None = None
    task_type_id: uuid.UUID | None = None
    offset_min: OffsetMin | None = None
    within_days: WithinDays | None = None
    until_next: bool | None = None
    confirm: bool | None = None
    position: int | None = Field(default=None, ge=0, le=1000)


class EventRuleRead(ReadModel):
    id: uuid.UUID
    event_type_id: uuid.UUID | None
    schedule_rule_id: uuid.UUID | None
    when: EventRuleWhen
    title_template: str
    estimate_min: int
    action_type_id: uuid.UUID | None
    task_type_id: uuid.UUID | None
    offset_min: int
    within_days: int | None
    until_next: bool
    confirm: bool
    position: int
