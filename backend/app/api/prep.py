import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.prep import (
    PrepItemCreate,
    PrepItemRead,
    PrepItemsImport,
    PrepItemUpdate,
    PrepPlanCreate,
    PrepPlanDetail,
    PrepPlanRead,
    PrepPlanUpdate,
)
from app.services.prep import PrepService


def get_service(db: SessionDep, user: CurrentUser) -> PrepService:
    return PrepService(db, user)


Service = Annotated[PrepService, Depends(get_service)]

router = APIRouter(prefix="/prep-plans", tags=["prep"])
items_router = APIRouter(prefix="/prep-items", tags=["prep"])
NO_CONTENT = status.HTTP_204_NO_CONTENT


@router.get("")
async def list_plans(
    svc: Service, area_id: uuid.UUID | None = None, event_id: uuid.UUID | None = None
) -> list[PrepPlanRead]:
    """Планы подготовки сферы или события; ближайшие — первыми."""
    return await svc.list_plans(area_id, event_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_plan(data: PrepPlanCreate, svc: Service) -> PrepPlanDetail:
    """План к событию (существующему или новому) или к дате."""
    return await svc.create(data)


@router.get("/{plan_id}")
async def read_plan(plan_id: uuid.UUID, svc: Service) -> PrepPlanDetail:
    return await svc.get_detail(plan_id)


@router.patch("/{plan_id}")
async def update_plan(plan_id: uuid.UUID, patch: PrepPlanUpdate, svc: Service) -> PrepPlanDetail:
    return await svc.update(plan_id, patch)


@router.delete("/{plan_id}", status_code=NO_CONTENT)
async def delete_plan(plan_id: uuid.UUID, svc: Service, with_event: bool = False) -> None:
    """Удаляет план (пункты и дни); `with_event` — и само событие."""
    await svc.delete(plan_id, with_event=with_event)


@router.post("/{plan_id}/items/import")
async def import_items(plan_id: uuid.UUID, data: PrepItemsImport, svc: Service) -> PrepPlanDetail:
    """Пункты списком: нумерация «1. …», «1) …», «Билет 1 …» или по одному в строке."""
    return await svc.import_items(plan_id, data.text)


@router.post("/{plan_id}/items", status_code=status.HTTP_201_CREATED)
async def add_item(plan_id: uuid.UUID, data: PrepItemCreate, svc: Service) -> PrepPlanDetail:
    return await svc.add_item(plan_id, data)


@router.post("/{plan_id}/enable")
async def enable_plan(plan_id: uuid.UUID, svc: Service) -> PrepPlanDetail:
    """Построить план: дни подготовки + превью плана (применяет пользователь)."""
    return await svc.enable(plan_id)


@router.post("/{plan_id}/disable")
async def disable_plan(plan_id: uuid.UUID, svc: Service) -> PrepPlanDetail:
    return await svc.disable(plan_id)


@items_router.patch("/{item_id}")
async def update_item(item_id: uuid.UUID, patch: PrepItemUpdate, svc: Service) -> PrepItemRead:
    return await svc.update_item(item_id, patch)


@items_router.delete("/{item_id}", status_code=NO_CONTENT)
async def delete_item(item_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_item(item_id)
