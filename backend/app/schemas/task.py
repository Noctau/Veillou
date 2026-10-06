"""Задания и подзадачи."""

import uuid
from datetime import date
from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from app.domain.enums import EventStatus, Feel, Priority, SubtaskStatus, TaskStatus, TaskType
from app.schemas.catalog import TimeWindow, Windows
from app.schemas.common import InputModel, Moment, ReadModel, UTCMoment

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Description = Annotated[str, StringConstraints(max_length=20_000)]
SubtaskEstimate = Annotated[int, Field(ge=5, le=600, description="Минуты")]
TaskEstimate = Annotated[int, Field(ge=5, le=10_000, description="Минуты")]


# ---------- подзадачи ----------


class SubtaskCreate(InputModel):
    title: Title
    estimate_min: SubtaskEstimate = 30
    depends_on: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    category_id: uuid.UUID | None = None
    action_type_id: uuid.UUID | None = None
    time_window: Windows | None = None
    note: Description = ""


class SubtaskUpdate(InputModel):
    title: Title | None = None
    estimate_min: SubtaskEstimate | None = None
    depends_on: list[uuid.UUID] | None = Field(default=None, max_length=50)
    status: SubtaskStatus | None = None
    actual_feel: Feel | None = None
    category_id: uuid.UUID | None = None
    action_type_id: uuid.UUID | None = None
    time_window: Windows | None = None
    note: Description | None = None


class SubtaskOrder(InputModel):
    """Новый порядок: все id подзадач задания."""

    ids: list[uuid.UUID] = Field(max_length=200)


class SubtaskSchedule(InputModel):
    """Ручная постановка в календарь. Без `end` — длительность = оценка."""

    start: Moment
    end: Moment | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.end is not None and self.end <= self.start:
            raise ValueError("Конец должен быть позже начала")
        return self


class SubtaskEvent(ReadModel):
    id: uuid.UUID
    start: UTCMoment
    end: UTCMoment
    status: EventStatus
    is_pinned: bool


class SubtaskRead(ReadModel):
    id: uuid.UUID
    task_id: uuid.UUID
    title: str
    estimate_min: int
    position: int
    depends_on: list[uuid.UUID]
    status: SubtaskStatus
    done_at: UTCMoment | None
    actual_feel: Feel | None
    category_id: uuid.UUID | None
    action_type_id: uuid.UUID | None
    time_window: list[TimeWindow] | None
    note: str
    events: list[SubtaskEvent] = Field(default_factory=list, description="Блоки в календаре")


# ---------- задания ----------


class TaskCreate(InputModel):
    title: Title
    task_type: TaskType = TaskType.other
    description: Description = ""
    subject_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = Field(
        default=None, description="null — выводится: проект → тип действия → «Учёба»"
    )
    action_type_id: uuid.UUID | None = Field(
        default=None, description="null — «Самостоятельная учёба»"
    )
    time_window: Windows | None = None
    deadline: Moment | None = None
    priority: Priority = Priority.normal
    estimate_min: TaskEstimate | None = None
    issued_at: date | None = None
    subtasks: list[SubtaskCreate] = Field(default_factory=list, max_length=50)


class TaskUpdate(InputModel):
    title: Title | None = None
    task_type: TaskType | None = None
    description: Description | None = None
    subject_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    action_type_id: uuid.UUID | None = None
    time_window: Windows | None = None
    deadline: Moment | None = None
    priority: Priority | None = None
    status: TaskStatus | None = None
    estimate_min: TaskEstimate | None = None
    issued_at: date | None = None


class TaskRead(ReadModel):
    id: uuid.UUID
    title: str
    task_type: TaskType
    description: str
    subject_id: uuid.UUID | None
    category_id: uuid.UUID | None
    action_type_id: uuid.UUID | None
    time_window: list[TimeWindow] | None
    deadline: UTCMoment | None
    priority: Priority
    status: TaskStatus
    done_at: UTCMoment | None
    estimate_min: int | None
    issued_at: date | None
    created_at: UTCMoment
    subtasks_total: int = 0
    subtasks_done: int = 0
    progress: float = Field(default=0.0, description="Доля сделанных подзадач, 0…1")


class TaskDetail(TaskRead):
    subtasks: list[SubtaskRead]
