from dataclasses import asdict

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.quickadd import QuickParseRead, QuickParseRequest
from app.services import quickadd

router = APIRouter(prefix="/quick-add", tags=["quick-add"])


@router.post("/parse")
async def parse_quick_add(
    data: QuickParseRequest, user: CurrentUser, db: SessionDep
) -> QuickParseRead:
    """Разбор строки быстрого ввода «на лету»: название, дата/время, предмет, тип.

    Ничего не сохраняет — клиент создаёт задание / дело / событие обычными запросами.
    """
    result = await quickadd.parse_text(db, user, data.text)
    return QuickParseRead.model_validate(asdict(result))
