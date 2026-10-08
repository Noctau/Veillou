import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.core.security import MAX_PASSWORD_LENGTH


class LoginRequest(BaseModel):
    # Формат не проверяем: при входе email только ищется (валидируется при создании)
    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=MAX_PASSWORD_LENGTH)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    timezone: str
