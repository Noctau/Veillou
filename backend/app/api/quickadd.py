import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.domain.quickparse import needs_ai
from app.schemas.quickadd import QuickParseRead, QuickParseRequest
from app.services import quickadd

router = APIRouter(prefix="/quick-add", tags=["quick-add"])
# Быстрый разбор смотрит только на начало: дальше — текст задания для ИИ
QUICK_LEN = 500


@router.post("/parse")
async def parse_quick_add(
    data: QuickParseRequest, user: CurrentUser, db: SessionDep
) -> QuickParseRead:
    """Разбор строки быстрого ввода «на лету»: название, дата/время, сфера, типы.

    Ничего не сохраняет — клиент создаёт задание / дело / событие обычными запросами.
    `needs_ai` — разбор неуверенный (длинный текст, задание без срока или сферы):
    стоит спросить ИИ (`POST /quick-add/ai-parse`).
    """
    parsed = await quickadd.parse_text(db, user, data.text[:QUICK_LEN])
    result = parsed.result
    return QuickParseRead(
        title=result.title,
        date=result.date,
        time=result.time,
        end_time=result.end_time,
        duration_min=result.duration_min,
        deadline=result.deadline,
        is_deadline=result.is_deadline,
        area_id=result.area_id if isinstance(result.area_id, uuid.UUID) else None,
        task_type_id=parsed.task_type_id,
        action_type_id=parsed.action_type_id,
        event_type_id=parsed.event_type_id,
        kind_hint=result.kind_hint,
        needs_ai=needs_ai(data.text, result, has_areas=parsed.has_areas),
    )
