"""M18.1–M18.2: режимы дня — разрешение правил и сутки планировщика."""

from datetime import time, timedelta

import pytest

from app.domain import dayprofile
from app.domain.dayprofile import Profile, Rule, assign, resolve
from app.domain.enums import DayRuleKind
from app.domain.planner import Block, Busy, PlanSettings, solve
from app.domain.planner.grid import prepare

from .test_planner import MON, SAT, SUN, TUE, TZ, WED, at, parts

SHIFT = "shift"
WEEKDAYS = Rule("weekdays", DayRuleKind.weekdays, 0, weekdays=frozenset({1, 2, 3, 4, 5}))
WEEKENDS = Rule("weekends", DayRuleKind.weekdays, 1, weekdays=frozenset({6, 7}))
AFTER_NIGHT = Rule("after_night", DayRuleKind.day_after, 2, event_type_id=SHIFT)
SHIFT_DAY = Rule("shift_day", DayRuleKind.event_day, 3, event_type_id=SHIFT)
NO_EVENTS: dict = {}


# ---------- приоритет ----------


def test_weekdays():
    rules = [WEEKDAYS, WEEKENDS]
    assert resolve(MON, rules, NO_EVENTS) == "weekdays"
    assert resolve(SAT, rules, NO_EVENTS) == "weekends"


def test_empty_rules_give_default_profile():
    assert resolve(MON, [], NO_EVENTS, default="first") == "first"
    assert resolve(MON, [], NO_EVENTS) is None


def test_no_rule_matches_gives_default():
    assert resolve(SAT, [WEEKDAYS], NO_EVENTS, default="first") == "first"


def test_date_beats_event_and_weekday():
    off = Rule("off", DayRuleKind.dates, 99, date_from=TUE, date_to=TUE)
    rules = [WEEKDAYS, AFTER_NIGHT, off]
    events = {MON: {SHIFT}}
    assert resolve(TUE, rules, events) == "off"
    assert resolve(WED, rules, events) == "weekdays"


def test_date_range_inclusive():
    vacation = Rule("vacation", DayRuleKind.dates, date_from=MON, date_to=WED)
    assert [
        resolve(MON + timedelta(days=i), [vacation, WEEKDAYS], NO_EVENTS) for i in range(4)
    ] == [
        "vacation",
        "vacation",
        "vacation",
        "weekdays",
    ]


def test_narrower_date_rule_wins():
    vacation = Rule("vacation", DayRuleKind.dates, 0, date_from=MON, date_to=SUN)
    today = Rule("off", DayRuleKind.dates, 5, date_from=TUE, date_to=TUE)
    assert resolve(TUE, [vacation, today], NO_EVENTS) == "off"
    assert resolve(WED, [vacation, today], NO_EVENTS) == "vacation"


def test_event_beats_weekday():
    rules = [WEEKDAYS, SHIFT_DAY]
    assert resolve(MON, rules, {MON: {SHIFT}}) == "shift_day"
    assert resolve(MON, rules, {MON: {"other"}}) == "weekdays"


def test_day_after_night_shift():
    """Ночная смена начинается в понедельник — «после ночной» во вторник."""
    rules = [WEEKDAYS, AFTER_NIGHT]
    events = {MON: {SHIFT}}
    assert resolve(MON, rules, events) == "weekdays"
    assert resolve(TUE, rules, events) == "after_night"
    assert resolve(WED, rules, events) == "weekdays"


def test_event_rules_ordered_by_position():
    """Смена 2/2 «день-ночь»: в день смены — «Смена» (выше), на следующий без смены —
    «после ночной»."""
    shift_first = Rule("shift_day", DayRuleKind.event_day, 0, event_type_id=SHIFT)
    after = Rule("after_night", DayRuleKind.day_after, 1, event_type_id=SHIFT)
    events = {MON: {SHIFT}, TUE: {SHIFT}}
    rules = [WEEKDAYS, after, shift_first]
    assert resolve(MON, rules, events) == "shift_day"
    assert resolve(TUE, rules, events) == "shift_day"
    assert resolve(WED, rules, events) == "after_night"


def test_assign_unknown_profile_falls_back():
    profiles = [dayprofile.FALLBACK_WEEKDAYS]
    rules = [Rule("deleted", DayRuleKind.weekdays, weekdays=frozenset(range(1, 8)))]
    days = assign([MON], profiles, rules, NO_EVENTS, TZ)
    assert days.profile(MON) is dayprofile.FALLBACK_WEEKDAYS


def test_assign_without_profiles_uses_builtin():
    days = assign([MON, SAT], [], [], NO_EVENTS, TZ)
    assert days.profile(MON).name == "Будни"
    assert days.profile(SUN).name == "Выходные"


# ---------- сутки ----------


def test_bedtime_after_midnight():
    p = Profile("p", "Сова", wake=time(10), sleep=time(1, 30))
    assert dayprofile.bedtime(MON, p, TZ) == at(TUE, 1, 30)
    p = Profile("p", "Жаворонок", wake=time(6), sleep=time(22))
    assert dayprofile.bedtime(MON, p, TZ) == at(MON, 22)


def test_sleep_until_next_days_wake():
    late = Profile("late", "После ночной", wake=time(15), sleep=time(23))
    early = dayprofile.FALLBACK_WEEKDAYS
    assert dayprofile.sleep_interval(MON, early, late, TZ) == (at(MON, 23, 30), at(TUE, 15))


def test_work_window_through_midnight():
    p = Profile("p", "Ночь", wake=time(14), sleep=time(4), work=((time(20), time(2)),))
    spec = dayprofile.day_spec(MON, p, TZ)
    assert spec.work == ((at(MON, 20), at(TUE, 2)),)


# ---------- планировщик ----------

DAY = Profile(
    "day", "Будни", wake=time(7), sleep=time(23), work=((time(8), time(22)),), rest_evening_ok=False
)
AFTER = Profile("after", "После ночной", wake=time(15), sleep=time(23), work=((time(8), time(22)),))
NO_REST = PlanSettings(free_evenings_per_week=0, weekend_half_days=0)


def _days(profile_of) -> tuple:
    first = MON - timedelta(days=2)
    return tuple(
        dayprofile.day_spec(d, profile_of(d), TZ)
        for d in (first + timedelta(days=i) for i in range(30))
    )


@pytest.mark.parametrize("limit", [0, 0.5])
def test_night_shift_and_after_night(limit):
    """Ночная смена 20:00–08:00 (дорога 40 мин), назавтра сон до 15:00: ни одного блока
    во вторник в [08:00, 15:00], и в саму смену тоже."""
    busy = (Busy(at(MON, 20), at(TUE, 8), buffer_before=40, buffer_after=40),)
    days = _days(lambda d: AFTER if d == TUE else DAY)
    blocks = tuple(
        Block(f"b{i}", 60, deadline=at(TUE, 22), buffer_days=0, splittable=True) for i in range(8)
    )
    result = solve(_input(blocks, busy=busy, days=days, now=at(MON, 18), time_limit_s=limit))
    assert result.placements
    for p in result.placements:
        assert not (p.start < at(TUE, 15) and p.end > at(TUE, 8)), p
        assert not (p.start < at(TUE, 8, 40) and p.end > at(MON, 19, 20)), p


def test_wake_starts_planning_day():
    """День планировщика «после ночной» начинается в 15:00."""
    days = _days(lambda d: AFTER if d == TUE else DAY)
    prep = prepare(_input((Block("b", 30),), days=days, now=at(MON, 8)))
    tue = next(d for d in prep.days if d.date == TUE)
    assert prep.grid.dt(tue.lo) == at(TUE, 15)


def test_day_off_by_date_uses_its_windows():
    """Выходной по дате (во вторник): рабочие окна выходного, а не будней."""
    off = Profile("off", "Выходной", wake=time(10), sleep=time(23), work=((time(12), time(14)),))
    days = _days(lambda d: off if d == TUE else DAY)
    result = solve(
        _input(
            (Block("b", 120, deadline=at(WED, 0), buffer_days=0),),
            days=days,
            now=at(TUE, 9),
            time_limit_s=0,
        )
    )
    assert parts(result, "b") == [(at(TUE, 12), at(TUE, 14))]


def test_rest_evening_only_on_allowed_days():
    days = _days(lambda d: AFTER if d.isoweekday() == 2 else DAY)
    prep = prepare(
        _input(
            (Block("b", 30),),
            days=days,
            now=at(MON, 8),
            settings=PlanSettings(free_evenings_per_week=2, weekend_half_days=0),
        )
    )
    evenings = {prep.grid.dt(w.lo).date() for w in prep.evenings}
    assert {d.isoweekday() for d in evenings} == {2}


def _input(blocks, **kw):
    from app.domain.planner import PlanInput

    kw.setdefault("settings", NO_REST)
    return PlanInput(tz=TZ, blocks=blocks, **kw)
