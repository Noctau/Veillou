from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest

from app.domain import recurrence
from app.domain.recurrence import (
    DateRange,
    DayCyclePattern,
    OncePattern,
    PeriodSpec,
    RRulePattern,
    RuleSpec,
    Slot,
    SlotGridSpec,
    WeeklyPattern,
    cycle_week,
    expand_rule,
    parse_rrule,
    rrule_dates,
    validate_pattern,
)

MSK = ZoneInfo("Europe/Moscow")
BERLIN = ZoneInfo("Europe/Berlin")

# 1 сентября 2026 — вторник; занятия до 27 декабря (вс); цикл 2 недели (числитель = 1)
FALL = PeriodSpec(start=date(2026, 9, 1), end=date(2026, 12, 27), cycle_weeks=2)
GRID = SlotGridSpec.from_slots(
    [
        Slot(1, time(9, 0), time(10, 35)),
        Slot(2, time(10, 45), time(12, 20)),
        Slot(3, time(13, 0), time(14, 35)),
    ],
    {6: [Slot(1, time(9, 30), time(11, 0))]},  # в субботу свои слоты
)
WIDE = DateRange(date(2026, 1, 1), date(2027, 12, 31))


def dates(occurrences) -> list[date]:
    return [o.date for o in occurrences]


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def weekly(key, weekday, *, mask=None, **kw) -> RuleSpec:
    pattern = WeeklyPattern(frozenset({weekday}), frozenset(mask) if mask else None)
    return RuleSpec(key, pattern, **kw)


def expand(rule, *, period=FALL, grid=GRID, window=WIDE, tz=MSK, days_off=()):
    return expand_rule(rule, tz=tz, window=window, period=period, grid=grid, days_off=days_off)


# ---------- неделя цикла ----------


def test_cycle_week_first_week_and_alternation():
    # Неделя 31.08–06.09 содержит начало периода -> неделя 1 (бывший числитель)
    assert cycle_week(date(2026, 8, 31), FALL) == 1
    assert cycle_week(date(2026, 9, 6), FALL) == 1
    assert cycle_week(date(2026, 9, 7), FALL) == 2
    assert cycle_week(date(2026, 9, 14), FALL) == 1
    second = PeriodSpec(FALL.start, FALL.end, cycle_weeks=2, first_cycle_week=2)
    assert cycle_week(date(2026, 9, 7), second) == 1


def test_cycle_week_alternates_across_new_year():
    # В 2026 году 53 ISO-недели: по номерам недель чётность бы «сломалась»
    period = PeriodSpec(date(2026, 12, 21), date(2027, 3, 1), cycle_weeks=2)
    assert cycle_week(date(2026, 12, 28), period) == 2  # ISO 53
    assert cycle_week(date(2027, 1, 4), period) == 1  # ISO 1
    assert cycle_week(date(2027, 1, 11), period) == 2  # ISO 2


def test_cycle_week_without_cycle_is_always_one():
    period = PeriodSpec(FALL.start, FALL.end)
    assert {cycle_week(date(2026, 9, 1) + timedelta(weeks=i), period) for i in range(8)} == {1}


def test_three_week_cycle_mask_1_3():
    period = PeriodSpec(date(2026, 9, 1), date(2026, 11, 30), cycle_weeks=3)
    occ = expand(weekly("x", 2, mask=[1, 3], slot_from=1), period=period)
    # Вт: 01.09 (1), 08.09 (2 — нет), 15.09 (3), 22.09 (1), 29.09 (2 — нет), 06.10 (3)
    assert dates(occ)[:4] == [
        date(2026, 9, 1),
        date(2026, 9, 15),
        date(2026, 9, 22),
        date(2026, 10, 6),
    ]
    assert all(cycle_week(d, period) in (1, 3) for d in dates(occ))


# ---------- по дням недели ----------


def test_weekly_rule_first_week_midweek_start():
    # Понедельник: первая неделя (31.08) до начала периода -> первое вхождение 07.09
    occ = expand(weekly("mon", 1, slot_from=1))
    assert occ[0].date == date(2026, 9, 7)
    assert len(occ) == 16  # 07.09 … 21.12
    # Вторник: первое вхождение — в день начала периода
    assert expand(weekly("tue", 2, slot_from=1))[0].date == date(2026, 9, 1)


def test_cycle_weeks_mask_odd_and_even():
    odd = expand(weekly("o", 2, mask=[1], slot_from=2))
    even = expand(weekly("e", 2, mask=[2], slot_from=2))
    assert dates(odd)[:3] == [date(2026, 9, 1), date(2026, 9, 15), date(2026, 9, 29)]
    assert dates(even)[:3] == [date(2026, 9, 8), date(2026, 9, 22), date(2026, 10, 6)]
    every = expand(weekly("a", 2, slot_from=2))
    assert sorted(dates(odd) + dates(even)) == dates(every)


def test_several_weekdays():
    rule = RuleSpec("x", WeeklyPattern(frozenset({2, 4})), start_time=time(19), end_time=time(20))
    occ = expand(rule, period=None, window=DateRange(date(2026, 10, 5), date(2026, 10, 11)))
    assert dates(occ) == [date(2026, 10, 6), date(2026, 10, 8)]


def test_time_is_wall_time_in_user_tz():
    occ = expand(weekly("x", 2, slot_from=1))[0]
    assert occ.start == utc(2026, 9, 1, 6, 0)  # 09:00 МСК
    assert occ.end == utc(2026, 9, 1, 7, 35)
    assert occ.slot == 1


def test_dst_keeps_wall_time():
    # В Берлине 25.10.2026 переход на зимнее время: 09:00 остаётся 09:00 по местному
    period = PeriodSpec(date(2026, 10, 19), date(2026, 10, 26))
    occ = expand(weekly("x", 1, slot_from=1), period=period, tz=BERLIN)
    assert [o.start for o in occ] == [utc(2026, 10, 19, 7, 0), utc(2026, 10, 26, 8, 0)]


def test_slot_range_from_to():
    occ = expand(weekly("x", 2, slot_from=1, slot_to=2))[0]
    assert (occ.start, occ.end) == (utc(2026, 9, 1, 6, 0), utc(2026, 9, 1, 9, 20))


def test_slots_by_weekday():
    sat = expand(weekly("sat", 6, slot_from=1))
    assert sat[0].start == utc(2026, 9, 5, 6, 30)  # 09:30 по субботней сетке
    # Во вторник переопределения нет — общие слоты
    assert expand(weekly("tue", 2, slot_from=1))[0].start == utc(2026, 9, 1, 6, 0)
    # В субботу 2-го слота нет -> вхождений нет
    assert expand(weekly("s2", 6, slot_from=2)) == []
    # Без сетки слоты ничего не дают
    assert expand(weekly("ng", 2, slot_from=1), grid=None) == []


def test_custom_time_overrides_slots():
    rule = weekly("x", 2, slot_from=5, start_time=time(18, 30), end_time=time(20))
    occ = expand(rule)[0]
    assert (occ.start, occ.end) == (utc(2026, 9, 1, 15, 30), utc(2026, 9, 1, 17, 0))


# ---------- границы, паузы, исключения ----------


def test_single_day_off_skipped():
    # 4 ноября (ср) — праздник
    off = [DateRange(date(2026, 11, 4), date(2026, 11, 4))]
    occ = expand(weekly("wed", 3, slot_from=1), days_off=off)
    assert date(2026, 11, 4) not in dates(occ)
    assert date(2026, 10, 28) in dates(occ)
    assert date(2026, 11, 11) in dates(occ)


def test_day_off_range_skips_whole_week():
    off = DateRange(date(2026, 11, 2), date(2026, 11, 8))
    occ = [o for wd in range(1, 7) for o in expand(weekly(wd, wd, slot_from=1), days_off=[off])]
    assert not [d for d in dates(occ) if d in off]
    assert date(2026, 11, 9) in dates(occ)


def test_period_bounds():
    # Вс 27.12 — последний день периода
    occ = expand(weekly("sun", 7, start_time=time(10), end_time=time(11)))
    assert dates(occ)[0] == date(2026, 9, 6)
    assert dates(occ)[-1] == date(2026, 12, 27)
    assert dates(expand(weekly("mon", 1, slot_from=1)))[-1] == date(2026, 12, 21)


def test_period_pause():
    # Сессия — пауза в конце периода; каникулы — посреди
    period = PeriodSpec(
        date(2026, 9, 1),
        date(2027, 1, 25),
        cycle_weeks=2,
        pauses=(
            DateRange(date(2026, 11, 2), date(2026, 11, 8)),
            DateRange(date(2026, 12, 28), date(2027, 1, 25)),
        ),
    )
    occ = expand(weekly("mon", 1, slot_from=1), period=period)
    assert date(2026, 11, 2) not in dates(occ)
    assert date(2026, 11, 9) in dates(occ)
    assert dates(occ)[-1] == date(2026, 12, 21)
    # Неделя цикла после паузы не сбивается: 09.11 — неделя 2, как и без паузы
    assert cycle_week(date(2026, 11, 9), period) == cycle_week(date(2026, 11, 9), FALL)


def test_valid_from_to_clip_rule():
    rule = weekly("x", 2, slot_from=1, valid_from=date(2026, 10, 1), valid_to=date(2026, 10, 31))
    assert dates(expand(rule)) == [
        date(2026, 10, 6),
        date(2026, 10, 13),
        date(2026, 10, 20),
        date(2026, 10, 27),
    ]
    # Срок действия вне периода -> пусто
    assert expand(weekly("y", 2, slot_from=1, valid_from=date(2027, 2, 1))) == []


def test_window_limits():
    window = DateRange(date(2026, 9, 7), date(2026, 9, 13))
    assert dates(expand(weekly("thu", 4, slot_from=2), window=window)) == [date(2026, 9, 10)]


# ---------- смены «N через M» ----------


def test_two_on_two_off_anchor_in_past():
    anchor = date(2020, 1, 1)  # якорь давно в прошлом: считается по модулю, без перебора
    rule = RuleSpec("shift", DayCyclePattern(2, 2, anchor), start_time=time(8), end_time=time(20))
    window = DateRange(date(2026, 10, 1), date(2026, 10, 14))
    occ = expand(rule, period=None, window=window)
    assert all((d - anchor).days % 4 < 2 for d in dates(occ))
    assert len(occ) == 7
    # Подряд по два дня, потом два выходных
    days = dates(occ)
    pairs = {(b - a).days for a, b in pairwise(days)}
    assert pairs <= {1, 3}


def test_two_on_two_off_anchor_in_future():
    anchor = date(2026, 10, 12)
    rule = RuleSpec("s", DayCyclePattern(2, 2, anchor), start_time=time(8), end_time=time(20))
    occ = expand(rule, period=None, window=DateRange(date(2026, 10, 1), date(2026, 10, 15)))
    # До якоря цикл продолжается назад: …, 01, 04, 05, 08, 09, 12, 13
    assert dates(occ) == [
        date(2026, 10, 1),
        date(2026, 10, 4),
        date(2026, 10, 5),
        date(2026, 10, 8),
        date(2026, 10, 9),
        date(2026, 10, 12),
        date(2026, 10, 13),
    ]


def test_day_on_three_off_24h():
    # Сутки через трое: 08:00 → 08:00 следующего дня
    rule = RuleSpec(
        "d", DayCyclePattern(1, 3, date(2026, 10, 1)), start_time=time(8), end_time=time(8)
    )
    occ = expand(rule, period=None, window=DateRange(date(2026, 10, 1), date(2026, 10, 12)))
    assert dates(occ) == [date(2026, 10, 1), date(2026, 10, 5), date(2026, 10, 9)]
    assert occ[0].end - occ[0].start == timedelta(hours=24)


def test_night_shift_over_midnight_dst_neutral():
    # Ночная 20:00–08:00 в ночь перехода на зимнее время (25.10, Берлин): настенное
    # время сохраняется, длина смены в UTC — 13 ч
    rule = RuleSpec(
        "n", DayCyclePattern(1, 1, date(2026, 10, 22)), start_time=time(20), end_time=time(8)
    )
    occ = expand(
        rule, period=None, tz=BERLIN, window=DateRange(date(2026, 10, 22), date(2026, 10, 26))
    )
    assert dates(occ) == [date(2026, 10, 22), date(2026, 10, 24), date(2026, 10, 26)]
    night = occ[1]
    assert night.start == utc(2026, 10, 24, 18)  # 20:00 CEST
    assert night.end == utc(2026, 10, 25, 7)  # 08:00 CET
    assert occ[0].end - occ[0].start == timedelta(hours=12)


def test_day_off_in_middle_of_shift_cycle():
    # Исключение выкидывает смену, но цикл не сдвигается
    anchor = date(2026, 10, 1)
    rule = RuleSpec("s", DayCyclePattern(2, 2, anchor), start_time=time(8), end_time=time(20))
    period = PeriodSpec(date(2026, 10, 1), date(2026, 10, 31))
    window = DateRange(date(2026, 10, 1), date(2026, 10, 12))
    off = [DateRange(date(2026, 10, 5), date(2026, 10, 5))]
    occ = expand(rule, period=period, window=window, days_off=off)
    assert dates(occ) == [
        date(2026, 10, 1),
        date(2026, 10, 2),
        date(2026, 10, 6),
        date(2026, 10, 9),
        date(2026, 10, 10),
    ]


# ---------- RRULE и разово ----------


def test_rrule_monthly_second_tuesday():
    rule = RuleSpec(
        "r", RRulePattern("FREQ=MONTHLY;BYDAY=2TU"), start_time=time(19), end_time=time(20)
    )
    occ = expand(rule, period=None, window=DateRange(date(2026, 10, 1), date(2026, 12, 31)))
    assert dates(occ) == [date(2026, 10, 13), date(2026, 11, 10), date(2026, 12, 8)]
    assert (occ[0].start, occ[0].end) == (utc(2026, 10, 13, 16), utc(2026, 10, 13, 17))


def test_rrule_interval_anchored_at_valid_from():
    rule = RuleSpec(
        "r",
        RRulePattern("FREQ=WEEKLY;INTERVAL=2;BYDAY=TU"),
        start_time=time(8),
        end_time=time(9),
        valid_from=date(2026, 10, 13),
    )
    occ = expand(rule, period=None, window=DateRange(date(2026, 10, 1), date(2026, 11, 10)))
    assert dates(occ) == [date(2026, 10, 13), date(2026, 10, 27), date(2026, 11, 10)]


def test_rrule_overnight_and_dst():
    rule = RuleSpec(
        "r",
        RRulePattern("FREQ=WEEKLY;BYDAY=SA"),
        start_time=time(23),
        end_time=time(1),
        valid_from=date(2026, 10, 17),
    )
    occ = expand(
        rule, period=None, tz=BERLIN, window=DateRange(date(2026, 10, 17), date(2026, 10, 31))
    )
    # 23:00 по Берлину: летом 21:00Z, после 25.10 — 22:00Z; конец — на следующий день
    assert [o.start for o in occ] == [
        utc(2026, 10, 17, 21),
        utc(2026, 10, 24, 21),
        utc(2026, 10, 31, 22),
    ]
    assert occ[0].end == utc(2026, 10, 17, 23)


def test_once():
    rule = RuleSpec("o", OncePattern(date(2026, 10, 20)), start_time=time(10), end_time=time(12))
    assert dates(expand(rule, period=None)) == [date(2026, 10, 20)]
    assert expand(rule, period=None, window=DateRange(date(2026, 11, 1), date(2026, 11, 30))) == []


# ---------- защита ----------


@pytest.mark.parametrize(
    "pattern",
    [
        WeeklyPattern(frozenset()),
        WeeklyPattern(frozenset({8})),
        WeeklyPattern(frozenset({1}), frozenset({0})),
        DayCyclePattern(0, 2, date(2026, 1, 1)),
        DayCyclePattern(1, -1, date(2026, 1, 1)),
        DayCyclePattern(300, 100, date(2026, 1, 1)),
        RRulePattern("FREQ=HOURLY"),
    ],
)
def test_validate_pattern_rejects_impossible(pattern):
    with pytest.raises(ValueError, match=r"(?i)дни|недел|смен|повтор"):
        validate_pattern(pattern)


def test_span_is_capped():
    # Огромное окно без периода — не дальше MAX_SPAN_DAYS от начала
    rule = RuleSpec(
        "d", DayCyclePattern(1, 0, date(2000, 1, 1)), start_time=time(8), end_time=time(9)
    )
    occ = expand(rule, period=None, window=DateRange(date(2000, 1, 1), date(2100, 12, 31)))
    assert len(occ) == recurrence.MAX_SPAN_DAYS + 1
    assert occ[-1].date == date(2000, 1, 1) + timedelta(days=recurrence.MAX_SPAN_DAYS)


def test_occurrences_are_capped(monkeypatch):
    monkeypatch.setattr(recurrence, "MAX_OCCURRENCES", 10)
    rule = RuleSpec("d", RRulePattern("FREQ=DAILY"), start_time=time(8), end_time=time(9))
    assert len(expand(rule, period=None)) == 10


@pytest.mark.parametrize(
    "value",
    ["", "FREQ=HOURLY", "FREQ=WEEKLY;BYHOUR=10", "DTSTART:20260101\nRRULE:FREQ=DAILY", "bogus"],
)
def test_parse_rrule_rejects(value):
    with pytest.raises(ValueError, match=r"(?i)повтор|правил"):
        parse_rrule(value)


def test_impossible_rrule_has_no_occurrences():
    assert not recurrence.has_occurrences("FREQ=DAILY;BYMONTH=2;BYMONTHDAY=30")
    assert recurrence.has_occurrences("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29")


def test_rrule_dates_window_and_start():
    window = DateRange(date(2026, 10, 6), date(2026, 10, 31))
    # По четвергам с 1 октября — в окне с 6-го: 8, 15, 22, 29
    found = rrule_dates("FREQ=WEEKLY;BYDAY=TH", dtstart=date(2026, 10, 1), window=window)
    assert found == [date(2026, 10, 8), date(2026, 10, 15), date(2026, 10, 22), date(2026, 10, 29)]
    # Раз в две недели, начало позже окна
    found = rrule_dates(
        "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU", dtstart=date(2026, 10, 13), window=window
    )
    assert found == [date(2026, 10, 13), date(2026, 10, 27)]
    assert rrule_dates("FREQ=DAILY", dtstart=date(2026, 11, 1), window=window) == []
    until = rrule_dates(
        "FREQ=DAILY", dtstart=date(2026, 10, 1), window=window, until=date(2026, 10, 7)
    )
    assert until == [date(2026, 10, 6), date(2026, 10, 7)]
