import uuid
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import StringConstraints, model_validator

from app.domain.enums import ClassType, EventKind, EventStatus, TemplateType
from app.schemas.common import HexColor, InputModel, Moment, ReadModel, UTCMoment

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]

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
    note: str = ""
    subject_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.end <= self.start:
            raise ValueError("Конец должен быть позже начала")
        return self


class EventUpdate(InputModel):
    """Правка события. У вхождения шаблона любая правка ставит detached=true."""

    title: Title | None = None
    start: Moment | None = None
    end: Moment | None = None
    location: Location | None = None
    color: HexColor | None = None
    note: str | None = None
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
