"""Долгий ящик в плане (M11.2–M11.3): неделя, окна по условиям, приоритет, выбор дел.

В план попадают только дела, «взятые на неделю» (`planned_week` — понедельник).
Условия-чипы превращаются в окна: «в будни днём» — Пн–Пт 9–18, «часы
учреждений» — окна типа «учреждения»; «в дни пар» — ограничение по датам (его
считает сервис по расписанию), «нужен ноутбук» время не ограничивает.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, time, timedelta

from app.domain.enums import BacklogCondition
from app.domain.planner import Window

WEEKDAY_DAYTIME = (Window(frozenset({1, 2, 3, 4, 5}), time(9), time(18)),)
DAY = 24 * 60
WEEK = 7 * DAY
# Оценка дела без оценки
DEFAULT_ESTIMATE_MIN = 60
# Приоритет растёт на 1 за неделю ожидания, но не больше чем на столько
MAX_AGE_BONUS = 4
# Желаемый срок в пределах недели — вперёд
DESIRED_BONUS = 3
DESIRED_SOON = timedelta(days=7)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def review_week(today: date) -> date:
    """Неделя, которую планирует недельный разбор: в Сб/Вс — следующая, иначе текущая."""
    start = week_start(today)
    return start + timedelta(days=7) if today.isoweekday() >= 6 else start


# ---------- окна ----------

Interval = tuple[int, int]  # минуты от начала недели (Пн 00:00), [lo, hi)


def week_intervals(windows: Iterable[Window]) -> list[Interval]:
    """Окна → интервалы недели; через полночь Вс → Пн переносится в начало недели."""
    result: list[Interval] = []
    for w in windows:
        start = w.start.hour * 60 + w.start.minute
        end = w.end.hour * 60 + w.end.minute
        if end <= start:
            end += DAY
        for d in w.weekdays:
            lo, hi = (d - 1) * DAY + start, (d - 1) * DAY + end
            if hi > WEEK:
                result += [(lo, WEEK), (0, hi - WEEK)]
            else:
                result.append((lo, hi))
    return merge(result)


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    result: list[Interval] = []
    for lo, hi in sorted(i for i in intervals if i[0] < i[1]):
        if result and lo <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], hi))
        else:
            result.append((lo, hi))
    return result


def _intersect(a: Sequence[Interval], b: Sequence[Interval]) -> list[Interval]:
    result: list[Interval] = []
    i = j = 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if lo < hi:
            result.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return result


def _windows(intervals: Iterable[Interval]) -> tuple[Window, ...]:
    """Интервалы недели → окна, по кусочку на день (одинаковые часы — одним окном)."""
    by_hours: dict[tuple[int, int], set[int]] = defaultdict(set)
    for lo, hi in intervals:
        while lo < hi:
            day_end = (lo // DAY + 1) * DAY
            piece_hi = min(hi, day_end)
            by_hours[(lo % DAY, piece_hi - lo // DAY * DAY)].add(lo // DAY + 1)
            lo = piece_hi
    result = []
    for (start, end), days in sorted(by_hours.items()):
        end_time = time(0) if end == DAY else time(end // 60, end % 60)
        result.append(Window(frozenset(days), time(start // 60, start % 60), end_time))
    return tuple(sorted(result, key=lambda w: (min(w.weekdays), w.start, w.end)))


def intersect_windows(a: Sequence[Window], b: Sequence[Window]) -> tuple[Window, ...]:
    """Время, когда открыты оба набора окон."""
    return _windows(_intersect(week_intervals(a), week_intervals(b)))


def condition_windows(
    base: Sequence[Window],
    conditions: Iterable[str],
    institution: Sequence[Window] = (),
) -> tuple[Window, ...]:
    """Окна дела с учётом чипов. `base` — своё окно дела, окно его типа действия
    или рабочие часы; `institution` — окна типа «учреждения»."""
    result: Sequence[Window] = base
    conditions = set(conditions)
    if BacklogCondition.weekday_daytime in conditions:
        result = intersect_windows(result, WEEKDAY_DAYTIME)
    if BacklogCondition.institution_hours in conditions and institution:
        result = intersect_windows(result, institution)
    return tuple(result)


# ---------- приоритет и выбор ----------


@dataclass(frozen=True)
class Candidate:
    id: object
    created: date
    desired_by: date | None = None
    planned_week: date | None = None


def priority(created: date, desired_by: date | None, today: date) -> int:
    """Вес дела в планировщике: растёт с возрастом, желаемый срок скоро — вперёд."""
    age_bonus = min(max((today - created).days, 0) // 7, MAX_AGE_BONUS)
    soon = desired_by is not None and desired_by <= today + DESIRED_SOON
    return 1 + age_bonus + (DESIRED_BONUS if soon else 0)


def rank_key(c: Candidate, week: date) -> tuple:
    """Порядок предложений: не сделанное на прошлых неделях → с желаемым сроком
    (ближе — раньше) → самые старые."""
    carried = c.planned_week is not None and c.planned_week < week
    return (
        not carried,
        c.desired_by is None,
        c.desired_by or date.max,
        c.created,
        str(c.id),
    )


def suggest(candidates: Iterable[Candidate], week: date, limit: int) -> list[Candidate]:
    """1–N дел на неделю `week`. Уже взятые на эту неделю не предлагаются заново."""
    pool = [c for c in candidates if c.planned_week != week]
    return sorted(pool, key=lambda c: rank_key(c, week))[: max(limit, 0)]
