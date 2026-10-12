import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.schedule import (
    DayOffCreate,
    DayOffRead,
    DayOffUpdate,
    EventTypeCreate,
    EventTypeRead,
    EventTypeUpdate,
    PeriodCreate,
    PeriodRead,
    PeriodUpdate,
    ScheduleRuleCreate,
    ScheduleRuleRead,
    ScheduleRuleUpdate,
    SlotGridPut,
    SlotGridRead,
)
from app.services.event_types import EventTypeService
from app.services.schedule import ScheduleService


def get_service(db: SessionDep, user: CurrentUser) -> ScheduleService:
    return ScheduleService(db, user)


def get_types(db: SessionDep, user: CurrentUser) -> EventTypeService:
    return EventTypeService(db, user)


Service = Annotated[ScheduleService, Depends(get_service)]
Types = Annotated[EventTypeService, Depends(get_types)]

router = APIRouter(tags=["schedule"])
NO_CONTENT = status.HTTP_204_NO_CONTENT
CREATED = status.HTTP_201_CREATED


# ---------- типы занятости ----------


@router.get("/event-types")
async def list_event_types(svc: Types) -> list[EventTypeRead]:
    return [EventTypeRead.model_validate(t) for t in await svc.list()]


@router.post("/event-types", status_code=CREATED)
async def create_event_type(data: EventTypeCreate, svc: Types) -> EventTypeRead:
    return EventTypeRead.model_validate(await svc.create(data))


@router.patch("/event-types/{type_id}")
async def update_event_type(
    type_id: uuid.UUID, patch: EventTypeUpdate, svc: Types
) -> EventTypeRead:
    return EventTypeRead.model_validate(await svc.update(type_id, patch))


@router.delete("/event-types/{type_id}", status_code=NO_CONTENT)
async def delete_event_type(type_id: uuid.UUID, svc: Types) -> None:
    """Удаляет тип, его правила (с будущими вхождениями) и участие в лимитах."""
    await svc.delete(type_id)


# ---------- периоды ----------


@router.get("/periods")
async def list_periods(svc: Service) -> list[PeriodRead]:
    return [PeriodRead.model_validate(p) for p in await svc.list_periods()]


@router.post("/periods", status_code=CREATED)
async def create_period(data: PeriodCreate, svc: Service) -> PeriodRead:
    return PeriodRead.model_validate(await svc.create_period(data))


@router.patch("/periods/{period_id}")
async def update_period(period_id: uuid.UUID, patch: PeriodUpdate, svc: Service) -> PeriodRead:
    return PeriodRead.model_validate(await svc.update_period(period_id, patch))


@router.delete("/periods/{period_id}", status_code=NO_CONTENT)
async def delete_period(period_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_period(period_id)


# ---------- сетки слотов ----------


@router.get("/slot-grids")
async def list_slot_grids(svc: Service, period_id: uuid.UUID | None = None) -> list[SlotGridRead]:
    """Строки всех сеток (или сеток периода): сетка — строки с одним (period_id, name)."""
    return [SlotGridRead.model_validate(g) for g in await svc.list_grids(period_id)]


@router.put("/slot-grids")
async def put_slot_grid(data: SlotGridPut, svc: Service) -> list[SlotGridRead]:
    """Сетка целиком: общие слоты (weekday = null) + переопределения дней."""
    return [SlotGridRead.model_validate(g) for g in await svc.put_grid(data)]


@router.delete("/slot-grids/{grid_id}", status_code=NO_CONTENT)
async def delete_slot_grid(grid_id: uuid.UUID, svc: Service) -> None:
    """Удаляет сетку (по id общей строки); если по ней есть правила — 409."""
    await svc.delete_grid(grid_id)


# ---------- исключения ----------


@router.get("/days-off")
async def list_days_off(svc: Service) -> list[DayOffRead]:
    return [DayOffRead.model_validate(d) for d in await svc.list_days_off()]


@router.post("/days-off", status_code=CREATED)
async def create_day_off(data: DayOffCreate, svc: Service) -> DayOffRead:
    return DayOffRead.model_validate(await svc.create_day_off(data))


@router.patch("/days-off/{day_off_id}")
async def update_day_off(day_off_id: uuid.UUID, patch: DayOffUpdate, svc: Service) -> DayOffRead:
    return DayOffRead.model_validate(await svc.update_day_off(day_off_id, patch))


@router.delete("/days-off/{day_off_id}", status_code=NO_CONTENT)
async def delete_day_off(day_off_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_day_off(day_off_id)


# ---------- правила расписания ----------


@router.get("/schedule-rules")
async def list_schedule_rules(
    svc: Service,
    period_id: uuid.UUID | None = None,
    area_id: uuid.UUID | None = None,
    event_type_id: uuid.UUID | None = None,
) -> list[ScheduleRuleRead]:
    rules = await svc.list_rules(period_id, area_id, event_type_id)
    return [ScheduleRuleRead.model_validate(r) for r in rules]


@router.post("/schedule-rules", status_code=CREATED)
async def create_schedule_rule(data: ScheduleRuleCreate, svc: Service) -> ScheduleRuleRead:
    return ScheduleRuleRead.model_validate(await svc.create_rule(data))


@router.patch("/schedule-rules/{rule_id}")
async def update_schedule_rule(
    rule_id: uuid.UUID, patch: ScheduleRuleUpdate, svc: Service
) -> ScheduleRuleRead:
    return ScheduleRuleRead.model_validate(await svc.update_rule(rule_id, patch))


@router.delete("/schedule-rules/{rule_id}", status_code=NO_CONTENT)
async def delete_schedule_rule(rule_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_rule(rule_id)
