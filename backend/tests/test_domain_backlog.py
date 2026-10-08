"""M11.2–M11.3: ящик в плане — неделя, окна по условиям, приоритет, выбор дел."""

from datetime import date, time

from app.domain.backlog import (
    Candidate,
    condition_windows,
    intersect_windows,
    priority,
    review_week,
    suggest,
    week_start,
)
from app.domain.enums import BacklogCondition
from app.domain.planner import Window

MON = date(2026, 10, 12)
ALL = frozenset(range(1, 8))
WEEKDAYS = frozenset({1, 2, 3, 4, 5})


def w(days, start: str, end: str) -> Window:
    return Window(frozenset(days), time.fromisoformat(start), time.fromisoformat(end))


def test_week_start_and_review_week():
    assert week_start(date(2026, 10, 15)) == MON
    assert week_start(MON) == MON
    assert review_week(date(2026, 10, 14)) == MON  # среда — текущая неделя
    assert review_week(date(2026, 10, 17)) == date(2026, 10, 19)  # суббота — следующая
    assert review_week(date(2026, 10, 18)) == date(2026, 10, 19)  # воскресенье


def test_intersect_simple():
    assert intersect_windows([w(ALL, "09:00", "21:00")], [w(WEEKDAYS, "10:00", "18:00")]) == (
        w(WEEKDAYS, "10:00", "18:00"),
    )


def test_intersect_disjoint_is_empty():
    assert intersect_windows([w({6, 7}, "10:00", "18:00")], [w(WEEKDAYS, "09:00", "18:00")]) == ()


def test_intersect_overnight_window():
    """Учёба 07:00–01:00 ∩ 23:00–02:00 → 23:00–00:00 того же дня и 00:00–01:00 следующего."""
    study = [w(ALL, "07:00", "01:00")]
    late = [w({1}, "23:00", "02:00")]
    assert intersect_windows(study, late) == (w({1}, "23:00", "00:00"), w({2}, "00:00", "01:00"))


def test_intersect_wraps_sunday_to_monday():
    sunday_night = [w({7}, "22:00", "02:00")]
    monday_early = [w({1}, "00:00", "01:00")]
    assert intersect_windows(sunday_night, monday_early) == (w({1}, "00:00", "01:00"),)


def test_intersect_keeps_different_hours_per_day():
    a = [w({1, 2}, "09:00", "19:00")]
    b = [w({1}, "12:00", "14:00"), w({2}, "16:00", "20:00")]
    assert intersect_windows(a, b) == (w({1}, "12:00", "14:00"), w({2}, "16:00", "19:00"))


def test_conditions_weekday_daytime():
    outside = [w(ALL, "09:00", "21:00")]
    assert condition_windows(outside, [BacklogCondition.weekday_daytime]) == (
        w(WEEKDAYS, "09:00", "18:00"),
    )


def test_conditions_institution_hours():
    home = [w(ALL, "08:00", "22:00")]
    inst = [w(WEEKDAYS, "10:00", "18:00")]
    assert condition_windows(home, [BacklogCondition.institution_hours], inst) == (
        w(WEEKDAYS, "10:00", "18:00"),
    )


def test_conditions_without_time_limits_keep_base():
    base = (w(ALL, "08:00", "22:00"),)
    conds = [BacklogCondition.needs_laptop, BacklogCondition.on_class_days]
    assert condition_windows(base, conds) == base


def test_priority_grows_with_age_and_desired_by():
    today = date(2026, 10, 20)
    assert priority(today, None, today) == 1
    assert priority(date(2026, 10, 6), None, today) == 3  # две недели
    assert priority(date(2025, 1, 1), None, today) == 5  # потолок возраста
    assert priority(today, date(2026, 10, 25), today) == 4  # срок на неделе
    assert priority(today, date(2026, 12, 1), today) == 1  # срок нескоро


def test_suggest_order():
    week = date(2026, 10, 19)
    old = Candidate("old", date(2026, 1, 1))
    new = Candidate("new", date(2026, 10, 1))
    desired = Candidate("desired", date(2026, 10, 10), desired_by=date(2026, 11, 1))
    carried = Candidate("carried", date(2026, 10, 15), planned_week=date(2026, 10, 12))
    taken = Candidate("taken", date(2025, 1, 1), planned_week=week)
    result = suggest([new, old, desired, carried, taken], week, 3)
    assert [c.id for c in result] == ["carried", "desired", "old"]


def test_suggest_limit_zero():
    assert suggest([Candidate("a", MON)], MON, 0) == []
