import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.domain.quickparse import KindHint
from app.schemas.common import InputModel, UTCMoment, WallTime


class QuickParseRequest(InputModel):
    text: Annotated[str, StringConstraints(max_length=6000)]


class QuickParseRead(BaseModel):
    """Что удалось достать из строки. Ничего не сохраняет."""

    title: str
    date: date | None
    time: WallTime | None
    end_time: WallTime | None
    duration_min: int | None
    deadline: UTCMoment | None
    is_deadline: bool
    area_id: uuid.UUID | None
    task_type_id: uuid.UUID | None = Field(description="Тип задачи из справочника по словам")
    action_type_id: uuid.UUID | None = Field(
        description="Тип действия по словам; похоже на задачу — тип по умолчанию"
    )
    kind_hint: KindHint
    needs_ai: bool = Field(description="Разбор неуверенный — стоит спросить ИИ")
