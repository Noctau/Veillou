"""Автозадачи от событий (Part 2, M19): правила (CRUD) и материализация задач.

По образцу services/recurring_tasks.py — идемпотентная сверка «что должно быть» с
тем, что есть, ключ — (правило, вхождение):
- вхождение типа (или правила расписания) правила → задача с окном
  (domain/event_tasks.py) на горизонт вхождений, но не дальше `HORIZON`;
- перенос вхождения пересчитывает окно несделанной задачи (детачнутое — тоже: ключ —
  id события, а не дата);
- отмена или удаление вхождения отменяет несделанную задачу;
- удаление правила убирает его будущие несделанные задачи;
- сделанное, отменённое и удалённое пользователем заново не создаётся.

Правило с подтверждением (`confirm`) создаёт предложение (`TaskStatus.proposed`)
только для вхождений сегодня и завтра — его показывает вечерний разбор;
непринятое предложение с прошедшим сроком отменяется.

Срок типа задачи «к следующему вхождению» (`deadline_auto`) — начало ближайшего
вхождения правила расписания той же сферы после постановки задачи; пересчитывается
здесь же (перенос, отмена, пауза периода).

Запуск: джоба `event_tasks.sync` (триггер на изменения жёстких событий и правил),
ночная докатка и сразу после правки правил.
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc, wall_to_utc
from app.domain import event_tasks as et
from app.domain.enums import EventKind, EventRuleWhen, EventStatus, TaskStatus, TemplateType
from app.domain.fields import parse_defs, render_values
from app.models import (
    ActionType,
    Area,
    AreaType,
    Event,
    EventRule,
    EventType,
    Job,
    ScheduleRule,
    Task,
    TaskType,
    User,
)
from app.schemas.event_rule import EventRuleCreate, EventRuleUpdate
from app.services.base import UserScopedRepository, validate_patch
from app.services.settings import effective_settings

log = logging.getLogger(__name__)

# Дальше этого задачи не создаются (вхождения периода могут быть на полгода вперёд)
HORIZON = timedelta(days=90)
# Соседние вхождения серии ищем в таком запасе вокруг горизонта
NEIGHBOURS = timedelta(days=60)
# «После»: задачу по вхождению, которое закончилось недавно, ещё можно создать
LATE = timedelta(days=3)
OPEN = (TaskStatus.active, TaskStatus.proposed)


class EventRuleRepo(UserScopedRepository[EventRule]):
    model = EventRule
    not_found_message = "Автозадача не найдена"


class _EventTypeRepo(UserScopedRepository[EventType]):
    model = EventType
    not_found_message = "Тип занятости не найден"


class _ScheduleRuleRepo(UserScopedRepository[ScheduleRule]):
    model = ScheduleRule
    not_found_message = "Правило расписания не найдено"


class _ActionTypeRepo(UserScopedRepository[ActionType]):
    model = ActionType
    not_found_message = "Тип действия не найден"


class _TaskTypeRepo(UserScopedRepository[TaskType]):
    model = TaskType
    not_found_message = "Тип задачи не найден"


@dataclass
class SyncStats:
    created: int = 0
    updated: int = 0
    cancelled: int = 0
    removed: int = 0


def _series(e: Event) -> tuple[Any, ...]:
    """Серия вхождения: правило расписания или (тип, сфера) у разового события."""
    if e.template_id is not None:
        return ("rule", e.template_id)
    return ("type", e.event_type_id, e.area_id)


def _window_of(rule: EventRule) -> et.RuleWindow:
    return et.RuleWindow(
        EventRuleWhen(rule.when), rule.offset_min, rule.within_days, rule.until_next
    )


def _field_texts(defs_raw: Any, values: dict[str, Any] | None) -> dict[str, str]:
    """Тексты полей по id и по подписи (для `{field:…}`)."""
    result: dict[str, str] = {}
    for d in parse_defs(defs_raw):
        for _, text in render_values([d], values):
            result.setdefault(d.id, text)
            result.setdefault(d.label, text)
    return result


class _Sync:
    def __init__(self, db: AsyncSession, user: User, now: datetime) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.now = now
        self.tz = get_tz(user.timezone)
        self.today = local_date(now, self.tz)
        self.stats = SyncStats()

    async def _all[M: Any](self, model: type[M], *where: Any) -> list[M]:
        return list(
            await self.db.scalars(
                select(model).where(
                    model.user_id == self.user_id, model.deleted_at.is_(None), *where
                )
            )
        )

    async def run(self) -> SyncStats:
        rules = await self._all(EventRule)
        await self._drop_deleted_rules()
        if rules:
            await self._materialize(rules)
        await self._auto_deadlines()
        return self.stats

    # ---------- правила ----------

    async def _drop_deleted_rules(self) -> None:
        """Будущие несделанные задачи удалённых правил — убрать."""
        rows = await self.db.execute(
            select(Task, Event.start)
            .join(EventRule, EventRule.id == Task.origin_rule_id)
            .outerjoin(Event, Event.id == Task.origin_event_id)
            .where(
                Task.user_id == self.user_id,
                Task.deleted_at.is_(None),
                Task.status.in_(OPEN),
                EventRule.deleted_at.is_not(None),
            )
        )
        for task, start in rows.all():
            event_start: datetime | None = start  # вхождения могло не остаться
            if event_start is None or event_start > self.now:
                task.deleted_at = self.now
                self.stats.removed += 1

    async def _materialize(self, rules: list[EventRule]) -> None:
        schedule_rules = {
            r.id: r
            for r in await self._all(
                ScheduleRule,
                ScheduleRule.id.in_([x.schedule_rule_id for x in rules if x.schedule_rule_id]),
            )
        }
        type_ids = {r.event_type_id for r in rules if r.event_type_id} | {
            r.event_type_id for r in schedule_rules.values()
        }
        types = {t.id: t for t in await self._all(EventType, EventType.id.in_(type_ids))}
        lo, hi = self.now - LATE - NEIGHBOURS, self.now + HORIZON + NEIGHBOURS
        # Удалённые и отменённые тоже: их задачи надо отменить
        events = list(
            await self.db.scalars(
                select(Event).where(
                    Event.user_id == self.user_id,
                    Event.kind == EventKind.busy,
                    Event.event_type_id.in_(types),
                    Event.start >= lo,
                    Event.start < hi,
                )
            )
        )
        live = [e for e in events if e.deleted_at is None and e.status != EventStatus.cancelled]
        series: dict[tuple[Any, ...], list[Event]] = defaultdict(list)
        for e in sorted(live, key=lambda e: (e.start, e.id)):
            series[_series(e)].append(e)
        position = {e.id: i for group in series.values() for i, e in enumerate(group)}

        areas = {
            a.id: a
            for a in await self._all(Area, Area.id.in_({e.area_id for e in events if e.area_id}))
        }
        area_types = {
            t.id: t
            for t in await self._all(
                AreaType, AreaType.id.in_({a.area_type_id for a in areas.values()})
            )
        }
        action_types = {a.id: a for a in await self._all(ActionType)}
        task_types = {t.id: t for t in await self._all(TaskType)}
        default_action = effective_settings(self.user).default_action_type_id

        existing: dict[tuple[uuid.UUID, uuid.UUID], Task] = {}
        rows = await self.db.scalars(
            select(Task).where(
                Task.user_id == self.user_id,
                Task.origin_rule_id.in_([r.id for r in rules]),
                Task.origin_event_id.is_not(None),
            )
        )
        for t in rows:
            key = (t.origin_rule_id, t.origin_event_id)
            # Живая важнее удалённой (одна живая на ключ — уникальный индекс)
            if key not in existing or existing[key].deleted_at is not None:
                existing[key] = t  # type: ignore[index]

        tomorrow_end = wall_to_utc(self.today + timedelta(days=2), time(0), self.tz)
        horizon_end = self.now + HORIZON

        def neighbours(e: Event) -> tuple[datetime | None, datetime | None]:
            group = series.get(_series(e), [])
            i = position.get(e.id)
            if i is None:
                return None, None
            prev_end = group[i - 1].end if i > 0 else None
            next_start = group[i + 1].start if i + 1 < len(group) else None
            return prev_end, next_start

        def title_of(rule: EventRule, e: Event) -> str:
            area = areas.get(e.area_id) if e.area_id else None
            fields = _field_texts(types[e.event_type_id].fields, e.fields)  # type: ignore[index]
            if area is not None and (at := area_types.get(area.area_type_id)):
                for k, v in _field_texts(at.fields, area.fields).items():
                    fields.setdefault(k, v)
            name = (area.short_name or area.name) if area else None
            return et.render_title(rule.title_template, event=e.title, area=name, fields=fields)[
                :300
            ]

        for rule in rules:
            targets = [
                e
                for e in events
                if (
                    e.template_id == rule.schedule_rule_id
                    if rule.schedule_rule_id
                    else e.event_type_id == rule.event_type_id
                )
            ]
            for e in targets:
                task = existing.get((rule.id, e.id))
                gone = e.deleted_at is not None or e.status == EventStatus.cancelled
                if task is not None:
                    if task.deleted_at is not None or task.status not in OPEN:
                        continue
                    if gone:
                        task.status = TaskStatus.cancelled
                        self.stats.cancelled += 1
                        continue
                    w = et.window(_window_of(rule), e.start, e.end, *neighbours(e))
                    if task.status == TaskStatus.proposed and w.deadline and w.deadline <= self.now:
                        task.status = TaskStatus.cancelled
                        self.stats.cancelled += 1
                        continue
                    changed = False
                    for name, value in (
                        ("earliest", w.earliest),
                        ("deadline", w.deadline),
                        ("area_id", e.area_id),
                    ):
                        if getattr(task, name) != value:
                            setattr(task, name, value)
                            changed = True
                    self.stats.updated += changed
                    continue
                if gone or e.start >= horizon_end:
                    continue
                if rule.confirm and e.start >= tomorrow_end:
                    continue
                w = et.window(_window_of(rule), e.start, e.end, *neighbours(e))
                if w.deadline is not None and w.deadline <= self.now:
                    continue
                if w.deadline is None and e.end + LATE <= self.now:
                    continue
                task_type = task_types.get(rule.task_type_id) if rule.task_type_id else None
                action_id = rule.action_type_id or (
                    task_type.default_action_type_id if task_type else None
                )
                if action_id not in action_types:
                    action_id = default_action if default_action in action_types else None
                action = action_types.get(action_id) if action_id else None
                result = await self.db.execute(
                    insert(Task)
                    .values(
                        id=uuid.uuid4(),
                        user_id=self.user_id,
                        title=title_of(rule, e),
                        task_type_id=task_type.id if task_type else None,
                        description="",
                        area_id=e.area_id,
                        category_id=action.default_category_id if action else None,
                        action_type_id=action_id,
                        deadline=w.deadline,
                        earliest=w.earliest,
                        # Окно точное: без «закончить за N дней до срока»
                        deadline_buffer_days=0,
                        priority="normal",
                        status=TaskStatus.proposed if rule.confirm else TaskStatus.active,
                        estimate_min=rule.estimate_min,
                        deadline_auto=False,
                        origin_event_id=e.id,
                        origin_rule_id=rule.id,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["origin_rule_id", "origin_event_id"],
                        index_where=Task.deleted_at.is_(None) & Task.origin_rule_id.is_not(None),
                    )
                )
                self.stats.created += result.rowcount or 0  # type: ignore[attr-defined]

    # ---------- сроки «к следующему вхождению» ----------

    async def _auto_deadlines(self) -> None:
        tasks = await self._all(
            Task,
            Task.deadline_auto.is_(True),
            Task.status.in_(OPEN),
            Task.area_id.is_not(None),
        )
        for task in tasks:
            deadline = await next_occurrence(self.db, self.user_id, task.area_id, task.created_at)  # type: ignore[arg-type]
            if deadline != task.deadline:
                task.deadline = deadline
                self.stats.updated += 1


async def next_occurrence(
    db: AsyncSession, user_id: uuid.UUID, area_id: uuid.UUID, after: datetime
) -> datetime | None:
    """Начало ближайшего вхождения правила расписания сферы после `after`."""
    return await db.scalar(
        select(func.min(Event.start)).where(
            Event.user_id == user_id,
            Event.deleted_at.is_(None),
            Event.kind == EventKind.busy,
            Event.template_type == TemplateType.schedule_rule,
            Event.area_id == area_id,
            Event.status != EventStatus.cancelled,
            Event.start > after,
        )
    )


async def sync_user(db: AsyncSession, user: User, now: datetime | None = None) -> SyncStats:
    """Сверяет автозадачи и сроки «к следующему» пользователя. Не коммитит."""
    return await _Sync(db, user, now or now_utc()).run()


async def handle_sync_job(db: AsyncSession, job: Job) -> None:
    if job.user_id is None:
        return
    user = await db.get(User, job.user_id)
    if user is None or user.deleted_at is not None:
        return
    await sync_user(db, user)
    # Событие плана подготовки перенесли или отменили — дни плана следуют за ним
    from app.services import prep

    await prep.sync_user(db, user)
    await db.commit()


async def sync_all(db: AsyncSession, now: datetime | None = None) -> int:
    """Ночная докатка: горизонт сдвинулся, предложения на завтра. Коммитит."""
    ids = list(await db.scalars(select(User.id).where(User.deleted_at.is_(None))))
    created = 0
    for user_id in ids:
        try:
            user = await db.get(User, user_id)
            if user is None:
                continue
            created += (await sync_user(db, user, now)).created
            await db.commit()
        except Exception:
            log.exception("Автозадачи пользователя %s упали", user_id)
            await db.rollback()
    return created


# ---------- CRUD правил ----------


class EventRuleService:
    def __init__(self, db: AsyncSession, user: User, now: datetime | None = None) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.now = now
        self.rules = EventRuleRepo(db, user.id)
        self.event_types = _EventTypeRepo(db, user.id)
        self.schedule_rules = _ScheduleRuleRepo(db, user.id)
        self.action_types = _ActionTypeRepo(db, user.id)
        self.task_types = _TaskTypeRepo(db, user.id)

    async def list_rules(
        self, event_type_id: uuid.UUID | None = None, schedule_rule_id: uuid.UUID | None = None
    ) -> list[EventRule]:
        where = []
        if event_type_id:
            where.append(EventRule.event_type_id == event_type_id)
        if schedule_rule_id:
            where.append(EventRule.schedule_rule_id == schedule_rule_id)
        return await self.rules.find_all(
            *where, order_by=[EventRule.position, EventRule.created_at, EventRule.id]
        )

    async def check_refs(self, data: EventRuleCreate) -> None:
        if data.event_type_id:
            await self.event_types.get_or_404(data.event_type_id)
        if data.schedule_rule_id:
            await self.schedule_rules.get_or_404(data.schedule_rule_id)
        if data.action_type_id:
            await self.action_types.get_or_404(data.action_type_id)
        if data.task_type_id:
            await self.task_types.get_or_404(data.task_type_id)

    async def _sync(self) -> None:
        await sync_user(self.db, self.user, self.now)

    async def create(self, data: EventRuleCreate) -> EventRule:
        await self.check_refs(data)
        position = await self.db.scalar(
            select(func.coalesce(func.max(EventRule.position) + 1, 0)).where(
                EventRule.user_id == self.user_id, EventRule.deleted_at.is_(None)
            )
        )
        rule = EventRule(**data.model_dump(), position=position or 0)
        self.rules.add(rule)
        await self.db.flush()
        await self._sync()
        await self.db.commit()
        return rule

    async def update(self, id: uuid.UUID, patch: EventRuleUpdate) -> EventRule:
        rule = await self.rules.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name in (
            "when",
            "title_template",
            "estimate_min",
            "offset_min",
            "until_next",
            "confirm",
        ):
            if name in changes and changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        data = validate_patch(rule, patch, EventRuleCreate)
        await self.check_refs(data)
        for name, value in data.model_dump().items():
            setattr(rule, name, value)
        if patch.position is not None:
            rule.position = patch.position
        await self.db.flush()
        await self._sync()
        await self.db.commit()
        return rule

    async def delete(self, id: uuid.UUID) -> None:
        """Правило удаляется, его будущие несделанные задачи — тоже."""
        rule = await self.rules.get_or_404(id)
        self.rules.soft_delete(rule)
        await self.db.flush()
        await self._sync()
        await self.db.commit()
