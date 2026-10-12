"""CRUD расписания: периоды, сетки слотов, исключения, правила расписания.

Каждое изменение пересинхронизирует затронутые серии правил (schedule_sync.py).
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, InvalidDataError
from app.core.time import get_tz
from app.domain.fields import FieldError, parse_defs
from app.domain.fields import validate_values as clean_values
from app.models import Area, DayOff, EventType, Period, ScheduleRule, SlotGrid, User
from app.schemas.schedule import (
    DayOffCreate,
    DayOffUpdate,
    PeriodCreate,
    PeriodUpdate,
    RRulePatternIn,
    ScheduleRuleCreate,
    ScheduleRuleUpdate,
    SlotGridPut,
)
from app.services.base import UserScopedRepository, validate_patch
from app.services.recurring_tasks import ensure_has_occurrences
from app.services.schedule_sync import SeriesSync


class PeriodRepo(UserScopedRepository[Period]):
    model = Period
    not_found_message = "Период не найден"


class SlotGridRepo(UserScopedRepository[SlotGrid]):
    model = SlotGrid
    not_found_message = "Сетка слотов не найдена"


class DayOffRepo(UserScopedRepository[DayOff]):
    model = DayOff
    not_found_message = "Исключение не найдено"


class AreaRepo(UserScopedRepository[Area]):
    model = Area
    not_found_message = "Сфера не найдена"


class EventTypeRepo(UserScopedRepository[EventType]):
    model = EventType
    not_found_message = "Тип занятости не найден"


class ScheduleRuleRepo(UserScopedRepository[ScheduleRule]):
    model = ScheduleRule
    not_found_message = "Правило расписания не найдено"


def _pauses(data: PeriodCreate) -> list[dict[str, Any]]:
    return [p.model_dump(mode="json", by_alias=True) for p in data.pauses]


class ScheduleService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user_id = user.id
        self.sync = SeriesSync(db, user_id, get_tz(user.timezone))
        self.periods = PeriodRepo(db, user_id)
        self.grids = SlotGridRepo(db, user_id)
        self.days_off = DayOffRepo(db, user_id)
        self.areas = AreaRepo(db, user_id)
        self.types = EventTypeRepo(db, user_id)
        self.rules = ScheduleRuleRepo(db, user_id)

    # ---------- периоды ----------

    async def list_periods(self) -> list[Period]:
        return await self.periods.find_all(order_by=[Period.start_date.desc()])

    async def create_period(self, data: PeriodCreate) -> Period:
        period = Period(**data.model_dump(exclude={"pauses"}), pauses=_pauses(data))
        self.periods.add(period)
        await self.db.commit()
        return period

    async def update_period(self, id: uuid.UUID, patch: PeriodUpdate) -> Period:
        period = await self.periods.get_or_404(id)
        data = validate_patch(period, patch, PeriodCreate)
        for name, value in data.model_dump(exclude={"pauses"}).items():
            setattr(period, name, value)
        period.pauses = _pauses(data)
        await self.db.flush()
        await self.sync.sync_period(id)
        await self.db.commit()
        return period

    async def delete_period(self, id: uuid.UUID) -> None:
        """Удаляет период с его правилами, сетками и исключениями. Сферы — «без периода»."""
        period = await self.periods.get_or_404(id)
        for rule in await self.rules.find_all(ScheduleRule.period_id == id):
            self.rules.soft_delete(rule)
            await self.sync.remove_series(rule.id)
        for grid in await self.grids.find_all(SlotGrid.period_id == id):
            self.grids.soft_delete(grid)
        for day_off in await self.days_off.find_all(DayOff.period_id == id):
            self.days_off.soft_delete(day_off)
        for area in await self.areas.find_all(Area.period_id == id):
            area.period_id = None
        self.periods.soft_delete(period)
        await self.db.commit()

    # ---------- сетки слотов ----------

    async def list_grids(self, period_id: uuid.UUID | None = None) -> list[SlotGrid]:
        where = [SlotGrid.period_id == period_id] if period_id else []
        rows = await self.grids.find_all(*where, order_by=[SlotGrid.name])
        return sorted(rows, key=lambda g: (str(g.period_id or ""), g.name, g.weekday or 0))

    async def _group(self, head: SlotGrid) -> list[SlotGrid]:
        period = (
            SlotGrid.period_id == head.period_id if head.period_id else SlotGrid.period_id.is_(None)
        )
        return await self.grids.find_all(period, SlotGrid.name == head.name)

    async def _head(self, period_id: uuid.UUID | None, name: str) -> SlotGrid | None:
        period = SlotGrid.period_id == period_id if period_id else SlotGrid.period_id.is_(None)
        found = await self.grids.find_all(period, SlotGrid.name == name, SlotGrid.weekday.is_(None))
        return found[0] if found else None

    async def put_grid(self, data: SlotGridPut) -> list[SlotGrid]:
        """Сетка целиком. Строки обновляются на месте: id общей строки (на неё ссылаются
        правила) не меняется."""
        if data.period_id:
            await self.periods.get_or_404(data.period_id)
        head = await self.grids.get_or_404(data.id) if data.id else None
        if head is not None and head.weekday is not None:
            raise InvalidDataError("id — это общая строка сетки (без дня недели)")
        same = await self._head(data.period_id, data.name)
        if same is not None and (head is None or same.id != head.id):
            if head is not None:
                raise ConflictError("Сетка с таким названием уже есть", code="slot_grid_exists")
            head = same
        rows = await self._group(head) if head else []
        by_day = {r.weekday: r for r in rows}
        wanted = {d.weekday for d in data.schedules}
        for row in rows:
            if row.weekday not in wanted:
                self.grids.soft_delete(row)
            row.period_id, row.name = data.period_id, data.name
        await self.db.flush()  # частичный уникальный индекс: сначала гасим и переименовываем
        for day in data.schedules:
            slots = [s.model_dump(mode="json") for s in day.slots]
            if (existing := by_day.get(day.weekday)) is not None:
                existing.slots = slots
                continue
            new = SlotGrid(
                period_id=data.period_id, name=data.name, weekday=day.weekday, slots=slots
            )
            self.grids.add(new)
            if day.weekday is None:
                head = new
        await self.db.flush()
        if head is not None:
            await self.sync.sync_grid([head.id])
        await self.db.commit()
        return sorted(await self._group(head), key=lambda g: g.weekday or 0) if head else []

    async def delete_grid(self, id: uuid.UUID) -> None:
        head = await self.grids.get_or_404(id)
        if await self.rules.find_all(ScheduleRule.slot_grid_id == head.id, limit=1):
            raise ConflictError(
                "По этой сетке есть правила — сначала переведите их на время или другую сетку",
                code="slot_grid_in_use",
            )
        for row in await self._group(head):
            self.grids.soft_delete(row)
        await self.db.commit()

    # ---------- исключения ----------

    async def list_days_off(self) -> list[DayOff]:
        return await self.days_off.find_all(order_by=[DayOff.date_from])

    async def create_day_off(self, data: DayOffCreate) -> DayOff:
        if data.period_id:
            await self.periods.get_or_404(data.period_id)
        day_off = DayOff(**data.model_dump())
        self.days_off.add(day_off)
        await self._days_off_changed(data.period_id)
        return day_off

    async def update_day_off(self, id: uuid.UUID, patch: DayOffUpdate) -> DayOff:
        day_off = await self.days_off.get_or_404(id)
        before = day_off.period_id
        data = validate_patch(day_off, patch, DayOffCreate)
        if data.period_id and data.period_id != before:
            await self.periods.get_or_404(data.period_id)
        for name, value in data.model_dump().items():
            setattr(day_off, name, value)
        await self._days_off_changed(before, data.period_id)
        return day_off

    async def delete_day_off(self, id: uuid.UUID) -> None:
        day_off = await self.days_off.get_or_404(id)
        self.days_off.soft_delete(day_off)
        await self._days_off_changed(day_off.period_id)

    async def _days_off_changed(self, *period_ids: uuid.UUID | None) -> None:
        await self.db.flush()
        # Исключение без периода касается всех периодов — достаточно одного прохода
        scopes = {None} if None in period_ids else set(period_ids)
        for period_id in scopes:
            await self.sync.sync_with_days_off(period_id)
        await self.db.commit()

    # ---------- правила расписания ----------

    async def list_rules(
        self,
        period_id: uuid.UUID | None = None,
        area_id: uuid.UUID | None = None,
        event_type_id: uuid.UUID | None = None,
    ) -> list[ScheduleRule]:
        where: list[Any] = []
        if period_id:
            where.append(ScheduleRule.period_id == period_id)
        if area_id:
            where.append(ScheduleRule.area_id == area_id)
        if event_type_id:
            where.append(ScheduleRule.event_type_id == event_type_id)
        return await self.rules.find_all(
            *where, order_by=[ScheduleRule.slot_from, ScheduleRule.start_time, ScheduleRule.id]
        )

    async def check_rule(
        self, data: ScheduleRuleCreate, rule: ScheduleRule | None = None
    ) -> dict[str, Any]:
        """Ссылки свои и живые, поля — по типу занятости. Возвращает значения для записи."""
        event_type = await self.types.get_or_404(data.event_type_id)
        if data.area_id:
            await self.areas.get_or_404(data.area_id)
        period = await self.periods.get_or_404(data.period_id) if data.period_id else None
        mask = getattr(data.pattern, "cycle_weeks", None)
        if mask and period is not None and max(mask) > period.cycle_weeks:
            raise InvalidDataError(f"В цикле периода {period.cycle_weeks} нед.")
        if data.slot_grid_id:
            grid = await self.grids.get_or_404(data.slot_grid_id)
            if grid.weekday is not None:
                raise InvalidDataError("Сетка указывается общей строкой (без дня недели)")
        pattern = data.pattern.model_dump(mode="json")
        if isinstance(data.pattern, RRulePatternIn) and (rule is None or rule.pattern != pattern):
            await ensure_has_occurrences(data.pattern.rrule)
        try:
            fields = clean_values(
                parse_defs(event_type.fields),
                data.fields,
                stored=rule.fields if rule is not None else None,
            )
        except FieldError as exc:
            raise InvalidDataError(str(exc)) from exc
        values = data.model_dump(exclude={"pattern", "fields"})
        return {**values, "pattern": pattern, "fields": fields}

    async def create_rule(self, data: ScheduleRuleCreate) -> ScheduleRule:
        rule = ScheduleRule(**await self.check_rule(data))
        self.rules.add(rule)
        await self.db.flush()
        await self.sync.sync_rules([rule])
        await self.db.commit()
        return rule

    async def update_rule(self, id: uuid.UUID, patch: ScheduleRuleUpdate) -> ScheduleRule:
        rule = await self.rules.get_or_404(id)
        data = validate_patch(rule, patch, ScheduleRuleCreate)
        for name, value in (await self.check_rule(data, rule)).items():
            setattr(rule, name, value)
        await self.db.flush()
        await self.sync.sync_rules([rule])
        await self.db.commit()
        return rule

    async def delete_rule(self, id: uuid.UUID) -> None:
        rule = await self.rules.get_or_404(id)
        self.rules.soft_delete(rule)
        await self.sync.remove_series(rule.id)
        await self.db.commit()
