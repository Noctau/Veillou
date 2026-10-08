"""M11.2, M11.5: дела из ящика в планировщике, допустимые дни, риск «из-за отдыха»."""

from datetime import time, timedelta

import pytest

from app.domain.planner import Block, Busy, PlanSettings, RiskReason, TimeRange, Window

from .test_planner import (
    MON,
    NO_REST,
    STUDY,
    SUN,
    THU,
    TUE,
    TZ,
    WED,
    at,
    parts,
    plan,
    risks,
    start,
)

ONE_FREE_HOUR = PlanSettings(lunch=None, free_evenings_per_week=0, weekend_half_days=0)


def busy_except(d, h_free: int) -> tuple[Busy, ...]:
    """Весь рабочий день занят, кроме часа h_free:00–h_free+1:00."""
    return (Busy(at(d, 7), at(d, h_free)), Busy(at(d, h_free + 1), at(d, 23, 59)))


@pytest.mark.parametrize("limit", [0, 0.5])
def test_filler_never_displaces_study(limit):
    """Свободен один час: его получает учёба, а не дело из ящика (даже старое)."""
    study = Block("study", 60, deadline=at(MON, 23), buffer_days=0)
    filler = Block("box", 60, filler=True, priority=8, deadline=at(MON, 23), buffer_days=0)
    result = plan(
        study, filler, busy=busy_except(MON, 15), settings=ONE_FREE_HOUR, time_limit_s=limit
    )
    assert parts(result, "study") == [(at(MON, 15), at(MON, 16))]
    assert not parts(result, "box")
    assert risks(result) == {"box": RiskReason.no_time}


@pytest.mark.parametrize("limit", [0, 0.5])
def test_filler_takes_what_is_left(limit):
    study = Block("study", 60, windows=STUDY, deadline=at(TUE, 23))
    filler = Block("box", 60, filler=True)
    result = plan(study, filler, settings=NO_REST, time_limit_s=limit)
    assert parts(result, "study") and parts(result, "box")
    assert start(result, "study") <= start(result, "box")
    assert result.at_risk == ()


def test_greedy_puts_filler_after_study_even_with_earlier_deadline():
    filler = Block("box", 60, filler=True, deadline=at(MON, 10), buffer_days=0)
    study = Block("study", 60, deadline=at(MON, 10), buffer_days=0)
    result = plan(filler, study, settings=NO_REST, time_limit_s=0)
    assert result.stats.engine == "greedy"
    assert parts(result, "study") == [(at(MON, 9), at(MON, 10))]
    assert risks(result) == {"box": RiskReason.no_time}


def test_filler_does_not_count_as_study():
    settings = PlanSettings(
        study_limit_min_per_day=60, free_evenings_per_week=0, weekend_half_days=0
    )
    study = Block("study", 60, deadline=at(MON, 23), buffer_days=0)
    filler = Block(
        "box", 60, filler=True, counts_as_study=False, deadline=at(MON, 23), buffer_days=0
    )
    result = plan(study, filler, settings=settings)
    assert parts(result, "study") and parts(result, "box")


@pytest.mark.parametrize("limit", [0, 0.5])
def test_allowed_days(limit):
    block = Block("shop", 60, days=frozenset({WED, THU}))
    result = plan(block, settings=NO_REST, time_limit_s=limit)
    assert start(result, "shop").date() == WED


def test_allowed_days_without_slots():
    block = Block("shop", 60, days=frozenset({MON - timedelta(days=7)}))
    result = plan(block, settings=NO_REST)
    assert risks(result) == {"shop": RiskReason.no_slots}


def test_allowed_days_night_belongs_to_previous_day():
    """Блок в 00:30 относится к вечеру предыдущего дня — и к его «дню пар»."""
    night = (Window(frozenset(range(1, 8)), time(0), time(1)),)
    block = Block("late", 30, windows=night, days=frozenset({TUE}))
    settings = PlanSettings(
        sleep=TimeRange(time(1), time(8)), free_evenings_per_week=0, weekend_half_days=0
    )
    result = plan(block, settings=settings)
    local = start(result, "late").astimezone(TZ)
    assert local.date() == WED and local.hour == 0


# ---------- риск «не хватает времени без отдыха» ----------


def test_rest_reason_when_only_evenings_are_left():
    """Днём всё занято парами; уместилось бы вечером, но вечера — отдых."""
    busy = tuple(
        Busy(at(MON + timedelta(days=i), 7), at(MON + timedelta(days=i), 18)) for i in range(7)
    )
    settings = PlanSettings(free_evenings_per_week=7, weekend_half_days=0, deadline_buffer_days=0)
    block = Block("essay", 120, windows=STUDY, deadline=at(WED, 23))
    result = plan(block, busy=busy, settings=settings)
    assert risks(result) == {"essay": RiskReason.rest}


def test_no_time_stays_when_rest_does_not_help():
    block = Block("huge", 600, windows=STUDY, deadline=at(MON, 12), buffer_days=0)
    result = plan(block)
    assert risks(result)["huge"] in (RiskReason.no_time, RiskReason.no_slots)


def test_rest_reason_not_used_without_rest_minimum():
    busy = tuple(
        Busy(at(MON + timedelta(days=i), 7), at(MON + timedelta(days=i), 23)) for i in range(3)
    )
    block = Block("essay", 120, windows=STUDY, deadline=at(WED, 22), buffer_days=0)
    result = plan(block, busy=busy, settings=NO_REST)
    assert risks(result)["essay"] != RiskReason.rest


def test_weekly_rest_still_kept_when_week_is_full():
    """Минимум отдыха жёсткий: даже при угрозе вечер остаётся свободным."""
    blocks = [Block(f"b{i}", 120, windows=STUDY, deadline=at(SUN, 23)) for i in range(40)]
    result = plan(
        *blocks, settings=PlanSettings(deadline_buffer_days=0, study_limit_min_per_day=960)
    )
    assert any(r == RiskReason.rest for r in risks(result).values())
