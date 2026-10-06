"""Литература."""

import uuid
from typing import Annotated

from pydantic import Field, HttpUrl, StringConstraints

from app.domain.enums import SourceKind, SourceStatus
from app.schemas.common import InputModel, Moment, ReadModel, UTCMoment
from app.schemas.task import TaskEstimate

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Author = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Note = Annotated[str, StringConstraints(max_length=5000)]


class SourceCreate(InputModel):
    subject_id: uuid.UUID
    title: Title
    author: Author = ""
    kind: SourceKind = SourceKind.textbook
    url: HttpUrl | None = None
    required: bool = Field(default=True, description="Обязательная или дополнительная")
    status: SourceStatus = SourceStatus.to_read
    note: Note = ""


class SourceUpdate(InputModel):
    subject_id: uuid.UUID | None = None
    title: Title | None = None
    author: Author | None = None
    kind: SourceKind | None = None
    url: HttpUrl | None = None
    required: bool | None = None
    status: SourceStatus | None = None
    note: Note | None = None


class SourceRead(ReadModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    title: str
    author: str
    kind: SourceKind
    url: str | None
    required: bool
    status: SourceStatus
    note: str
    created_at: UTCMoment
    files_count: int = 0


class ReadingTaskCreate(InputModel):
    """Задание «прочитать» из источника: тип «чтение», предмет источника."""

    chapters: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = Field(
        default="", description="«главы 3–5», «с. 40–75»; пусто — весь источник"
    )
    deadline: Moment | None = None
    estimate_min: TaskEstimate | None = None
