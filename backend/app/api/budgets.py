import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.budget import (
    BudgetOverridePut,
    BudgetOverrideRead,
    LoadBudgetCreate,
    LoadBudgetRead,
    LoadBudgetUpdate,
)
from app.services.budgets import BudgetService


def get_service(db: SessionDep, user: CurrentUser) -> BudgetService:
    return BudgetService(db, user)


Service = Annotated[BudgetService, Depends(get_service)]

router = APIRouter(prefix="/load-budgets", tags=["budgets"])


@router.get("")
async def list_budgets(svc: Service) -> list[LoadBudgetRead]:
    """Лимиты нагрузки с составом и разовыми лимитами на сегодня и дальше."""
    return await svc.list_all()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_budget(data: LoadBudgetCreate, svc: Service) -> LoadBudgetRead:
    return await svc.create(data)


@router.patch("/{budget_id}")
async def update_budget(
    budget_id: uuid.UUID, patch: LoadBudgetUpdate, svc: Service
) -> LoadBudgetRead:
    """`action_type_ids` — состав целиком."""
    return await svc.update(budget_id, patch)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(budget_id: uuid.UUID, svc: Service) -> None:
    await svc.delete(budget_id)


@router.put("/{budget_id}/overrides/{day}")
async def put_override(
    budget_id: uuid.UUID, day: date, data: BudgetOverridePut, svc: Service
) -> BudgetOverrideRead:
    """«Расширить часы в этот день»: лимит на дату вместо обычного."""
    return await svc.put_override(budget_id, day, data.minutes)


@router.delete("/{budget_id}/overrides/{day}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_override(budget_id: uuid.UUID, day: date, svc: Service) -> None:
    await svc.delete_override(budget_id, day)
