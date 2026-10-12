"""Правила расписания → вхождения (Part 2, M17.3). Чистые функции, без БД.

- `expand_rule` — вхождения одного правила: паттерн (по дням недели с маской
  недель цикла, смены «N через M», RRULE, разово), время настенное или из слотов
  сетки, границы периода и срока действия правила, паузы периода, исключения.
- `rrule_dates` — только даты RRULE (регулярные задачи: «встреча по чт»).

Вхождение идентифицируется (ключ правила, локальная дата начала) — на этом
держится материализация: перенесённое вручную вхождение не создаётся заново.

Неделя цикла: неделя (Пн–Вс), в которую попадает начало периода, получает
`first_cycle_week`, дальше номера идут по кругу 1…`cycle_weeks` каждую неделю —
в т. ч. через Новый год, независимо от номеров ISO-недель. Цикл 2 — бывшие
числитель (1) и знаменатель (2).

Защита от «невозможных» правил: генерация идёт только в ограниченном окне
(не длиннее `MAX_SPAN_DAYS`) и обрывается на `MAX_OCCURRENCES` вхождениях.
"""

from collections.abc import Hashable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule, rrulestr

from app.core.time import wall_to_utc

# Окно генерации и число вхождений одного правила — с запасом на годовой период
MAX_SPAN_DAYS = 800
MAX_OCCURRENCES = 1500
# Смена «N через M»: цикл не длиннее года
MAX_DAY_CYCLE = 366
MAX_CYCLE_WEEKS = 8
# Якорь RRULE без даты начала: от него считаются INTERVAL и т. п. (понедельник)
DEFAULT_ANCHOR = date(2000, 1, 3)


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
class PeriodSpec:
    start: date
    end: date  # последний день включительно
    cycle_weeks: int = 1
    first_cycle_week: int = 1
    pauses: tuple[DateRange, ...] = ()


@dataclass(frozen=True)
class Slot:
    number: int
    start: time
    end: time


@dataclass(frozen=True)
class SlotGridSpec:
    """Сетка слотов: общие + переопределения по дням недели (ISO 1–7).

    Переопределение заменяет общие слоты для этого дня целиком.
    """

    default: Mapping[int, Slot] = field(default_factory=dict)
    by_weekday: Mapping[int, Mapping[int, Slot]] = field(default_factory=dict)

    @classmethod
    def from_slots(
        cls,
        default: Iterable[Slot],
        by_weekday: Mapping[int, Iterable[Slot]] | None = None,
    ) -> "SlotGridSpec":
        return cls(
            default={s.number: s for s in default},
            by_weekday={
                wd: {s.number: s for s in slots} for wd, slots in (by_weekday or {}).items()
            },
        )

    def slot(self, weekday: int, number: int) -> Slot | None:
        return self.by_weekday.get(weekday, self.default).get(number)


# ---------- паттерны ----------


@dataclass(frozen=True)
class WeeklyPattern:
    """По дням недели (ISO 1–7). `cycle_weeks` — маска недель цикла периода
    (`{1}` при цикле 2 — бывший числитель); None — каждую неделю."""

    weekdays: frozenset[int]
    cycle_weeks: frozenset[int] | None = None


@dataclass(frozen=True)
class DayCyclePattern:
    """Смены: `on` дней подряд, затем `off` дней перерыва; `anchor` — первый день `on`."""

    on: int
    off: int
    anchor: date


@dataclass(frozen=True)
class RRulePattern:
    rrule: str  # без DTSTART и времени: «FREQ=MONTHLY;BYDAY=2TU»


@dataclass(frozen=True)
class OncePattern:
    date: date


Pattern = WeeklyPattern | DayCyclePattern | RRulePattern | OncePattern


@dataclass(frozen=True)
class RuleSpec:
    key: Hashable  # id правила
    pattern: Pattern
    # Время: настенное (end <= start — через полночь) или слоты сетки
    start_time: time | None = None
    end_time: time | None = None
    slot_from: int | None = None
    slot_to: int | None = None  # None — как slot_from
    valid_from: date | None = None
    valid_to: date | None = None


@dataclass(frozen=True)
class Occurrence:
    key: Hashable  # ключ правила
    date: date  # локальная дата начала вхождения по правилу
    start: datetime  # UTC
    end: datetime  # UTC
    slot: int | None = None


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def cycle_week(d: date, period: PeriodSpec) -> int:
    """Номер недели цикла (1…cycle_weeks) для даты `d`."""
    if period.cycle_weeks <= 1:
        return 1
    weeks = (week_monday(d) - week_monday(period.start)).days // 7
    return (period.first_cycle_week - 1 + weeks) % period.cycle_weeks + 1


def validate_pattern(pattern: Pattern) -> None:
    """Бросает ValueError на заведомо невозможный паттерн."""
    match pattern:
        case WeeklyPattern(weekdays=days, cycle_weeks=mask):
            if not days or not days <= set(range(1, 8)):
                raise ValueError("Укажите дни недели")
            if mask is not None and (not mask or not mask <= set(range(1, MAX_CYCLE_WEEKS + 1))):
                raise ValueError("Некорректные недели цикла")
        case DayCyclePattern(on=on, off=off):
            if on < 1 or off < 0 or on + off > MAX_DAY_CYCLE:
                raise ValueError("Смены: от 1 рабочего дня, цикл не длиннее года")
        case RRulePattern(rrule=value):
            parse_rrule(value)
        case OncePattern():
            pass


# ---------- генерация ----------


def _wall_interval(d: date, start: time, end: time, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Настенный интервал в день `d` → UTC. end <= start — конец на следующий день."""
    end_day = d if end > start else d + timedelta(days=1)
    return wall_to_utc(d, start, tz), wall_to_utc(end_day, end, tz)


def _times(rule: RuleSpec, weekday: int, grid: SlotGridSpec | None) -> tuple[time, time] | None:
    if rule.start_time is not None and rule.end_time is not None:
        return rule.start_time, rule.end_time
    if rule.slot_from is None or grid is None:
        return None
    first = grid.slot(weekday, rule.slot_from)
    last = grid.slot(weekday, rule.slot_to or rule.slot_from)
    if first is None or last is None or last.end <= first.start:
        return None
    return first.start, last.end


def _span(rule: RuleSpec, window: DateRange, period: PeriodSpec | None) -> DateRange | None:
    span: DateRange | None = window
    if period is not None:
        span = DateRange(period.start, period.end).intersect(window)
    if span is not None and (rule.valid_from or rule.valid_to):
        span = span.intersect(DateRange(rule.valid_from or date.min, rule.valid_to or date.max))
    if span is not None and (span.end - span.start).days > MAX_SPAN_DAYS:
        span = DateRange(span.start, span.start + timedelta(days=MAX_SPAN_DAYS))
    return span


def _dates(rule: RuleSpec, span: DateRange, period: PeriodSpec | None) -> Iterator[date]:
    """Даты паттерна в `span` по порядку (без пауз и исключений)."""
    match rule.pattern:
        case WeeklyPattern(weekdays=days, cycle_weeks=mask):
            cycle = period or PeriodSpec(span.start, span.end)
            for d in span.days():
                if d.isoweekday() in days and (mask is None or cycle_week(d, cycle) in mask):
                    yield d
        case DayCyclePattern(on=on, off=off, anchor=anchor):
            length = on + off
            for d in span.days():
                if (d - anchor).days % length < on:
                    yield d
        case RRulePattern(rrule=value):
            dtstart = rule.valid_from or (period.start if period else DEFAULT_ANCHOR)
            parsed = parse_rrule(value).replace(dtstart=datetime.combine(dtstart, time(0)))
            # Наивная полночь — только носитель даты для dateutil
            for dt in parsed.xafter(datetime.combine(span.start, time(0)), inc=True):
                if dt.date() > span.end:
                    return
                yield dt.date()
        case OncePattern(date=d):
            if d in span:
                yield d


def expand_rule(
    rule: RuleSpec,
    *,
    tz: ZoneInfo,
    window: DateRange,
    period: PeriodSpec | None = None,
    grid: SlotGridSpec | None = None,
    days_off: Sequence[DateRange] = (),
) -> list[Occurrence]:
    """Вхождения правила в `window` ∩ период ∩ срок действия правила.

    Паузы периода и `days_off` вхождений не дают. День, на который у слота нет
    времени (номера нет в сетке этого дня), пропускается.
    """
    span = _span(rule, window, period)
    if span is None:
        return []
    skip = (*(period.pauses if period else ()), *days_off)
    result: list[Occurrence] = []
    for d in _dates(rule, span, period):
        if any(d in r for r in skip):
            continue
        times = _times(rule, d.isoweekday(), grid)
        if times is None:
            continue
        start, end = _wall_interval(d, times[0], times[1], tz)
        result.append(Occurrence(rule.key, d, start, end, rule.slot_from))
        if len(result) >= MAX_OCCURRENCES:
            break
    return result


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


def has_occurrences(value: str) -> bool:
    """Есть ли у правила хоть одно вхождение. Для «невозможного» правила
    (30 февраля) dateutil перебирает дни до 9999 года — секунда CPU, поэтому
    вызывать из потока, а не из event loop (`ensure_has_occurrences`)."""
    start = datetime(2000, 1, 1)
    return parse_rrule(value).replace(dtstart=start).after(start, inc=True) is not None


def rrule_dates(
    value: str, *, dtstart: date, window: DateRange, until: date | None = None
) -> list[date]:
    """Даты вхождений RRULE в окне `window` (включительно), начиная с `dtstart`."""
    rule = parse_rrule(value).replace(dtstart=datetime.combine(dtstart, time(0)))
    span = DateRange(dtstart, until or date.max).intersect(window)
    if span is None:
        return []
    days = rule.between(
        datetime.combine(span.start, time(0)), datetime.combine(span.end, time(0)), inc=True
    )
    return [d.date() for d in days]
