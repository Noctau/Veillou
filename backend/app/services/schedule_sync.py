"""Материализация правил расписания в `events`.

Серия правила синхронизируется по ключу (template_type, template_id,
occurrence_date) начиная с сегодняшнего дня (локального):

- вхождение есть и в правиле, и в БД → поля обновляются на месте (id, а значит
  и привязанные конспекты/напоминания, сохраняются);
- есть только в правиле → создаётся;
- есть только в БД → мягко удаляется;
- `detached` (правили руками) и прошедшие дни не трогаются.

Горизонт: до конца периода правила, без периода — скользящие 90 дней (ночная
джоба докатывает окно). Вызывается после любого изменения правила, периода,
сетки слотов, исключений, сферы и типа занятости.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import get_tz, local_date, now_utc
from app.domain.enums import EventKind, EventStatus, PatternKind, TemplateType
from app.domain.recurrence import (
    DateRange,
    DayCyclePattern,
    OncePattern,
    Pattern,
    PeriodSpec,
    RRulePattern,
    RuleSpec,
    Slot,
    SlotGridSpec,
    WeeklyPattern,
    expand_rule,
)
from app.models import Area, DayOff, Event, EventType, Period, ScheduleRule, SlotGrid, User
from app.services.jobs import request_reminders_sync

log = logging.getLogger(__name__)

# Правила без периода материализуются на столько дней вперёд (ночная джоба докатывает)
HORIZON_DAYS = 90


@dataclass(frozen=True)
class Desired:
    """Каким должно быть вхождение по правилу."""

    date: date
    start: datetime
    end: datetime
    fields: dict[str, Any]  # title, kind, location, color, …


@dataclass(frozen=True)
class SyncStats:
    created: int = 0
    updated: int = 0
    deleted: int = 0

    def __add__(self, other: "SyncStats") -> "SyncStats":
        return SyncStats(
            self.created + other.created,
            self.updated + other.updated,
            self.deleted + other.deleted,
        )


# Поля, которые правило переписывает у не-detached вхождения
_TEMPLATE_FIELDS = (
    "kind",
    "title",
    "is_fixed",
    "location",
    "color",
    "area_id",
    "event_type_id",
    "fields",
    "slot",
)


def grid_from_rows(rows: Sequence[SlotGrid]) -> SlotGridSpec:
    def slots(raw: list[dict[str, Any]]) -> list[Slot]:
        return [
            Slot(s["number"], time.fromisoformat(s["start"]), time.fromisoformat(s["end"]))
            for s in raw
        ]

    default = next((r for r in rows if r.weekday is None), None)
    return SlotGridSpec.from_slots(
        slots(default.slots) if default else [],
        {r.weekday: slots(r.slots) for r in rows if r.weekday is not None},
    )


def period_spec(p: Period) -> PeriodSpec:
    return PeriodSpec(
        p.start_date,
        p.end_date,
        p.cycle_weeks,
        p.first_cycle_week,
        tuple(
            DateRange(date.fromisoformat(x["from"]), date.fromisoformat(x["to"]))
            for x in p.pauses or []
        ),
    )


def pattern_from_json(raw: dict[str, Any]) -> Pattern:
    match raw.get("kind"):
        case PatternKind.weekly:
            mask = raw.get("cycle_weeks")
            return WeeklyPattern(
                frozenset(raw.get("weekdays") or ()),
                frozenset(mask) if mask else None,
            )
        case PatternKind.day_cycle:
            return DayCyclePattern(
                int(raw["on"]), int(raw["off"]), date.fromisoformat(raw["anchor"])
            )
        case PatternKind.rrule:
            return RRulePattern(str(raw["rrule"]))
        case PatternKind.once:
            return OncePattern(date.fromisoformat(raw["date"]))
    raise ValueError(f"Неизвестный паттерн: {raw!r}")


def rule_spec(rule: ScheduleRule) -> RuleSpec:
    return RuleSpec(
        key=rule.id,
        pattern=pattern_from_json(rule.pattern),
        start_time=rule.start_time,
        end_time=rule.end_time,
        slot_from=rule.slot_from,
        slot_to=rule.slot_to,
        valid_from=rule.valid_from,
        valid_to=rule.valid_to,
    )


def rule_title(rule: ScheduleRule, area: Area | None, event_type: EventType) -> str:
    return rule.title or (area.name if area else None) or event_type.name


@dataclass
class _Context:
    """Кэш на один проход синхронизации."""

    days_off: list[DayOff]
    periods: dict[uuid.UUID, Period | None] = field(default_factory=dict)
    grids: dict[uuid.UUID, SlotGridSpec | None] = field(default_factory=dict)
    areas: dict[uuid.UUID, Area | None] = field(default_factory=dict)
    types: dict[uuid.UUID, EventType | None] = field(default_factory=dict)


def _alive[M](obj: M | None) -> M | None:
    return obj if obj is not None and getattr(obj, "deleted_at", None) is None else None


class SeriesSync:
    def __init__(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        tz: ZoneInfo,
        *,
        now: datetime | None = None,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.tz = tz
        self.now = now or now_utc()
        self.today = local_date(self.now, tz)

    @property
    def horizon(self) -> date:
        return self.today + timedelta(days=HORIZON_DAYS)

    # ---------- общий механизм ----------

    async def _existing(self, template_id: uuid.UUID) -> list[Event]:
        rows = await self.db.scalars(
            select(Event).where(
                Event.user_id == self.user_id,
                Event.template_type == TemplateType.schedule_rule,
                Event.template_id == template_id,
                Event.deleted_at.is_(None),
            )
        )
        return list(rows)

    async def sync_series(
        self,
        template_id: uuid.UUID,
        desired: Sequence[Desired],
        *,
        until: date | None = None,
    ) -> SyncStats:
        """Приводит будущие вхождения правила к `desired`.

        `until` — граница окна материализации (правила без периода — на 90 дней):
        вхождения позже неё не удаляются, даже если их нет в `desired`.
        """
        existing = {e.occurrence_date: e for e in await self._existing(template_id)}
        wanted = {d.date: d for d in desired if d.date >= self.today}
        created = updated = deleted = 0

        for day, event in existing.items():
            if day is None or day < self.today or event.detached:
                continue
            target = wanted.get(day)
            if target is None:
                if until is None or day <= until:
                    event.deleted_at = self.now
                    deleted += 1
                continue
            changed = False
            for name, value in (("start", target.start), ("end", target.end), *_items(target)):
                if getattr(event, name) != value:
                    setattr(event, name, value)
                    changed = True
            updated += changed

        for day, target in wanted.items():
            if day in existing:
                continue
            self.db.add(
                Event(
                    user_id=self.user_id,
                    template_type=TemplateType.schedule_rule,
                    template_id=template_id,
                    occurrence_date=day,
                    start=target.start,
                    end=target.end,
                    status=EventStatus.planned,
                    **target.fields,
                )
            )
            created += 1
        await self.db.flush()
        return SyncStats(created, updated, deleted)

    async def remove_series(self, template_id: uuid.UUID) -> None:
        """Правило удалено: убираем все будущие вхождения, включая правленные руками."""
        await self.db.execute(
            update(Event)
            .where(
                Event.user_id == self.user_id,
                Event.template_type == TemplateType.schedule_rule,
                Event.template_id == template_id,
                Event.occurrence_date >= self.today,
                Event.deleted_at.is_(None),
            )
            .values(deleted_at=self.now)
        )
        await request_reminders_sync(self.db, self.user_id)

    async def restore_occurrence(self, event: Event) -> None:
        """«Как в расписании» для одного вхождения — в том числе прошедшего.

        Время и поля берутся из правила на дату вхождения, статус сбрасывается.
        Если по правилу в этот день вхождения нет (или правило удалено) — событие удаляется.
        """
        if event.template_id is None or event.occurrence_date is None:
            raise ValueError(f"Событие {event.id} не из правила")
        day = event.occurrence_date
        desired: list[Desired] | None = None
        rule = await self.db.get(ScheduleRule, event.template_id)
        if rule is not None and rule.user_id == self.user_id:
            ctx = await self._context()
            desired = await self._rule_desired(rule, DateRange(day, day), ctx)

        event.detached = False
        event.status = EventStatus.planned
        target = next((d for d in desired or [] if d.date == day), None)
        if target is None:
            event.deleted_at = self.now
        else:
            event.start, event.end = target.start, target.end
            for name, value in _items(target):
                setattr(event, name, value)
        await self.db.flush()

    # ---------- правила ----------

    async def _context(self) -> _Context:
        rows = await self.db.scalars(
            select(DayOff).where(DayOff.user_id == self.user_id, DayOff.deleted_at.is_(None))
        )
        return _Context(list(rows))

    async def _grid(self, grid_id: uuid.UUID) -> SlotGridSpec | None:
        """Сетка — группа строк с тем же (period_id, name), что у общей строки `grid_id`."""
        head = _alive(await self.db.get(SlotGrid, grid_id))
        if head is None or head.user_id != self.user_id:
            return None
        rows = await self.db.scalars(
            select(SlotGrid).where(
                SlotGrid.user_id == self.user_id,
                SlotGrid.deleted_at.is_(None),
                SlotGrid.name == head.name,
                SlotGrid.period_id == head.period_id
                if head.period_id
                else SlotGrid.period_id.is_(None),
            )
        )
        return grid_from_rows(list(rows))

    async def _rule_desired(
        self, rule: ScheduleRule, window: DateRange, ctx: _Context
    ) -> list[Desired] | None:
        """Вхождения правила в `window`; None — правило (или его тип, период, сфера) удалено."""
        if rule.deleted_at is not None:
            return None
        if rule.event_type_id not in ctx.types:
            ctx.types[rule.event_type_id] = _alive(await self.db.get(EventType, rule.event_type_id))
        event_type = ctx.types[rule.event_type_id]
        if event_type is None:
            return None
        area: Area | None = None
        if rule.area_id is not None:
            if rule.area_id not in ctx.areas:
                ctx.areas[rule.area_id] = _alive(await self.db.get(Area, rule.area_id))
            area = ctx.areas[rule.area_id]
            if area is None:
                return None
        period: Period | None = None
        if rule.period_id is not None:
            if rule.period_id not in ctx.periods:
                ctx.periods[rule.period_id] = _alive(await self.db.get(Period, rule.period_id))
            period = ctx.periods[rule.period_id]
            if period is None:
                return None
        grid: SlotGridSpec | None = None
        if rule.slot_grid_id is not None:
            if rule.slot_grid_id not in ctx.grids:
                ctx.grids[rule.slot_grid_id] = await self._grid(rule.slot_grid_id)
            grid = ctx.grids[rule.slot_grid_id]

        # Исключения — только для правил периода: общие и этого периода
        days_off = (
            [
                DateRange(d.date_from, d.date_to)
                for d in ctx.days_off
                if d.period_id is None or d.period_id == rule.period_id
            ]
            if period is not None
            else []
        )
        occurrences = expand_rule(
            rule_spec(rule),
            tz=self.tz,
            window=window,
            period=period_spec(period) if period else None,
            grid=grid,
            days_off=days_off,
        )
        fields = {
            "kind": EventKind.busy,
            "title": rule_title(rule, area, event_type),
            "is_fixed": True,
            "location": rule.location,
            "color": rule.color or (area.color if area else None),
            "area_id": rule.area_id,
            "event_type_id": rule.event_type_id,
            "fields": dict(rule.fields or {}),
        }
        return [Desired(o.date, o.start, o.end, {**fields, "slot": o.slot}) for o in occurrences]

    async def sync_rules(self, rules: Sequence[ScheduleRule]) -> SyncStats:
        """Синхронизирует серии правил (удалённые правила — убирает)."""
        total = SyncStats()
        if not rules:
            return total
        ctx = await self._context()
        for rule in rules:
            # Горизонт: конец периода; без периода — 90 дней (дальше не трогаем)
            until = None if rule.period_id else self.horizon
            desired = await self._rule_desired(
                rule, DateRange(self.today, until or self.today + timedelta(days=800)), ctx
            )
            if desired is None:
                await self.remove_series(rule.id)
                continue
            total += await self.sync_series(rule.id, desired, until=until)
        return total

    async def _live_rules(self, *where: Any) -> list[ScheduleRule]:
        rows = await self.db.scalars(
            select(ScheduleRule).where(
                ScheduleRule.user_id == self.user_id, ScheduleRule.deleted_at.is_(None), *where
            )
        )
        return list(rows)

    async def sync_period(self, period_id: uuid.UUID) -> SyncStats:
        return await self.sync_rules(await self._live_rules(ScheduleRule.period_id == period_id))

    async def sync_grid(self, grid_ids: Sequence[uuid.UUID]) -> SyncStats:
        return await self.sync_rules(
            await self._live_rules(ScheduleRule.slot_grid_id.in_(list(grid_ids)))
        )

    async def sync_event_type(self, event_type_id: uuid.UUID) -> SyncStats:
        return await self.sync_rules(
            await self._live_rules(ScheduleRule.event_type_id == event_type_id)
        )

    async def sync_area(self, area: Area) -> SyncStats:
        rules = await self._live_rules(ScheduleRule.area_id == area.id)
        stats = await self.sync_rules(rules)
        # Название и цвет сферы обновляются и у правленных руками вхождений
        for values, ids in (
            ({"title": area.name}, [r.id for r in rules if r.title is None]),
            ({"color": area.color}, [r.id for r in rules if r.color is None]),
        ):
            if not ids:
                continue
            await self.db.execute(
                update(Event)
                .where(
                    Event.user_id == self.user_id,
                    Event.template_type == TemplateType.schedule_rule,
                    Event.template_id.in_(ids),
                    Event.detached.is_(True),
                    Event.occurrence_date >= self.today,
                    Event.deleted_at.is_(None),
                )
                .values(**values)
            )
        return stats

    async def sync_with_days_off(self, period_id: uuid.UUID | None) -> SyncStats:
        """Исключение без периода влияет на правила всех периодов."""
        where = (
            ScheduleRule.period_id == period_id
            if period_id
            else ScheduleRule.period_id.is_not(None)
        )
        return await self.sync_rules(await self._live_rules(where))

    async def roll(self) -> int:
        """Докатывает окно правил без периода. Возвращает число созданных вхождений."""
        rules = await self._live_rules(ScheduleRule.period_id.is_(None))
        return (await self.sync_rules(rules)).created


def _items(target: Desired) -> list[tuple[str, Any]]:
    return [(name, target.fields[name]) for name in _TEMPLATE_FIELDS if name in target.fields]


async def roll_all_users(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Ночная джоба: докатывает окно правил без периода у всех пользователей."""
    users = list(await db.execute(select(User.id, User.timezone).where(User.deleted_at.is_(None))))
    created = 0
    for user_id, timezone in users:
        try:
            created += await SeriesSync(db, user_id, get_tz(timezone), now=now).roll()
            await db.commit()
        except Exception:
            log.exception("Докатка правил расписания пользователя %s упала", user_id)
            await db.rollback()
    return created
