"""Конспекты."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import Field, HttpUrl, StringConstraints

from app.domain.enums import ClassType, NoteKind
from app.schemas.common import InputModel, ReadModel, SaneDate, UTCMoment

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Body = Annotated[str, StringConstraints(max_length=200_000)]


class NoteCreate(InputModel):
    title: Title | None = Field(
        default=None, description="null — «Пара · 6 окт» по паре или «Конспект 6 окт»"
    )
    kind: NoteKind = NoteKind.text
    subject_id: uuid.UUID | None = Field(default=None, description="null — предмет пары")
    event_id: uuid.UUID | None = Field(default=None, description="Пара, к которой конспект")
    class_date: SaneDate | None = Field(default=None, description="null — дата пары или сегодня")
    body_md: Body = ""
    url: HttpUrl | None = None


class NoteUpdate(InputModel):
    title: Title | None = None
    kind: NoteKind | None = None
    subject_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    class_date: SaneDate | None = None
    body_md: Body | None = None
    url: HttpUrl | None = None


class NoteEvent(ReadModel):
    """Пара конспекта — коротко, для подписи «2 пара, ауд. 1801»."""

    id: uuid.UUID
    title: str
    start: UTCMoment
    end: UTCMoment
    location: str | None
    pair_number: int | None
    class_type: ClassType | None


class NoteListItem(ReadModel):
    id: uuid.UUID
    title: str
    kind: NoteKind
    subject_id: uuid.UUID | None
    event_id: uuid.UUID | None
    class_date: date | None
    url: str | None
    created_at: UTCMoment
    updated_at: UTCMoment
    excerpt: str = Field(default="", description="Начало текста без разметки")
    attachments_count: int = 0
    cover_url: str | None = Field(default=None, description="Первая страница-картинка")


class NoteRead(NoteListItem):
    body_md: str
    event: NoteEvent | None = None
