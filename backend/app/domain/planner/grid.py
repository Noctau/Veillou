"""Сетка времени и доступность блоков.

Время дискретизировано слотами по `grid_min` минут от `t0` (сейчас, округлено
вверх). Интервалы — полуоткрытые `[lo, hi)` в слотах. Свободное время
округляется внутрь (окно 10:35–12:00 → 10:45–12:00), занятое — наружу.

«День» планировщика начинается в момент подъёма (конец сна): блок в 00:30
относится к вечеру предыдущего дня — для лимита учёбы и «≤ 2 подзадач в день».
"""

import bisect
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from app.core.time import ensure_aware, local_date, wall_to_utc
from app.domain.planner.contracts import (
    Block,
    BlockId,
    FixedBlock,
    PlanInput,
    PlanSettings,
    TimeRange,
    Window,
)

Interval = tuple[int, int]

SATURDAY, SUNDAY = 6, 7


# ---------- операции над интервалами ----------


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    """Сортирует и склеивает пересекающиеся и смежные интервалы, пустые выкидывает."""
    result: list[Interval] = []
    for lo, hi in sorted(i for i in intervals if i[0] < i[1]):
        if result and lo <= result[-1][1]:
            if hi > result[-1][1]:
                result[-1] = (result[-1][0], hi)
        else:
            result.append((lo, hi))
    return result


def subtract(base: Iterable[Interval], holes: Iterable[Interval]) -> list[Interval]:
    """`base` минус `holes`. На входе — любые интервалы, на выходе — склеенные."""
    holes = merge(holes)
    result: list[Interval] = []
    for lo, hi in merge(base):
        cur = lo
        i = bisect.bisect_right(holes, (lo, lo)) - 1
        i = max(i, 0)
        while i < len(holes) and holes[i][0] < hi:
            h_lo, h_hi = holes[i]
            if h_hi > cur:
                if h_lo > cur:
                    result.append((cur, min(h_lo, hi)))
                cur = max(cur, h_hi)
            if cur >= hi:
                break
            i += 1
        if cur < hi:
            result.append((cur, hi))
    return result


def intersect(a: Iterable[Interval], b: Iterable[Interval]) -> list[Interval]:
    a, b = merge(a), merge(b)
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


def overlaps(a: Interval, b: Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]


# ---------- сетка ----------


@dataclass(frozen=True)
class Grid:
    t0: datetime  # UTC, кратно шагу
    n: int  # слотов в горизонте
    step_min: int

    @classmethod
    def build(cls, now: datetime, end: datetime, step_min: int) -> "Grid":
        step = step_min * 60
        ts = ensure_aware(now).timestamp()
        t0 = datetime.fromtimestamp(-(-ts // step) * step, UTC)
        n = max(0, int((ensure_aware(end) - t0).total_seconds() // step))
        return cls(t0, n, step_min)

    @property
    def end(self) -> datetime:
        return self.dt(self.n)

    def dt(self, slot: int) -> datetime:
        return self.t0 + timedelta(minutes=slot * self.step_min)

    def floor(self, dt: datetime) -> int:
        return int((ensure_aware(dt) - self.t0).total_seconds() // (self.step_min * 60))

    def ceil(self, dt: datetime) -> int:
        return -int(-(ensure_aware(dt) - self.t0).total_seconds() // (self.step_min * 60))

    def slots(self, minutes: int) -> int:
        """Длительность в слотах, с округлением вверх."""
        return -(-minutes // self.step_min)

    def outer(self, start: datetime, end: datetime) -> Interval:
        """Занятый интервал — наружу, обрезан по горизонту."""
        return max(self.floor(start), 0), min(self.ceil(end), self.n)

    def inner(self, start: datetime, end: datetime) -> Interval:
        """Свободный интервал — внутрь, обрезан по горизонту."""
        return max(self.ceil(start), 0), min(self.floor(end), self.n)


@dataclass(frozen=True)
class Domain:
    """Допустимые старты блока: объединение отрезков `[lo, hi]` включительно."""

    intervals: tuple[tuple[int, int], ...]

    @classmethod
    def of_starts(cls, free: Iterable[Interval], length: int) -> "Domain":
        return cls(tuple((lo, hi - length) for lo, hi in free if hi - lo >= length))

    def __contains__(self, slot: object) -> bool:
        return any(lo <= slot <= hi for lo, hi in self.intervals)  # type: ignore[operator]

    def __bool__(self) -> bool:
        return bool(self.intervals)

    def __iter__(self) -> Iterator[int]:
        for lo, hi in self.intervals:
            yield from range(lo, hi + 1)

    @property
    def size(self) -> int:
        return sum(hi - lo + 1 for lo, hi in self.intervals)

    def flat(self) -> list[int]:
        """Для `cp_model.Domain.FromFlatIntervals`."""
        return [v for pair in self.intervals for v in pair]


@dataclass(frozen=True)
class Day:
    index: int
    date: date
    lo: int
    hi: int


@dataclass(frozen=True)
class RestWindow:
    """Кандидат на отдых: если выбран, гибких блоков в нём нет."""

    lo: int
    hi: int
    week: tuple[int, int]  # ISO (год, неделя)


@dataclass
class PreparedBlock:
    block: Block
    index: int
    dur: int  # слотов
    pad: int  # перерыв после блока, слотов
    split: bool  # можно разрезать на 2 части
    free: list[Interval]  # допустимое время, сегменты не пересекают границу дня
    starts: Domain  # старты целого блока
    latest_end: int  # жёстко: дедлайн или конец горизонта
    due: int | None  # мягко: дедлайн − буфер
    overdue: bool

    @property
    def id(self) -> BlockId:
        return self.block.id

    def part_free(self, min_part: int) -> list[Interval]:
        return [s for s in self.free if s[1] - s[0] >= min_part]


@dataclass
class Prepared:
    inp: PlanInput
    grid: Grid
    days: list[Day]
    blocks: list[PreparedBlock]
    fixed: list[tuple[Interval, FixedBlock]]
    evenings: list[RestWindow]
    halves: list[RestWindow]
    evenings_required: dict[tuple[int, int], int]
    halves_required: dict[tuple[int, int], int]
    min_part: int
    study_limit: int  # слотов в день
    study_limit_by_day: dict[int, int]  # разовые лимиты: день → слотов
    max_per_group: int
    fixed_study: dict[int, int] = field(default_factory=dict)  # день → слотов
    fixed_per_group: dict[tuple[BlockId, int], int] = field(default_factory=dict)
    _day_starts: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._day_starts = [d.lo for d in self.days]
        self.by_id = {pb.id: pb for pb in self.blocks}
        self.fixed_by_id = {f.id: iv for iv, f in self.fixed}

    def day_of(self, slot: int) -> int:
        """Индекс дня, к которому относится слот (-1 — до первого дня)."""
        return bisect.bisect_right(self._day_starts, slot) - 1

    def limit(self, day: int) -> int:
        """Лимит учёбы дня в слотах."""
        return self.study_limit_by_day.get(day, self.study_limit)

    def pad_for(self, length: int) -> int:
        s = self.inp.settings
        return self.grid.slots(s.break_min) if length > self.grid.slots(s.long_block_min) else 0


# ---------- построение ----------


def _dates(grid: Grid, tz) -> list[date]:
    first = local_date(grid.t0, tz) - timedelta(days=1)
    last = local_date(grid.end, tz) + timedelta(days=1)
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def _daily(d: date, start: time, end: time, tz) -> tuple[datetime, datetime]:
    """Ежедневный интервал дня `d`; `end <= start` — до следующего дня."""
    end_date = d + timedelta(days=1) if end <= start else d
    return wall_to_utc(d, start, tz), wall_to_utc(end_date, end, tz)


def _work_windows(s: PlanSettings) -> tuple[Window, ...]:
    def window(days: set[int], r: TimeRange) -> Window:
        return Window(frozenset(days), r.start, r.end)

    return (window({1, 2, 3, 4, 5}, s.work_weekdays), window({6, 7}, s.work_weekends))


def window_slots(
    grid: Grid, windows: Sequence[Window], dates: Sequence[date], tz
) -> list[Interval]:
    return merge(
        grid.inner(*_daily(d, w.start, w.end, tz))
        for d in dates
        for w in windows
        if d.isoweekday() in w.weekdays
    )


def busy_slots(inp: PlanInput, grid: Grid, dates: Sequence[date]) -> list[Interval]:
    """Всё, куда нельзя ставить гибкие блоки: сон, обед, жёсткое, дорога, закреплённое."""
    s, tz = inp.settings, inp.tz
    holes: list[Interval] = []
    for d in dates:
        holes.append(grid.outer(*_daily(d, s.sleep.start, s.sleep.end, tz)))
        if s.lunch:
            holes.append(grid.outer(*_daily(d, s.lunch.start, s.lunch.end, tz)))
    classes_by_date: dict[date, list[tuple[datetime, datetime]]] = defaultdict(list)
    for b in inp.busy:
        holes.append(grid.outer(b.start, b.end))
        if b.is_class:
            classes_by_date[local_date(b.start, tz)].append((b.start, b.end))
    if s.travel_buffer_min > 0:
        buf = timedelta(minutes=s.travel_buffer_min)
        for classes in classes_by_date.values():
            first = min(c[0] for c in classes)
            last = max(c[1] for c in classes)
            holes.append(grid.outer(first - buf, first))
            holes.append(grid.outer(last, last + buf))
    holes.extend(grid.outer(f.start, f.end) for f in inp.fixed)
    return merge(holes)


def _days(grid: Grid, s: PlanSettings, dates: Sequence[date], tz) -> list[Day]:
    days: list[Day] = []
    bounds = [grid.ceil(wall_to_utc(d, s.sleep.end, tz)) for d in dates]
    for d, lo, hi in zip(dates, bounds, bounds[1:], strict=False):
        lo, hi = max(lo, 0), min(hi, grid.n)
        if lo < hi:
            days.append(Day(len(days), d, lo, hi))
    if days and days[0].lo > 0:
        # горизонт начался ночью — хвост «вчера»
        days[0] = Day(0, days[0].date, 0, days[0].hi)
    return days


def _date_of(slot: int, days: Sequence[Day], starts: Sequence[int]) -> date | None:
    i = bisect.bisect_right(starts, slot) - 1
    return days[i].date if i >= 0 else None


def _split_by_days(free: Iterable[Interval], days: Sequence[Day]) -> list[Interval]:
    result: list[Interval] = []
    for lo, hi in free:
        for day in days:
            a, b = max(lo, day.lo), min(hi, day.hi)
            if a < b:
                result.append((a, b))
    return result


def _horizon_end(inp: PlanInput) -> datetime:
    now = ensure_aware(inp.now)
    deadlines = [b.deadline for b in inp.blocks if b.deadline and b.deadline > now]
    end = max(deadlines, default=now)
    return min(
        max(end, now + timedelta(days=inp.min_horizon_days)),
        now + timedelta(days=inp.max_horizon_days),
    )


def _rest_windows(
    inp: PlanInput, grid: Grid, dates: Sequence[date], fixed: Sequence[Interval]
) -> tuple[list[RestWindow], list[RestWindow]]:
    s, tz = inp.settings, inp.tz

    def make(d: date, start: time, end: time) -> RestWindow | None:
        lo, hi = grid.inner(*_daily(d, start, end, tz))
        if lo >= hi or any(overlaps((lo, hi), f) for f in fixed):
            return None
        iso = d.isocalendar()
        return RestWindow(lo, hi, (iso.year, iso.week))

    evenings, halves = [], []
    for d in dates:
        if s.free_evenings_per_week > 0 and (w := make(d, s.evening_start, s.sleep.start)):
            evenings.append(w)
        if s.weekend_half_days > 0 and d.isoweekday() in (SATURDAY, SUNDAY):
            if s.sleep.end < s.half_day_split and (w := make(d, s.sleep.end, s.half_day_split)):
                halves.append(w)
            if w := make(d, s.half_day_split, s.sleep.start):
                halves.append(w)
    return evenings, halves


def _required(windows: Iterable[RestWindow], per_week: int) -> dict[tuple[int, int], int]:
    count: dict[tuple[int, int], int] = defaultdict(int)
    for w in windows:
        count[w.week] += 1
    return {week: min(per_week, c) for week, c in count.items()}


def _day_limits(inp: PlanInput, days: Sequence[Day]) -> dict[int, int]:
    by_date = dict(inp.study_limits)
    return {d.index: by_date[d.date] // inp.grid_min for d in days if d.date in by_date}


def prepare(inp: PlanInput) -> Prepared:
    s, tz = inp.settings, inp.tz
    grid = Grid.build(inp.now, _horizon_end(inp), inp.grid_min)
    dates = _dates(grid, tz)
    days = _days(grid, s, dates, tz)
    busy = busy_slots(inp, grid, dates)
    base_free = subtract([(0, grid.n)], busy)
    min_part = grid.slots(s.min_part_min)
    day_starts = [d.lo for d in days]

    by_windows: dict[tuple[Window, ...], list[Interval]] = {}
    work = _work_windows(s)
    blocks: list[PreparedBlock] = []
    for index, b in enumerate(inp.blocks):
        windows = b.windows or work
        if windows not in by_windows:
            allowed = intersect(window_slots(grid, windows, dates, tz), base_free)
            by_windows[windows] = _split_by_days(allowed, days)
        dur = max(1, grid.slots(b.duration_min))
        overdue = b.deadline is not None and b.deadline <= grid.t0
        latest_end = grid.n
        due = None
        if b.deadline is not None and not overdue:
            latest_end = min(grid.floor(b.deadline), grid.n)
            buffer = s.deadline_buffer_days if b.buffer_days is None else b.buffer_days
            due_dt = b.deadline - timedelta(days=buffer)
            due = max(grid.floor(due_dt), 0)
        earliest = max(grid.ceil(b.earliest), 0) if b.earliest else 0
        free = [
            (max(lo, earliest), min(hi, latest_end))
            for lo, hi in by_windows[windows]
            if hi > earliest and lo < latest_end
        ]
        if b.days is not None:
            free = [f for f in free if _date_of(f[0], days, day_starts) in b.days]
        split = b.splittable and dur >= 2 * min_part
        free = [f for f in free if f[1] - f[0] >= (min_part if split else dur)]
        blocks.append(
            PreparedBlock(
                block=b,
                index=index,
                dur=dur,
                pad=grid.slots(s.break_min) if dur > grid.slots(s.long_block_min) else 0,
                split=split,
                free=free,
                starts=Domain.of_starts(free, dur),
                latest_end=latest_end,
                due=due,
                overdue=overdue,
            )
        )

    fixed = [(grid.outer(f.start, f.end), f) for f in inp.fixed]
    fixed_in = [iv for iv, _ in fixed if iv[0] < iv[1]]
    evenings, halves = _rest_windows(inp, grid, dates, fixed_in)
    prepared = Prepared(
        inp=inp,
        grid=grid,
        days=days,
        blocks=blocks,
        fixed=fixed,
        evenings=evenings,
        halves=halves,
        evenings_required=_required(evenings, s.free_evenings_per_week),
        halves_required=_required(halves, s.weekend_half_days),
        min_part=min_part,
        study_limit=s.study_limit_min_per_day // grid.step_min,
        study_limit_by_day=_day_limits(inp, days),
        max_per_group=s.max_subtasks_per_task_per_day,
    )
    # Закреплённое и сделанное сегодня до `now` тоже считается в лимиты сегодняшнего дня
    day0_start = grid.ceil(wall_to_utc(days[0].date, s.sleep.end, tz)) if days else 0
    for f in inp.fixed:
        lo, hi = grid.floor(f.start), grid.ceil(f.end)
        if lo >= grid.n or lo < day0_start or hi <= lo:
            continue
        day = max(prepared.day_of(lo), 0)
        if f.counts_as_study:
            prepared.fixed_study[day] = prepared.fixed_study.get(day, 0) + hi - lo
        if f.group_id is not None:
            key = (f.group_id, day)
            prepared.fixed_per_group[key] = prepared.fixed_per_group.get(key, 0) + 1
    return prepared


def available_slots(inp: PlanInput) -> dict[BlockId, Domain]:
    """Допустимые старты каждого блока целиком (без учёта других гибких блоков)."""
    return {pb.id: pb.starts for pb in prepare(inp).blocks}
