import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.area import (
    AreaCreate,
    AreaRead,
    AreaTypeCreate,
    AreaTypeRead,
    AreaTypeUpdate,
    AreaUpdate,
)
from app.services.areas import AreaService


def get_service(db: SessionDep, user: CurrentUser) -> AreaService:
    return AreaService(db, user)


Service = Annotated[AreaService, Depends(get_service)]

router = APIRouter(tags=["areas"])
NO_CONTENT = status.HTTP_204_NO_CONTENT


# ---------- типы сфер ----------


@router.get("/area-types")
async def list_area_types(svc: Service) -> list[AreaTypeRead]:
    return [AreaTypeRead.model_validate(t) for t in await svc.list_types()]


@router.post("/area-types", status_code=status.HTTP_201_CREATED)
async def create_area_type(data: AreaTypeCreate, svc: Service) -> AreaTypeRead:
    return AreaTypeRead.model_validate(await svc.create_type(data))


@router.patch("/area-types/{area_type_id}")
async def update_area_type(
    area_type_id: uuid.UUID, patch: AreaTypeUpdate, svc: Service
) -> AreaTypeRead:
    """`fields` — полный список: поле без id — новое, пропавшее — удалено (значения
    сфер остаются и вернутся, если поле с тем же id прислать снова)."""
    return AreaTypeRead.model_validate(await svc.update_type(area_type_id, patch))


@router.delete("/area-types/{area_type_id}", status_code=NO_CONTENT)
async def delete_area_type(area_type_id: uuid.UUID, svc: Service) -> None:
    """Тип с живыми сферами не удаляется — 409."""
    await svc.delete_type(area_type_id)


# ---------- сферы ----------


@router.get("/areas")
async def list_areas(svc: Service, period_id: uuid.UUID | None = None) -> list[AreaRead]:
    """Все сферы (и архивные — у них `archived_at`), по названию."""
    return [AreaRead.model_validate(a) for a in await svc.list_areas(period_id)]


@router.get("/areas/{area_id}")
async def read_area(area_id: uuid.UUID, svc: Service) -> AreaRead:
    return AreaRead.model_validate(await svc.get_area(area_id))


@router.post("/areas", status_code=status.HTTP_201_CREATED)
async def create_area(data: AreaCreate, svc: Service) -> AreaRead:
    return AreaRead.model_validate(await svc.create_area(data))


@router.patch("/areas/{area_id}")
async def update_area(area_id: uuid.UUID, patch: AreaUpdate, svc: Service) -> AreaRead:
    return AreaRead.model_validate(await svc.update_area(area_id, patch))


@router.delete("/areas/{area_id}", status_code=NO_CONTENT)
async def delete_area(area_id: uuid.UUID, svc: Service) -> None:
    """Удаляет сферу и её правила пар; задачи и заметки остаются."""
    await svc.delete_area(area_id)
