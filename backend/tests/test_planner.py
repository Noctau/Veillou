"""M8.2–M8.5: сценарии планировщика (`solve`)."""

from datetime import date, datetime, time, timedelta

import pytest

from app.core.time import get_tz, wall_to_utc
from app.domain.planner import (
    Block,
    Busy,
    FixedBlock,
    Placement,
    PlanInput,
    PlanResult,
    PlanSettings,
    RiskReason,
    TimeRange,
    Window,
    solve,
)
from app.domain.planner.check import violations
from app.domain.planner.grid import prepare
from app.domain.planner.solve import diff

TZ = get_tz("Europe/Moscow")
MON = date(2026, 10, 12)  # понедельник
TUE, WED, THU, FRI = (MON + timedelta(days=i) for i in range(1, 5))
SAT, SUN = MON + timedelta(days=5), MON + timedelta(days=6)
WEEKDAYS = frozenset({1, 2, 3, 4, 5})
PEOPLE = (Window(WEEKDAYS, time(9), time(19)),)
STUDY = (Window(frozenset(range(1, 8)), time(7), time(1)),)
NO_REST = PlanSettings(free_evenings_per_week=0, weekend_half_days=0)


def at(d: date, h: int, m: int = 0) -> datetime:
    return wall_to_utc(d, time(h, m), TZ)


def plan(*blocks: Block, now: datetime | None = None, **kw) -> PlanResult:
    """Решает и проверяет, что решение не нарушает жёстких ограничений."""
    kw.setdefault("time_limit_s", 0.5)
    data = PlanInput(now=now or at(MON, 8), tz=TZ, blocks=blocks, **kw)
    result = solve(data)
    prep = prepare(data)
    solution: dict = {}
    for p in sorted(result.placements, key=lambda p: p.part):
        lo = prep.grid.floor(p.start)
        solution.setdefault(p.block_id, []).append((lo, lo + _slots(p, prep)))
    assert violations(prep, solution) == []
    return result


def _slots(p: Placement, prep) -> int:
    return prep.grid.slots(int((p.end - p.start).total_seconds() // 60))


def parts(result: PlanResult, block_id) -> list[tuple[datetime, datetime]]:
    return [
        (p.start.astimezone(TZ), p.end.astimezone(TZ))
        for p in sorted(result.placements, key=lambda p: p.part)
        if p.block_id == block_id
    ]


def start(result: PlanResult, block_id) -> datetime:
    return parts(result, block_id)[0][0]


def end(result: PlanResult, block_id) -> datetime:
    return parts(result, block_id)[-1][1]


def risks(result: PlanResult) -> dict:
    return {r.block_id: r.reason for r in result.at_risk}


# ---------- базовое размещение ----------


def test_empty_input():
    result = solve(PlanInput(now=at(MON, 8), tz=TZ, blocks=()))
    assert result.placements == () and result.at_risk == ()
    assert result.stats.blocks == 0


def test_single_block_goes_to_first_free_slot():
    result = plan(Block("a", 60))
    assert parts(result, "a") == [(at(MON, 9), at(MON, 10))]
    assert result.stats.engine == "cp_sat"


def test_late_evening_goes_to_next_morning():
    result = plan(Block("a", 60), now=at(MON, 23))
    assert start(result, "a") == at(TUE, 9)


def test_class_day_with_travel_buffer():
    busy = (
        Busy(at(MON, 9), at(MON, 10, 35), is_class=True),
        Busy(at(MON, 10, 45), at(MON, 12, 20), is_class=True),
    )
    # после пар 12:20 + дорога 60 = 13:20 → обед до 14:00
    assert start(plan(Block("a", 60), busy=busy), "a") == at(MON, 14)


def test_people_on_friday_evening_moves_to_monday_morning():
    result = plan(Block("a", 60, windows=PEOPLE), now=at(FRI, 18, 30))
    assert start(result, "a") == at(MON + timedelta(days=7), 9)


def test_task_window_only_thursday():
    only_thu = (Window(frozenset({4}), time(10), time(17)),)
    assert start(plan(Block("a", 60, windows=only_thu)), "a") == at(THU, 10)


def test_earliest_respected():
    assert start(plan(Block("a", 30, earliest=at(WED, 15))), "a") == at(WED, 15)


def test_pinned_block_not_overlapped():
    fixed = (FixedBlock("f", at(MON, 9), at(MON, 12)),)
    result = plan(Block("a", 60), fixed=fixed)
    # 12:00 + перерыв после трёхчасового блока → 12:15, но до обеда только 45 минут
    assert start(result, "a") == at(MON, 14)


# ---------- зависимости ----------


def test_dependency_order():
    result = plan(
        Block("b", 60, depends_on=("a",), priority=3),
        Block("a", 60),
    )
    assert end(result, "a") <= start(result, "b")


def test_sequence_is_soft_order():
    # Без зависимостей шаги задания идут по порядку
    result = plan(
        Block("c", 60, group_id="t", sequence=2),
        Block("a", 60, group_id="t", sequence=0),
        Block("b", 60, group_id="t", sequence=1),
        settings=PlanSettings(max_subtasks_per_task_per_day=3),
    )
    assert start(result, "a") < start(result, "b") < start(result, "c")


def test_sequence_yields_to_narrow_window():
    # Порядок мягкий: шаг с узким окном может встать раньше предыдущего
    window = (Window(frozenset({1}), time(9), time(10)),)
    result = plan(
        Block("a", 120, group_id="t", sequence=0, deadline=at(MON, 23)),
        Block("b", 60, group_id="t", sequence=1, windows=window, deadline=at(MON, 23)),
        settings=PlanSettings(deadline_buffer_days=0),
    )
    assert start(result, "b") == at(MON, 9)
    assert risks(result) == {}


def test_dependency_on_unplaceable_block():
    short = (Window(WEEKDAYS, time(9), time(9, 30)),)
    result = plan(Block("a", 60, windows=short), Block("b", 30, depends_on=("a",)))
    assert risks(result) == {"a": RiskReason.no_slots, "b": RiskReason.dependency}
    assert result.placements == ()


def test_dependency_on_pinned_block():
    fixed = (FixedBlock("f", at(TUE, 9), at(TUE, 10)),)
    result = plan(Block("b", 30, depends_on=("f",)), fixed=fixed)
    assert start(result, "b") >= at(TUE, 10)


def test_dependency_on_unknown_block_is_ignored():
    """Зависимость от уже сделанной подзадачи — её нет во входе."""
    assert start(plan(Block("b", 30, depends_on=("done",))), "b") == at(MON, 9)


def test_dependency_cycle_does_not_crash():
    result = plan(Block("a", 30, depends_on=("b",)), Block("b", 30, depends_on=("a",)))
    assert result.placements == ()
    assert set(risks(result)) == {"a", "b"}


# ---------- дедлайны ----------


def test_not_enough_time_before_deadline():
    blocks = [Block(f"b{i}", 60, deadline=at(MON, 11)) for i in range(4)]
    result = plan(*blocks, settings=PlanSettings(deadline_buffer_days=0))
    assert len(result.placements) == 2
    assert sorted(risks(result).values()) == [RiskReason.no_time] * 2


def test_no_slots_before_deadline():
    result = plan(Block("a", 60, windows=PEOPLE, deadline=at(SAT, 12)), now=at(FRI, 19, 30))
    assert risks(result) == {"a": RiskReason.no_slots}


def test_finishes_before_internal_deadline_when_possible():
    result = plan(
        Block("a", 60, deadline=at(WED, 23)),
        Block("b", 60, deadline=at(MON + timedelta(days=20), 23)),
        busy=(Busy(at(MON, 9), at(MON, 21)),),
    )
    assert end(result, "a") <= at(TUE, 23)  # дедлайн − 1 день
    assert "a" not in risks(result)


def test_late_inside_buffer_is_at_risk():
    result = plan(Block("a", 60, deadline=at(TUE, 21)), now=at(MON, 20, 30))
    assert start(result, "a") == at(TUE, 9)
    assert risks(result) == {"a": RiskReason.late}


def test_block_buffer_overrides_settings():
    # Внутренний срок сдвинут к самому дедлайну — блок не «опаздывает»
    result = plan(Block("a", 60, deadline=at(TUE, 21), buffer_days=0), now=at(MON, 20, 30))
    assert start(result, "a") == at(TUE, 9)
    assert risks(result) == {}


def test_overdue_is_placed_asap():
    result = plan(
        Block("old", 60, deadline=at(MON - timedelta(days=2), 12)),
        Block("new", 60, deadline=at(WED, 12), priority=3),
    )
    assert start(result, "old") == at(MON, 9)
    assert risks(result) == {"old": RiskReason.overdue}


def test_priority_wins_single_slot():
    window = (Window(frozenset({1}), time(9), time(10)),)
    result = plan(
        Block("low", 60, windows=window, deadline=at(MON, 23)),
        Block("high", 60, windows=window, deadline=at(MON, 23), priority=3),
        settings=PlanSettings(deadline_buffer_days=0),
    )
    assert start(result, "high") == at(MON, 9)
    assert risks(result) == {"low": RiskReason.no_time}


# ---------- дневные ограничения ----------


def test_daily_study_limit():
    settings = PlanSettings(study_limit_min_per_day=120)
    result = plan(*(Block(f"b{i}", 60) for i in range(3)), settings=settings)
    days = sorted(start(result, f"b{i}").date() for i in range(3))
    assert days == [MON, MON, TUE]


def test_study_limit_override_for_one_day():
    settings = PlanSettings(study_limit_min_per_day=120)
    result = plan(
        *(Block(f"b{i}", 60) for i in range(4)),
        settings=settings,
        study_limits=((MON, 240),),
    )
    assert {start(result, f"b{i}").date() for i in range(4)} == {MON}


def test_study_limit_override_can_lower_limit():
    settings = PlanSettings(study_limit_min_per_day=120)
    result = plan(Block("a", 60), settings=settings, study_limits=((MON, 0),))
    assert start(result, "a").date() == TUE


def test_non_study_blocks_ignore_limit():
    settings = PlanSettings(study_limit_min_per_day=60)
    result = plan(*(Block(f"b{i}", 60, counts_as_study=False) for i in range(3)), settings=settings)
    assert {start(result, f"b{i}").date() for i in range(3)} == {MON}


def test_pinned_study_counts_in_limit():
    settings = PlanSettings(study_limit_min_per_day=120)
    fixed = (FixedBlock("f", at(MON, 8), at(MON, 9, 30)),)  # уже сделано сегодня
    result = plan(Block("a", 60), fixed=fixed, now=at(MON, 9, 30), settings=settings)
    assert start(result, "a").date() == TUE


def test_at_most_two_subtasks_of_task_per_day():
    result = plan(*(Block(f"s{i}", 30, group_id="t") for i in range(5)))
    per_day: dict[date, int] = {}
    for i in range(5):
        d = start(result, f"s{i}").date()
        per_day[d] = per_day.get(d, 0) + 1
    assert max(per_day.values()) == 2
    assert len(per_day) == 3


def test_pinned_subtasks_count_in_task_limit():
    fixed = (
        FixedBlock("f1", at(MON, 8), at(MON, 8, 30), group_id="t"),
        FixedBlock("f2", at(MON, 8, 30), at(MON, 9), group_id="t"),
    )
    result = plan(Block("s", 30, group_id="t"), Block("x", 30), fixed=fixed, now=at(MON, 9))
    assert start(result, "s").date() == TUE
    assert start(result, "x").date() == MON


def test_night_block_counts_for_previous_day():
    """Учёба в 00:00 вторника — это ещё вечер понедельника (день начинается с подъёма)."""
    settings = PlanSettings(
        sleep=TimeRange(time(1, 30), time(9)),
        study_limit_min_per_day=60,
        free_evenings_per_week=0,
        weekend_half_days=0,
    )
    night = (Window(frozenset({2}), time(0), time(1, 30)),)
    result = plan(
        Block("night", 60, windows=night), Block("day", 60), now=at(MON, 23), settings=settings
    )
    assert start(result, "night") == at(TUE, 0)
    assert start(result, "day") == at(TUE, 9)


# ---------- перерывы ----------


def test_break_after_long_block():
    result = plan(Block("a", 90), Block("b", 90))
    first, second = sorted([parts(result, "a")[0], parts(result, "b")[0]])
    assert second[0] - first[1] >= timedelta(minutes=10)


def test_no_break_after_short_blocks():
    result = plan(Block("a", 60), Block("b", 60))
    assert sorted([start(result, "a"), start(result, "b")]) == [at(MON, 9), at(MON, 10)]


# ---------- разрезание ----------


def test_split_when_whole_does_not_fit():
    two_hours = (Window(frozenset({1, 2}), time(9), time(11)),)
    result = plan(Block("a", 180, windows=two_hours, splittable=True, deadline=at(WED, 23)))
    ps = parts(result, "a")
    assert len(ps) == 2
    assert sum((e - s for s, e in ps), timedelta()) == timedelta(minutes=180)
    assert all(e - s >= timedelta(minutes=30) for s, e in ps)
    assert ps[0][1] <= ps[1][0]
    assert result.stats.split == 1


def test_not_splittable_has_no_slots():
    two_hours = (Window(frozenset({1, 2}), time(9), time(11)),)
    result = plan(Block("a", 180, windows=two_hours, deadline=at(WED, 23)))
    assert risks(result) == {"a": RiskReason.no_slots}


def test_split_not_used_when_whole_fits():
    result = plan(Block("a", 120, splittable=True))
    assert parts(result, "a") == [(at(MON, 9), at(MON, 11))]


def test_split_parts_count_once_for_task_limit():
    two_hours = (
        Window(frozenset({1}), time(9), time(11)),
        Window(frozenset({1}), time(15), time(17)),
    )
    result = plan(
        Block("a", 180, windows=two_hours, splittable=True, group_id="t"),
        Block("b", 30, group_id="t"),
    )
    assert len(parts(result, "a")) == 2
    assert start(result, "b").date() == MON  # a — одна подзадача, хоть и в двух частях


# ---------- стабильность ----------


def test_stability_keeps_tomorrow_block():
    previous = (Placement("a", 0, at(TUE, 15), at(TUE, 16)),)
    result = plan(Block("a", 60), previous=previous)
    assert start(result, "a") == at(TUE, 15)
    assert result.diff.empty


def test_far_block_moves_earlier():
    previous = (
        Placement("a", 0, at(MON + timedelta(days=10), 15), at(MON + timedelta(days=10), 16)),
    )
    result = plan(Block("a", 60), previous=previous)
    assert start(result, "a") == at(MON, 9)
    assert len(result.diff.moved) == 1


def test_new_task_does_not_shuffle_today():
    previous = (Placement("a", 0, at(MON, 10), at(MON, 11)),)
    result = plan(Block("a", 60), Block("new", 60, priority=3), previous=previous)
    assert start(result, "a") == at(MON, 10)
    assert [p.block_id for p in result.diff.added] == ["new"]


def test_diff():
    a = Placement("a", 0, at(MON, 9), at(MON, 10))
    b_old, b_new = (
        Placement("b", 0, at(MON, 10), at(MON, 11)),
        Placement("b", 0, at(TUE, 9), at(TUE, 10)),
    )
    c = Placement("c", 0, at(MON, 12), at(MON, 13))
    d = Placement("d", 0, at(WED, 9), at(WED, 10))
    result = diff([a, b_old, c], [a, b_new, d])
    assert result.added == (d,)
    assert result.removed == (c,)
    assert result.moved == ((b_old, b_new),)


def test_unplaceable_previous_block_is_removed():
    previous = (Placement("a", 0, at(TUE, 9), at(TUE, 10)),)
    result = plan(
        Block("a", 60, windows=PEOPLE, deadline=at(MON, 12)), previous=previous, now=at(MON, 11, 30)
    )
    assert [p.block_id for p in result.diff.removed] == ["a"]


# ---------- отдых ----------


def _flex_overlaps(result: PlanResult, lo: datetime, hi: datetime) -> bool:
    return any(p.start < hi and lo < p.end for p in result.placements)


def test_rest_keeps_free_evenings_and_half_day():
    blocks = [Block(f"b{i}", 120, windows=STUDY, deadline=at(SUN, 23)) for i in range(30)]
    result = plan(*blocks, settings=PlanSettings(deadline_buffer_days=0))
    evenings = sum(
        not _flex_overlaps(result, at(d, 18), at(d, 23, 30))
        for d in (MON + timedelta(days=i) for i in range(7))
    )
    halves = sum(
        not _flex_overlaps(result, lo, hi)
        for d in (SAT, SUN)
        for lo, hi in ((at(d, 7, 30), at(d, 14)), (at(d, 14), at(d, 23, 30)))
    )
    assert evenings >= 2
    assert halves >= 1
    assert result.at_risk  # всего не влезло — но отдых не тронут


def test_rest_disabled_uses_evenings():
    blocks = [Block(f"b{i}", 120, windows=STUDY, deadline=at(SUN, 23)) for i in range(60)]
    base = dict(deadline_buffer_days=0, study_limit_min_per_day=960)
    with_rest = plan(*blocks, settings=PlanSettings(**base))
    without = plan(
        *blocks, settings=PlanSettings(**base, free_evenings_per_week=0, weekend_half_days=0)
    )
    assert len(without.placements) > len(with_rest.placements)


# ---------- прочее ----------


def test_greedy_fallback_without_time():
    blocks = [Block(f"b{i}", 60, group_id=f"t{i % 3}", deadline=at(FRI, 23)) for i in range(8)]
    result = plan(*blocks, time_limit_s=0)
    assert result.stats.engine == "greedy"
    assert result.stats.placed == 8


@pytest.mark.parametrize("limit", [0, 0.5])
def test_engines_agree_on_feasibility(limit):
    busy = tuple(
        Busy(at(d, 10, 45), at(d, 14, 35), is_class=True) for d in (MON, TUE, WED, THU, FRI)
    )
    blocks = [
        Block(
            f"t{t}s{k}",
            45 + 15 * k,
            group_id=f"t{t}",
            deadline=at(MON + timedelta(days=3 + t), 23),
            depends_on=(f"t{t}s{k - 1}",) if k else (),
            splittable=k == 2,
        )
        for t in range(4)
        for k in range(3)
    ]
    result = plan(*blocks, busy=busy, time_limit_s=limit)
    assert result.stats.placed == 12
