import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.storage import Storage, get_storage
from app.domain.enums import AttachmentOwner
from app.schemas.attachment import AttachmentOrder, AttachmentRead, AttachmentUpdate
from app.services.attachments import AttachmentService, is_inline_safe, resolve_signed, to_read

StorageDep = Annotated[Storage, Depends(get_storage)]


def get_service(db: SessionDep, user: CurrentUser, storage: StorageDep) -> AttachmentService:
    return AttachmentService(db, user, storage)


Service = Annotated[AttachmentService, Depends(get_service)]

router = APIRouter(prefix="/attachments", tags=["attachments"])
files_router = APIRouter(prefix="/files", tags=["attachments"])


@router.get("")
async def list_attachments(
    owner_type: AttachmentOwner, owner_id: uuid.UUID, svc: Service
) -> list[AttachmentRead]:
    """Ссылки в ответе подписаны и живут FILE_URL_TTL_MIN минут."""
    return [to_read(a) for a in await svc.list(owner_type, owner_id)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    svc: Service,
    owner_type: Annotated[AttachmentOwner, Form()],
    owner_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
) -> AttachmentRead:
    """До MAX_UPLOAD_MB (100 МБ; тело больше отсекает BodySizeLimitMiddleware ещё до
    разбора). Одинаковые файлы хранятся один раз (sha256)."""
    return to_read(await svc.upload(owner_type, owner_id, file))


@router.put("/order")
async def reorder_attachments(data: AttachmentOrder, svc: Service) -> list[AttachmentRead]:
    """Порядок файлов объекта (страниц фото-конспекта)."""
    return [to_read(a) for a in await svc.reorder(data)]


@router.post("/{attachment_id}/replace")
async def replace_attachment(
    attachment_id: uuid.UUID, svc: Service, file: Annotated[UploadFile, File()]
) -> AttachmentRead:
    """Заменить содержимое (повёрнутая страница) — id и позиция сохраняются."""
    return to_read(await svc.replace(attachment_id, file))


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
    headers = {
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(attachment.filename)}",
        "Cache-Control": f"private, max-age={settings.FILE_URL_TTL_MIN * 60}",
        "X-Content-Type-Options": "nosniff",
    }
    # Встроенный просмотрщик PDF в браузере не работает в sandbox — для него
    # ограничение снимаем (сам PDF к странице приложения доступа не получает)
    if not (inline and attachment.mime == "application/pdf"):
        headers["Content-Security-Policy"] = "sandbox"
    return FileResponse(
        storage.path(attachment.storage_key),
        media_type=attachment.mime if inline else "application/octet-stream",
        headers=headers,
    )
