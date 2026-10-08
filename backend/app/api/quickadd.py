from dataclasses import asdict

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
    """Разбор строки быстрого ввода «на лету»: название, дата/время, предмет, тип.

    Ничего не сохраняет — клиент создаёт задание / дело / событие обычными запросами.
    `needs_ai` — разбор неуверенный (длинный текст, задание без срока или предмета):
    стоит спросить ИИ (`POST /quick-add/ai-parse`).
    """
    result = await quickadd.parse_text(db, user, data.text[:QUICK_LEN])
    return QuickParseRead.model_validate(
        {**asdict(result), "needs_ai": needs_ai(data.text, result)}
    )
