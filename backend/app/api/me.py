from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUser, SessionDep, SessionToken
from app.schemas.settings import UserSettings, UserSettingsPatch
from app.schemas.user import PasswordChange, UserRead, UserUpdate
from app.services import auth
from app.services import settings as settings_service
from app.services.users import update_me

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("")
async def patch_me(data: UserUpdate, user: CurrentUser, db: SessionDep) -> UserRead:
    """Часовой пояс: расписание пересобирается в новом поясе (настенное время то же)."""
    return UserRead.model_validate(await update_me(db, user, data))


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: PasswordChange,
    request: Request,
    user: CurrentUser,
    db: SessionDep,
    token: SessionToken = None,
) -> None:
    """Смена пароля: нужен текущий. Другие устройства выходят, это — остаётся."""
    await auth.change_password(
        db,
        user,
        current=data.current_password,
        new=data.new_password,
        keep_token=token,
        ip=request.client.host if request.client else None,
    )


@router.get("/settings")
async def read_settings(user: CurrentUser) -> UserSettings:
    return settings_service.effective_settings(user)


@router.patch("/settings")
async def update_settings(
    patch: UserSettingsPatch,  # type: ignore[valid-type]  # модель создаётся в рантайме (_partial)
    user: CurrentUser,
    db: SessionDep,
) -> UserSettings:
    """Глубокий мёрж: переданные поля меняются, остальные остаются. null — вернуть дефолт."""
    return await settings_service.update_settings(db, user, patch)
