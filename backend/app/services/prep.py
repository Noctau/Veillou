"""Подготовка к событию (Part 2, M20; бывшие экзамены M12): план, пункты, дни.

План крепится к жёсткому событию (экзамен, выступление, собеседование — тип с
`supports_prep`) или к сфере с датой. Событие живёт своей жизнью в календаре: его
переносят и отменяют там, план следует за ним (пересборка по джобе
`event_tasks.sync` после правки событий и ночью).

План включается кнопкой и дальше пересобирается сам — после правки пунктов,
статусов, параметров, переноса события, отметок на блоках и ночью: стратегия
(`domain/srs.py`: spaced / even) считает дни, `sync_sessions` сверяет их с
`prep_sessions` (правит на месте по ключу «день + вид», лишние убирает). Блоки этих
дней ставит в календарь планировщик (services/replan.py) — через обычное превью.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc, wall_to_utc
from app.domain import srs
from app.domain.enums import (
    EventKind,
    EventStatus,
    PlanReason,
    PrepItemStatus,
    PrepSessionKind,
    PrepSessionStatus,
    PrepStrategy,
    SourceType,
)
from app.domain.prep import parse_items, plan_title, session_title
from app.models import Area, Event, EventType, PrepItem, PrepPlan, PrepSession, User
from app.schemas.prep import (
    PrepEventRead,
    PrepItemCreate,
    PrepItemRead,
    PrepItemUpdate,
    PrepPlanCreate,
    PrepPlanDetail,
    PrepPlanRead,
    PrepPlanUpdate,
    PrepSessionRead,
)
from app.services.base import UserScopedRepository


class PlanRepo(UserScopedRepository[PrepPlan]):
    model = PrepPlan
    not_found_message = "План подготовки не найден"


class ItemRepo(UserScopedRepository[PrepItem]):
    model = PrepItem
    not_found_message = "Пункт не найден"


class SessionRepo(UserScopedRepository[PrepSession]):
    model = PrepSession
    not_found_message = "День подготовки не найден"


class _AreaRepo(UserScopedRepository[Area]):
    model = Area
    not_found_message = "Сфера не найдена"


class _EventRepo(UserScopedRepository[Event]):
    model = Event
    not_found_message = "Событие не найдено"


class _EventTypeRepo(UserScopedRepository[EventType]):
    model = EventType
    not_found_message = "Тип занятости не найден"


MAX_ITEMS = 300


def params_of(plan: PrepPlan) -> srs.Params:
    return srs.Params(
        learn_min=plan.learn_min,
        review_min=plan.review_min,
        run_min=plan.run_min,
        start_days_before=plan.start_days_before,
    )


def live(event: Event | None) -> Event | None:
    """Событие плана, если оно ещё есть (не удалено и не отменено)."""
    if event is None or event.deleted_at is not None or event.status == EventStatus.cancelled:
        return None
    return event


class PrepService:
    def __init__(self, db: AsyncSession, user: User, now: datetime | None = None) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.now = now or now_utc()
        self.today = local_date(self.now, self.tz)
        self.plans = PlanRepo(db, user.id)
        self.items = ItemRepo(db, user.id)
        self.sessions = SessionRepo(db, user.id)
        self.areas = _AreaRepo(db, user.id)
        self.events = _EventRepo(db, user.id)
        self.event_types = _EventTypeRepo(db, user.id)

    # ---------- цель плана ----------

    async def _event(self, plan: PrepPlan) -> Event | None:
        if plan.event_id is None:
            return None
        return await self.db.scalar(
            select(Event).where(Event.id == plan.event_id, Event.user_id == self.user_id)
        )

    def _target(self, plan: PrepPlan, event: Event | None) -> datetime | None:
        """К какому моменту готовиться: начало живого события или начало даты."""
        if plan.event_id is not None:
            e = live(event)
            return e.start if e else None
        return wall_to_utc(plan.date, time(0), self.tz) if plan.date else None

    async def name(self, plan: PrepPlan, event: Event | None = None) -> str:
        """Короткое имя для блоков: сфера (короткое имя) → название плана."""
        area = await self.areas.get(plan.area_id) if plan.area_id else None
        if area is not None:
            return area.short_name or area.name
        return plan_title(plan.title, event.title if event else None, None)

    # ---------- чтение ----------

    async def _counts(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        if not ids:
            return {}
        rows = await self.db.execute(
            select(
                PrepItem.plan_id,
                func.count(),
                func.count().filter(PrepItem.status != PrepItemStatus.not_started),
            )
            .where(
                PrepItem.user_id == self.user_id,
                PrepItem.deleted_at.is_(None),
                PrepItem.plan_id.in_(ids),
            )
            .group_by(PrepItem.plan_id)
        )
        return {plan_id: (total, learned) for plan_id, total, learned in rows}

    async def _read(self, plan: PrepPlan, counts: tuple[int, int]) -> PrepPlanRead:
        event = await self._event(plan)
        area = await self.areas.get(plan.area_id) if plan.area_id else None
        read = PrepPlanRead.model_validate(plan)
        read.title = plan_title(
            plan.title, event.title if event else None, area.name if area else None
        )
        read.target = self._target(plan, event)
        read.event = PrepEventRead.model_validate(event) if event else None
        read.items_total, read.items_learned = counts
        return read

    async def list_plans(
        self, area_id: uuid.UUID | None = None, event_id: uuid.UUID | None = None
    ) -> list[PrepPlanRead]:
        where = []
        if area_id:
            where.append(PrepPlan.area_id == area_id)
        if event_id:
            where.append(PrepPlan.event_id == event_id)
        plans = await self.plans.find_all(*where, order_by=[PrepPlan.created_at])
        counts = await self._counts([p.id for p in plans])
        reads = [await self._read(p, counts.get(p.id, (0, 0))) for p in plans]
        far = datetime.max.replace(tzinfo=self.now.tzinfo)
        return sorted(reads, key=lambda r: r.target or far)

    async def _items(self, plan_id: uuid.UUID) -> list[PrepItem]:
        return await self.items.find_all(
            PrepItem.plan_id == plan_id, order_by=[PrepItem.number, PrepItem.created_at]
        )

    async def get_detail(self, id: uuid.UUID) -> PrepPlanDetail:
        plan = await self.plans.get_or_404(id)
        event = await self._event(plan)
        items = await self._items(plan.id)
        learned = sum(q.status != PrepItemStatus.not_started for q in items)
        sessions = await self.sessions.find_all(
            PrepSession.plan_id == plan.id,
            PrepSession.date >= self.today,
            order_by=[PrepSession.date, PrepSession.kind],
        )
        placed: dict[uuid.UUID, list[Event]] = defaultdict(list)
        if sessions:
            for e in await self.events.find_all(
                Event.source_type == SourceType.prep_session,
                Event.source_id.in_([x.id for x in sessions]),
                Event.status.in_([EventStatus.planned, EventStatus.done]),
                order_by=[Event.start],
            ):
                if e.source_id is not None:
                    placed[e.source_id].append(e)
        numbers = {str(q.id): q.number for q in items}
        name = await self.name(plan, event)
        session_reads = []
        for x in sessions:
            nums = sorted(numbers[q] for q in x.item_ids if q in numbers)
            events = placed.get(x.id, [])
            session_reads.append(
                PrepSessionRead(
                    id=x.id,
                    date=x.date,
                    kind=PrepSessionKind(x.kind),
                    title=session_title(PrepSessionKind(x.kind), name, nums),
                    numbers=nums,
                    minutes=x.minutes,
                    status=PrepSessionStatus(x.status),
                    start=events[0].start if events else None,
                    end=events[-1].end if events else None,
                )
            )
        base = await self._read(plan, (len(items), learned))
        return PrepPlanDetail(
            **base.model_dump(),
            items=[PrepItemRead.model_validate(q) for q in items],
            sessions=session_reads,
        )

    # ---------- план ----------

    async def _prep_type(self, type_id: uuid.UUID | None) -> EventType | None:
        if type_id is not None:
            return await self.event_types.get_or_404(type_id)
        return await self.db.scalar(
            select(EventType)
            .where(
                EventType.user_id == self.user_id,
                EventType.deleted_at.is_(None),
                EventType.supports_prep.is_(True),
            )
            .order_by(EventType.position, EventType.created_at)
            .limit(1)
        )

    async def create(self, data: PrepPlanCreate) -> PrepPlanDetail:
        area = await self.areas.get_or_404(data.area_id) if data.area_id else None
        event_id, plan_date = data.event_id, data.date
        if data.event_id is not None:
            event = await self.events.get_or_404(data.event_id)
            if event.kind != EventKind.busy:
                raise InvalidDataError("Готовиться можно только к жёсткому событию")
            if area is None and event.area_id:
                area = await self.areas.get(event.area_id)
        elif data.event is not None:
            event_type = await self._prep_type(data.event.event_type_id)
            title = data.event.title or ": ".join(
                x
                for x in (event_type.name if event_type else None, area.name if area else None)
                if x
            )
            event = Event(
                kind=EventKind.busy,
                event_type_id=event_type.id if event_type else None,
                title=title or "Событие",
                start=data.event.start,
                end=data.event.start + timedelta(minutes=data.event.duration_min),
                location=data.event.location,
                area_id=area.id if area else None,
                is_fixed=True,
                is_pinned=False,
                status=EventStatus.planned,
                note="",
            )
            self.events.add(event)
            await self.db.flush()
            event_id = event.id
        values = data.model_dump(exclude={"event", "event_id", "date", "area_id"})
        plan = PrepPlan(
            event_id=event_id, date=plan_date, area_id=area.id if area else None, **values
        )
        self.plans.add(plan)
        await self.db.commit()
        return await self.get_detail(plan.id)

    async def update(self, id: uuid.UUID, patch: PrepPlanUpdate) -> PrepPlanDetail:
        plan = await self.plans.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name, value in changes.items():
            if value is None and name not in ("area_id", "date"):
                raise InvalidDataError(f"{name}: не может быть пустым")
        if "date" in changes:
            if plan.event_id is not None:
                raise InvalidDataError("Дата плана с событием — это дата события")
            if changes["date"] is None:
                raise InvalidDataError("date: не может быть пустым")
        if changes.get("area_id"):
            await self.areas.get_or_404(changes["area_id"])
        for name, value in changes.items():
            setattr(plan, name, value)
        await self.sync_sessions(plan)
        await self.db.commit()
        return await self.get_detail(plan.id)

    async def delete(self, id: uuid.UUID, *, with_event: bool = False) -> None:
        """План удаляется с пунктами и днями (их блоки уберёт превью); событие — по флагу."""
        plan = await self.plans.get_or_404(id)
        self.plans.soft_delete(plan)
        for q in await self._items(plan.id):
            self.items.soft_delete(q)
        for x in await self.sessions.find_all(PrepSession.plan_id == plan.id):
            self.sessions.soft_delete(x)
        if with_event and (event := await self._event(plan)) is not None:
            self.events.soft_delete(event)
        await self.db.commit()

    # ---------- пункты ----------

    async def import_items(self, id: uuid.UUID, text: str) -> PrepPlanDetail:
        plan = await self.plans.get_or_404(id)
        existing = await self._items(plan.id)
        start = max((q.number for q in existing), default=0) + 1
        parsed = parse_items(text, start_number=start)
        if not parsed:
            raise InvalidDataError("Не нашлось пунктов в тексте")
        if len(existing) + len(parsed) > MAX_ITEMS:
            raise InvalidDataError(f"Слишком много пунктов (максимум {MAX_ITEMS})")
        for p in parsed:
            self.items.add(
                PrepItem(
                    plan_id=plan.id,
                    number=p.number,
                    text=p.text,
                    status=PrepItemStatus.not_started,
                    reviews_done=0,
                )
            )
        await self.db.flush()
        await self.sync_sessions(plan)
        await self.db.commit()
        return await self.get_detail(plan.id)

    async def add_item(self, id: uuid.UUID, data: PrepItemCreate) -> PrepPlanDetail:
        plan = await self.plans.get_or_404(id)
        existing = await self._items(plan.id)
        if len(existing) >= MAX_ITEMS:
            raise InvalidDataError(f"Слишком много пунктов (максимум {MAX_ITEMS})")
        number = data.number or max((q.number for q in existing), default=0) + 1
        self.items.add(
            PrepItem(
                plan_id=plan.id,
                number=number,
                text=data.text,
                status=PrepItemStatus.not_started,
                reviews_done=0,
            )
        )
        await self.db.flush()
        await self.sync_sessions(plan)
        await self.db.commit()
        return await self.get_detail(plan.id)

    def _set_status(self, q: PrepItem, status: PrepItemStatus) -> None:
        if status == q.status:
            return
        if status == PrepItemStatus.not_started:
            q.learned_on, q.reviews_done = None, 0
        elif status == PrepItemStatus.review:
            # «Повторить»: цикл повторений заново, от сегодняшнего дня
            q.learned_on, q.reviews_done = self.today, 0
        elif q.status == PrepItemStatus.not_started or q.learned_on is None:
            q.learned_on, q.reviews_done = self.today, 0
        q.status = status

    async def update_item(self, item_id: uuid.UUID, patch: PrepItemUpdate) -> PrepItemRead:
        q = await self.items.get_or_404(item_id)
        changes = patch.model_dump(exclude_unset=True)
        for name in ("number", "text", "status"):
            if name in changes and changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if "number" in changes:
            q.number = changes["number"]
        if "text" in changes:
            q.text = changes["text"]
        if "status" in changes:
            self._set_status(q, PrepItemStatus(changes["status"]))
        await self.db.flush()
        plan = await self.plans.get_or_404(q.plan_id)
        await self.sync_sessions(plan)
        await self.db.commit()
        return PrepItemRead.model_validate(q)

    async def delete_item(self, item_id: uuid.UUID) -> None:
        q = await self.items.get_or_404(item_id)
        self.items.soft_delete(q)
        await self.db.flush()
        plan = await self.plans.get_or_404(q.plan_id)
        await self.sync_sessions(plan)
        await self.db.commit()

    # ---------- дни плана ----------

    async def enable(self, id: uuid.UUID) -> PrepPlanDetail:
        """«Построить план»: дни подготовки + превью плана (применяет пользователь)."""
        from app.services.replan import ReplanService

        plan = await self.plans.get_or_404(id)
        if not await self._items(plan.id):
            raise InvalidDataError("Сначала добавьте пункты")
        target = self._target(plan, await self._event(plan))
        if target is None or target <= self.now:
            raise InvalidDataError("Событие уже прошло")
        plan.enabled = True
        await self.sync_sessions(plan)
        await self.db.commit()
        await ReplanService(self.db, self.user, self.now).preview([PlanReason.prep], force=True)
        return await self.get_detail(plan.id)

    async def disable(self, id: uuid.UUID) -> PrepPlanDetail:
        """Убрать план: будущие дни удаляются, их блоки уберёт превью."""
        plan = await self.plans.get_or_404(id)
        plan.enabled = False
        await self.sync_sessions(plan)
        await self.db.commit()
        return await self.get_detail(plan.id)

    async def sync_sessions(self, plan: PrepPlan) -> bool:
        """Сверяет дни плана с расчётом стратегии. Не коммитит. True — что-то изменилось."""
        sessions = await self.sessions.find_all(PrepSession.plan_id == plan.id)
        changed = False
        for x in sessions:
            if x.status == PrepSessionStatus.planned and x.date < self.today:
                x.status = PrepSessionStatus.missed
                changed = True
        closed = frozenset(
            (x.date, PrepSessionKind(x.kind))
            for x in sessions
            if x.date >= self.today and x.status != PrepSessionStatus.planned
        )
        event = await self._event(plan)
        target = self._target(plan, event)
        if plan.event_id is not None and event is not None and event.area_id != plan.area_id:
            plan.area_id = event.area_id  # сферу события поменяли — план за ней
        desired: list[srs.DayPlan] = []
        if plan.enabled and plan.deleted_at is None and target is not None and target > self.now:
            items = [
                srs.Item(
                    str(q.id),
                    q.number,
                    PrepItemStatus(q.status),
                    learned_on=q.learned_on,
                    reviews_done=q.reviews_done,
                )
                for q in await self._items(plan.id)
            ]
            desired = srs.plan(
                PrepStrategy(plan.strategy),
                items,
                self.today,
                local_date(target, self.tz),
                params_of(plan),
                closed,
            )

        current = {
            (x.date, x.kind): x
            for x in sessions
            if x.status == PrepSessionStatus.planned and x.date >= self.today
        }
        renamed: list[PrepSession] = []
        for day in desired:
            ids = list(day.item_ids)
            existing = current.pop((day.date, str(day.kind)), None)
            if existing is None:
                self.sessions.add(
                    PrepSession(
                        plan_id=plan.id,
                        date=day.date,
                        kind=day.kind,
                        item_ids=ids,
                        minutes=day.minutes,
                        status=PrepSessionStatus.planned,
                    )
                )
                changed = True
            elif existing.item_ids != ids or existing.minutes != day.minutes:
                if existing.item_ids != ids:
                    renamed.append(existing)
                existing.item_ids, existing.minutes = ids, day.minutes
                changed = True
        for x in current.values():
            self.sessions.soft_delete(x)
            changed = True
        if renamed:
            await self._rename_events(plan, renamed, event)
        return changed

    async def _rename_events(
        self, plan: PrepPlan, sessions: list[PrepSession], event: Event | None
    ) -> None:
        """Название блока следует за пунктами дня."""
        name = await self.name(plan, event)
        numbers = {str(q.id): q.number for q in await self._items(plan.id)}
        by_id = {x.id: x for x in sessions}
        for e in await self.events.find_all(
            Event.source_type == SourceType.prep_session,
            Event.source_id.in_(by_id),
            Event.status == EventStatus.planned,
        ):
            if e.source_id is None:
                continue
            x = by_id[e.source_id]
            nums = [numbers[q] for q in x.item_ids if q in numbers]
            e.title = session_title(PrepSessionKind(x.kind), name, nums)

    # ---------- отметки на блоках ----------

    async def on_session_status(self, session_id: uuid.UUID, status: str) -> None:
        """Блок дня отметили: сделано → пункты пройдены / повторены; снятие отметки →
        назад; «не сделано» → день пропущен, пункты уходят дальше. Не коммитит."""
        x = await self.sessions.get(session_id)
        if x is None:
            return
        items = {
            str(q.id): q
            for q in await self.items.find_all(PrepItem.id.in_([uuid.UUID(i) for i in x.item_ids]))
        }
        kind = PrepSessionKind(x.kind)
        if status == EventStatus.done and x.status != PrepSessionStatus.done:
            x.status, x.done_at = PrepSessionStatus.done, self.now
            for q in items.values():
                if kind == PrepSessionKind.learn and q.status == PrepItemStatus.not_started:
                    q.status, q.learned_on, q.reviews_done = PrepItemStatus.learned, x.date, 0
                elif kind == PrepSessionKind.review and q.learned_on is not None:
                    q.reviews_done += 1
                    if q.status == PrepItemStatus.review:
                        q.status = PrepItemStatus.learned
        elif status == EventStatus.planned and x.status == PrepSessionStatus.done:
            x.status, x.done_at = PrepSessionStatus.planned, None
            for q in items.values():
                if kind == PrepSessionKind.learn and q.learned_on == x.date and not q.reviews_done:
                    q.status, q.learned_on = PrepItemStatus.not_started, None
                elif kind == PrepSessionKind.review and q.reviews_done > 0:
                    q.reviews_done -= 1
        elif status == EventStatus.missed and x.status == PrepSessionStatus.planned:
            x.status = PrepSessionStatus.missed
        else:
            return
        await self.db.flush()
        plan = await self.plans.get(x.plan_id)
        if plan is not None:
            await self.sync_sessions(plan)


async def sync_user(db: AsyncSession, user: User, now: datetime | None = None) -> int:
    """Пересобрать все включённые планы пользователя (событие перенесли, ночь). Не коммитит."""
    svc = PrepService(db, user, now)
    changed = 0
    for plan in await svc.plans.find_all(PrepPlan.enabled.is_(True)):
        changed += await svc.sync_sessions(plan)
    return changed


async def sync_all(db: AsyncSession, user: User, now: datetime | None = None) -> int:
    """Ночью: пропущенные дни → missed, планы пересобраны. Коммитит."""
    changed = await sync_user(db, user, now)
    await db.commit()
    return changed


async def upcoming(
    db: AsyncSession, user: User, start: datetime, end: datetime
) -> list[tuple[PrepPlan, str, datetime, Event | None]]:
    """Планы, чей срок (событие или дата) в [start, end): (план, название, срок,
    событие) — для сводки."""
    svc = PrepService(db, user)
    result = []
    for plan in await svc.plans.find_all():
        event = await svc._event(plan)
        target = svc._target(plan, event)
        if target is None or not start <= target < end:
            continue
        area = await svc.areas.get(plan.area_id) if plan.area_id else None
        title = plan_title(plan.title, event.title if event else None, area.name if area else None)
        result.append((plan, title, target, live(event)))
    return sorted(result, key=lambda r: r[2])


def days_until(target: datetime, today: date, tz: object) -> int:
    return (local_date(target, tz) - today).days  # type: ignore[arg-type]
