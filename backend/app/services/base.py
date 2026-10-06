import uuid
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.exceptions import InvalidDataError, NotFoundError, format_validation_error
from app.core.time import now_utc
from app.models.base import UserOwnedMixin


class UserScopedRepository[M: UserOwnedMixin]:
    """Базовый репозиторий для данных пользователя.

    Каждый запрос автоматически ограничен `user_id = :me AND deleted_at IS NULL`,
    удаление — мягкое. Чужие и удалённые записи для репозитория не существуют.
    """

    model: type[M]
    not_found_message: str = "Не найдено"

    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id

    def select(self) -> Select[tuple[M]]:
        return select(self.model).where(
            self.model.user_id == self.user_id,
            self.model.deleted_at.is_(None),
        )

    async def get(self, id: uuid.UUID) -> M | None:
        return await self.session.scalar(self.select().where(self.model.id == id))

    async def get_or_404(self, id: uuid.UUID) -> M:
        obj = await self.get(id)
        if obj is None:
            raise NotFoundError(self.not_found_message)
        return obj

    async def find_all(
        self,
        *where: ColumnElement[bool],
        order_by: Sequence[Any] = (),
        offset: int = 0,
        limit: int | None = None,
    ) -> list[M]:
        stmt = self.select().where(*where).order_by(*order_by).offset(offset).limit(limit)
        return list(await self.session.scalars(stmt))

    def add(self, obj: M) -> M:
        obj.user_id = self.user_id
        self.session.add(obj)
        return obj

    def update(self, obj: M, **fields: Any) -> M:
        for name, value in fields.items():
            setattr(obj, name, value)
        return obj

    def soft_delete(self, obj: M) -> None:
        obj.deleted_at = now_utc()


def validate_patch[T: BaseModel](obj: object, patch: BaseModel, schema: type[T]) -> T:
    """Накладывает частичное обновление на текущие поля `obj` и валидирует итог схемой.

    Так межполевые проверки схемы создания работают и для PATCH.
    """
    data = {name: getattr(obj, name) for name in schema.model_fields if hasattr(obj, name)}
    data.update(patch.model_dump(exclude_unset=True))
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise InvalidDataError(format_validation_error(exc)) from exc


def apply_fields(obj: object, data: BaseModel, *, exclude: set[str] | None = None) -> None:
    for name, value in data.model_dump(exclude=exclude).items():
        setattr(obj, name, value)
