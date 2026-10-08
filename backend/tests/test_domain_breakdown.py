"""M10.2: черновик разбивки (domain/breakdown) и свободное время до дедлайна."""

from datetime import date, datetime, time, timedelta

import pytest

from app.core.time import get_tz, wall_to_utc
from app.domain.breakdown import (
    RawStep,
    fmt_minutes,
    normalize_steps,
    round_estimate,
    time_warning,
)
from app.domain.planner import Block, Busy, PlanInput, PlanSettings, Window, free_minutes

TZ = get_tz("Europe/Moscow")
MON = date(2026, 10, 12)
ALL_DAYS = frozenset(range(1, 8))


def at(d: date, h: int, m: int = 0) -> datetime:
    return wall_to_utc(d, time(h, m), TZ)


# ---------- оценки ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(5, 15), (15, 15), (22, 20), (23, 25), (60, 60), (119, 120), (180, 120), (0, 15), (47.5, 50)],
)
def test_round_estimate(raw, expected):
    assert round_estimate(raw) == expected


def test_fmt_minutes():
    assert fmt_minutes(45) == "45 мин"
    assert fmt_minutes(120) == "2 ч"
    assert fmt_minutes(210) == "3 ч 30 мин"


# ---------- шаги ----------


def step(order, title=None, deps=(), est=30):
    return RawStep(order, title or f"s{order}", est, "study", tuple(deps))


def test_sorted_by_order_and_deps_become_indices():
    draft = normalize_steps([step(3, deps=[1, 2]), step(1), step(2, deps=[1])])
    assert [s.title for s in draft.steps] == ["s1", "s2", "s3"]
    # 3 после 1 — уже через 2
    assert [s.depends_on for s in draft.steps] == [(), (0,), (1,)]
    assert draft.total_estimate_min == 90


def test_dependency_moves_step_after_its_prerequisite():
    """ИИ поставил «написать» (1) раньше «найти источники» (2), но 1 зависит от 2."""
    draft = normalize_steps([step(1, "написать", deps=[2]), step(2, "найти"), step(3, "сдать")])
    assert [s.title for s in draft.steps] == ["найти", "написать", "сдать"]
    assert draft.steps[1].depends_on == (0,)


def test_transitive_deps_reduced_but_parallel_kept():
    draft = normalize_steps(
        [step(1), step(2), step(3, deps=[1, 2]), step(4, deps=[1, 2, 3]), step(5, deps=[1])]
    )
    assert [s.depends_on for s in draft.steps] == [(), (), (0, 1), (2,), (0,)]


def test_unknown_self_and_duplicate_refs_dropped():
    draft = normalize_steps([step(1, deps=[1, 9]), step(2, deps=[1, 1])])
    assert [s.depends_on for s in draft.steps] == [(), (0,)]


def test_cycle_is_broken_not_fatal():
    draft = normalize_steps([step(1, deps=[2]), step(2, deps=[1]), step(3, deps=[2])])
    assert len(draft.steps) == 3
    for i, s in enumerate(draft.steps):
        assert all(d < i for d in s.depends_on)


def test_duplicate_orders_keep_answer_order():
    draft = normalize_steps([step(1, "a"), step(1, "b"), step(2, "c", deps=[1])])
    assert [s.title for s in draft.steps] == ["a", "b", "c"]
    assert draft.steps[2].depends_on == (0,)


def test_estimates_clamped():
    draft = normalize_steps([step(1, est=5), step(2, est=300)])
    assert [s.estimate_min for s in draft.steps] == [15, 120]


def test_empty():
    assert normalize_steps([]).steps == []


# ---------- предупреждение ----------


def test_time_warning():
    assert time_warning(120, None) is None
    assert time_warning(120, 600) is None
    assert "Впритык" in time_warning(120, 140)
    assert "не всё успеется" in time_warning(300, 200)
    # Калибровка: «делаю в 1.5 раза дольше» → 120 мин превращаются в 180
    assert "не всё успеется" in time_warning(120, 150, coef=1.5)
    assert time_warning(60, 0) == "До дедлайна свободного времени не осталось"


# ---------- свободное время ----------


def plan(*blocks, busy=(), now=None, **settings):
    return PlanInput(
        now=now or at(MON, 0),
        tz=TZ,
        blocks=blocks,
        busy=busy,
        settings=PlanSettings(**settings) if settings else PlanSettings(),
    )


def test_free_minutes_counts_work_hours_and_study_limit():
    # Пн: рабочие часы 9–21 минус обед = 11 ч, но лимит учёбы по умолчанию меньше
    inp = plan()
    limit = PlanSettings().study_limit_min_per_day
    assert free_minutes(inp, deadline=at(MON + timedelta(days=1), 0)) == min(11 * 60, limit)


def test_free_minutes_without_study_limit_for_non_study():
    inp = plan()
    assert free_minutes(inp, deadline=at(MON, 12), counts_as_study=False) == 3 * 60


def test_free_minutes_subtracts_busy_and_competing_blocks():
    deadline = at(MON, 13)
    busy = (Busy(at(MON, 10), at(MON, 11), is_class=False),)
    competing = Block("x", 60, group_id="other", deadline=at(MON, 12))
    later = Block("y", 60, group_id="other", deadline=at(MON + timedelta(days=3), 12))
    mine = Block("m", 60, group_id="me", deadline=at(MON, 12))
    inp = plan(competing, later, mine, busy=busy)
    # 9–13 = 4 ч, минус пара 1 ч, минус «x» 1 ч; свои блоки и более поздний «y» не мешают
    assert free_minutes(inp, deadline=deadline, counts_as_study=False, exclude_group="me") == 2 * 60


def test_free_minutes_respects_windows():
    thursday_only = (Window(frozenset({4}), time(10), time(12)),)
    inp = plan()
    deadline = at(MON + timedelta(days=7), 0)
    assert free_minutes(inp, deadline=deadline, windows=thursday_only) == 2 * 60


def test_free_minutes_overdue_is_zero():
    inp = plan(now=at(MON, 15))
    assert free_minutes(inp, deadline=at(MON, 10)) == 0


def test_free_minutes_all_day_window():
    window = (Window(ALL_DAYS, time(0), time(0)),)
    inp = plan()
    # Окно на весь день, но сон всё равно вычитается
    assert free_minutes(inp, deadline=at(MON, 12), windows=window, counts_as_study=False) > 0
