import uuid
from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.domain.enums import ClassType, EventKind, EventStatus, TemplateType
from app.domain.recurrence import parse_rrule
from app.schemas.common import (
    MAX_EVENT_DURATION,
    HexColor,
    InputModel,
    Moment,
    ReadModel,
    SaneDate,
    UTCMoment,
    WallTime,
)

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
RRule = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Note = Annotated[str, StringConstraints(max_length=5000)]

# Руками создаются только жёсткие личные события; пары — из ClassRule,
# гибкие блоки — планировщиком (M8+).
ManualKind = Literal[EventKind.personal, EventKind.rest]


class EventCreate(InputModel):
    kind: ManualKind = EventKind.personal
    title: Title
    start: Moment
    end: Moment
    location: Location | None = None
    color: HexColor | None = None
    note: Note = ""
    subject_id: uuid.UUID | None = None

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
    """Правка события. У вхождения шаблона ставит detached=true (кроме «сделано», pin, заметки)."""

    title: Title | None = None
    start: Moment | None = None
    end: Moment | None = None
    location: Location | None = None
    color: HexColor | None = None
    note: Note | None = None
    status: EventStatus | None = None
    is_pinned: bool | None = None


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
    subject_id: uuid.UUID | None
    location: str | None
    color: str | None
    note: str
    class_type: ClassType | None
    pair_number: int | None
    teacher: str | None


# ---------- личные повторы ----------


class RecurringEventCreate(InputModel):
    kind: ManualKind = EventKind.personal
    title: Title
    rrule: RRule = Field(description="RRULE без DTSTART, напр. «FREQ=WEEKLY;BYDAY=TU,TH»")
    start_date: SaneDate
    until: SaneDate | None = None
    start_time: WallTime
    end_time: WallTime = Field(description="<= start_time — заканчивается на следующий день")
    location: Location | None = None
    color: HexColor | None = None
    note: Note = ""

    @field_validator("rrule")
    @classmethod
    def _check_rrule(cls, value: str) -> str:
        parse_rrule(value)
        return value.removeprefix("RRULE:")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.until and self.until < self.start_date:
            raise ValueError("«До» раньше начала")
        if self.end_time == self.start_time:
            raise ValueError("Конец должен отличаться от начала")
        return self


class RecurringEventUpdate(InputModel):
    kind: ManualKind | None = None
    title: Title | None = None
    rrule: str | None = None
    start_date: SaneDate | None = None
    until: SaneDate | None = None
    start_time: WallTime | None = None
    end_time: WallTime | None = None
    location: Location | None = None
    color: HexColor | None = None
    note: Note | None = None


class RecurringEventRead(ReadModel):
    id: uuid.UUID
    kind: EventKind
    title: str
    rrule: str
    start_date: date
    until: date | None
    start_time: WallTime
    end_time: WallTime
    location: str | None
    color: str | None
    note: str


# ---------- календарь ----------


class CalendarDayOff(ReadModel):
    id: uuid.UUID
    date_from: date
    date_to: date
    title: str


class CalendarRead(BaseModel):
    events: list[EventRead]
    days_off: list[CalendarDayOff]
