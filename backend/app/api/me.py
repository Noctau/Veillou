from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.settings import UserSettings, UserSettingsPatch
from app.schemas.user import UserRead
from app.services import settings as settings_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.get("/settings")
async def read_settings(user: CurrentUser) -> UserSettings:
    return settings_service.effective_settings(user)


@router.patch("/settings")
async def update_settings(
    patch: UserSettingsPatch,  # type: ignore[valid-type]
    user: CurrentUser,
    db: SessionDep,
) -> UserSettings:
    """Глубокий мёрж: переданные поля меняются, остальные остаются. null — вернуть дефолт."""
    return await settings_service.update_settings(db, user, patch)
