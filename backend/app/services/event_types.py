"""Типы занятости (Part 2, M17.1): CRUD, поля (domain/fields.py) и что делать
со ссылками при удалении.

Удаление типа: его правила расписания удаляются вместе с будущими вхождениями,
участие в лимитах и чип ящика «в дни событий типа» снимаются. Прошедшие события
остаются со ссылкой на удалённый тип — для планировщика и текстов это «просто занято».
"""

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz
from app.domain.fields import FieldError, dump_defs, merge_defs, parse_defs
from app.models import AreaType, BacklogItem, EventType, LoadBudgetMember, ScheduleRule, User
from app.schemas.schedule import EventTypeCreate, EventTypeUpdate
from app.services.base import UserScopedRepository
from app.services.schedule_sync import SeriesSync

# Поля, от которых зависят вхождения правил (название без сферы и своего названия)
_SERIES_FIELDS = {"name", "fields"}
# null допустим: «не напоминать», «без типа сфер»
_NULLABLE = {"remind_before_min", "default_area_type_id"}


class EventTypeRepo(UserScopedRepository[EventType]):
    model = EventType
    not_found_message = "Тип занятости не найден"


class _AreaTypeRepo(UserScopedRepository[AreaType]):
    model = AreaType
    not_found_message = "Тип сферы не найден"


class _RuleRepo(UserScopedRepository[ScheduleRule]):
    model = ScheduleRule


class _MemberRepo(UserScopedRepository[LoadBudgetMember]):
    model = LoadBudgetMember


class EventTypeService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user.id
        self.types = EventTypeRepo(db, user.id)
        self.area_types = _AreaTypeRepo(db, user.id)
        self.rules = _RuleRepo(db, user.id)
        self.members = _MemberRepo(db, user.id)
        self.sync = SeriesSync(db, user.id, get_tz(user.timezone))

    async def list(self) -> list[EventType]:
        return await self.types.find_all(order_by=[EventType.position, EventType.created_at])

    async def get(self, id: uuid.UUID) -> EventType:
        return await self.types.get_or_404(id)

    async def create(self, data: EventTypeCreate) -> EventType:
        try:
            defs = merge_defs([], [f.to_def() for f in data.fields])
        except FieldError as exc:
            raise InvalidDataError(str(exc)) from exc
        if data.default_area_type_id:
            await self.area_types.get_or_404(data.default_area_type_id)
        position = await self.db.scalar(
            select(func.coalesce(func.max(EventType.position) + 1, 0)).where(
                EventType.user_id == self.user_id, EventType.deleted_at.is_(None)
            )
        )
        values = data.model_dump(exclude={"fields", "name_plural"})
        event_type = EventType(
            key=None,
            **values,
            name_plural=data.name_plural or data.name,
            fields=dump_defs(defs),
            position=position or 0,
        )
        self.types.add(event_type)
        await self.db.commit()
        return event_type

    async def update(self, id: uuid.UUID, patch: EventTypeUpdate) -> EventType:
        event_type = await self.types.get_or_404(id)
        changes: dict[str, Any] = patch.model_dump(exclude_unset=True)
        for name, value in changes.items():
            if value is None and name not in _NULLABLE:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if patch.fields is not None:
            try:
                defs = merge_defs(parse_defs(event_type.fields), [f.to_def() for f in patch.fields])
            except FieldError as exc:
                raise InvalidDataError(str(exc)) from exc
            changes["fields"] = dump_defs(defs)
        if changes.get("default_area_type_id"):
            await self.area_types.get_or_404(changes["default_area_type_id"])
        for name, value in changes.items():
            setattr(event_type, name, value)
        await self.db.flush()
        if changes.keys() & _SERIES_FIELDS:
            await self.sync.sync_event_type(event_type.id)
        await self.db.commit()
        return event_type

    async def delete(self, id: uuid.UUID) -> None:
        event_type = await self.types.get_or_404(id)
        for rule in await self.rules.find_all(ScheduleRule.event_type_id == id):
            self.rules.soft_delete(rule)
            await self.sync.remove_series(rule.id)
        for m in await self.members.find_all(LoadBudgetMember.event_type_id == id):
            self.members.soft_delete(m)
        await self.db.execute(
            update(BacklogItem)
            .where(BacklogItem.user_id == self.user_id, BacklogItem.days_event_type_id == id)
            .values(days_event_type_id=None)
        )
        self.types.soft_delete(event_type)
        await self.db.commit()


async def event_types_by_id(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, EventType]:
    """Живые типы занятости пользователя (для планировщика, напоминаний, текстов)."""
    rows = await db.scalars(
        select(EventType).where(EventType.user_id == user_id, EventType.deleted_at.is_(None))
    )
    return {t.id: t for t in rows}
