import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.domain.enums import BacklogStatus
from app.schemas.backlog import BacklogCreate, BacklogRead, BacklogUpdate
from app.services.backlog import BacklogService


def get_service(db: SessionDep, user: CurrentUser) -> BacklogService:
    return BacklogService(db, user)


Service = Annotated[BacklogService, Depends(get_service)]

router = APIRouter(prefix="/backlog", tags=["backlog"])


@router.get("")
async def list_backlog(
    svc: Service, status: BacklogStatus = BacklogStatus.active
) -> list[BacklogRead]:
    """Активные — с желаемым сроком первыми, дальше по возрасту (старые сверху)."""
    return [BacklogRead.model_validate(i) for i in await svc.list(status)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_backlog_item(data: BacklogCreate, svc: Service) -> BacklogRead:
    """Тип действия и категория без явных значений угадываются по названию."""
    return BacklogRead.model_validate(await svc.create(data))


@router.patch("/{item_id}")
async def update_backlog_item(
    item_id: uuid.UUID, patch: BacklogUpdate, svc: Service
) -> BacklogRead:
    """status: done — сделано, archived — «неактуально», active — вернуть."""
    return BacklogRead.model_validate(await svc.update(item_id, patch))


@router.put("/{item_id}/week")
async def take_backlog_item_for_week(item_id: uuid.UUID, svc: Service) -> BacklogRead:
    """«Взять на неделю» (в Сб/Вс — на следующую): дело попадёт в план. Не больше
    N дел в неделю (Настройки)."""
    return BacklogRead.model_validate(await svc.take_for_week(item_id, take=True))


@router.delete("/{item_id}/week")
async def drop_backlog_item_from_week(item_id: uuid.UUID, svc: Service) -> BacklogRead:
    """Снять с недели: блок уберёт следующее превью плана."""
    return BacklogRead.model_validate(await svc.take_for_week(item_id, take=False))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backlog_item(item_id: uuid.UUID, svc: Service) -> None:
    await svc.delete(item_id)
