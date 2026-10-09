import uuid
from datetime import date
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator

from app.domain.enums import BacklogCondition, BacklogStatus
from app.schemas.catalog import TimeWindow, Windows
from app.schemas.common import InputModel, ReadModel, SaneDate, UTCMoment

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Note = Annotated[str, StringConstraints(max_length=5000)]
Estimate = Annotated[int, Field(ge=5, le=720, description="Минуты: 15 / 60 / 240 в UI")]
Conditions = Annotated[list[BacklogCondition], Field(max_length=4)]


def _unique(value: list[BacklogCondition] | None) -> list[BacklogCondition] | None:
    return None if value is None else list(dict.fromkeys(value))


class BacklogCreate(InputModel):
    title: Title
    note: Note = ""
    category_id: uuid.UUID | None = Field(
        default=None, description="null — по типу действия (он угадывается по названию)"
    )
    action_type_id: uuid.UUID | None = None
    estimate_min: Estimate | None = None
    desired_by: SaneDate | None = None
    conditions: Conditions = Field(default_factory=list)
    time_window: Windows | None = None

    _conditions = field_validator("conditions")(_unique)


class BacklogUpdate(InputModel):
    title: Title | None = None
    note: Note | None = None
    category_id: uuid.UUID | None = None
    action_type_id: uuid.UUID | None = None
    estimate_min: Estimate | None = None
    desired_by: SaneDate | None = None
    conditions: Conditions | None = None
    time_window: Windows | None = None
    status: BacklogStatus | None = None

    _conditions = field_validator("conditions")(_unique)


class BacklogRead(ReadModel):
    id: uuid.UUID
    title: str
    note: str
    category_id: uuid.UUID | None
    action_type_id: uuid.UUID | None
    estimate_min: int | None
    desired_by: date | None
    conditions: list[BacklogCondition]
    time_window: list[TimeWindow] | None
    status: BacklogStatus
    planned_week: date | None = Field(description="Взято на неделю (понедельник) — в плане")
    done_at: UTCMoment | None
    archived_at: UTCMoment | None
    created_at: UTCMoment
