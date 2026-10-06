"""Шаблоны → вхождения. Чистые функции, без БД.

- `expand_class_rules` — пары из сетки недели с учётом чётности, звонков,
  срока действия правила, праздников и границ семестра (сессия — без пар).
- `expand_rrule` — личные блоки с RRULE («по Вт, Чт»).

Вхождение идентифицируется (ключ шаблона, локальная дата) — на этом держится
материализация: перенесённое вручную вхождение не создаётся заново.

Чётность: неделя (Пн–Вс), в которую попадает начало семестра, получает
`first_week_parity`, дальше чередуется каждую неделю — в т. ч. через Новый год,
независимо от номеров ISO-недель.
"""

from collections.abc import Hashable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule, rrulestr

from app.core.time import wall_to_utc
from app.domain.enums import Parity, RuleParity


@dataclass(frozen=True)
class DateRange:
    """Диапазон дат включительно."""

    start: date
    end: date

    def __contains__(self, d: object) -> bool:
        return isinstance(d, date) and self.start <= d <= self.end

    def days(self) -> Iterator[date]:
        d = self.start
        while d <= self.end:
            yield d
            d += timedelta(days=1)

    def intersect(self, other: "DateRange") -> "DateRange | None":
        start, end = max(self.start, other.start), min(self.end, other.end)
        return DateRange(start, end) if start <= end else None


@dataclass(frozen=True)
class SemesterSpec:
    start: date
    classes_end: date  # последний день занятий включительно
    first_week_parity: Parity = Parity.odd


@dataclass(frozen=True)
class BellSlot:
    number: int
    start: time
    end: time


@dataclass(frozen=True)
class Bells:
    """Звонки: общие + переопределения по дням недели (ISO 1–7).

    Переопределение заменяет общие звонки для этого дня целиком.
    """

    default: Mapping[int, BellSlot] = field(default_factory=dict)
    by_weekday: Mapping[int, Mapping[int, BellSlot]] = field(default_factory=dict)

    @classmethod
    def from_slots(
        cls,
        default: Iterable[BellSlot],
        by_weekday: Mapping[int, Iterable[BellSlot]] | None = None,
    ) -> "Bells":
        return cls(
            default={s.number: s for s in default},
            by_weekday={
                wd: {s.number: s for s in slots} for wd, slots in (by_weekday or {}).items()
            },
        )

    def slot(self, weekday: int, number: int) -> BellSlot | None:
        return self.by_weekday.get(weekday, self.default).get(number)


@dataclass(frozen=True)
class ClassRuleSpec:
    key: Hashable  # id правила
    weekday: int  # ISO: 1 = Пн
    parity: RuleParity = RuleParity.all
    pair_number: int | None = None
    start_time: time | None = None  # своё время вместо звонков
    end_time: time | None = None
    valid_from: date | None = None
    valid_to: date | None = None


@dataclass(frozen=True)
class Occurrence:
    key: Hashable  # ключ шаблона
    date: date  # локальная дата вхождения по шаблону
    start: datetime  # UTC
    end: datetime  # UTC
    pair_number: int | None = None


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_parity(d: date, semester_start: date, first_week_parity: Parity) -> Parity:
    weeks = (week_monday(d) - week_monday(semester_start)).days // 7
    if weeks % 2 == 0:
        return first_week_parity
    return Parity.even if first_week_parity == Parity.odd else Parity.odd


def _wall_interval(d: date, start: time, end: time, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Настенный интервал в день `d` → UTC. end <= start — конец на следующий день."""
    end_day = d if end > start else d + timedelta(days=1)
    return wall_to_utc(d, start, tz), wall_to_utc(end_day, end, tz)


def _rule_times(rule: ClassRuleSpec, bells: Bells) -> tuple[time, time] | None:
    if rule.start_time is not None and rule.end_time is not None:
        return rule.start_time, rule.end_time
    if rule.pair_number is None:
        return None
    slot = bells.slot(rule.weekday, rule.pair_number)
    return (slot.start, slot.end) if slot else None


def _is_day_off(d: date, days_off: Sequence[DateRange]) -> bool:
    return any(d in r for r in days_off)


def expand_class_rule(
    rule: ClassRuleSpec,
    semester: SemesterSpec,
    bells: Bells,
    tz: ZoneInfo,
    *,
    days_off: Sequence[DateRange] = (),
    window: DateRange | None = None,
) -> list[Occurrence]:
    """Все вхождения правила пары в семестре (или в пересечении с `window`).

    Пара без времени (номер пары, которого нет в звонках этого дня) не даёт вхождений.
    """
    times = _rule_times(rule, bells)
    if times is None:
        return []

    span: DateRange | None = DateRange(semester.start, semester.classes_end)
    if rule.valid_from or rule.valid_to:
        span = span.intersect(DateRange(rule.valid_from or date.min, rule.valid_to or date.max))
    if span is not None and window is not None:
        span = span.intersect(window)
    if span is None:
        return []

    # Первый нужный день недели внутри диапазона
    d = span.start + timedelta(days=(rule.weekday - span.start.isoweekday()) % 7)
    result: list[Occurrence] = []
    while d <= span.end:
        parity_ok = rule.parity == RuleParity.all or (
            week_parity(d, semester.start, semester.first_week_parity) == rule.parity
        )
        if parity_ok and not _is_day_off(d, days_off):
            start, end = _wall_interval(d, times[0], times[1], tz)
            result.append(Occurrence(rule.key, d, start, end, rule.pair_number))
        d += timedelta(days=7)
    return result


def expand_class_rules(
    rules: Iterable[ClassRuleSpec],
    semester: SemesterSpec,
    bells: Bells,
    tz: ZoneInfo,
    *,
    days_off: Sequence[DateRange] = (),
    window: DateRange | None = None,
) -> list[Occurrence]:
    """Вхождения всех правил, по времени начала."""
    result = [
        occ
        for rule in rules
        for occ in expand_class_rule(rule, semester, bells, tz, days_off=days_off, window=window)
    ]
    return sorted(result, key=lambda o: (o.start, str(o.key)))


# ---------- RRULE ----------

_ALLOWED_FREQ = {DAILY, WEEKLY, MONTHLY, YEARLY}


def parse_rrule(value: str) -> rrule:
    """Проверяет RRULE («FREQ=WEEKLY;BYDAY=TU,TH»). Бросает ValueError.

    Без DTSTART (начало задаётся отдельно) и без повторов чаще раза в день.
    """
    text = value.strip().removeprefix("RRULE:")
    upper = text.upper()
    if not text or "DTSTART" in upper or "\n" in text:
        raise ValueError("Некорректное правило повтора")
    if any(part in upper for part in ("BYHOUR", "BYMINUTE", "BYSECOND")):
        raise ValueError("Время задаётся отдельно от правила повтора")
    try:
        rule = rrulestr(text, dtstart=datetime(2000, 1, 1))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Некорректное правило повтора: {exc}") from exc
    if not isinstance(rule, rrule) or rule._freq not in _ALLOWED_FREQ:
        raise ValueError("Повтор допускается не чаще раза в день")
    return rule


def expand_rrule(
    value: str,
    *,
    dtstart: date,
    start_time: time,
    end_time: time,
    tz: ZoneInfo,
    window: DateRange,
    until: date | None = None,
    key: Hashable = None,
) -> list[Occurrence]:
    """Вхождения RRULE в окне `window`. Время — настенное в `tz` (DST учитывается).

    `end_time <= start_time` — блок заканчивается на следующий день.
    """
    text = value.strip().removeprefix("RRULE:")
    # Наивная полночь здесь — только носитель даты для dateutil
    rule = parse_rrule(text).replace(dtstart=datetime.combine(dtstart, time(0)))
    span = DateRange(dtstart, until or date.max).intersect(window)
    if span is None:
        return []
    days = rule.between(
        datetime.combine(span.start, time(0)), datetime.combine(span.end, time(0)), inc=True
    )
    result = []
    for dt in days:
        start, end = _wall_interval(dt.date(), start_time, end_time, tz)
        result.append(Occurrence(key, dt.date(), start, end))
    return result
