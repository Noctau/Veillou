import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.day_profile import (
    DayProfileCreate,
    DayProfileDay,
    DayProfileDayPut,
    DayProfileRead,
    DayProfileRuleCreate,
    DayProfileRuleRead,
    DayProfileRuleUpdate,
    DayProfileUpdate,
)
from app.services.day_profiles import DayProfileService, profile_read


def get_service(db: SessionDep, user: CurrentUser) -> DayProfileService:
    return DayProfileService(db, user)


Service = Annotated[DayProfileService, Depends(get_service)]

router = APIRouter(tags=["day-profiles"])
NO_CONTENT = status.HTTP_204_NO_CONTENT
CREATED = status.HTTP_201_CREATED


# ---------- режимы ----------


@router.get("/day-profiles")
async def list_profiles(svc: Service) -> list[DayProfileRead]:
    """Режимы дня по позиции: первый — режим по умолчанию."""
    return [profile_read(p) for p in await svc.list_profiles()]


@router.post("/day-profiles", status_code=CREATED)
async def create_profile(data: DayProfileCreate, svc: Service) -> DayProfileRead:
    return profile_read(await svc.create(data))


@router.patch("/day-profiles/{profile_id}")
async def update_profile(
    profile_id: uuid.UUID, patch: DayProfileUpdate, svc: Service
) -> DayProfileRead:
    return profile_read(await svc.update(profile_id, patch))


@router.delete("/day-profiles/{profile_id}", status_code=NO_CONTENT)
async def delete_profile(profile_id: uuid.UUID, svc: Service) -> None:
    """Удаляет режим и его правила назначения."""
    await svc.delete(profile_id)


# ---------- по датам ----------


@router.get("/day-profiles/days")
async def list_days(
    svc: Service, start: Annotated[date, Query()], end: Annotated[date, Query()]
) -> list[DayProfileDay]:
    """Режим каждой даты отрезка [start, end] (не длиннее 93 дней)."""
    return await svc.days(start, end)


@router.put("/day-profiles/days/{day}")
async def set_day(day: date, data: DayProfileDayPut, svc: Service) -> DayProfileDay:
    """Режим одной даты («сегодня — выходной»); null — снова по правилам."""
    return await svc.set_day(day, data.profile_id)


# ---------- правила ----------


@router.get("/day-profile-rules")
async def list_rules(svc: Service) -> list[DayProfileRuleRead]:
    return [DayProfileRuleRead.model_validate(r) for r in await svc.list_rules()]


@router.post("/day-profile-rules", status_code=CREATED)
async def create_rule(data: DayProfileRuleCreate, svc: Service) -> DayProfileRuleRead:
    return DayProfileRuleRead.model_validate(await svc.create_rule(data))


@router.patch("/day-profile-rules/{rule_id}")
async def update_rule(
    rule_id: uuid.UUID, patch: DayProfileRuleUpdate, svc: Service
) -> DayProfileRuleRead:
    return DayProfileRuleRead.model_validate(await svc.update_rule(rule_id, patch))


@router.delete("/day-profile-rules/{rule_id}", status_code=NO_CONTENT)
async def delete_rule(rule_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_rule(rule_id)
