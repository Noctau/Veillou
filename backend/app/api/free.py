from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SessionDep
from app.schemas.event import EventRead
from app.schemas.review import FreeStart, FreeSuggestion
from app.services.free import FreeService

router = APIRouter(prefix="/free", tags=["review"])


@router.get("")
async def suggest_free(
    db: SessionDep, user: CurrentUser, minutes: Annotated[int, Query(ge=5, le=480)]
) -> list[FreeSuggestion]:
    """«У меня есть N минут»: лучшее подходящее дело и до двух альтернатив."""
    return await FreeService(db, user).suggest(minutes)


@router.post("/start")
async def start_free(data: FreeStart, db: SessionDep, user: CurrentUser) -> EventRead:
    """«Начать»: блок на «сейчас», закреплённый (у шага — переносится его блок)."""
    return EventRead.model_validate(await FreeService(db, user).start(data.kind, data.id))
