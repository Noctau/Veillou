import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.event_rule import EventRuleCreate, EventRuleRead, EventRuleUpdate
from app.services.event_tasks import EventRuleService


def get_service(db: SessionDep, user: CurrentUser) -> EventRuleService:
    return EventRuleService(db, user)


Service = Annotated[EventRuleService, Depends(get_service)]

router = APIRouter(prefix="/event-rules", tags=["event-rules"])


@router.get("")
async def list_event_rules(
    svc: Service, event_type_id: uuid.UUID | None = None, schedule_rule_id: uuid.UUID | None = None
) -> list[EventRuleRead]:
    """Автозадачи типа занятости или правила расписания (без фильтра — все)."""
    rules = await svc.list_rules(event_type_id, schedule_rule_id)
    return [EventRuleRead.model_validate(r) for r in rules]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event_rule(data: EventRuleCreate, svc: Service) -> EventRuleRead:
    """Создаёт правило и сразу задачи на горизонт вхождений."""
    return EventRuleRead.model_validate(await svc.create(data))


@router.patch("/{rule_id}")
async def update_event_rule(
    rule_id: uuid.UUID, patch: EventRuleUpdate, svc: Service
) -> EventRuleRead:
    return EventRuleRead.model_validate(await svc.update(rule_id, patch))


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_rule(rule_id: uuid.UUID, svc: Service) -> None:
    """Удаляет правило и его будущие несделанные задачи."""
    await svc.delete(rule_id)
