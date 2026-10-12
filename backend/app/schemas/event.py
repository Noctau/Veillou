import uuid
from datetime import date, datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.domain.enums import EventKind, EventStatus, TemplateType
from app.schemas.common import (
    MAX_EVENT_DURATION,
    HexColor,
    InputModel,
    Moment,
    ReadModel,
    UTCMoment,
)

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Note = Annotated[str, StringConstraints(max_length=5000)]
FieldValues = Annotated[dict[str, Any], Field(description="Значения полей типа занятости")]


class EventCreate(InputModel):
    """Разовое жёсткое событие. Вхождения правил — из ScheduleRule, гибкие блоки —
    планировщиком."""

    event_type_id: uuid.UUID | None = Field(default=None, description="null — просто занято")
    title: Title
    start: Moment
    end: Moment
    location: Location | None = None
    color: HexColor | None = None
    note: Note = ""
    area_id: uuid.UUID | None = None
    fields: FieldValues = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> Self:
        check_event_bounds(self.start, self.end)
        return self


def check_event_bounds(start: datetime, end: datetime) -> None:
    if end <= start:
        raise ValueError("Конец должен быть позже начала")
    if end - start > MAX_EVENT_DURATION:
        raise ValueError(f"Событие — не дольше {MAX_EVENT_DURATION.days} дней")


class EventUpdate(InputModel):
    """Правка события. У вхождения правила ставит detached=true (кроме «сделано», pin, заметки)."""

    title: Title | None = None
    start: Moment | None = None
    end: Moment | None = None
    location: Location | None = None
    color: HexColor | None = None
    note: Note | None = None
    status: EventStatus | None = None
    is_pinned: bool | None = None
    event_type_id: uuid.UUID | None = None
    area_id: uuid.UUID | None = None
    fields: FieldValues | None = None


class EventRead(ReadModel):
    id: uuid.UUID
    kind: EventKind
    title: str
    start: UTCMoment
    end: UTCMoment
    is_fixed: bool
    is_pinned: bool
    status: EventStatus
    template_type: TemplateType | None
    template_id: uuid.UUID | None
    occurrence_date: date | None
    detached: bool
    source_type: str | None
    source_id: uuid.UUID | None
    area_id: uuid.UUID | None
    location: str | None
    color: str | None
    note: str
    event_type_id: uuid.UUID | None
    fields: dict[str, Any]
    slot: int | None


# ---------- календарь ----------


class CalendarDayOff(ReadModel):
    id: uuid.UUID
    period_id: uuid.UUID | None
    date_from: date
    date_to: date
    title: str


class CalendarRead(BaseModel):
    events: list[EventRead]
    days_off: list[CalendarDayOff]
