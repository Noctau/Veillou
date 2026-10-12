"""Режимы дня (Part 2, M18): CRUD режимов и правил, сид «Будни / Выходные» и
загрузка режимов на отрезок дат для планировщика, напоминаний и «Есть время».

Разрешение — чистое (`domain/dayprofile.py`); здесь только данные: режимы по
позиции, правила, типы занятости событий по датам начала (для `event_day` и
`day_after`). Нет ни одного режима — встроенный дефолт.
"""

import uuid
from collections import defaultdict
from datetime import date, time, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError, format_validation_error
from app.core.time import get_tz, local_date, wall_to_utc
from app.domain import dayprofile
from app.domain.dayprofile import Days, Profile, Rule
from app.domain.enums import DayRuleKind, EventKind, EventStatus
from app.models import DayProfile, DayProfileRule, Event, EventType, User
from app.schemas.day_profile import (
    DayProfileCreate,
    DayProfileDay,
    DayProfileRead,
    DayProfileRuleCreate,
    DayProfileRuleUpdate,
    DayProfileUpdate,
    SpanRead,
)
from app.services.base import UserScopedRepository, validate_patch

MAX_DAYS = 93
EVENT_KINDS = (DayRuleKind.event_day, DayRuleKind.day_after)


class ProfileRepo(UserScopedRepository[DayProfile]):
    model = DayProfile
    not_found_message = "Режим дня не найден"


class RuleRepo(UserScopedRepository[DayProfileRule]):
    model = DayProfileRule
    not_found_message = "Правило не найдено"


class _EventTypeRepo(UserScopedRepository[EventType]):
    model = EventType
    not_found_message = "Тип занятости не найден"


# ---------- модель ↔ домен ----------


def _span(raw: dict[str, Any]) -> tuple[time, time]:
    return time.fromisoformat(raw["start"]), time.fromisoformat(raw["end"])


def to_profile(p: DayProfile) -> Profile:
    lunch = (p.lunch_start, p.lunch_end) if p.lunch_start and p.lunch_end else None
    return Profile(
        id=p.id,
        name=p.name,
        wake=p.wake,
        sleep=p.sleep,
        lunch=lunch,
        work=tuple(_span(w) for w in p.work_windows or ()),
        rest_evening_ok=p.rest_evening_ok,
        rest_halfday_ok=p.rest_halfday_ok,
        quiet_follows_sleep=p.quiet_follows_sleep,
    )


def to_rule(r: DayProfileRule) -> Rule:
    return Rule(
        profile_id=r.profile_id,
        kind=DayRuleKind(r.kind),
        position=r.position,
        date_from=r.date_from,
        date_to=r.date_to,
        event_type_id=r.event_type_id,
        weekdays=frozenset(r.weekdays or ()),
    )


def profile_read(p: DayProfile) -> DayProfileRead:
    lunch = (
        SpanRead(start=p.lunch_start, end=p.lunch_end) if p.lunch_start and p.lunch_end else None
    )
    return DayProfileRead(
        id=p.id,
        key=p.key,
        name=p.name,
        wake=p.wake,
        sleep=p.sleep,
        lunch=lunch,
        work_windows=[SpanRead(start=s, end=e) for s, e in map(_span, p.work_windows or ())],
        rest_evening_ok=p.rest_evening_ok,
        rest_halfday_ok=p.rest_halfday_ok,
        quiet_follows_sleep=p.quiet_follows_sleep,
        position=p.position,
    )


def _windows_json(data: DayProfileCreate) -> list[dict[str, str]]:
    return [
        {"start": w.start.strftime("%H:%M"), "end": w.end.strftime("%H:%M")}
        for w in data.work_windows
    ]


def _apply(p: DayProfile, data: DayProfileCreate) -> None:
    p.name = data.name
    p.wake, p.sleep = data.wake, data.sleep
    p.lunch_start = data.lunch.start if data.lunch else None
    p.lunch_end = data.lunch.end if data.lunch else None
    p.work_windows = _windows_json(data)
    p.rest_evening_ok = data.rest_evening_ok
    p.rest_halfday_ok = data.rest_halfday_ok
    p.quiet_follows_sleep = data.quiet_follows_sleep


# ---------- сид ----------


def _seed_values(p: Profile) -> dict[str, Any]:
    return {
        "name": p.name,
        "wake": p.wake,
        "sleep": p.sleep,
        "lunch_start": p.lunch[0] if p.lunch else None,
        "lunch_end": p.lunch[1] if p.lunch else None,
        "work_windows": [
            {"start": s.strftime("%H:%M"), "end": e.strftime("%H:%M")} for s, e in p.work
        ],
        "rest_evening_ok": p.rest_evening_ok,
        "rest_halfday_ok": p.rest_halfday_ok,
        "quiet_follows_sleep": p.quiet_follows_sleep,
    }


SEED = (
    ("weekdays", dayprofile.FALLBACK_WEEKDAYS, dayprofile.WEEKDAYS),
    ("weekends", dayprofile.FALLBACK_WEEKENDS, dayprofile.WEEKENDS),
)


async def ensure_day_profiles(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """«Будни» (Пн–Пт) и «Выходные» (Сб–Вс) новому пользователю — если режимов у него
    ещё не было никогда (удалённые тоже считаются). Не коммитит."""
    seeded = await db.scalar(select(DayProfile.id).where(DayProfile.user_id == user_id).limit(1))
    if seeded is not None:
        return False
    for i, (key, profile, weekdays) in enumerate(SEED):
        row = DayProfile(user_id=user_id, key=key, position=i, **_seed_values(profile))
        db.add(row)
        await db.flush()
        db.add(
            DayProfileRule(
                user_id=user_id,
                profile_id=row.id,
                kind=DayRuleKind.weekdays,
                weekdays=sorted(weekdays),
                position=i,
            )
        )
    await db.flush()
    return True


# ---------- режимы на отрезок дат ----------


async def load_days(db: AsyncSession, user: User, start: date, end: date) -> Days:
    """Режимы дат [start, end] (включительно)."""
    tz = get_tz(user.timezone)
    profiles = list(
        await db.scalars(
            select(DayProfile)
            .where(DayProfile.user_id == user.id, DayProfile.deleted_at.is_(None))
            .order_by(DayProfile.position, DayProfile.created_at, DayProfile.id)
        )
    )
    rules = [
        to_rule(r)
        for r in await db.scalars(
            select(DayProfileRule).where(
                DayProfileRule.user_id == user.id, DayProfileRule.deleted_at.is_(None)
            )
        )
    ]
    events_by_date: dict[date, set[uuid.UUID]] = defaultdict(set)
    types = {
        r.event_type_id for r in rules if r.kind in EVENT_KINDS and r.event_type_id is not None
    }
    if types:
        lo = wall_to_utc(start - timedelta(days=1), time(0), tz)
        hi = wall_to_utc(end + timedelta(days=1), time(0), tz)
        rows = await db.execute(
            select(Event.start, Event.event_type_id).where(
                Event.user_id == user.id,
                Event.deleted_at.is_(None),
                Event.kind == EventKind.busy,
                Event.status != EventStatus.cancelled,
                Event.event_type_id.in_(types),
                Event.start >= lo,
                Event.start < hi,
            )
        )
        for moment, type_id in rows.all():
            if type_id is not None:
                events_by_date[local_date(moment, tz)].add(type_id)
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    return dayprofile.assign(dates, [to_profile(p) for p in profiles], rules, events_by_date, tz)


# ---------- CRUD ----------


class DayProfileService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.profiles = ProfileRepo(db, user.id)
        self.rules = RuleRepo(db, user.id)
        self.event_types = _EventTypeRepo(db, user.id)

    async def list_profiles(self) -> list[DayProfile]:
        return await self.profiles.find_all(
            order_by=[DayProfile.position, DayProfile.created_at, DayProfile.id]
        )

    async def create(self, data: DayProfileCreate) -> DayProfile:
        position = await self.db.scalar(
            select(func.coalesce(func.max(DayProfile.position) + 1, 0)).where(
                DayProfile.user_id == self.user_id, DayProfile.deleted_at.is_(None)
            )
        )
        profile = DayProfile(key=None, position=position or 0)
        _apply(profile, data)
        self.profiles.add(profile)
        await self.db.commit()
        return profile

    async def update(self, id: uuid.UUID, patch: DayProfileUpdate) -> DayProfile:
        profile = await self.profiles.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name, value in changes.items():
            if value is None and name != "lunch":
                raise InvalidDataError(f"{name}: не может быть пустым")
        current = profile_read(profile).model_dump(exclude={"id", "key", "position"})
        current.update(changes)
        current.pop("position", None)
        try:
            data = DayProfileCreate.model_validate(current)
        except ValidationError as exc:
            raise InvalidDataError(format_validation_error(exc)) from exc
        _apply(profile, data)
        if patch.position is not None:
            profile.position = patch.position
        await self.db.commit()
        return profile

    async def delete(self, id: uuid.UUID) -> None:
        profile = await self.profiles.get_or_404(id)
        for rule in await self.rules.find_all(DayProfileRule.profile_id == id):
            self.rules.soft_delete(rule)
        self.profiles.soft_delete(profile)
        await self.db.commit()

    # ---------- правила ----------

    async def list_rules(self) -> list[DayProfileRule]:
        return await self.rules.find_all(
            order_by=[DayProfileRule.position, DayProfileRule.created_at, DayProfileRule.id]
        )

    async def _check_refs(self, data: DayProfileRuleCreate) -> None:
        await self.profiles.get_or_404(data.profile_id)
        if data.event_type_id is not None:
            await self.event_types.get_or_404(data.event_type_id)

    async def create_rule(self, data: DayProfileRuleCreate) -> DayProfileRule:
        await self._check_refs(data)
        position = await self.db.scalar(
            select(func.coalesce(func.max(DayProfileRule.position) + 1, 0)).where(
                DayProfileRule.user_id == self.user_id, DayProfileRule.deleted_at.is_(None)
            )
        )
        rule = DayProfileRule(**data.model_dump(), position=position or 0)
        self.rules.add(rule)
        await self.db.commit()
        return rule

    async def update_rule(self, id: uuid.UUID, patch: DayProfileRuleUpdate) -> DayProfileRule:
        rule = await self.rules.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name in ("profile_id", "kind", "weekdays", "position"):
            if name in changes and changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        data = validate_patch(rule, patch, DayProfileRuleCreate)
        await self._check_refs(data)
        for name, value in data.model_dump().items():
            setattr(rule, name, value)
        if patch.position is not None:
            rule.position = patch.position
        await self.db.commit()
        return rule

    async def delete_rule(self, id: uuid.UUID) -> None:
        rule = await self.rules.get_or_404(id)
        self.rules.soft_delete(rule)
        await self.db.commit()

    # ---------- по датам ----------

    async def days(self, start: date, end: date) -> list[DayProfileDay]:
        if end < start or (end - start).days >= MAX_DAYS:
            raise InvalidDataError(f"Отрезок — от 1 до {MAX_DAYS} дней")
        days = await load_days(self.db, self.user, start, end)
        pinned = await self._pinned(start, end)
        result = []
        for d, p in days.by_date.items():
            own = isinstance(p.id, uuid.UUID)
            result.append(
                DayProfileDay(
                    date=d, profile_id=p.id if own else None, name=p.name, pinned=d in pinned
                )
            )
        return result

    async def _single_day_rules(self, day: date) -> list[DayProfileRule]:
        return await self.rules.find_all(
            DayProfileRule.kind == DayRuleKind.dates,
            DayProfileRule.date_from == day,
            DayProfileRule.date_to == day,
        )

    async def _pinned(self, start: date, end: date) -> set[date]:
        rows = await self.rules.find_all(
            DayProfileRule.kind == DayRuleKind.dates,
            DayProfileRule.date_from == DayProfileRule.date_to,
            DayProfileRule.date_from >= start,
            DayProfileRule.date_from <= end,
        )
        return {r.date_from for r in rows if r.date_from}

    async def set_day(self, day: date, profile_id: uuid.UUID | None) -> DayProfileDay:
        """Режим одной даты: правило «на эту дату» заменяется (null — снимается)."""
        for rule in await self._single_day_rules(day):
            self.rules.soft_delete(rule)
        if profile_id is not None:
            await self.profiles.get_or_404(profile_id)
            self.rules.add(
                DayProfileRule(
                    profile_id=profile_id,
                    kind=DayRuleKind.dates,
                    date_from=day,
                    date_to=day,
                    weekdays=[],
                    position=0,
                )
            )
        await self.db.commit()
        return (await self.days(day, day))[0]
