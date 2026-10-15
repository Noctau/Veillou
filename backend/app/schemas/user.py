import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.core.security import MAX_PASSWORD_LENGTH
from app.core.time import is_valid_tz

MIN_PASSWORD_LENGTH = 8


class LoginRequest(BaseModel):
    # Формат не проверяем: при входе email только ищется (валидируется при создании)
    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=MAX_PASSWORD_LENGTH)]


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: Annotated[
        str, StringConstraints(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    ]
    new_password: Annotated[
        str, StringConstraints(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    ]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    timezone: str


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_tz(value):
            raise ValueError("Неизвестный часовой пояс")
        return value
