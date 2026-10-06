"""Справочники: категории и типы действий + сид дефолтов из ТЗ §4.8."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, InvalidDataError
from app.domain.enums import ActionTypeKey, CategoryIcon, CategoryKey
from app.models import ActionType, Category, User
from app.schemas.catalog import ActionTypeUpdate, CategoryCreate, CategoryUpdate
from app.services.base import UserScopedRepository


@dataclass(frozen=True)
class DefaultCategory:
    key: CategoryKey
    name: str
    color: str
    icon: CategoryIcon


@dataclass(frozen=True)
class DefaultActionType:
    key: ActionTypeKey
    name: str
    category: CategoryKey
    windows: list[dict[str, Any]]


WEEKDAYS = [1, 2, 3, 4, 5]
ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]


def _w(days: list[int], start: str, end: str) -> dict[str, Any]:
    return {"weekdays": days, "start": start, "end": end}


DEFAULT_CATEGORIES = [
    DefaultCategory(CategoryKey.study, "Учёба", "#3b82f6", CategoryIcon.graduation_cap),
    DefaultCategory(CategoryKey.work, "Работа", "#8b5cf6", CategoryIcon.briefcase),
    DefaultCategory(CategoryKey.home, "Быт", "#f59e0b", CategoryIcon.house),
    DefaultCategory(CategoryKey.personal, "Личное", "#ec4899", CategoryIcon.heart),
]

DEFAULT_ACTION_TYPES = [
    DefaultActionType(
        ActionTypeKey.people, "Связь с людьми", CategoryKey.study, [_w(WEEKDAYS, "09:00", "19:00")]
    ),
    DefaultActionType(
        ActionTypeKey.institutions,
        "Учреждения",
        CategoryKey.home,
        [_w(WEEKDAYS, "10:00", "18:00")],
    ),
    # Любое время, кроме сна (его вычитает планировщик); ночью — до 01:00
    DefaultActionType(
        ActionTypeKey.study,
        "Самостоятельная учёба",
        CategoryKey.study,
        [_w(ALL_DAYS, "07:00", "01:00")],
    ),
    DefaultActionType(
        ActionTypeKey.outside, "Вне дома", CategoryKey.home, [_w(ALL_DAYS, "09:00", "21:00")]
    ),
    DefaultActionType(
        ActionTypeKey.home, "Домашние дела", CategoryKey.home, [_w(ALL_DAYS, "08:00", "22:00")]
    ),
    DefaultActionType(
        ActionTypeKey.personal,
        "Личное",
        CategoryKey.personal,
        [_w(WEEKDAYS, "18:00", "23:00"), _w([6, 7], "10:00", "23:00")],
    ),
]

DEFAULT_ACTION_TYPE_BY_KEY = {d.key: d for d in DEFAULT_ACTION_TYPES}


async def ensure_defaults(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Досеивает недостающие системные категории и типы действий. Идемпотентно и
    безопасно при параллельных запросах (ON CONFLICT DO NOTHING). Не коммитит.

    Возвращает True, если что-то добавлено.
    """
    have = await db.scalar(
        select(func.count())
        .select_from(ActionType)
        .where(ActionType.user_id == user_id, ActionType.deleted_at.is_(None))
    )
    if have == len(DEFAULT_ACTION_TYPES):
        return False

    await db.execute(
        insert(Category)
        .values(
            [
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "key": d.key,
                    "name": d.name,
                    "color": d.color,
                    "icon": d.icon,
                    "position": i,
                }
                for i, d in enumerate(DEFAULT_CATEGORIES)
            ]
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "key"],
            index_where=Category.deleted_at.is_(None) & Category.key.is_not(None),
        )
    )
    rows = await db.execute(
        select(Category.key, Category.id).where(
            Category.user_id == user_id,
            Category.deleted_at.is_(None),
            Category.key.is_not(None),
        )
    )
    category_ids: dict[str | None, uuid.UUID] = {key: id for key, id in rows.all()}
    await db.execute(
        insert(ActionType)
        .values(
            [
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "key": d.key,
                    "name": d.name,
                    "default_category_id": category_ids.get(d.category),
                    "windows": d.windows,
                    "position": i,
                }
                for i, d in enumerate(DEFAULT_ACTION_TYPES)
            ]
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "key"], index_where=ActionType.deleted_at.is_(None)
        )
    )
    return True


class CategoryRepo(UserScopedRepository[Category]):
    model = Category
    not_found_message = "Категория не найдена"


class ActionTypeRepo(UserScopedRepository[ActionType]):
    model = ActionType
    not_found_message = "Тип действия не найден"


class SystemCategoryError(ConflictError):
    code = "system_category"
    message = "Системную категорию нельзя удалить — её можно переименовать"


class CatalogService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user.id
        self.categories = CategoryRepo(db, user.id)
        self.action_types = ActionTypeRepo(db, user.id)

    async def _ensure(self) -> None:
        if await ensure_defaults(self.db, self.user_id):
            await self.db.commit()

    # ---------- категории ----------

    async def list_categories(self) -> list[Category]:
        await self._ensure()
        return await self.categories.find_all(order_by=[Category.position, Category.created_at])

    async def create_category(self, data: CategoryCreate) -> Category:
        last = await self.db.scalar(
            select(func.max(Category.position)).where(
                Category.user_id == self.user_id, Category.deleted_at.is_(None)
            )
        )
        category = Category(
            key=None,
            name=data.name,
            color=data.color,
            icon=data.icon,
            position=(last or 0) + 1,
        )
        self.categories.add(category)
        await self.db.commit()
        return category

    async def update_category(self, id: uuid.UUID, patch: CategoryUpdate) -> Category:
        category = await self.categories.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name, value in changes.items():
            if value is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
            setattr(category, name, value)
        await self.db.commit()
        return category

    async def delete_category(self, id: uuid.UUID) -> None:
        """Своя категория удаляется; дела с ней остаются без категории."""
        category = await self.categories.get_or_404(id)
        if category.key is not None:
            raise SystemCategoryError()
        self.categories.soft_delete(category)
        await self.db.execute(
            update(ActionType)
            .where(ActionType.user_id == self.user_id, ActionType.default_category_id == id)
            .values(default_category_id=None)
        )
        for model in CATEGORY_USERS:
            await self.db.execute(
                update(model)
                .where(model.user_id == self.user_id, model.category_id == id)
                .values(category_id=None)
            )
        await self.db.commit()

    # ---------- типы действий ----------

    async def list_action_types(self) -> list[ActionType]:
        await self._ensure()
        return await self.action_types.find_all(order_by=[ActionType.position])

    async def update_action_type(self, id: uuid.UUID, patch: ActionTypeUpdate) -> ActionType:
        action_type = await self.action_types.get_or_404(id)
        changes = patch.model_dump(mode="json", exclude_unset=True)
        if changes.get("name", "") is None or changes.get("windows", []) is None:
            raise InvalidDataError("Название и окна не могут быть пустыми")
        if category_id := patch.default_category_id:
            await self.categories.get_or_404(category_id)
            changes["default_category_id"] = category_id
        for name, value in changes.items():
            setattr(action_type, name, value)
        await self.db.commit()
        return action_type

    async def reset_action_type(self, id: uuid.UUID) -> ActionType:
        """Вернуть название, окна и категорию по умолчанию."""
        action_type = await self.action_types.get_or_404(id)
        default = DEFAULT_ACTION_TYPE_BY_KEY[ActionTypeKey(action_type.key)]
        category = await self.db.scalar(
            self.categories.select().where(Category.key == default.category)
        )
        action_type.name = default.name
        action_type.windows = default.windows
        action_type.default_category_id = category.id if category else None
        await self.db.commit()
        return action_type


# Модели с полем category_id: при удалении категории ссылки обнуляются (M4.2+)
CATEGORY_USERS: tuple[Any, ...] = ()
