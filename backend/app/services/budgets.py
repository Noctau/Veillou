"""Лимиты нагрузки (M15.3): CRUD, состав (типы действий) и разовые лимиты дня.

Разовый лимит — вариант «расширить часы в этот день» при угрозе дедлайну.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc
from app.domain.planner import Budget
from app.models import ActionType, BudgetDayOverride, LoadBudget, LoadBudgetMember, User
from app.schemas.budget import (
    BudgetOverrideRead,
    LoadBudgetCreate,
    LoadBudgetRead,
    LoadBudgetUpdate,
)
from app.services.base import UserScopedRepository


class LoadBudgetRepo(UserScopedRepository[LoadBudget]):
    model = LoadBudget
    not_found_message = "Лимит не найден"


class _MemberRepo(UserScopedRepository[LoadBudgetMember]):
    model = LoadBudgetMember


class _OverrideRepo(UserScopedRepository[BudgetDayOverride]):
    model = BudgetDayOverride
    not_found_message = "Разового лимита на этот день нет"


class _ActionTypeRepo(UserScopedRepository[ActionType]):
    model = ActionType
    not_found_message = "Тип действия не найден"


class BudgetService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.budgets = LoadBudgetRepo(db, user.id)
        self.members = _MemberRepo(db, user.id)
        self.overrides = _OverrideRepo(db, user.id)
        self.action_types = _ActionTypeRepo(db, user.id)

    async def _read(self, budgets: list[LoadBudget]) -> list[LoadBudgetRead]:
        ids = [b.id for b in budgets]
        members: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        for m in await self.members.find_all(
            LoadBudgetMember.budget_id.in_(ids), order_by=[LoadBudgetMember.created_at]
        ):
            if m.action_type_id is not None:
                members[m.budget_id].append(m.action_type_id)
        today = local_date(now_utc(), self.tz)
        overrides: dict[uuid.UUID, list[BudgetOverrideRead]] = defaultdict(list)
        for o in await self.overrides.find_all(
            BudgetDayOverride.budget_id.in_(ids),
            BudgetDayOverride.date >= today,
            order_by=[BudgetDayOverride.date],
        ):
            overrides[o.budget_id].append(BudgetOverrideRead.model_validate(o))
        return [
            LoadBudgetRead(
                id=b.id,
                name=b.name,
                minutes_per_day=b.minutes_per_day,
                position=b.position,
                action_type_ids=members.get(b.id, []),
                overrides=overrides.get(b.id, []),
            )
            for b in budgets
        ]

    async def list_all(self) -> list[LoadBudgetRead]:
        return await self._read(
            await self.budgets.find_all(order_by=[LoadBudget.position, LoadBudget.created_at])
        )

    async def get(self, id: uuid.UUID) -> LoadBudgetRead:
        return (await self._read([await self.budgets.get_or_404(id)]))[0]

    async def _set_members(self, budget: LoadBudget, action_type_ids: list[uuid.UUID]) -> None:
        for type_id in action_type_ids:
            await self.action_types.get_or_404(type_id)
        current = await self.members.find_all(LoadBudgetMember.budget_id == budget.id)
        keep = set(action_type_ids)
        for m in current:
            if m.action_type_id not in keep:
                self.members.soft_delete(m)
        have = {m.action_type_id for m in current}
        for type_id in action_type_ids:
            if type_id not in have:
                self.members.add(LoadBudgetMember(budget_id=budget.id, action_type_id=type_id))

    async def create(self, data: LoadBudgetCreate) -> LoadBudgetRead:
        last = await self.db.scalar(
            select(func.max(LoadBudget.position)).where(
                LoadBudget.user_id == self.user_id, LoadBudget.deleted_at.is_(None)
            )
        )
        budget = LoadBudget(
            name=data.name,
            minutes_per_day=data.minutes_per_day,
            position=(last if last is not None else -1) + 1,
        )
        self.budgets.add(budget)
        await self.db.flush()
        await self._set_members(budget, data.action_type_ids)
        await self.db.commit()
        return await self.get(budget.id)

    async def update(self, id: uuid.UUID, patch: LoadBudgetUpdate) -> LoadBudgetRead:
        budget = await self.budgets.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name in changes.keys() & {"name", "minutes_per_day", "position", "action_type_ids"}:
            if changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if (ids := changes.pop("action_type_ids", None)) is not None:
            await self._set_members(budget, ids)
        for name, value in changes.items():
            setattr(budget, name, value)
        await self.db.commit()
        return await self.get(id)

    async def delete(self, id: uuid.UUID) -> None:
        budget = await self.budgets.get_or_404(id)
        for m in await self.members.find_all(LoadBudgetMember.budget_id == id):
            self.members.soft_delete(m)
        for o in await self.overrides.find_all(BudgetDayOverride.budget_id == id):
            self.overrides.soft_delete(o)
        self.budgets.soft_delete(budget)
        await self.db.commit()

    # ---------- разовые лимиты дня ----------

    async def put_override(self, id: uuid.UUID, day: date, minutes: int) -> BudgetOverrideRead:
        """Upsert одним запросом: параллельные PUT на тот же день не падают на
        уникальном индексе."""
        await self.budgets.get_or_404(id)
        stmt = (
            insert(BudgetDayOverride)
            .values(id=uuid.uuid4(), user_id=self.user_id, budget_id=id, date=day, minutes=minutes)
            .on_conflict_do_update(
                index_elements=["budget_id", "date"],
                index_where=BudgetDayOverride.deleted_at.is_(None),
                set_={"minutes": minutes, "updated_at": func.now()},
            )
            .returning(BudgetDayOverride.id)
        )
        item_id = await self.db.scalar(stmt)
        await self.db.commit()
        if item_id is None:  # RETURNING есть и у вставки, и у обновления
            raise RuntimeError("Лимит не сохранён")
        return BudgetOverrideRead.model_validate(await self.overrides.get_or_404(item_id))

    async def delete_override(self, id: uuid.UUID, day: date) -> None:
        await self.budgets.get_or_404(id)
        item = await self.db.scalar(
            self.overrides.select().where(
                BudgetDayOverride.budget_id == id, BudgetDayOverride.date == day
            )
        )
        if item is not None:
            self.overrides.soft_delete(item)
            await self.db.commit()


# ---------- для планировщика ----------


@dataclass(frozen=True)
class BudgetIndex:
    """Лимиты пользователя для `PlanInput` и в какие лимиты идёт каждый тип действия."""

    budgets: tuple[Budget, ...]
    by_action: dict[uuid.UUID, frozenset[uuid.UUID]]

    def of(self, action_type_id: uuid.UUID | None) -> frozenset[uuid.UUID]:
        return self.by_action.get(action_type_id, frozenset()) if action_type_id else frozenset()


async def budget_index(db: AsyncSession, user_id: uuid.UUID, today: date) -> BudgetIndex:
    def alive[M: (LoadBudget, LoadBudgetMember, BudgetDayOverride)](model: type[M]) -> Any:
        return select(model).where(model.user_id == user_id, model.deleted_at.is_(None))

    budgets = list(await db.scalars(alive(LoadBudget).order_by(LoadBudget.position, LoadBudget.id)))
    ids = {b.id for b in budgets}
    by_action: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for m in await db.scalars(alive(LoadBudgetMember)):
        if m.budget_id in ids and m.action_type_id is not None:
            by_action[m.action_type_id].add(m.budget_id)
    overrides: dict[uuid.UUID, list[tuple[date, int]]] = defaultdict(list)
    for o in await db.scalars(
        alive(BudgetDayOverride)
        .where(BudgetDayOverride.date >= today)
        .order_by(BudgetDayOverride.date)
    ):
        overrides[o.budget_id].append((o.date, o.minutes))
    return BudgetIndex(
        tuple(Budget(b.id, b.minutes_per_day, tuple(overrides.get(b.id, []))) for b in budgets),
        {k: frozenset(v) for k, v in by_action.items()},
    )
