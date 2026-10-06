import uuid
from typing import Annotated

from pydantic import Field, StringConstraints

from app.domain.enums import AttachmentOwner
from app.schemas.common import InputModel, ReadModel, UTCMoment

FileName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class AttachmentUpdate(InputModel):
    filename: FileName | None = None
    position: Annotated[int, Field(ge=0, le=10_000)] | None = None


class AttachmentOrder(InputModel):
    """Новый порядок файлов объекта (страниц конспекта): все id по порядку."""

    owner_type: AttachmentOwner
    owner_id: uuid.UUID
    ids: list[uuid.UUID] = Field(max_length=500)


class AttachmentRead(ReadModel):
    id: uuid.UUID
    owner_type: AttachmentOwner
    owner_id: uuid.UUID
    filename: str
    mime: str
    size: int
    position: int
    created_at: UTCMoment
    url: str = Field(default="", description="Подписанная ссылка (живёт FILE_URL_TTL_MIN минут)")
    download_url: str = Field(default="", description="То же, но браузер скачивает файл")
