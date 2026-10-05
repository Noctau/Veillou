import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.exceptions import NotFoundError
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
