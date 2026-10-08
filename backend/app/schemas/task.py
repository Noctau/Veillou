"""Задания и подзадачи."""

import uuid
from datetime import date
from typing import Annotated, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.domain.enums import EventStatus, Feel, Priority, SubtaskStatus, TaskStatus, TaskType
from app.domain.recurrence import parse_rrule
from app.schemas.catalog import TimeWindow, Windows
from app.schemas.common import InputModel, Moment, ReadModel, UTCMoment

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Description = Annotated[str, StringConstraints(max_length=20_000)]
SubtaskEstimate = Annotated[int, Field(ge=5, le=600, description="Минуты")]
TaskEstimate = Annotated[int, Field(ge=5, le=10_000, description="Минуты")]
BufferDays = Annotated[int, Field(ge=0, le=14, description="Закончить за N дней до дедлайна")]
RRule = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    Field(description="RRULE без DTSTART: «FREQ=WEEKLY;BYDAY=TH»"),
]


def _check_rrule(value: str | None) -> str | None:
    if value is None:
        return None
    parse_rrule(value)
    return value.removeprefix("RRULE:")


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
    occurrence_date: date | None = Field(description="День вхождения регулярного задания")
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
    project_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = Field(default=None, description="Проект берётся из этапа")
    recurrence: RRule | None = Field(
        default=None, description="Регулярное задание: вхождения станут подзадачами с датой"
    )
    recurrence_start: date | None = Field(default=None, description="null — с сегодня")
    subtasks: list[SubtaskCreate] = Field(default_factory=list, max_length=50)

    _rrule = field_validator("recurrence")(_check_rrule)


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
    deadline_buffer_days: BufferDays | None = None
    issued_at: date | None = None
    project_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    recurrence: RRule | None = None
    recurrence_start: date | None = None

    _rrule = field_validator("recurrence")(_check_rrule)


class WorkTaskCreate(InputModel):
    """«Задание с работы»: категория «Работа», дедлайн = выдача + 14 дней, проект ВКР."""

    title: Title
    description: Description = ""
    issued_at: date | None = Field(default=None, description="null — сегодня")
    deadline: Moment | None = Field(default=None, description="null — выдача + 14 дней, 23:59")
    project_id: uuid.UUID | None = Field(
        default=None, description="null — проект «по умолчанию для заданий с работы»"
    )
    no_project: bool = Field(default=False, description="Не привязывать к проекту")


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
    deadline_buffer_days: int | None = Field(
        description="Свой «закончить за N дней до дедлайна»; null — из настроек"
    )
    issued_at: date | None
    project_id: uuid.UUID | None
    milestone_id: uuid.UUID | None
    recurrence: str | None
    recurrence_start: date | None
    created_at: UTCMoment
    subtasks_total: int = 0
    subtasks_done: int = 0
    progress: float = Field(default=0.0, description="Доля сделанных подзадач, 0…1")


class TaskDetail(TaskRead):
    subtasks: list[SubtaskRead]
