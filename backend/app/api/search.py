import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SessionDep
from app.schemas.search import SearchResults
from app.services.search import SearchService

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(
    user: CurrentUser,
    db: SessionDep,
    q: Annotated[str, Query(max_length=200)],
    area_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchResults:
    """Конспекты (название и текст) и литература (название, автор, заметка).
    Каждое слово — префикс: искать можно по мере набора. Самое подходящее — первым."""
    return await SearchService(db, user).search(q, area_id=area_id, limit=limit)
