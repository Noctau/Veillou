from datetime import date, datetime, time, timedelta
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

# Разумный диапазон дат на входе: без него семестр до 9999 года давал OverflowError
# и сотни тысяч вхождений пар одним запросом
MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 12, 31)
# Самое длинное событие (поездка, сессия) и самый длинный блок дела
MAX_EVENT_DURATION = timedelta(days=31)
MAX_BLOCK_DURATION = timedelta(hours=24)
# Семестр с сессией, выходные/каникулы — не длиннее года
MAX_PERIOD = timedelta(days=366)


def _check_date(value: date) -> date:
    if not MIN_DATE <= value <= MAX_DATE:
        raise ValueError(f"Дата вне допустимого диапазона ({MIN_DATE.year}–{MAX_DATE.year})")
    return value


def _check_moment(value: datetime) -> datetime:
    _check_date(value.date())
    return value


SaneDate = Annotated[date, AfterValidator(_check_date)]
# Naive datetime на входе API запрещены
Moment = Annotated[AwareDatetime, AfterValidator(_check_moment)]
# В ответах — всегда UTC ("...Z")
UTCMoment = Annotated[datetime, AfterValidator(to_utc)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadModel(BaseModel):
    # Поля с дефолтами в ответе всегда есть — в TS-типах они обязательные
    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )
