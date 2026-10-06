import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.catalog import (
    ActionTypeRead,
    ActionTypeUpdate,
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
)
from app.services.catalog import CatalogService


def get_service(db: SessionDep, user: CurrentUser) -> CatalogService:
    return CatalogService(db, user)


Service = Annotated[CatalogService, Depends(get_service)]

router = APIRouter(tags=["catalog"])


# ---------- категории ----------


@router.get("/categories")
async def list_categories(svc: Service) -> list[CategoryRead]:
    return [CategoryRead.model_validate(c) for c in await svc.list_categories()]


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(data: CategoryCreate, svc: Service) -> CategoryRead:
    return CategoryRead.model_validate(await svc.create_category(data))


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: uuid.UUID, patch: CategoryUpdate, svc: Service
) -> CategoryRead:
    return CategoryRead.model_validate(await svc.update_category(category_id, patch))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: uuid.UUID, svc: Service) -> None:
    """Системные (Учёба, Работа, Быт, Личное) не удаляются — 409."""
    await svc.delete_category(category_id)


# ---------- типы действий ----------


@router.get("/action-types")
async def list_action_types(svc: Service) -> list[ActionTypeRead]:
    return [ActionTypeRead.model_validate(a) for a in await svc.list_action_types()]


@router.patch("/action-types/{action_type_id}")
async def update_action_type(
    action_type_id: uuid.UUID, patch: ActionTypeUpdate, svc: Service
) -> ActionTypeRead:
    return ActionTypeRead.model_validate(await svc.update_action_type(action_type_id, patch))


@router.post("/action-types/{action_type_id}/reset")
async def reset_action_type(action_type_id: uuid.UUID, svc: Service) -> ActionTypeRead:
    """Вернуть окна, название и категорию по умолчанию (ТЗ §4.8)."""
    return ActionTypeRead.model_validate(await svc.reset_action_type(action_type_id))
