from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.schemas.settings import UserSettings, deep_merge


class InvalidSettingsError(AppError):
    status_code = 422
    code = "invalid_settings"


def _defaults() -> dict[str, Any]:
    return UserSettings().model_dump(mode="json")


def effective_settings(user: User) -> UserSettings:
    return UserSettings.model_validate(deep_merge(_defaults(), user.settings or {}))


async def update_settings(db: AsyncSession, user: User, patch: BaseModel) -> UserSettings:
    """Глубокий мёрж patch в переопределения пользователя.

    Поле со значением null сбрасывает переопределение к дефолту.
    """
    changes = patch.model_dump(mode="json", exclude_unset=True)
    overrides = deep_merge(user.settings or {}, changes)
    try:
        result = UserSettings.model_validate(deep_merge(_defaults(), overrides))
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors()
        )
        raise InvalidSettingsError(details) from exc

    user.settings = overrides  # новый dict -> SQLAlchemy видит изменение JSONB
    await db.commit()
    return result
