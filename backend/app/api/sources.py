import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.source import ReadingTaskCreate, SourceCreate, SourceRead, SourceUpdate
from app.schemas.task import TaskDetail
from app.services.sources import SourceService


def get_service(db: SessionDep, user: CurrentUser) -> SourceService:
    return SourceService(db, user)


Service = Annotated[SourceService, Depends(get_service)]

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("")
async def list_sources(svc: Service, subject_id: uuid.UUID | None = None) -> list[SourceRead]:
    """Обязательные первыми; внутри — «читаю», «прочитать», «прочитано»."""
    return await svc.list(subject_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(data: SourceCreate, svc: Service) -> SourceRead:
    return await svc.create(data)


@router.get("/{source_id}")
async def read_source(source_id: uuid.UUID, svc: Service) -> SourceRead:
    return await svc.get(source_id)


@router.patch("/{source_id}")
async def update_source(source_id: uuid.UUID, patch: SourceUpdate, svc: Service) -> SourceRead:
    return await svc.update(source_id, patch)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: uuid.UUID, svc: Service) -> None:
    """Вместе с файлами источника."""
    await svc.delete(source_id)


@router.post("/{source_id}/reading-task", status_code=status.HTTP_201_CREATED)
async def create_reading_task(
    source_id: uuid.UUID, data: ReadingTaskCreate, svc: Service
) -> TaskDetail:
    """Задание «прочитать …» (тип «чтение», предмет источника, ссылка в описании)."""
    return await svc.create_reading_task(source_id, data)
