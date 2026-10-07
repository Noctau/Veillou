"""M8.6: property-тесты планировщика и бенчмарк.

Инварианты проверяются по исходному входу (datetime и «настенное» время),
независимо от сетки и подготовки внутри планировщика.
"""

import random
from collections import Counter
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from time import perf_counter

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core.time import get_tz, wall_to_utc
from app.domain.planner import (
    Block,
    Busy,
    FixedBlock,
    PlanInput,
    PlanResult,
    PlanSettings,
    Window,
    solve,
)

TZ = get_tz("Europe/Moscow")
MON = date(2026, 10, 12)
WEEKDAYS = frozenset({1, 2, 3, 4, 5})
ALL_DAYS = frozenset(range(1, 8))
WINDOWS = [
    (),  # рабочие часы
    (Window(WEEKDAYS, time(9), time(19)),),  # связь с людьми
    (Window(ALL_DAYS, time(7), time(1)),),  # учёба, через полночь
    (Window(frozenset({4}), time(10), time(17)),),  # только чт
    (Window(WEEKDAYS, time(18), time(23)), Window(frozenset({6, 7}), time(10), time(23))),
]
CLASSES = [(time(9), time(10, 35)), (time(10, 45), time(12, 20)), (time(13), time(14, 35))]


def at(d: date, t: time) -> datetime:
    return wall_to_utc(d, t, TZ)


# ---------- генерация ----------


@st.composite
def plan_inputs(draw) -> PlanInput:
    now = at(MON + timedelta(days=draw(st.integers(0, 6))), time(draw(st.integers(0, 23)), 7))
    n = draw(st.integers(1, 12))
    blocks = []
    for i in range(n):
        deadline_days = draw(st.one_of(st.none(), st.integers(-1, 12)))
        blocks.append(
            Block(
                id=f"b{i}",
                duration_min=draw(st.sampled_from([15, 30, 45, 60, 90, 120, 180])),
                group_id=draw(st.sampled_from([None, "t0", "t1", "t2"])),
                deadline=None
                if deadline_days is None
                else now + timedelta(days=deadline_days, hours=draw(st.integers(0, 23))),
                priority=draw(st.sampled_from([1, 3])),
                windows=draw(st.sampled_from(WINDOWS)),
                depends_on=tuple(
                    f"b{j}" for j in range(i) if draw(st.booleans()) and draw(st.booleans())
                ),
                splittable=draw(st.booleans()),
                counts_as_study=draw(st.booleans()),
                prefer_morning=draw(st.booleans()),
            )
        )
    busy = []
    for day in range(14):
        d = MON + timedelta(days=day)
        if d.isoweekday() <= 5 and draw(st.booleans()):
            for start, end in CLASSES[: draw(st.integers(1, 3))]:
                busy.append(Busy(at(d, start), at(d, end), is_class=True))
    if draw(st.booleans()):
        d = MON + timedelta(days=draw(st.integers(0, 10)))
        busy.append(Busy(at(d, time(17)), at(d, time(19))))
    fixed = []
    for k in range(draw(st.integers(0, 2))):
        start = now + timedelta(hours=draw(st.integers(-6, 72)))
        start = start.replace(minute=0)
        fixed.append(FixedBlock(f"f{k}", start, start + timedelta(minutes=60), group_id="t0"))
    plan_settings = PlanSettings(
        study_limit_min_per_day=draw(st.sampled_from([60, 120, 240, 360])),
        deadline_buffer_days=draw(st.integers(0, 2)),
        travel_buffer_min=draw(st.sampled_from([0, 30, 60])),
        free_evenings_per_week=draw(st.integers(0, 3)),
        weekend_half_days=draw(st.integers(0, 2)),
    )
    return PlanInput(
        now=now,
        tz=TZ,
        blocks=tuple(blocks),
        busy=tuple(busy),
        fixed=tuple(fixed),
        settings=plan_settings,
    )


# ---------- инварианты ----------


def _overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def _daily(d: date, start: time, end: time) -> tuple[datetime, datetime]:
    return at(d, start), at(d + timedelta(days=1) if end <= start else d, end)


def _within_windows(block: Block, s: PlanSettings, start: datetime, end: datetime) -> bool:
    windows = block.windows or (
        Window(WEEKDAYS, s.work_weekdays.start, s.work_weekdays.end),
        Window(frozenset({6, 7}), s.work_weekends.start, s.work_weekends.end),
    )
    first = start.astimezone(TZ).date() - timedelta(days=1)
    for i in range(2):
        d = first + timedelta(days=i)
        for w in windows:
            if d.isoweekday() in w.weekdays:
                lo, hi = _daily(d, w.start, w.end)
                if lo <= start and end <= hi:
                    return True
    return False


def _planning_day(dt: datetime, s: PlanSettings) -> date:
    """День планировщика: начинается с подъёма."""
    local = dt.astimezone(TZ)
    wake = datetime.combine(local.date(), s.sleep.end, TZ)
    return local.date() if local >= wake else local.date() - timedelta(days=1)


def check_invariants(inp: PlanInput, result: PlanResult) -> None:
    s = inp.settings
    blocks = {b.id: b for b in inp.blocks}
    by_block: dict = {}
    for p in sorted(result.placements, key=lambda p: (p.block_id, p.part)):
        by_block.setdefault(p.block_id, []).append(p)

    placements = sorted(result.placements, key=lambda p: p.start)
    for a, b in pairwise(placements):
        assert a.end <= b.start, f"пересечение {a} и {b}"

    study: Counter = Counter()
    per_group: dict = {}
    for f in inp.fixed:
        day = _planning_day(f.start, s)
        if f.counts_as_study:
            study[day] += (f.end - f.start).total_seconds() / 60
        per_group.setdefault((f.group_id, day), set()).add(f.id)

    for block_id, parts in by_block.items():
        block = blocks[block_id]
        assert sum((p.end - p.start for p in parts), timedelta()) >= timedelta(
            minutes=block.duration_min
        )
        assert len(parts) <= (2 if block.splittable else 1)
        for p in parts:
            assert p.start >= inp.now
            assert _within_windows(block, s, p.start, p.end), f"{block_id} вне окна: {p}"
            for b in inp.busy:
                assert not _overlap(p.start, p.end, b.start, b.end), f"{block_id} на занятом"
            for f in inp.fixed:
                assert not _overlap(p.start, p.end, f.start, f.end)
            d = p.start.astimezone(TZ).date()
            for day in (d - timedelta(days=1), d):
                assert not _overlap(p.start, p.end, *_daily(day, s.sleep.start, s.sleep.end))
                assert not _overlap(p.start, p.end, *_daily(day, s.lunch.start, s.lunch.end))
            day = _planning_day(p.start, s)
            if block.counts_as_study:
                study[day] += (p.end - p.start).total_seconds() / 60
            if block.group_id is not None:
                per_group.setdefault((block.group_id, day), set()).add(block_id)
        if block.deadline and block.deadline > inp.now:
            assert parts[-1].end <= block.deadline
        for dep in block.depends_on:
            if dep in blocks:
                assert dep in by_block, f"{block_id} размещён без {dep}"
                assert by_block[dep][-1].end <= parts[0].start
            elif fixed := next((f for f in inp.fixed if f.id == dep), None):
                assert fixed.end <= parts[0].start

    fixed_study: Counter = Counter()
    for f in inp.fixed:
        if f.counts_as_study:
            fixed_study[_planning_day(f.start, s)] += (f.end - f.start).total_seconds() / 60
    for day, minutes in study.items():
        if minutes > fixed_study[day]:
            # округление 20 мин → 30 на сетке даёт запас вверх, но не сверх лимита
            assert minutes <= max(s.study_limit_min_per_day, fixed_study[day]), f"{day}: {minutes}"
    for (group, day), ids in per_group.items():
        flex = [i for i in ids if i in blocks]
        if flex:
            assert len(ids) <= s.max_subtasks_per_task_per_day, f"{group} {day}: {ids}"

    placed = {r.block_id for r in result.at_risk} | set(by_block)
    assert placed == set(blocks), "каждый блок либо размещён, либо под угрозой"


def property_settings(max_examples: int) -> settings:
    return settings(
        max_examples=max_examples,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
        derandomize=True,
        database=None,
    )


@property_settings(150)
@given(plan_inputs())
def test_greedy_invariants(inp: PlanInput):
    inp = PlanInput(**{**inp.__dict__, "time_limit_s": 0})
    result = solve(inp)
    assert result.stats.engine == "greedy"
    check_invariants(inp, result)


@property_settings(30)
@given(plan_inputs())
def test_cp_sat_invariants(inp: PlanInput):
    inp = PlanInput(**{**inp.__dict__, "time_limit_s": 0.4})
    result = solve(inp)
    check_invariants(inp, result)


# ---------- бенчмарк ----------


def benchmark_input(n_blocks: int = 150, days: int = 60, seed: int = 1) -> PlanInput:
    rnd = random.Random(seed)
    now = at(MON, time(7, 3))
    blocks: list[Block] = []
    task = 0
    while len(blocks) < n_blocks:
        deadline = at(MON + timedelta(days=rnd.randint(3, days - 1)), time(23, 59))
        for k in range(rnd.randint(2, 5)):
            if len(blocks) >= n_blocks:
                break
            blocks.append(
                Block(
                    id=f"t{task}s{k}",
                    duration_min=rnd.choice([30, 45, 60, 90, 120]),
                    group_id=f"t{task}",
                    deadline=deadline,
                    priority=rnd.choice([1, 1, 3]),
                    windows=WINDOWS[1] if rnd.random() < 0.15 else WINDOWS[2],
                    depends_on=(f"t{task}s{k - 1}",) if k and rnd.random() < 0.5 else (),
                    splittable=rnd.random() < 0.5,
                )
            )
        task += 1
    busy = [
        Busy(at(d, start), at(d, end), is_class=True)
        for week in range(days // 7 + 1)
        for wd in range(5)
        for d in [MON + timedelta(days=7 * week + wd)]
        for start, end in rnd.sample(CLASSES, 2)
    ]
    return PlanInput(now=now, tz=TZ, blocks=tuple(blocks), busy=tuple(busy), max_horizon_days=days)


@pytest.mark.parametrize("n_blocks", [150])
def test_benchmark_150_blocks_60_days(n_blocks):
    inp = benchmark_input(n_blocks)
    started = perf_counter()
    result = solve(inp)
    elapsed = perf_counter() - started
    assert elapsed < 2.0, f"{elapsed:.2f} с ({result.stats.engine}, {result.stats.status})"
    assert result.stats.placed == n_blocks
    check_invariants(inp, result)
