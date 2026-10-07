"""M8.1: сетка и доступность блоков (`available_slots`)."""

from datetime import date, datetime, time, timedelta

from app.core.time import get_tz, wall_to_utc
from app.domain.planner import (
    Block,
    Busy,
    FixedBlock,
    PlanInput,
    PlanSettings,
    TimeRange,
    Window,
    available_slots,
)
from app.domain.planner.grid import Grid, intersect, merge, prepare, subtract

TZ = get_tz("Europe/Moscow")
MON = date(2026, 10, 12)  # понедельник
THU = MON + timedelta(days=3)
WEEKDAYS = frozenset({1, 2, 3, 4, 5})
PEOPLE = (Window(WEEKDAYS, time(9), time(19)),)
STUDY = (Window(frozenset(range(1, 8)), time(7), time(1)),)


def at(d: date, h: int, m: int = 0) -> datetime:
    return wall_to_utc(d, time(h, m), TZ)


def ranges(inp: PlanInput, block_id="b") -> list[tuple[datetime, datetime]]:
    """Свободное время блока как [(начало, конец)] в локальном времени."""
    prep = prepare(inp)
    pb = prep.by_id[block_id]
    return [
        (prep.grid.dt(lo).astimezone(TZ), prep.grid.dt(hi).astimezone(TZ)) for lo, hi in pb.free
    ]


def free_on(inp: PlanInput, d: date, block_id="b") -> list[tuple[time, time]]:
    return [(a.time(), b.time()) for a, b in ranges(inp, block_id) if a.date() == d]


def inp(*blocks: Block, now: datetime | None = None, **kw) -> PlanInput:
    return PlanInput(now=now or at(MON, 0), tz=TZ, blocks=blocks, **kw)


# ---------- интервалы ----------


def test_merge_and_subtract():
    assert merge([(5, 7), (0, 2), (2, 3), (6, 9), (4, 4)]) == [(0, 3), (5, 9)]
    assert subtract([(0, 10)], [(2, 3), (5, 7), (9, 12)]) == [(0, 2), (3, 5), (7, 9)]
    assert subtract([(0, 10), (20, 30)], [(-5, 1), (8, 22)]) == [(1, 8), (22, 30)]
    assert subtract([(0, 10)], []) == [(0, 10)]
    assert intersect([(0, 5), (8, 12)], [(3, 10)]) == [(3, 5), (8, 10)]


def test_grid_rounds_now_up_and_free_time_inward():
    grid = Grid.build(at(MON, 8, 7), at(MON, 20), 15)
    assert grid.t0 == at(MON, 8, 15)
    assert grid.inner(at(MON, 10, 35), at(MON, 12, 20)) == (grid.floor(at(MON, 10, 45)), 16)
    assert grid.outer(at(MON, 10, 35), at(MON, 12, 20)) == (9, 17)


# ---------- рабочие часы, сон, обед ----------


def test_default_work_hours_minus_lunch():
    data = inp(Block("b", 60))
    assert free_on(data, MON) == [(time(9), time(13)), (time(14), time(21))]
    # выходные: 11–19
    assert free_on(data, MON + timedelta(days=5)) == [(time(11), time(13)), (time(14), time(19))]


def test_sleep_cuts_late_study_window():
    """Окно учёбы до 01:00, но сон с 23:30 — сон важнее."""
    data = inp(Block("b", 60, windows=STUDY))
    assert free_on(data, MON) == [(time(7, 30), time(13)), (time(14), time(23, 30))]


def test_night_study_when_sleep_is_late():
    settings = PlanSettings(sleep=TimeRange(time(1, 30), time(9)))
    data = inp(Block("b", 60, windows=STUDY), settings=settings)
    tue = MON + timedelta(days=1)
    # Пн 09:00–13:00, 14:00–… до 01:00 вторника (окно), сон с 01:30
    assert (time(14), time(1)) in [
        (a.time(), b.time()) for a, b in ranges(data) if a.date() == MON and b.date() == tue
    ]


def test_starts_must_fit_duration():
    data = inp(Block("b", 120))
    domain = available_slots(data)["b"]
    grid = prepare(data).grid
    assert grid.floor(at(MON, 11)) in domain  # 11:00–13:00
    assert grid.floor(at(MON, 11, 15)) not in domain  # залезает на обед
    assert grid.floor(at(MON, 19)) in domain
    assert grid.floor(at(MON, 19, 15)) not in domain  # после 21:00


def test_now_cuts_today():
    data = inp(Block("b", 30), now=at(MON, 15, 50))
    assert free_on(data, MON) == [(time(16), time(21))]


# ---------- дорога и жёсткие события ----------


def test_travel_buffer_around_class_day():
    busy = (
        Busy(at(MON, 10, 45), at(MON, 12, 20), is_class=True),
        Busy(at(MON, 13, 0), at(MON, 14, 35), is_class=True),
    )
    data = inp(Block("b", 30), busy=busy)
    # 09:00–09:45 (до 10:45 − 60), окно между парами 12:20→12:30–13:00 обед, после — 15:35→15:45
    assert free_on(data, MON) == [
        (time(9), time(9, 45)),
        (time(12, 30), time(13)),
        (time(15, 45), time(21)),
    ]


def test_no_travel_buffer_around_personal_events():
    busy = (Busy(at(MON, 16), at(MON, 17)),)
    assert free_on(inp(Block("b", 30), busy=busy), MON) == [
        (time(9), time(13)),
        (time(14), time(16)),
        (time(17), time(21)),
    ]


def test_travel_buffer_setting_zero():
    busy = (Busy(at(MON, 10, 45), at(MON, 12, 20), is_class=True),)
    data = inp(Block("b", 30), busy=busy, settings=PlanSettings(travel_buffer_min=0))
    assert free_on(data, MON)[:2] == [(time(9), time(10, 45)), (time(12, 30), time(13))]


def test_fixed_block_is_busy():
    fixed = (FixedBlock("f", at(MON, 9), at(MON, 10, 30)),)
    assert free_on(inp(Block("b", 30), fixed=fixed), MON)[0] == (time(10, 30), time(13))


# ---------- окна типа действия и задачи ----------


def test_people_window_weekdays_until_19():
    data = inp(Block("b", 60, windows=PEOPLE))
    assert free_on(data, MON) == [(time(9), time(13)), (time(14), time(19))]
    sat = MON + timedelta(days=5)
    assert free_on(data, sat) == []
    assert free_on(data, sat + timedelta(days=1)) == []


def test_type_window_beats_work_hours():
    """Учёба в 22:00 разрешена, хотя рабочие часы — до 21:00."""
    data = inp(Block("b", 60, windows=STUDY))
    assert free_on(data, MON)[-1] == (time(14), time(23, 30))


def test_task_window_only_thursday():
    only_thu = (Window(frozenset({4}), time(10), time(17)),)
    data = inp(Block("b", 60, windows=only_thu))
    days = {a.date() for a, _ in ranges(data)}
    assert days and all(d.isoweekday() == 4 for d in days)
    assert free_on(data, THU) == [(time(10), time(13)), (time(14), time(17))]


def test_deadline_and_earliest_clip():
    block = Block("b", 60, deadline=at(THU, 12), earliest=at(MON + timedelta(days=1), 15))
    data = inp(block)
    rs = ranges(data)
    assert rs[0][0] == datetime.combine(MON + timedelta(days=1), time(15), TZ)
    assert rs[-1][1] == datetime.combine(THU, time(12), TZ)


def test_no_slots_when_window_too_short():
    short = (Window(WEEKDAYS, time(9), time(9, 30)),)
    assert not available_slots(inp(Block("b", 60, windows=short)))["b"]


def test_splittable_block_keeps_short_segments():
    """Разрезаемому блоку годятся окна от 30 минут, хоть целиком он туда и не влезает."""
    win = (Window(frozenset({1}), time(9), time(10)),)
    whole = prepare(inp(Block("b", 120, windows=win)))
    split = prepare(inp(Block("b", 120, windows=win, splittable=True)))
    assert whole.by_id["b"].free == []
    assert split.by_id["b"].free
    assert not split.by_id["b"].starts  # целиком всё равно некуда


# ---------- горизонт, дни, отдых ----------


def test_horizon_to_farthest_deadline_but_max_60_days():
    near = prepare(inp(Block("b", 30, deadline=at(MON + timedelta(days=20), 12))))
    assert near.grid.end <= at(MON + timedelta(days=20), 12)
    assert near.grid.end >= at(MON + timedelta(days=20), 11)
    far = prepare(inp(Block("b", 30, deadline=at(MON + timedelta(days=200), 12))))
    assert far.grid.end == at(MON, 0) + timedelta(days=60)
    short = prepare(inp(Block("b", 30, deadline=at(MON + timedelta(days=2), 12))))
    assert short.grid.end == at(MON, 0) + timedelta(days=14)


def test_day_starts_at_wake_up():
    prep = prepare(inp(Block("b", 30), now=at(MON, 12)))
    tue = MON + timedelta(days=1)
    assert prep.days[0].date == MON
    assert prep.day_of(prep.grid.floor(at(tue, 0, 30))) == 0  # ночь — ещё понедельник
    assert prep.day_of(prep.grid.floor(at(tue, 7, 30))) == 1


def test_rest_candidates():
    prep = prepare(inp(Block("b", 30)))
    grid = prep.grid
    first = prep.evenings[0]
    assert grid.dt(first.lo) == at(MON, 18)
    assert grid.dt(first.hi) == at(MON, 23, 30)
    sat = MON + timedelta(days=5)
    halves = [(grid.dt(w.lo), grid.dt(w.hi)) for w in prep.halves[:2]]
    assert halves == [(at(sat, 7, 30), at(sat, 14)), (at(sat, 14), at(sat, 23, 30))]
    assert prep.evenings_required[(2026, 42)] == 2
    assert prep.halves_required[(2026, 42)] == 1


def test_rest_candidate_with_pinned_block_is_excluded():
    fixed = (FixedBlock("f", at(MON, 19), at(MON, 20)),)
    prep = prepare(inp(Block("b", 30), fixed=fixed))
    assert prep.grid.dt(prep.evenings[0].lo) == at(MON + timedelta(days=1), 18)


def test_fixed_blocks_count_in_daily_limits():
    fixed = (
        FixedBlock("f1", at(MON, 9), at(MON, 11), group_id="t"),
        FixedBlock("f2", at(MON, 14), at(MON, 15), group_id="t", counts_as_study=False),
    )
    prep = prepare(inp(Block("b", 30), fixed=fixed, now=at(MON, 16)))
    assert prep.fixed_study == {0: 8}
    assert prep.fixed_per_group == {("t", 0): 2}


def test_dst_transition_keeps_wall_time():
    """Берлин, 25.10.2026 — переход на зимнее время: окна остаются 09:00–19:00 по часам."""
    berlin = get_tz("Europe/Berlin")
    sun = date(2026, 10, 25)
    data = PlanInput(
        now=wall_to_utc(sun - timedelta(days=1), time(0), berlin),
        tz=berlin,
        blocks=(Block("b", 60, windows=(Window(frozenset(range(1, 8)), time(9), time(19)),)),),
        settings=PlanSettings(lunch=None),
    )
    prep = prepare(data)
    for lo, hi in prep.by_id["b"].free[:4]:
        start, end = prep.grid.dt(lo).astimezone(berlin), prep.grid.dt(hi).astimezone(berlin)
        assert (start.time(), end.time()) == (time(9), time(19))
