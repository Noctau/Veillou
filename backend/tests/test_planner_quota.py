"""M13.1: недельная норма проекта в планировщике (`Quota`, резервные блоки)."""

from datetime import timedelta

import pytest

from app.domain.planner import Block, Busy, FixedBlock, PlanSettings, Quota, RiskReason

from .test_planner import FRI, MON, NO_REST, STUDY, SUN, TUE, WED, at, parts, plan, risks, start

NEXT_MON = MON + timedelta(days=7)
TAG = "project:vkr"
WEEK = Quota("quota:vkr", TAG, MON, NEXT_MON, 180)


def reserve(k: int, minutes: int = 90, **kw) -> Block:
    return Block(
        f"res{k}",
        minutes,
        group_id=TAG,
        windows=STUDY,
        earliest=at(MON, 0),
        deadline=at(NEXT_MON, 0),
        buffer_days=0,
        quota=TAG,
        reserve=True,
        **kw,
    )


def placed(result, *ids) -> list:
    return [i for i in ids if parts(result, i)]


@pytest.mark.parametrize("limit", [0, 0.5])
def test_reserve_fills_quota(limit):
    result = plan(reserve(0), reserve(1), quotas=(WEEK,), settings=NO_REST, time_limit_s=limit)
    assert placed(result, "res0", "res1") == ["res0", "res1"]
    assert result.at_risk == ()


@pytest.mark.parametrize("limit", [0, 0.5])
def test_project_task_counts_toward_quota(limit):
    """Шаг задания проекта на 2 часа — резерва нужно только на остаток."""
    step = Block("step", 120, group_id="task", quota=TAG, deadline=at(FRI, 20))
    result = plan(
        step, reserve(0), reserve(1), quotas=(WEEK,), settings=NO_REST, time_limit_s=limit
    )
    assert parts(result, "step")
    assert len(placed(result, "res0", "res1")) == 1
    assert result.at_risk == ()


@pytest.mark.parametrize("limit", [0, 0.5])
def test_fixed_project_time_counts(limit):
    """Сделанное сегодня (закреплённое) уже засчитано — резерв не нужен."""
    done = FixedBlock("event:1", at(MON, 6), at(MON, 7, 30), quota=TAG)
    done2 = FixedBlock("event:2", at(MON, 7, 30), at(MON, 9), quota=TAG)
    result = plan(
        reserve(0),
        reserve(1),
        fixed=(done, done2),
        quotas=(WEEK,),
        now=at(MON, 9),
        settings=NO_REST,
        time_limit_s=limit,
    )
    assert placed(result, "res0", "res1") == []
    assert result.at_risk == ()


@pytest.mark.parametrize("limit", [0, 0.5])
def test_reserve_only_in_its_week(limit):
    nxt = Quota("quota:next", TAG, NEXT_MON, NEXT_MON + timedelta(days=7), 90)
    late = Block(
        "next0",
        90,
        group_id=TAG,
        windows=STUDY,
        earliest=at(NEXT_MON, 0),
        deadline=at(NEXT_MON + timedelta(days=7), 0),
        buffer_days=0,
        quota=TAG,
        reserve=True,
    )
    result = plan(reserve(0), late, quotas=(WEEK, nxt), settings=NO_REST, time_limit_s=limit)
    assert start(result, "res0") < at(NEXT_MON, 0) <= start(result, "next0")


@pytest.mark.parametrize("limit", [0, 0.5])
def test_quota_beats_backlog(limit):
    """Свободно 90 минут: их получает норма, а не (даже старое) дело из ящика."""
    busy = (Busy(at(MON, 7), at(MON, 14)), Busy(at(MON, 15, 30), at(MON, 23, 59)))
    busy += tuple(Busy(at(d, 0), at(d, 23, 59)) for d in (TUE, WED, MON + timedelta(days=3)))
    busy += tuple(Busy(at(d, 0), at(d, 23, 59)) for d in (FRI, FRI + timedelta(days=1), SUN))
    box = Block("box", 90, filler=True, priority=8, deadline=at(NEXT_MON, 0), buffer_days=0)
    result = plan(
        box,
        reserve(0),
        busy=busy,
        quotas=(Quota("q", TAG, MON, NEXT_MON, 90),),
        settings=PlanSettings(lunch=None, free_evenings_per_week=0, weekend_half_days=0),
        time_limit_s=limit,
    )
    assert parts(result, "res0") == [(at(MON, 14), at(MON, 15, 30))]
    assert not parts(result, "box")


@pytest.mark.parametrize("limit", [0, 0.5])
def test_quota_does_not_make_task_late(limit):
    """Свободно ровно 2 часа до внутреннего срока задания: их получает задание,
    норма недобрана — угроза `quota`, а не опоздание."""
    busy = (Busy(at(MON, 7), at(MON, 14)), Busy(at(MON, 16), at(TUE, 23, 59)))
    task = Block("task", 120, deadline=at(WED, 12), buffer_days=1)
    result = plan(
        task,
        reserve(0, 120),
        busy=busy,
        quotas=(Quota("q", TAG, MON, TUE, 120),),
        settings=PlanSettings(lunch=None, free_evenings_per_week=0, weekend_half_days=0),
        time_limit_s=limit,
    )
    assert parts(result, "task") == [(at(MON, 14), at(MON, 16))]
    assert risks(result) == {"q": RiskReason.quota}


@pytest.mark.parametrize("limit", [0, 0.5])
def test_unplaced_reserve_is_not_a_risk_itself(limit):
    """Резерв не влез — угроза одна, на норму; блоки резерва в угрозах не значатся."""
    busy = tuple(
        Busy(at(MON + timedelta(days=i), 0), at(MON + timedelta(days=i), 23, 59)) for i in range(7)
    )
    result = plan(
        reserve(0), reserve(1), busy=busy, quotas=(WEEK,), settings=NO_REST, time_limit_s=limit
    )
    assert risks(result) == {"quota:vkr": RiskReason.quota}
    assert result.at_risk[0].group_id == TAG


def test_small_shortfall_is_not_a_risk():
    """Недобор меньше получаса угрозой не считается."""
    result = plan(reserve(0, 60), quotas=(Quota("q", TAG, MON, NEXT_MON, 75),), settings=NO_REST)
    assert parts(result, "res0")
    assert result.at_risk == ()


def test_no_reserve_when_quota_already_met_by_tasks():
    steps = [
        Block(f"s{i}", 90, group_id=f"t{i}", quota=TAG, deadline=at(WED, 20)) for i in range(2)
    ]
    result = plan(*steps, reserve(0), quotas=(WEEK,), settings=NO_REST)
    assert not parts(result, "res0")
    assert all(parts(result, f"s{i}") for i in range(2))
