"""Вложения: загрузка в Storage, список, подписанные ссылки на скачивание.

Ссылка на файл не требует cookie (её можно отдать в <img src> или открыть в
новой вкладке), но живёт ограниченное время: /files/{id}?exp=…&sig=… — HMAC
от id и срока действия.
"""

import mimetypes
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from pathlib import PurePath
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ForbiddenError, InvalidDataError, NotFoundError
from app.core.security import sign, verify_signature
from app.core.storage import CHUNK, Storage
from app.domain.enums import AttachmentOwner
from app.models import Attachment, Project, Task, User
from app.schemas.attachment import AttachmentRead, AttachmentUpdate
from app.services.base import UserScopedRepository

OWNER_MODELS: dict[AttachmentOwner, Any] = {
    AttachmentOwner.task: Task,
    AttachmentOwner.project: Project,
}

# Что безопасно показывать в браузере прямо со своего домена. Остальное (HTML,
# SVG, JS…) отдаётся только на скачивание — иначе это XSS с сессией пользователя.
INLINE_MIME_PREFIXES = ("image/png", "image/jpeg", "image/webp", "image/gif", "image/heic")
INLINE_MIME = {"application/pdf", "text/plain", "audio/mpeg", "video/mp4"}


def is_inline_safe(mime: str) -> bool:
    return mime in INLINE_MIME or mime.startswith(INLINE_MIME_PREFIXES)


class AttachmentRepo(UserScopedRepository[Attachment]):
    model = Attachment
    not_found_message = "Файл не найден"


def _clean_filename(name: str | None) -> str:
    base = PurePath((name or "").replace("\\", "/")).name.strip()
    return (base or "файл")[:255]


def _message(attachment_id: uuid.UUID, exp: int) -> str:
    return f"{attachment_id}:{exp}"


def signed_url(
    attachment_id: uuid.UUID, *, download: bool = False, now: float | None = None
) -> str:
    exp = int((now or time.time()) + settings.FILE_URL_TTL_MIN * 60)
    sig = sign(_message(attachment_id, exp), settings.SECRET_KEY.get_secret_value())
    url = f"{settings.API_PREFIX}/files/{attachment_id}?exp={exp}&sig={sig}"
    return url + "&download=1" if download else url


def to_read(attachment: Attachment) -> AttachmentRead:
    read = AttachmentRead.model_validate(attachment)
    read.url = signed_url(attachment.id)
    read.download_url = signed_url(attachment.id, download=True)
    return read


async def resolve_signed(
    db: AsyncSession, attachment_id: uuid.UUID, exp: int, sig: str
) -> Attachment:
    """Файл по подписанной ссылке (без сессии). Просроченная или чужая подпись — 403."""
    if exp < time.time() or not verify_signature(
        _message(attachment_id, exp), sig, settings.SECRET_KEY.get_secret_value()
    ):
        raise ForbiddenError("Ссылка устарела — обновите страницу", code="link_expired")
    attachment = await db.scalar(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.deleted_at.is_(None))
    )
    if attachment is None:
        raise NotFoundError("Файл не найден")
    return attachment


class AttachmentService:
    def __init__(self, db: AsyncSession, user: User, storage: Storage) -> None:
        self.db = db
        self.user_id = user.id
        self.storage = storage
        self.attachments = AttachmentRepo(db, user.id)

    async def _check_owner(self, owner_type: AttachmentOwner, owner_id: uuid.UUID) -> None:
        model = OWNER_MODELS[owner_type]
        exists = await self.db.scalar(
            select(model.id).where(
                model.id == owner_id, model.user_id == self.user_id, model.deleted_at.is_(None)
            )
        )
        if exists is None:
            raise NotFoundError("Не найдено, к чему приложить файл")

    async def list(self, owner_type: AttachmentOwner, owner_id: uuid.UUID) -> list[Attachment]:
        await self._check_owner(owner_type, owner_id)
        return await self.attachments.find_all(
            Attachment.owner_type == owner_type,
            Attachment.owner_id == owner_id,
            order_by=[Attachment.position, Attachment.created_at],
        )

    async def upload(
        self, owner_type: AttachmentOwner, owner_id: uuid.UUID, file: UploadFile
    ) -> Attachment:
        await self._check_owner(owner_type, owner_id)

        async def chunks() -> AsyncIterator[bytes]:
            while chunk := await file.read(CHUNK):
                yield chunk

        blob = await self.storage.save(chunks(), max_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024)
        if blob.size == 0:
            raise InvalidDataError("Пустой файл")
        # Тот же файл к тому же объекту второй раз не прикладываем
        same = await self.attachments.find_all(
            Attachment.owner_type == owner_type,
            Attachment.owner_id == owner_id,
            Attachment.sha256 == blob.sha256,
        )
        if same:
            return same[0]

        filename = _clean_filename(file.filename)
        mime = file.content_type or ""
        if not mime or mime == "application/octet-stream":
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        last = await self.db.scalar(
            select(func.max(Attachment.position)).where(
                Attachment.user_id == self.user_id,
                Attachment.owner_type == owner_type,
                Attachment.owner_id == owner_id,
                Attachment.deleted_at.is_(None),
            )
        )
        attachment = Attachment(
            owner_type=owner_type,
            owner_id=owner_id,
            filename=filename,
            mime=mime[:127],
            size=blob.size,
            sha256=blob.sha256,
            storage_key=blob.key,
            position=(last if last is not None else -1) + 1,
        )
        self.attachments.add(attachment)
        await self.db.commit()
        return attachment

    async def update(self, id: uuid.UUID, patch: AttachmentUpdate) -> Attachment:
        attachment = await self.attachments.get_or_404(id)
        for name, value in patch.model_dump(exclude_unset=True).items():
            if value is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
            setattr(attachment, name, value)
        await self.db.commit()
        return attachment

    async def delete(self, id: uuid.UUID) -> None:
        self.attachments.soft_delete(await self.attachments.get_or_404(id))
        await self.db.commit()


async def delete_for_owners(
    db: AsyncSession,
    user_id: uuid.UUID,
    owner_type: AttachmentOwner,
    owner_ids: Sequence[uuid.UUID],
) -> None:
    """Вложения удалённых объектов (мягко, вместе с ними). Не коммитит."""
    repo = AttachmentRepo(db, user_id)
    for a in await repo.find_all(
        Attachment.owner_type == owner_type, Attachment.owner_id.in_(list(owner_ids))
    ):
        repo.soft_delete(a)
