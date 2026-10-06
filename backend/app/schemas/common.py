from datetime import datetime, time
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer

from app.core.time import to_utc

# «Настенное» время в TZ пользователя, в JSON — "HH:MM"
WallTime = Annotated[
    time,
    PlainSerializer(lambda t: t.strftime("%H:%M"), return_type=str, when_used="json"),
]

HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
Weekday = Annotated[int, Field(ge=1, le=7, description="ISO: 1 = Пн, 7 = Вс")]

# Naive datetime на входе API запрещены
Moment = AwareDatetime
# В ответах — всегда UTC ("...Z")
UTCMoment = Annotated[datetime, AfterValidator(to_utc)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
