from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.schemas.telegram import TelegramLinkCodeRead, TelegramStatus
from app.services import telegram

router = APIRouter(prefix="/me/telegram", tags=["telegram"])


@router.get("")
async def telegram_status(user: CurrentUser) -> TelegramStatus:
    return TelegramStatus(
        linked=user.tg_user_id is not None, bot_username=settings.TELEGRAM_BOT_USERNAME
    )


@router.post("/link-code")
async def create_telegram_link_code(user: CurrentUser, db: SessionDep) -> TelegramLinkCodeRead:
    """Одноразовый код (10 мин) для `/start <код>` в боте."""
    code = await telegram.create_link_code(db, user)
    return TelegramLinkCodeRead(
        code=code.code, expires_at=code.expires_at, deep_link=code.deep_link
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_telegram(user: CurrentUser, db: SessionDep) -> None:
    await telegram.unlink(db, user)
