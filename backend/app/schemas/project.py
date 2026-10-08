"""Проекты и этапы."""

import datetime as dt
import uuid
from typing import Annotated

from pydantic import Field, StringConstraints

from app.domain.enums import MilestoneStatus, ProjectStatus
from app.schemas.common import InputModel, ReadModel, UTCMoment
from app.schemas.schedule import SubjectLink, Teacher

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Description = Annotated[str, StringConstraints(max_length=20_000)]
WeeklyNorm = Annotated[int, Field(ge=0, le=60 * 60, description="Минут в неделю")]

# Контакт проекта (научный руководитель и т. п.) — та же форма, что у преподавателя
Contact = Teacher


# ---------- этапы ----------


MilestoneNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class MilestoneCreate(InputModel):
    title: Title
    date: dt.date | None = None
    note: MilestoneNote = ""


class MilestoneUpdate(InputModel):
    title: Title | None = None
    note: MilestoneNote | None = None
    date: dt.date | None = None
    status: MilestoneStatus | None = None
    position: Annotated[int, Field(ge=0, le=10_000)] | None = None


class MilestoneRead(ReadModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    note: str
    date: dt.date | None
    status: MilestoneStatus
    done_at: UTCMoment | None
    position: int


# ---------- проекты ----------


class ProjectCreate(InputModel):
    title: Title
    category_id: uuid.UUID | None = Field(default=None, description="null — «Учёба»")
    deadline: dt.date | None = None
    description: Description = ""
    contacts: list[Contact] = Field(default_factory=list, max_length=20)
    links: list[SubjectLink] = Field(default_factory=list, max_length=50)
    weekly_norm_min: WeeklyNorm | None = None
    is_work_default: bool = Field(
        default=False, description="Сюда по умолчанию попадают задания с работы"
    )


class ProjectUpdate(InputModel):
    title: Title | None = None
    category_id: uuid.UUID | None = None
    deadline: dt.date | None = None
    description: Description | None = None
    contacts: list[Contact] | None = Field(default=None, max_length=20)
    links: list[SubjectLink] | None = Field(default=None, max_length=50)
    weekly_norm_min: WeeklyNorm | None = None
    is_work_default: bool | None = None
    status: ProjectStatus | None = None


class ProjectRead(ReadModel):
    id: uuid.UUID
    title: str
    category_id: uuid.UUID | None
    deadline: dt.date | None
    description: str
    contacts: list[Contact]
    links: list[SubjectLink]
    weekly_norm_min: int | None
    status: ProjectStatus
    is_work_default: bool
    created_at: UTCMoment
    tasks_total: int = 0
    tasks_done: int = 0
    milestones_total: int = 0
    milestones_done: int = 0
    next_milestone: MilestoneRead | None = None
    # Отставание: на сколько дней просрочен самый старый невыполненный этап
    behind_days: int = 0
    # Время проекта на этой неделе (блоки шагов заданий проекта и работы над ним)
    week_done_min: int = Field(default=0, description="Отмечено «сделано»")
    week_planned_min: int = Field(default=0, description="Сделано и запланировано")


class ProjectDetail(ProjectRead):
    milestones: list[MilestoneRead]
