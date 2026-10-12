"""Режимы дня (Part 2, M18): какой режим у даты и что из него следует. Чисто.

Режим — подъём, отбой, обед, общие рабочие окна и флаги отдыха. Правила назначения
(`Rule`) выбирают режим даты; побеждает более специфичное:

1. `dates` — конкретные даты («завтра — выходной», «отпуск 1–14 августа»);
2. `event_day` — в день, когда начинается событие типа X, и `day_after` — на
   следующий день после начала события типа X («после ночной смены»). Между
   собой — по позиции правила;
3. `weekdays` — по дням недели;
4. иначе — первый режим (по позиции), а без режимов вовсе — встроенный дефолт
   (`FALLBACK_WEEKDAYS` / `FALLBACK_WEEKENDS`, настройки Part 1).

Внутри одного уровня выигрывает правило с меньшей позицией, а среди дат — самое
узкое: «сегодня — выходной» внутри «отпуска 1–14 августа» побеждает отпуск.

Сутки режима: день начинается с подъёма своего режима и длится до подъёма
следующего; сон — от своего отбоя до подъёма следующего дня. Поэтому ночь после
ночной смены относится к предыдущему дню, а поздний подъём «после ночной»
(15:00) просто сдвигает начало дня. Отбой не позже подъёма (`sleep <= wake`) —
после полуночи, на следующую дату.
"""

from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.time import wall_to_utc
from app.domain.enums import DayRuleKind
from app.domain.planner.contracts import DaySpec

ProfileId = Hashable
WallRange = tuple[time, time]

WEEKDAYS = frozenset({1, 2, 3, 4, 5})
WEEKENDS = frozenset({6, 7})
# Приоритет уровня правила (меньше — сильнее)
LEVEL = {
    DayRuleKind.dates: 0,
    DayRuleKind.event_day: 1,
    DayRuleKind.day_after: 1,
    DayRuleKind.weekdays: 2,
}


@dataclass(frozen=True)
class Profile:
    id: ProfileId
    name: str
    wake: time
    sleep: time  # отбой; не позже подъёма — после полуночи
    lunch: WallRange | None = None
    # Общие окна для дел; end <= start — до следующего дня
    work: tuple[WallRange, ...] = ()
    rest_evening_ok: bool = True
    rest_halfday_ok: bool = False
    # Тихие часы этого дня — сон режима (иначе — общие тихие часы из настроек)
    quiet_follows_sleep: bool = True


@dataclass(frozen=True)
class Rule:
    profile_id: ProfileId
    kind: DayRuleKind
    position: int = 0
    # dates: [date_from, date_to] включительно
    date_from: date | None = None
    date_to: date | None = None
    # event_day / day_after
    event_type_id: Hashable | None = None
    # weekdays: ISO 1–7
    weekdays: frozenset[int] = frozenset()


# Настройки Part 1 по умолчанию: будни 9–21, выходные 11–19, сон 23:30–7:30, обед 13–14
FALLBACK_WEEKDAYS = Profile(
    id="fallback:weekdays",
    name="Будни",
    wake=time(7, 30),
    sleep=time(23, 30),
    lunch=(time(13, 0), time(14, 0)),
    work=((time(9, 0), time(21, 0)),),
)
FALLBACK_WEEKENDS = Profile(
    id="fallback:weekends",
    name="Выходные",
    wake=time(7, 30),
    sleep=time(23, 30),
    lunch=(time(13, 0), time(14, 0)),
    work=((time(11, 0), time(19, 0)),),
    rest_halfday_ok=True,
)


def fallback(day: date) -> Profile:
    """Встроенный режим, когда у пользователя нет ни одного своего."""
    return FALLBACK_WEEKENDS if day.isoweekday() in WEEKENDS else FALLBACK_WEEKDAYS


def _matches(rule: Rule, day: date, events_by_date: Mapping[date, Iterable[Hashable]]) -> bool:
    if rule.kind == DayRuleKind.dates:
        lo = rule.date_from
        hi = rule.date_to or lo
        return lo is not None and hi is not None and lo <= day <= hi
    if rule.kind == DayRuleKind.event_day:
        return rule.event_type_id in set(events_by_date.get(day, ()))
    if rule.kind == DayRuleKind.day_after:
        return rule.event_type_id in set(events_by_date.get(day - timedelta(days=1), ()))
    if rule.kind == DayRuleKind.weekdays:
        return day.isoweekday() in rule.weekdays
    return False


def resolve(
    day: date,
    rules: Sequence[Rule],
    events_by_date: Mapping[date, Iterable[Hashable]],
    default: ProfileId | None = None,
) -> ProfileId | None:
    """id режима даты.

    `events_by_date` — типы занятости событий, начинающихся в эту (локальную) дату.
    Ни одно правило не подошло — `default` (первый режим пользователя; None — встроенный).
    """
    best: tuple[int, int, int] | None = None
    result = default
    for rule in rules:
        if not _matches(rule, day, events_by_date):
            continue
        span = 0
        if rule.kind == DayRuleKind.dates and rule.date_from and rule.date_to:
            span = (rule.date_to - rule.date_from).days
        rank = (LEVEL[rule.kind], span, rule.position)
        if best is None or rank < best:
            best, result = rank, rule.profile_id
    return result


# ---------- сутки ----------


def _at(day: date, t: time, after: time | None, tz: ZoneInfo) -> datetime:
    """Настенное `t` в день `day`; не позже `after` — уже следующего дня."""
    shift = after is not None and t <= after
    return wall_to_utc(day + timedelta(days=1) if shift else day, t, tz)


def wake_at(day: date, p: Profile, tz: ZoneInfo) -> datetime:
    return wall_to_utc(day, p.wake, tz)


def bedtime(day: date, p: Profile, tz: ZoneInfo) -> datetime:
    """Отбой дня: не позже подъёма — после полуночи."""
    return _at(day, p.sleep, p.wake, tz)


def _range(day: date, r: WallRange, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start, end = r
    return wall_to_utc(day, start, tz), _at(day, end, start, tz)


def day_spec(day: date, p: Profile, tz: ZoneInfo) -> DaySpec:
    return DaySpec(
        date=day,
        wake=wake_at(day, p, tz),
        sleep=bedtime(day, p, tz),
        lunch=_range(day, p.lunch, tz) if p.lunch else None,
        work=tuple(_range(day, w, tz) for w in p.work),
        rest_evening_ok=p.rest_evening_ok,
        rest_halfday_ok=p.rest_halfday_ok,
    )


def fallback_spec(day: date, tz: ZoneInfo) -> DaySpec:
    return day_spec(day, fallback(day), tz)


def sleep_interval(
    day: date, p: Profile, next_p: Profile, tz: ZoneInfo
) -> tuple[datetime, datetime] | None:
    """Сон после дня `day`: от его отбоя до подъёма следующего дня. None — сна нет
    (следующий подъём не позже отбоя)."""
    start = bedtime(day, p, tz)
    end = wake_at(day + timedelta(days=1), next_p, tz)
    return (start, end) if start < end else None


@dataclass(frozen=True)
class Days:
    """Режимы на отрезок дат (результат сервиса, дальше — чистые вычисления)."""

    tz: ZoneInfo
    by_date: Mapping[date, Profile]

    def profile(self, day: date) -> Profile:
        return self.by_date.get(day) or fallback(day)

    def spec(self, day: date) -> DaySpec:
        return day_spec(day, self.profile(day), self.tz)

    def specs(self, dates: Iterable[date]) -> tuple[DaySpec, ...]:
        return tuple(self.spec(d) for d in dates)

    def wake(self, day: date) -> datetime:
        return wake_at(day, self.profile(day), self.tz)

    def bedtime(self, day: date) -> datetime:
        return bedtime(day, self.profile(day), self.tz)

    def sleep(self, day: date) -> tuple[datetime, datetime] | None:
        return sleep_interval(
            day, self.profile(day), self.profile(day + timedelta(days=1)), self.tz
        )


def assign(
    dates: Iterable[date],
    profiles: Sequence[Profile],
    rules: Sequence[Rule],
    events_by_date: Mapping[date, Iterable[Hashable]],
    tz: ZoneInfo,
) -> Days:
    """Режим каждой даты. `profiles` — по позиции: первый — режим по умолчанию."""
    by_id = {p.id: p for p in profiles}
    live = [r for r in rules if r.profile_id in by_id]
    default = profiles[0].id if profiles else None
    result: dict[date, Profile] = {}
    for d in dates:
        pid = resolve(d, live, events_by_date, default)
        result[d] = by_id[pid] if pid in by_id else fallback(d)
    return Days(tz, result)
