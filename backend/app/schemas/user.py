import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr

Email = Annotated[EmailStr, AfterValidator(str.lower)]


class LoginRequest(BaseModel):
    email: Email
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    timezone: str
