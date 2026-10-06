import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.common import Moment
from app.schemas.event import (
    CalendarDayOff,
    CalendarRead,
    EventCreate,
    EventRead,
    EventUpdate,
    RecurringEventCreate,
    RecurringEventRead,
    RecurringEventUpdate,
)
from app.services.events import EventService


def get_service(db: SessionDep, user: CurrentUser) -> EventService:
    return EventService(db, user)


Service = Annotated[EventService, Depends(get_service)]

router = APIRouter(prefix="/events", tags=["events"])
calendar_router = APIRouter(tags=["events"])
recurring_router = APIRouter(prefix="/recurring-events", tags=["events"])


@calendar_router.get("/calendar")
async def read_calendar(
    svc: Service,
    from_: Annotated[Moment, Query(alias="from")],
    to: Moment,
) -> CalendarRead:
    """Всё, что пересекает [from, to): пары, личные блоки, отдых (включая отменённые)
    и выходные. Даты — с часовым поясом."""
    events, days_off = await svc.calendar(from_, to)
    return CalendarRead(
        events=[EventRead.model_validate(e) for e in events],
        days_off=[CalendarDayOff.model_validate(d) for d in days_off],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event(data: EventCreate, svc: Service) -> EventRead:
    return EventRead.model_validate(await svc.create(data))


@router.get("/{event_id}")
async def read_event(event_id: uuid.UUID, svc: Service) -> EventRead:
    return EventRead.model_validate(await svc.get(event_id))


@router.patch("/{event_id}")
async def update_event(event_id: uuid.UUID, patch: EventUpdate, svc: Service) -> EventRead:
    """Правка вхождения пары/повтора (отмена, перенос, аудитория) ставит detached=true."""
    return EventRead.model_validate(await svc.update(event_id, patch))


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: uuid.UUID, svc: Service) -> None:
    await svc.delete(event_id)


@router.post("/{event_id}/reset")
async def reset_event(event_id: uuid.UUID, svc: Service) -> EventRead:
    """Вернуть вхождение как в расписании (снять detached). Если в этот день по
    шаблону вхождения больше нет — событие удаляется (404 при следующем чтении)."""
    return EventRead.model_validate(await svc.reset(event_id))


# ---------- личные повторы ----------


@recurring_router.get("")
async def list_recurring_events(svc: Service) -> list[RecurringEventRead]:
    return [RecurringEventRead.model_validate(r) for r in await svc.list_recurring()]


@recurring_router.post("", status_code=status.HTTP_201_CREATED)
async def create_recurring_event(data: RecurringEventCreate, svc: Service) -> RecurringEventRead:
    """Повтор материализуется в календарь на 90 дней вперёд."""
    return RecurringEventRead.model_validate(await svc.create_recurring(data))


@recurring_router.patch("/{recurring_id}")
async def update_recurring_event(
    recurring_id: uuid.UUID, patch: RecurringEventUpdate, svc: Service
) -> RecurringEventRead:
    return RecurringEventRead.model_validate(await svc.update_recurring(recurring_id, patch))


@recurring_router.delete("/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_event(recurring_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_recurring(recurring_id)
