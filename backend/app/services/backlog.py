"""Долгий ящик: дела без срока. В планировщик попадут в M11."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import now_utc
from app.domain.enums import BacklogStatus
from app.domain.quickparse import guess_action_type
from app.models import ActionType, BacklogItem, Category, User
from app.schemas.backlog import BacklogCreate, BacklogUpdate
from app.services.base import UserScopedRepository
from app.services.catalog import ensure_defaults


class BacklogRepo(UserScopedRepository[BacklogItem]):
    model = BacklogItem
    not_found_message = "Дело не найдено"


class _CategoryRepo(UserScopedRepository[Category]):
    model = Category
    not_found_message = "Категория не найдена"


class _ActionTypeRepo(UserScopedRepository[ActionType]):
    model = ActionType
    not_found_message = "Тип действия не найден"


_REQUIRED = {"title", "note", "conditions", "status"}


class BacklogService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user.id
        self.items = BacklogRepo(db, user.id)
        self.categories = _CategoryRepo(db, user.id)
        self.action_types = _ActionTypeRepo(db, user.id)

    async def list(self, status: BacklogStatus = BacklogStatus.active) -> list[BacklogItem]:
        """Активные: сначала с желаемым сроком (ближайший первым), потом самые старые.
        Архив и сделанные — последние сверху."""
        if status == BacklogStatus.active:
            order = [
                BacklogItem.desired_by.asc().nulls_last(),
                BacklogItem.created_at.asc(),
            ]
        else:
            stamp = BacklogItem.done_at if status == BacklogStatus.done else BacklogItem.archived_at
            order = [stamp.desc().nulls_last(), BacklogItem.created_at.desc()]
        return await self.items.find_all(BacklogItem.status == status, order_by=order)

    async def _check_refs(self, data: dict[str, Any]) -> None:
        if data.get("category_id"):
            await self.categories.get_or_404(data["category_id"])
        if data.get("action_type_id"):
            await self.action_types.get_or_404(data["action_type_id"])

    async def create(self, data: BacklogCreate) -> BacklogItem:
        fields = data.model_dump(mode="json")
        fields["category_id"] = data.category_id
        fields["action_type_id"] = data.action_type_id
        fields["desired_by"] = data.desired_by
        await self._check_refs(fields)

        action_type: ActionType | None = None
        if fields["action_type_id"] is None and (key := guess_action_type(data.title)):
            if await ensure_defaults(self.db, self.user_id):
                await self.db.flush()
            action_type = await self.db.scalar(
                self.action_types.select().where(ActionType.key == key)
            )
            fields["action_type_id"] = action_type.id if action_type else None
        elif fields["action_type_id"] is not None:
            action_type = await self.action_types.get_or_404(fields["action_type_id"])
        if fields["category_id"] is None and action_type is not None:
            fields["category_id"] = action_type.default_category_id

        item = BacklogItem(status=BacklogStatus.active, **fields)
        self.items.add(item)
        await self.db.commit()
        return item

    async def update(self, id: uuid.UUID, patch: BacklogUpdate) -> BacklogItem:
        item = await self.items.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name in _REQUIRED & changes.keys():
            if changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        await self._check_refs(changes)
        if "time_window" in changes:
            changes["time_window"] = patch.model_dump(mode="json")["time_window"]
        if "conditions" in changes:
            changes["conditions"] = [str(c) for c in changes["conditions"]]
        if (status := changes.get("status")) and status != item.status:
            now = now_utc()
            changes["done_at"] = now if status == BacklogStatus.done else None
            changes["archived_at"] = now if status == BacklogStatus.archived else None
        for name, value in changes.items():
            setattr(item, name, value)
        await self.db.commit()
        return item

    async def delete(self, id: uuid.UUID) -> None:
        self.items.soft_delete(await self.items.get_or_404(id))
        await self.db.commit()
