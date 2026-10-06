"""Материализация шаблонов в `events`.

Серия шаблона синхронизируется по ключу (template_type, template_id,
occurrence_date) начиная с сегодняшнего дня (локального):

- вхождение есть и в шаблоне, и в БД → поля обновляются на месте (id, а значит
  и привязанные конспекты/напоминания, сохраняются);
- есть только в шаблоне → создаётся;
- есть только в БД → мягко удаляется;
- `detached` (правили руками) и прошедшие дни не трогаются.

Вызывается после любого изменения ClassRule / BellSchedule / DayOff / Semester /
Subject, а для личных повторов — RecurringEvent (и ночной докаткой окна).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import get_tz, local_date, now_utc
from app.domain.enums import EventKind, EventStatus, TemplateType
from app.domain.recurrence import (
    Bells,
    BellSlot,
    ClassRuleSpec,
    DateRange,
    SemesterSpec,
    expand_class_rule,
    expand_rrule,
)
from app.models import (
    BellSchedule,
    ClassRule,
    DayOff,
    Event,
    RecurringEvent,
    Semester,
    Subject,
    User,
)
from app.services.jobs import request_reminders_sync

# Личные повторы материализуются на столько дней вперёд (ночная джоба докатывает)
RECURRING_HORIZON_DAYS = 90


@dataclass(frozen=True)
class Desired:
    """Каким должно быть вхождение по шаблону."""

    date: date
    start: datetime
    end: datetime
    fields: dict[str, Any]  # title, kind, location, color, …


@dataclass(frozen=True)
class SyncStats:
    created: int = 0
    updated: int = 0
    deleted: int = 0


# Поля, которые шаблон переписывает у не-detached вхождения
_TEMPLATE_FIELDS = (
    "kind",
    "title",
    "is_fixed",
    "location",
    "color",
    "subject_id",
    "class_type",
    "pair_number",
    "teacher",
)


def bells_from_rows(rows: Sequence[BellSchedule]) -> Bells:
    def slots(raw: list[dict[str, Any]]) -> list[BellSlot]:
        return [
            BellSlot(s["number"], time.fromisoformat(s["start"]), time.fromisoformat(s["end"]))
            for s in raw
        ]

    default = next((r for r in rows if r.weekday is None), None)
    return Bells.from_slots(
        slots(default.slots) if default else [],
        {r.weekday: slots(r.slots) for r in rows if r.weekday is not None},
    )


@dataclass
class _ClassContext:
    """Кэш на один проход синхронизации пар."""

    days_off: list[DateRange]
    semesters: dict[uuid.UUID, Semester | None] = field(default_factory=dict)
    bells: dict[uuid.UUID, Bells] = field(default_factory=dict)
    subjects: dict[uuid.UUID, Subject | None] = field(default_factory=dict)


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

    # ---------- общий механизм ----------

    async def _existing(self, template_type: TemplateType, template_id: uuid.UUID) -> list[Event]:
        rows = await self.db.scalars(
            select(Event).where(
                Event.user_id == self.user_id,
                Event.template_type == template_type,
                Event.template_id == template_id,
                Event.deleted_at.is_(None),
            )
        )
        return list(rows)

    async def sync_series(
        self,
        template_type: TemplateType,
        template_id: uuid.UUID,
        desired: Sequence[Desired],
        *,
        until: date | None = None,
    ) -> SyncStats:
        """Приводит будущие вхождения шаблона к `desired`.

        `until` — граница окна материализации (личные повторы на 90 дней):
        вхождения позже неё не удаляются, даже если их нет в `desired`.
        """
        existing = {e.occurrence_date: e for e in await self._existing(template_type, template_id)}
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
                    template_type=template_type,
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

    async def remove_series(
        self,
        template: ClassRule | RecurringEvent | uuid.UUID,
        template_type: TemplateType | None = None,
    ) -> None:
        """Шаблон удалён: убираем все будущие вхождения, включая правленные руками."""
        if isinstance(template, uuid.UUID):
            template_id = template
            template_type = template_type or TemplateType.class_rule
        else:
            template_id = template.id
            template_type = (
                TemplateType.recurring
                if isinstance(template, RecurringEvent)
                else TemplateType.class_rule
            )
        await self.db.execute(
            update(Event)
            .where(
                Event.user_id == self.user_id,
                Event.template_type == template_type,
                Event.template_id == template_id,
                Event.occurrence_date >= self.today,
                Event.deleted_at.is_(None),
            )
            .values(deleted_at=self.now)
        )
        await request_reminders_sync(self.db, self.user_id)

    async def restore_occurrence(self, event: Event) -> None:
        """«Как в расписании» для одного вхождения — в том числе прошедшего.

        Время и поля берутся из шаблона на дату вхождения, статус сбрасывается.
        Если по шаблону в этот день вхождения нет (или шаблон удалён) — событие удаляется.
        """
        assert event.template_id is not None and event.occurrence_date is not None
        day = event.occurrence_date
        window = DateRange(day, day)
        desired: list[Desired] | None = None
        if event.template_type == TemplateType.class_rule:
            rule = await self.db.get(ClassRule, event.template_id)
            if rule is not None:
                ctx = _ClassContext(await self._days_off())
                desired = await self._rule_desired(rule, window, ctx)
        elif event.template_type == TemplateType.recurring:
            rec = await self.db.get(RecurringEvent, event.template_id)
            if rec is not None and rec.deleted_at is None:
                desired = self._recurring_desired(rec, window)

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

    # ---------- пары ----------

    async def _days_off(self) -> list[DateRange]:
        rows = await self.db.scalars(
            select(DayOff).where(DayOff.user_id == self.user_id, DayOff.deleted_at.is_(None))
        )
        return [DateRange(r.date_from, r.date_to) for r in rows]

    async def _bells(self, semester_id: uuid.UUID) -> Bells:
        rows = await self.db.scalars(
            select(BellSchedule).where(
                BellSchedule.user_id == self.user_id,
                BellSchedule.semester_id == semester_id,
                BellSchedule.deleted_at.is_(None),
            )
        )
        return bells_from_rows(list(rows))

    async def _live_rules(self, *where: Any) -> list[ClassRule]:
        rows = await self.db.scalars(
            select(ClassRule).where(
                ClassRule.user_id == self.user_id, ClassRule.deleted_at.is_(None), *where
            )
        )
        return list(rows)

    async def _rule_desired(
        self, rule: ClassRule, window: DateRange, ctx: _ClassContext
    ) -> list[Desired] | None:
        """Вхождения правила пары в `window`; None — правило (или его семестр/предмет) удалено."""
        if rule.semester_id not in ctx.semesters:
            ctx.semesters[rule.semester_id] = await self.db.get(Semester, rule.semester_id)
            ctx.bells[rule.semester_id] = await self._bells(rule.semester_id)
        if rule.subject_id not in ctx.subjects:
            ctx.subjects[rule.subject_id] = await self.db.get(Subject, rule.subject_id)
        semester = ctx.semesters[rule.semester_id]
        subject = ctx.subjects[rule.subject_id]
        if (
            rule.deleted_at is not None
            or semester is None
            or semester.deleted_at is not None
            or subject is None
            or subject.deleted_at is not None
        ):
            return None

        spec = SemesterSpec(semester.start_date, semester.classes_end, semester.first_week_parity)
        occurrences = expand_class_rule(
            _rule_spec(rule),
            spec,
            ctx.bells[rule.semester_id],
            self.tz,
            days_off=ctx.days_off,
            window=window,
        )
        fields = {
            "kind": EventKind.class_,
            "title": subject.name,
            "is_fixed": True,
            "location": rule.location,
            "color": subject.color,
            "subject_id": subject.id,
            "class_type": rule.class_type,
            "pair_number": rule.pair_number,
            "teacher": rule.teacher,
        }
        return [Desired(o.date, o.start, o.end, fields) for o in occurrences]

    async def sync_class_rules(self, rules: Sequence[ClassRule]) -> SyncStats:
        """Синхронизирует серии правил пар (удалённые правила — убирает)."""
        total = SyncStats()
        if not rules:
            return total
        ctx = _ClassContext(await self._days_off())
        for rule in rules:
            desired = await self._rule_desired(rule, DateRange(self.today, date.max), ctx)
            if desired is None:
                await self.remove_series(rule)
                continue
            stats = await self.sync_series(TemplateType.class_rule, rule.id, desired)
            total = SyncStats(
                total.created + stats.created,
                total.updated + stats.updated,
                total.deleted + stats.deleted,
            )
        return total

    async def sync_semester(self, semester_id: uuid.UUID) -> SyncStats:
        rules = await self._live_rules(ClassRule.semester_id == semester_id)
        return await self.sync_class_rules(rules)

    async def sync_subject(self, subject: Subject) -> SyncStats:
        stats = await self.sync_class_rules(
            await self._live_rules(ClassRule.subject_id == subject.id)
        )
        # Название и цвет предмета обновляются и у правленных руками вхождений
        await self.db.execute(
            update(Event)
            .where(
                Event.user_id == self.user_id,
                Event.subject_id == subject.id,
                Event.kind == EventKind.class_,
                Event.detached.is_(True),
                Event.occurrence_date >= self.today,
                Event.deleted_at.is_(None),
            )
            .values(title=subject.name, color=subject.color)
        )
        return stats

    async def sync_all_class_rules(self) -> SyncStats:
        """Праздники влияют на все семестры."""
        return await self.sync_class_rules(await self._live_rules())

    # ---------- личные повторы ----------

    @property
    def horizon(self) -> date:
        return self.today + timedelta(days=RECURRING_HORIZON_DAYS)

    def _recurring_desired(self, rec: RecurringEvent, window: DateRange) -> list[Desired]:
        occurrences = expand_rrule(
            rec.rrule,
            dtstart=rec.start_date,
            start_time=rec.start_time,
            end_time=rec.end_time,
            tz=self.tz,
            window=window,
            until=rec.until,
            key=rec.id,
        )
        fields = {
            "kind": rec.kind,
            "title": rec.title,
            "is_fixed": True,
            "location": rec.location,
            "color": rec.color,
        }
        return [Desired(o.date, o.start, o.end, fields) for o in occurrences]

    async def sync_recurring(self, rec: RecurringEvent) -> SyncStats:
        """Вхождения повтора на [сегодня, сегодня + 90 дней]."""
        if rec.deleted_at is not None:
            await self.remove_series(rec)
            return SyncStats()
        return await self.sync_series(
            TemplateType.recurring,
            rec.id,
            self._recurring_desired(rec, DateRange(self.today, self.horizon)),
            until=self.horizon,
        )

    async def roll_recurring(self) -> int:
        """Докатывает окно всех повторов пользователя. Возвращает число созданных вхождений."""
        rows = await self.db.scalars(
            select(RecurringEvent).where(
                RecurringEvent.user_id == self.user_id, RecurringEvent.deleted_at.is_(None)
            )
        )
        created = 0
        for rec in rows:
            created += (await self.sync_recurring(rec)).created
        return created


def _items(target: Desired) -> list[tuple[str, Any]]:
    return [(name, target.fields[name]) for name in _TEMPLATE_FIELDS if name in target.fields]


def _rule_spec(rule: ClassRule) -> ClassRuleSpec:
    return ClassRuleSpec(
        key=rule.id,
        weekday=rule.weekday,
        parity=rule.parity,
        pair_number=rule.pair_number,
        start_time=rule.start_time,
        end_time=rule.end_time,
        valid_from=rule.valid_from,
        valid_to=rule.valid_to,
    )


async def roll_all_users(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Ночная джоба: докатывает окно личных повторов у всех пользователей."""
    users = list(await db.scalars(select(User).where(User.deleted_at.is_(None))))
    created = 0
    for user in users:
        created += await SeriesSync(db, user.id, get_tz(user.timezone), now=now).roll_recurring()
    await db.commit()
    return created
