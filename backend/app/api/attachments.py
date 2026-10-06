import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.storage import FileTooLargeError, Storage, get_storage
from app.domain.enums import AttachmentOwner
from app.schemas.attachment import AttachmentRead, AttachmentUpdate
from app.services.attachments import AttachmentService, is_inline_safe, resolve_signed, to_read

StorageDep = Annotated[Storage, Depends(get_storage)]


def get_service(db: SessionDep, user: CurrentUser, storage: StorageDep) -> AttachmentService:
    return AttachmentService(db, user, storage)


Service = Annotated[AttachmentService, Depends(get_service)]

router = APIRouter(prefix="/attachments", tags=["attachments"])
files_router = APIRouter(prefix="/files", tags=["attachments"])


def _limit_body(content_length: Annotated[int | None, Header()] = None) -> None:
    # Отсекаем заведомо большие загрузки до того, как тело ляжет во временный файл
    if content_length and content_length > (settings.MAX_UPLOAD_MB + 1) * 1024 * 1024:
        raise FileTooLargeError(f"Файл больше {settings.MAX_UPLOAD_MB} МБ")


@router.get("")
async def list_attachments(
    owner_type: AttachmentOwner, owner_id: uuid.UUID, svc: Service
) -> list[AttachmentRead]:
    """Ссылки в ответе подписаны и живут FILE_URL_TTL_MIN минут."""
    return [to_read(a) for a in await svc.list(owner_type, owner_id)]


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_limit_body)])
async def upload_attachment(
    svc: Service,
    owner_type: Annotated[AttachmentOwner, Form()],
    owner_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
) -> AttachmentRead:
    """До MAX_UPLOAD_MB (100 МБ). Одинаковые файлы хранятся один раз (sha256)."""
    return to_read(await svc.upload(owner_type, owner_id, file))


@router.patch("/{attachment_id}")
async def update_attachment(
    attachment_id: uuid.UUID, patch: AttachmentUpdate, svc: Service
) -> AttachmentRead:
    return to_read(await svc.update(attachment_id, patch))


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(attachment_id: uuid.UUID, svc: Service) -> None:
    await svc.delete(attachment_id)


@files_router.get("/{attachment_id}", response_class=FileResponse)
async def download_file(
    attachment_id: uuid.UUID,
    exp: int,
    sig: str,
    db: SessionDep,
    storage: StorageDep,
    download: bool = False,
) -> FileResponse:
    """Файл по подписанной ссылке (без cookie). Просроченная ссылка — 403."""
    attachment = await resolve_signed(db, attachment_id, exp, sig)
    if not storage.exists(attachment.storage_key):
        raise NotFoundError("Файл потерян в хранилище")
    inline = is_inline_safe(attachment.mime) and not download
    disposition = "inline" if inline else "attachment"
    return FileResponse(
        storage.path(attachment.storage_key),
        media_type=attachment.mime if inline else "application/octet-stream",
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(attachment.filename)}",
            "Cache-Control": f"private, max-age={settings.FILE_URL_TTL_MIN * 60}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )
