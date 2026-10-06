import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.domain.enums import TaskType
from app.domain.quickparse import KindHint
from app.schemas.common import InputModel, UTCMoment, WallTime


class QuickParseRequest(InputModel):
    text: Annotated[str, StringConstraints(max_length=500)]


class QuickParseRead(BaseModel):
    """Что удалось достать из строки. Ничего не сохраняет."""

    title: str
    date: date | None
    time: WallTime | None
    end_time: WallTime | None
    duration_min: int | None
    deadline: UTCMoment | None
    is_deadline: bool
    subject_id: uuid.UUID | None
    task_type: TaskType | None
    kind_hint: KindHint
