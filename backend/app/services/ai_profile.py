"""Контекст ИИ на конфигурации пользователя (M21.2): «о себе» из настроек, сферы,
типы задач, действий и категории. Промпты получают их названия (`ai.prompts.Profile`),
схемы ответов — те же названия как enum (`ai.schemas.with_choices`); ответ модели
переводится обратно в id по названию."""

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import AreaHint, Hint, Profile
from app.ai.schemas import with_choices
from app.models import ActionType, AreaType, Category, User
from app.services.areas import active_areas
from app.services.catalog import TaskTypes, ensure_defaults, load_task_types
from app.services.settings import effective_settings


def _index(items: list[tuple[str, uuid.UUID]]) -> dict[str, uuid.UUID]:
    """Название → id; при одинаковых названиях — первое по порядку."""
    result: dict[str, uuid.UUID] = {}
    for name, id in items:
        result.setdefault(name, id)
    return result


@dataclass
class AIContext:
    profile: Profile
    task_types: TaskTypes
    areas: dict[str, uuid.UUID] = field(default_factory=dict)
    actions: dict[str, uuid.UUID] = field(default_factory=dict)
    categories: dict[str, uuid.UUID] = field(default_factory=dict)

    def schema[T: BaseModel](self, schema: type[T]) -> type[T]:
        """Схема ответа, суженная до названий справочников пользователя."""
        return with_choices(
            schema,
            area=list(self.areas),
            task_type=self.task_types.names(),
            action_type=list(self.actions),
            category=list(self.categories),
        )

    def area_id(self, name: str | None) -> uuid.UUID | None:
        return self.areas.get(name) if name else None

    def action_id(self, name: str | None) -> uuid.UUID | None:
        return self.actions.get(name) if name else None

    def category_id(self, name: str | None) -> uuid.UUID | None:
        return self.categories.get(name) if name else None


async def load_ai_context(db: AsyncSession, user: User, today: date) -> AIContext:
    if await ensure_defaults(db, user.id):
        await db.flush()
    areas = await active_areas(db, user, today)
    type_rows = await db.execute(
        select(AreaType.id, AreaType.name).where(
            AreaType.user_id == user.id, AreaType.deleted_at.is_(None)
        )
    )
    type_names = {id: name for id, name in type_rows.all()}

    def rows(model: Any) -> Any:
        return db.scalars(
            select(model)
            .where(model.user_id == user.id, model.deleted_at.is_(None))
            .order_by(model.position, model.created_at)
        )

    actions = list(await rows(ActionType))
    categories = list(await rows(Category))
    task_types = await load_task_types(db, user.id)
    profile = Profile(
        about=effective_settings(user).about,
        areas=[
            AreaHint(
                a.name, type_names.get(a.area_type_id, ""), tuple(filter(None, [a.short_name]))
            )
            for a in areas
        ],
        task_types=task_types.hints(),
        action_types=[Hint(a.name, tuple(a.synonyms)) for a in actions],
        categories=[c.name for c in categories],
    )
    return AIContext(
        profile=profile,
        task_types=task_types,
        areas=_index([(a.name, a.id) for a in areas]),
        actions=_index([(a.name, a.id) for a in actions]),
        categories=_index([(c.name, c.id) for c in categories]),
    )
