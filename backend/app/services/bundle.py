"""Сборки (M21.3): экспорт конфигурации пользователя в `ConfigBundle` и импорт.

Экспорт даёт кирпичам читаемые `ref` по названиям («Смена», «Будни»), безымянным —
по номеру; порядок детерминированный, так что экспорт → импорт в пустого
пользователя → экспорт даёт тот же JSON.

Импорт: проверка ссылок (`domain/bundle.check_refs`) → сравнение с текущей
конфигурацией (`domain/bundle.diff`) → в порядке зависимостей добавляет новое и
обновляет изменённое (ничего не удаляет). Каждый кирпич проверяется той же
схемой `*Create`, что и в API, строки пишутся в одной транзакции; правила
расписания материализуются один раз в конце. `dry_run` — только отчёт.

Справочники здесь не засеваются: импорт в нового пользователя не смешивает сборку
с сидом по умолчанию.
"""

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import time
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, now_utc
from app.domain import bundle as dom
from app.domain.enums import FieldType
from app.domain.fields import FieldError, dump_defs, merge_defs, parse_defs
from app.domain.fields import validate_values as clean_values
from app.models import (
    ActionType,
    Area,
    AreaType,
    Category,
    DayOff,
    DayProfile,
    DayProfileRule,
    EventRule,
    EventType,
    LoadBudget,
    LoadBudgetMember,
    Period,
    ScheduleRule,
    SlotGrid,
    TaskType,
    User,
)
from app.schemas.area import AreaTypeCreate
from app.schemas.budget import LoadBudgetCreate
from app.schemas.bundle import BundleChange, BundleImportResult, ConfigBundle, bundle_json
from app.schemas.catalog import ActionTypeCreate, CategoryCreate, TaskTypeCreate
from app.schemas.day_profile import DayProfileCreate, DayProfileRuleCreate
from app.schemas.event_rule import EventRuleCreate
from app.schemas.schedule import (
    DayOffCreate,
    EventTypeCreate,
    PeriodCreate,
    ScheduleRuleCreate,
    SlotGridPut,
)
from app.services.day_profiles import apply_profile
from app.services.event_tasks import EventRuleService, sync_user
from app.services.schedule import ScheduleService
from app.services.schedule_sync import SeriesSync
from app.services.settings import effective_settings

Ids = dict[tuple[str, str], uuid.UUID]  # (раздел, ref) → id строки
# Разделы, чья правка меняет вхождения правил расписания
SCHEDULE_SECTIONS = frozenset(
    {"periods", "days_off", "slot_grids", "areas", "event_types", "schedule_rules"}
)


@dataclass
class Exported:
    bundle: dict[str, Any]
    ids: Ids = field(default_factory=dict)


def _hhmm(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value is not None else None


def _live_defs(raw: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        {
            "id": d.id,
            "label": d.label,
            "type": str(d.type),
            "options": list(d.options),
            "multiple": d.multiple,
            "show_in_reminder": d.show_in_reminder,
            "required": d.required,
        }
        for d in parse_defs(raw)
        if not d.deleted
    ]


def _map_area_values(
    defs_raw: Sequence[Mapping[str, Any]] | None,
    values: Mapping[str, Any],
    mapping: Mapping[str, str],
) -> dict[str, Any]:
    """Значения полей «сфера» (`area_ref`) через `mapping` (id ↔ ref); незнакомые — прочь."""
    result = dict(values)
    for d in parse_defs(defs_raw):
        if d.type != FieldType.area_ref or d.id not in result:
            continue
        value = result[d.id]
        if isinstance(value, list):
            result[d.id] = [mapping[v] for v in value if v in mapping]
        elif value in mapping:
            result[d.id] = mapping[value]
        else:
            result.pop(d.id)
    return result


class BundleService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id

    async def _rows[M](self, model: type[M], *order: Any) -> list[M]:
        m: Any = model
        return list(
            await self.db.scalars(
                select(model)
                .where(m.user_id == self.user_id, m.deleted_at.is_(None))
                .order_by(*order)
            )
        )

    # ---------- экспорт ----------

    async def export(self) -> Exported:
        out = Exported({"version": 1})
        ids = out.ids
        b = out.bundle

        def refs(section: str, rows: Sequence[Any], names: Sequence[str]) -> dict[Any, str]:
            """id строки → ref; заодно заполняет обратную карту."""
            result = {}
            for row, ref in zip(rows, dom.unique_refs(names), strict=True):
                result[row.id] = ref
                ids[(section, ref)] = row.id
            return result

        categories = await self._rows(Category, Category.position, Category.created_at)
        cat = refs("categories", categories, [c.name for c in categories])
        b["categories"] = [
            {"ref": cat[c.id], "name": c.name, "color": c.color, "icon": c.icon} for c in categories
        ]

        actions = await self._rows(ActionType, ActionType.position, ActionType.created_at)
        act = refs("action_types", actions, [a.name for a in actions])
        b["action_types"] = [
            {
                "ref": act[a.id],
                "name": a.name,
                "windows": a.windows,
                "category": cat.get(a.default_category_id),
                "prefer_morning": a.prefer_morning,
                "synonyms": list(a.synonyms or []),
            }
            for a in actions
        ]

        task_types = await self._rows(TaskType, TaskType.position, TaskType.created_at)
        tt = refs("task_types", task_types, [t.name for t in task_types])
        b["task_types"] = [
            {
                "ref": tt[t.id],
                "name": t.name,
                "icon": t.icon,
                "synonyms": list(t.synonyms or []),
                "action_type": act.get(t.default_action_type_id),
                "category": cat.get(t.default_category_id),
                "default_estimate_min": t.default_estimate_min,
                "deadline_rule": t.deadline_rule,
            }
            for t in task_types
        ]

        area_types = await self._rows(AreaType, AreaType.position, AreaType.created_at)
        at = refs("area_types", area_types, [t.name for t in area_types])
        at_defs = {t.id: t.fields for t in area_types}
        b["area_types"] = [
            {
                "ref": at[t.id],
                "name": t.name,
                "name_plural": t.name_plural,
                "icon": t.icon,
                "color": t.color,
                "fields": _live_defs(t.fields),
                "sections": list(t.sections or []),
            }
            for t in area_types
        ]

        periods = await self._rows(Period, Period.start_date, Period.name, Period.id)
        per = refs("periods", periods, [p.name for p in periods])
        b["periods"] = [
            {
                "ref": per[p.id],
                "name": p.name,
                "start_date": p.start_date.isoformat(),
                "end_date": p.end_date.isoformat(),
                "cycle_weeks": p.cycle_weeks,
                "first_cycle_week": p.first_cycle_week,
                "pauses": p.pauses or [],
            }
            for p in periods
        ]

        days_off = await self._rows(DayOff, DayOff.date_from, DayOff.date_to, DayOff.title)
        days_off.sort(key=lambda d: (per.get(d.period_id) or "", d.date_from, d.date_to, d.title))
        off = refs("days_off", days_off, [d.title or d.date_from.isoformat() for d in days_off])
        b["days_off"] = [
            {
                "ref": off[d.id],
                "period": per.get(d.period_id),
                "date_from": d.date_from.isoformat(),
                "date_to": d.date_to.isoformat(),
                "title": d.title,
            }
            for d in days_off
        ]

        grid_rows = await self._rows(SlotGrid, SlotGrid.name)
        heads = [g for g in grid_rows if g.weekday is None]
        heads.sort(key=lambda g: (per.get(g.period_id) or "", g.name))
        grid = refs("slot_grids", heads, [g.name or "Сетка" for g in heads])
        b["slot_grids"] = []
        for h in heads:
            group = [g for g in grid_rows if g.period_id == h.period_id and g.name == h.name]
            group.sort(key=lambda g: g.weekday or 0)
            b["slot_grids"].append(
                {
                    "ref": grid[h.id],
                    "period": per.get(h.period_id),
                    "name": h.name,
                    "schedules": [{"weekday": g.weekday, "slots": g.slots} for g in group],
                }
            )

        type_order = {t.id: i for i, t in enumerate(area_types)}
        areas = [a for a in await self._rows(Area, Area.name, Area.id) if a.archived_at is None]
        areas.sort(
            key=lambda a: (type_order.get(a.area_type_id, 0), a.name, per.get(a.period_id) or "")
        )
        ar = refs("areas", areas, [a.name for a in areas])
        area_ref_by_id = {str(id): ref for id, ref in ar.items()}
        b["areas"] = [
            {
                "ref": ar[a.id],
                "area_type": at[a.area_type_id],
                "period": per.get(a.period_id),
                "name": a.name,
                "short_name": a.short_name,
                "color": a.color,
                "synonyms": list(a.synonyms or []),
                "fields": _map_area_values(
                    at_defs.get(a.area_type_id), a.fields or {}, area_ref_by_id
                ),
                "notes": a.notes,
            }
            for a in areas
        ]

        event_types = await self._rows(EventType, EventType.position, EventType.created_at)
        et = refs("event_types", event_types, [t.name for t in event_types])
        et_defs = {t.id: t.fields for t in event_types}
        b["event_types"] = [
            {
                "ref": et[t.id],
                "name": t.name,
                "name_plural": t.name_plural,
                "icon": t.icon,
                "color": t.color,
                "buffer_before_min": t.buffer_before_min,
                "buffer_after_min": t.buffer_after_min,
                "merge_buffers": t.merge_buffers,
                "remind_before_min": t.remind_before_min,
                "remind_channels": list(t.remind_channels or []),
                "show_now_next": t.show_now_next,
                "is_rest": t.is_rest,
                "supports_prep": t.supports_prep,
                "location_label": t.location_label,
                "default_area_type": at.get(t.default_area_type_id),
                "fields": _live_defs(t.fields),
                "synonyms": list(t.synonyms or []),
            }
            for t in event_types
        ]

        budgets = await self._rows(LoadBudget, LoadBudget.position, LoadBudget.created_at)
        bud = refs("budgets", budgets, [x.name for x in budgets])
        members = await self._rows(LoadBudgetMember, LoadBudgetMember.created_at)
        b["budgets"] = [
            {
                "ref": bud[x.id],
                "name": x.name,
                "minutes_per_day": x.minutes_per_day,
                "action_types": sorted(
                    act[m.action_type_id]
                    for m in members
                    if m.budget_id == x.id and m.action_type_id in act
                ),
                "event_types": sorted(
                    et[m.event_type_id]
                    for m in members
                    if m.budget_id == x.id and m.event_type_id in et
                ),
            }
            for x in budgets
        ]

        profiles = await self._rows(DayProfile, DayProfile.position, DayProfile.created_at)
        prof = refs("day_profiles", profiles, [p.name for p in profiles])
        b["day_profiles"] = [
            {
                "ref": prof[p.id],
                "name": p.name,
                "wake": _hhmm(p.wake),
                "sleep": _hhmm(p.sleep),
                "lunch": (
                    {"start": _hhmm(p.lunch_start), "end": _hhmm(p.lunch_end)}
                    if p.lunch_start and p.lunch_end
                    else None
                ),
                "work_windows": p.work_windows or [],
                "rest_evening_ok": p.rest_evening_ok,
                "rest_halfday_ok": p.rest_halfday_ok,
                "quiet_follows_sleep": p.quiet_follows_sleep,
            }
            for p in profiles
        ]

        day_rules = await self._rows(
            DayProfileRule, DayProfileRule.position, DayProfileRule.created_at
        )
        day_rules = [r for r in day_rules if r.profile_id in prof]
        dr = refs(
            "day_profile_rules", day_rules, [f"{prof[r.profile_id]}: {r.kind}" for r in day_rules]
        )
        b["day_profile_rules"] = [
            {
                "ref": dr[r.id],
                "profile": prof[r.profile_id],
                "kind": r.kind,
                "date_from": r.date_from.isoformat() if r.date_from else None,
                "date_to": r.date_to.isoformat() if r.date_to else None,
                "event_type": et.get(r.event_type_id),
                "weekdays": list(r.weekdays or []),
            }
            for r in day_rules
        ]

        rules = await self._rows(ScheduleRule, ScheduleRule.id)
        rules = [
            r for r in rules if r.event_type_id in et and (r.area_id is None or r.area_id in ar)
        ]
        items = []
        for r in rules:
            item = {
                "event_type": et[r.event_type_id],
                "area": ar.get(r.area_id),
                "period": per.get(r.period_id),
                "slot_grid": grid.get(r.slot_grid_id),
                "pattern": r.pattern,
                "start_time": _hhmm(r.start_time),
                "end_time": _hhmm(r.end_time),
                "slot_from": r.slot_from,
                "slot_to": r.slot_to,
                "valid_from": r.valid_from.isoformat() if r.valid_from else None,
                "valid_to": r.valid_to.isoformat() if r.valid_to else None,
                "title": r.title,
                "location": r.location,
                "color": r.color,
                "fields": _map_area_values(
                    et_defs.get(r.event_type_id), r.fields or {}, area_ref_by_id
                ),
                "note": r.note,
            }
            items.append((json.dumps(item, ensure_ascii=False, sort_keys=True), r, item))
        items.sort(key=lambda x: x[0])
        names = [str(r.title or item["area"] or item["event_type"]) for _, r, item in items]
        sr = refs("schedule_rules", [r for _, r, _ in items], names)
        b["schedule_rules"] = [{"ref": sr[r.id], **item} for _, r, item in items]

        event_rules = await self._rows(EventRule, EventRule.position, EventRule.created_at)
        event_rules = [
            r for r in event_rules if (r.event_type_id in et) or (r.schedule_rule_id in sr)
        ]
        er = refs("event_rules", event_rules, [r.title_template for r in event_rules])
        b["event_rules"] = [
            {
                "ref": er[r.id],
                "event_type": et.get(r.event_type_id),
                "schedule_rule": sr.get(r.schedule_rule_id),
                "when": r.when,
                "title_template": r.title_template,
                "estimate_min": r.estimate_min,
                "action_type": act.get(r.action_type_id),
                "task_type": tt.get(r.task_type_id),
                "offset_min": r.offset_min,
                "within_days": r.within_days,
                "until_next": r.until_next,
                "confirm": r.confirm,
            }
            for r in event_rules
        ]

        default = effective_settings(self.user).default_action_type_id
        b["settings"] = {"default_action_type": act.get(default)}
        # Через схему: те же умолчания и форма, что у входящих сборок
        out.bundle = bundle_json(ConfigBundle.model_validate(b))
        return out

    # ---------- импорт ----------

    async def import_bundle(self, bundle: ConfigBundle, *, dry_run: bool) -> BundleImportResult:
        incoming = bundle_json(bundle)
        try:
            dom.check_refs(incoming)
        except dom.BundleError as exc:
            raise InvalidDataError(f"Сборка с ошибками: {exc}") from exc
        current = await self.export()
        diff = dom.diff(current.bundle, incoming)
        settings_changed = dom.settings_changes(current.bundle, incoming)
        if not dry_run:
            await _Importer(self, current, incoming, diff).run(settings_changed)
        return BundleImportResult(
            dry_run=dry_run,
            added=[_change(i) for i in diff.of("added")],
            changed=[_change(i) for i in diff.of("changed")]
            + [BundleChange(section="settings", ref=n, name=n) for n in settings_changed],
            skipped=[_change(i) for i in diff.of("skipped")],
        )


def _change(i: dom.ItemDiff) -> BundleChange:
    return BundleChange(section=i.section, ref=i.ref, name=i.name, fields=list(i.fields))


def _check[S: BaseModel](schema: type[S], where: str, **values: Any) -> S:
    try:
        return schema.model_validate(values)
    except ValidationError as exc:
        details = "; ".join(e["msg"] for e in exc.errors())
        raise InvalidDataError(f"{where}: {details}") from exc


class _Importer:
    """Применение сборки: секция за секцией, ссылки — через `self.ids`."""

    def __init__(
        self, svc: BundleService, current: Exported, incoming: dict[str, Any], diff: dom.BundleDiff
    ) -> None:
        self.db = svc.db
        self.user = svc.user
        self.user_id = svc.user_id
        self.svc = svc
        self.current = current
        self.incoming = incoming
        self.by_item = {(i.section, i.ref): i for i in diff.items}
        self.ids: Ids = {}
        # Что сделать после записи строки (ей уже выдан id): участники лимита
        self.after: list[Callable[[], None]] = []
        self.touched_schedule = False

    def ref(self, section: str, ref: str | None) -> uuid.UUID | None:
        return self.ids[(section, ref)] if ref is not None else None

    async def _existing(self, model: Any, id: uuid.UUID) -> Any:
        return await self.db.get(model, id)

    async def _next_position(self, model: Any) -> int:
        last = await self.db.scalar(
            select(func.max(model.position)).where(
                model.user_id == self.user_id, model.deleted_at.is_(None)
            )
        )
        return (last if last is not None else -1) + 1

    async def run(self, settings_changed: list[str]) -> None:
        for section in dom.SECTIONS:
            handler: Callable[[dict[str, Any], Any | None], Any] = getattr(self, f"_{section}")
            position = None
            for item in self.incoming.get(section) or []:
                d = self.by_item[(section, item["ref"])]
                existing = None
                if d.existing is not None:
                    existing_id = self.current.ids[(section, d.existing)]
                    self.ids[(section, item["ref"])] = existing_id
                    if d.status == "skipped":
                        continue
                    existing = existing_id
                row = await handler(item, existing)
                if existing is None:
                    if section in dom.ORDERED:
                        model = type(row)
                        if position is None:
                            position = await self._next_position(model)
                        row.position = position
                        position += 1
                    row.user_id = self.user_id
                    self.db.add(row)
                await self.db.flush()
                for action in self.after:
                    action()
                self.after.clear()
                self.ids[(section, item["ref"])] = row.id
                if section in (
                    "periods",
                    "days_off",
                    "slot_grids",
                    "areas",
                    "event_types",
                    "schedule_rules",
                ):
                    self.touched_schedule = True
        if "default_action_type" in settings_changed:
            ref = self.incoming["settings"]["default_action_type"]
            overrides = dict(self.user.settings or {})
            overrides["default_action_type_id"] = str(self.ref("action_types", ref))
            self.user.settings = overrides
        await self.db.flush()
        if self.touched_schedule:
            rules = await self.svc._rows(ScheduleRule, ScheduleRule.id)
            await SeriesSync(self.db, self.user_id, get_tz(self.user.timezone)).sync_rules(rules)
        if self.incoming.get("event_rules"):
            await sync_user(self.db, self.user, now_utc())
        await self.db.commit()

    async def _load(self, model: Any, existing: uuid.UUID | None) -> Any:
        return await self.db.get(model, existing) if existing else model()

    # ---------- разделы ----------

    async def _categories(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        data = _check(
            CategoryCreate, item["name"], name=item["name"], color=item["color"], icon=item["icon"]
        )
        row = await self._load(Category, existing)
        row.name, row.color, row.icon = data.name, data.color, data.icon
        return row

    async def _action_types(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        data = _check(
            ActionTypeCreate,
            item["name"],
            name=item["name"],
            windows=item["windows"],
            default_category_id=self.ref("categories", item["category"]),
            prefer_morning=item["prefer_morning"],
            synonyms=item["synonyms"],
        )
        row = await self._load(ActionType, existing)
        row.name = data.name
        row.windows = data.model_dump(mode="json")["windows"]
        row.default_category_id = data.default_category_id
        row.prefer_morning = data.prefer_morning
        row.synonyms = data.synonyms
        return row

    async def _task_types(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        data = _check(
            TaskTypeCreate,
            item["name"],
            name=item["name"],
            icon=item["icon"],
            synonyms=item["synonyms"],
            default_action_type_id=self.ref("action_types", item["action_type"]),
            default_category_id=self.ref("categories", item["category"]),
            default_estimate_min=item["default_estimate_min"],
            deadline_rule=item["deadline_rule"],
        )
        row = await self._load(TaskType, existing)
        dumped = data.model_dump(mode="json")
        for name in ("name", "icon", "synonyms", "default_estimate_min", "deadline_rule"):
            setattr(row, name, dumped[name])
        row.default_action_type_id = data.default_action_type_id
        row.default_category_id = data.default_category_id
        return row

    def _defs(self, row: Any, fields: list[Any], where: str) -> list[dict[str, Any]]:
        try:
            defs = merge_defs(parse_defs(row.fields), [f.to_def() for f in fields], keep_ids=True)
        except FieldError as exc:
            raise InvalidDataError(f"{where}: {exc}") from exc
        return dump_defs(defs)

    async def _area_types(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        data = _check(AreaTypeCreate, item["name"], **{k: v for k, v in item.items() if k != "ref"})
        row = await self._load(AreaType, existing)
        row.fields = self._defs(row, data.fields, data.name)
        row.name, row.name_plural = data.name, data.name_plural
        row.icon, row.color = data.icon, data.color
        row.sections = [str(s) for s in data.sections]
        return row

    async def _periods(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        data = _check(PeriodCreate, item["name"], **{k: v for k, v in item.items() if k != "ref"})
        row = await self._load(Period, existing)
        row.name, row.start_date, row.end_date = data.name, data.start_date, data.end_date
        row.cycle_weeks, row.first_cycle_week = data.cycle_weeks, data.first_cycle_week
        row.pauses = [p.model_dump(mode="json", by_alias=True) for p in data.pauses]
        return row

    async def _days_off(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        data = _check(
            DayOffCreate,
            item["title"] or item["date_from"],
            period_id=self.ref("periods", item["period"]),
            date_from=item["date_from"],
            date_to=item["date_to"],
            title=item["title"],
        )
        row = await self._load(DayOff, existing)
        row.period_id, row.date_from, row.date_to, row.title = (
            data.period_id,
            data.date_from,
            data.date_to,
            data.title,
        )
        return row

    async def _slot_grids(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        data = _check(
            SlotGridPut,
            item["name"],
            period_id=self.ref("periods", item["period"]),
            name=item["name"],
            schedules=item["schedules"],
        )
        head = await self._load(SlotGrid, existing)
        group: list[SlotGrid] = []
        if existing:
            group = [
                g
                for g in await self.svc._rows(SlotGrid, SlotGrid.weekday)
                if g.period_id == head.period_id and g.name == head.name and g.weekday is not None
            ]
        by_day = {g.weekday: g for g in group}
        for day in data.schedules:
            slots = [s.model_dump(mode="json") for s in day.slots]
            if day.weekday is None:
                head.period_id, head.name, head.weekday, head.slots = (
                    data.period_id,
                    data.name,
                    None,
                    slots,
                )
            elif (row := by_day.pop(day.weekday, None)) is not None:
                row.slots = slots
            else:
                self.db.add(
                    SlotGrid(
                        user_id=self.user_id,
                        period_id=data.period_id,
                        name=data.name,
                        weekday=day.weekday,
                        slots=slots,
                    )
                )
        for row in by_day.values():
            row.deleted_at = now_utc()
        return head

    async def _areas(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        type_id = self.ref("area_types", item["area_type"])
        area_type = await self.db.get(AreaType, type_id)
        if area_type is None:  # check_refs гарантирует, что тип есть
            raise InvalidDataError(f"{item['name']}: тип сферы не найден")
        values = _map_area_values(
            area_type.fields,
            item["fields"],
            {ref: str(id) for (s, ref), id in self.ids.items() if s == "areas"},
        )
        row = await self._load(Area, existing)
        try:
            row.fields = clean_values(parse_defs(area_type.fields), values, stored=row.fields)
        except FieldError as exc:
            raise InvalidDataError(f"{item['name']}: {exc}") from exc
        row.area_type_id = area_type.id
        row.period_id = self.ref("periods", item["period"])
        row.name = item["name"]
        row.short_name = item["short_name"] or None
        row.color = item["color"]
        row.synonyms = item["synonyms"]
        row.notes = item["notes"]
        return row

    async def _event_types(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        values = {k: v for k, v in item.items() if k not in ("ref", "default_area_type")}
        values["default_area_type_id"] = self.ref("area_types", item["default_area_type"])
        data = _check(EventTypeCreate, item["name"], **values)
        row = await self._load(EventType, existing)
        row.fields = self._defs(row, data.fields, data.name)
        for name, value in data.model_dump(exclude={"fields", "name_plural"}).items():
            setattr(row, name, value)
        row.name_plural = data.name_plural or data.name
        return row

    async def _budgets(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        _check(
            LoadBudgetCreate,
            item["name"],
            name=item["name"],
            minutes_per_day=item["minutes_per_day"],
        )
        row = await self._load(LoadBudget, existing)
        row.name, row.minutes_per_day = item["name"], item["minutes_per_day"]
        want = [("action_type_id", self.ref("action_types", r)) for r in item["action_types"]]
        want += [("event_type_id", self.ref("event_types", r)) for r in item["event_types"]]
        if existing:
            for m in await self.svc._rows(LoadBudgetMember, LoadBudgetMember.created_at):
                if m.budget_id == row.id:
                    m.deleted_at = now_utc()

        def members() -> None:
            for name, id in want:
                self.db.add(LoadBudgetMember(user_id=self.user_id, budget_id=row.id, **{name: id}))

        self.after.append(members)
        return row

    async def _day_profiles(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        data = _check(
            DayProfileCreate, item["name"], **{k: v for k, v in item.items() if k != "ref"}
        )
        row = await self._load(DayProfile, existing)
        apply_profile(row, data)
        return row

    async def _day_profile_rules(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        data = _check(
            DayProfileRuleCreate,
            item["ref"],
            profile_id=self.ref("day_profiles", item["profile"]),
            kind=item["kind"],
            date_from=item["date_from"],
            date_to=item["date_to"],
            event_type_id=self.ref("event_types", item["event_type"]),
            weekdays=item["weekdays"],
        )
        row = await self._load(DayProfileRule, existing)
        for name, value in data.model_dump().items():
            setattr(row, name, value)
        return row

    async def _schedule_rules(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        values = {
            k: v
            for k, v in item.items()
            if k not in ("ref", "event_type", "area", "period", "slot_grid")
        }
        type_id = self.ref("event_types", item["event_type"])
        event_type = await self.db.get(EventType, type_id)
        if event_type is None:
            raise InvalidDataError(f"{item['ref']}: тип занятости не найден")
        values["fields"] = _map_area_values(
            event_type.fields,
            values["fields"],
            {ref: str(id) for (s, ref), id in self.ids.items() if s == "areas"},
        )
        data = _check(
            ScheduleRuleCreate,
            item["ref"],
            event_type_id=type_id,
            area_id=self.ref("areas", item["area"]),
            period_id=self.ref("periods", item["period"]),
            slot_grid_id=self.ref("slot_grids", item["slot_grid"]),
            **values,
        )
        row = await self._load(ScheduleRule, existing)
        checked = await ScheduleService(self.db, self.user).check_rule(
            data, row if existing else None
        )
        for name, value in checked.items():
            setattr(row, name, value)
        return row

    async def _event_rules(self, item: dict[str, Any], existing: uuid.UUID | None) -> Any:
        data = _check(
            EventRuleCreate,
            item["title_template"],
            event_type_id=self.ref("event_types", item["event_type"]),
            schedule_rule_id=self.ref("schedule_rules", item["schedule_rule"]),
            when=item["when"],
            title_template=item["title_template"],
            estimate_min=item["estimate_min"],
            action_type_id=self.ref("action_types", item["action_type"]),
            task_type_id=self.ref("task_types", item["task_type"]),
            offset_min=item["offset_min"],
            within_days=item["within_days"],
            until_next=item["until_next"],
            confirm=item["confirm"],
        )
        await EventRuleService(self.db, self.user).check_refs(data)
        row = await self._load(EventRule, existing)
        for name, value in data.model_dump().items():
            setattr(row, name, value)
        return row
