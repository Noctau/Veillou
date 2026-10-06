from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.domain.enums import Parity, RuleParity
from app.domain.recurrence import (
    Bells,
    BellSlot,
    ClassRuleSpec,
    DateRange,
    SemesterSpec,
    expand_class_rule,
    expand_class_rules,
    expand_rrule,
    parse_rrule,
    week_parity,
)

MSK = ZoneInfo("Europe/Moscow")
BERLIN = ZoneInfo("Europe/Berlin")

# 1 сентября 2026 — вторник; занятия до 27 декабря (вс), потом сессия
FALL = SemesterSpec(start=date(2026, 9, 1), classes_end=date(2026, 12, 27))
BELLS = Bells.from_slots(
    [
        BellSlot(1, time(9, 0), time(10, 35)),
        BellSlot(2, time(10, 45), time(12, 20)),
        BellSlot(3, time(13, 0), time(14, 35)),
    ],
    {6: [BellSlot(1, time(9, 30), time(11, 0))]},  # в субботу свои звонки
)


def dates(occurrences) -> list[date]:
    return [o.date for o in occurrences]


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


# ---------- чётность ----------


def test_parity_first_week_and_alternation():
    # Неделя 31.08–06.09 содержит начало семестра -> числитель
    assert week_parity(date(2026, 8, 31), FALL.start, Parity.odd) == Parity.odd
    assert week_parity(date(2026, 9, 6), FALL.start, Parity.odd) == Parity.odd
    assert week_parity(date(2026, 9, 7), FALL.start, Parity.odd) == Parity.even
    assert week_parity(date(2026, 9, 14), FALL.start, Parity.odd) == Parity.odd
    assert week_parity(date(2026, 9, 7), FALL.start, Parity.even) == Parity.odd


def test_parity_alternates_across_new_year():
    # В 2026 году 53 ISO-недели: по номерам недель чётность бы «сломалась»
    start = date(2026, 12, 21)
    assert week_parity(date(2026, 12, 28), start, Parity.odd) == Parity.even  # ISO 53
    assert week_parity(date(2027, 1, 4), start, Parity.odd) == Parity.odd  # ISO 1
    assert week_parity(date(2027, 1, 11), start, Parity.odd) == Parity.even  # ISO 2


# ---------- пары ----------


def test_weekly_rule_first_week_midweek_start():
    # Понедельник: первая неделя (31.08) до начала семестра -> первое вхождение 07.09
    rule = ClassRuleSpec("mon", weekday=1, pair_number=1)
    occ = expand_class_rule(rule, FALL, BELLS, MSK)
    assert occ[0].date == date(2026, 9, 7)
    assert len(occ) == 16  # 07.09 … 21.12
    # Вторник: первое вхождение — в день начала семестра
    occ = expand_class_rule(ClassRuleSpec("tue", weekday=2, pair_number=1), FALL, BELLS, MSK)
    assert occ[0].date == date(2026, 9, 1)


def test_odd_and_even_weeks():
    odd = expand_class_rule(
        ClassRuleSpec("o", weekday=2, pair_number=2, parity=RuleParity.odd), FALL, BELLS, MSK
    )
    even = expand_class_rule(
        ClassRuleSpec("e", weekday=2, pair_number=2, parity=RuleParity.even), FALL, BELLS, MSK
    )
    assert dates(odd)[:3] == [date(2026, 9, 1), date(2026, 9, 15), date(2026, 9, 29)]
    assert dates(even)[:3] == [date(2026, 9, 8), date(2026, 9, 22), date(2026, 10, 6)]
    every = expand_class_rule(ClassRuleSpec("a", weekday=2, pair_number=2), FALL, BELLS, MSK)
    assert sorted(dates(odd) + dates(even)) == dates(every)


def test_every_other_week_when_first_week_is_even():
    # «Через неделю, начиная со второй» при первой неделе-знаменателе = числитель
    sem = SemesterSpec(FALL.start, FALL.classes_end, first_week_parity=Parity.even)
    occ = expand_class_rule(
        ClassRuleSpec("x", weekday=2, pair_number=1, parity=RuleParity.odd), sem, BELLS, MSK
    )
    assert dates(occ)[:2] == [date(2026, 9, 8), date(2026, 9, 22)]


def test_time_is_wall_time_in_user_tz():
    occ = expand_class_rule(ClassRuleSpec("x", weekday=2, pair_number=1), FALL, BELLS, MSK)[0]
    assert occ.start == utc(2026, 9, 1, 6, 0)  # 09:00 МСК
    assert occ.end == utc(2026, 9, 1, 7, 35)
    assert occ.pair_number == 1


def test_dst_keeps_wall_time():
    # В Берлине 25.10.2026 переход на зимнее время: 09:00 остаётся 09:00 по местному
    sem = SemesterSpec(date(2026, 10, 19), date(2026, 10, 26))
    occ = expand_class_rule(ClassRuleSpec("x", weekday=1, pair_number=1), sem, BELLS, BERLIN)
    assert [o.start for o in occ] == [utc(2026, 10, 19, 7, 0), utc(2026, 10, 26, 8, 0)]


def test_single_holiday_skipped():
    # 4 ноября (ср) — праздник
    rule = ClassRuleSpec("wed", weekday=3, pair_number=1)
    occ = expand_class_rule(
        rule, FALL, BELLS, MSK, days_off=[DateRange(date(2026, 11, 4), date(2026, 11, 4))]
    )
    assert date(2026, 11, 4) not in dates(occ)
    assert date(2026, 10, 28) in dates(occ) and date(2026, 11, 11) in dates(occ)


def test_holiday_range_skips_whole_week():
    off = DateRange(date(2026, 11, 2), date(2026, 11, 8))
    occ = expand_class_rules(
        [ClassRuleSpec(wd, weekday=wd, pair_number=1) for wd in range(1, 7)],
        FALL,
        BELLS,
        MSK,
        days_off=[off],
    )
    assert not [d for d in dates(occ) if d in off]
    assert date(2026, 11, 9) in dates(occ)


def test_semester_bounds_no_classes_in_session():
    # Вс 27.12 — последний день занятий; дальше сессия
    rule = ClassRuleSpec("sun", weekday=7, start_time=time(10), end_time=time(11))
    occ = expand_class_rule(rule, FALL, BELLS, MSK)
    assert dates(occ)[-1] == date(2026, 12, 27)
    assert dates(occ)[0] == date(2026, 9, 6)
    mon = expand_class_rule(ClassRuleSpec("mon", weekday=1, pair_number=1), FALL, BELLS, MSK)
    assert dates(mon)[-1] == date(2026, 12, 21)


def test_valid_from_to_clip_rule():
    rule = ClassRuleSpec(
        "x", weekday=2, pair_number=1, valid_from=date(2026, 10, 1), valid_to=date(2026, 10, 31)
    )
    occ = expand_class_rule(rule, FALL, BELLS, MSK)
    assert dates(occ) == [
        date(2026, 10, 6),
        date(2026, 10, 13),
        date(2026, 10, 20),
        date(2026, 10, 27),
    ]
    # Срок действия вне семестра -> пусто
    outside = ClassRuleSpec("y", weekday=2, pair_number=1, valid_from=date(2027, 2, 1))
    assert expand_class_rule(outside, FALL, BELLS, MSK) == []


def test_weekday_bell_override():
    sat = expand_class_rule(ClassRuleSpec("sat", weekday=6, pair_number=1), FALL, BELLS, MSK)
    assert sat[0].start == utc(2026, 9, 5, 6, 30)  # 09:30 по субботним звонкам
    # Во вторник переопределения нет — общие звонки
    tue = expand_class_rule(ClassRuleSpec("tue", weekday=2, pair_number=1), FALL, BELLS, MSK)
    assert tue[0].start == utc(2026, 9, 1, 6, 0)
    # В субботу 2-й пары нет в звонках -> вхождений нет
    assert expand_class_rule(ClassRuleSpec("s2", weekday=6, pair_number=2), FALL, BELLS, MSK) == []


def test_custom_time_overrides_bells():
    rule = ClassRuleSpec("x", weekday=2, pair_number=5, start_time=time(18, 30), end_time=time(20))
    occ = expand_class_rule(rule, FALL, BELLS, MSK)[0]
    assert (occ.start, occ.end) == (utc(2026, 9, 1, 15, 30), utc(2026, 9, 1, 17, 0))


def test_window_limits_and_sorting():
    rules = [
        ClassRuleSpec("late", weekday=2, pair_number=3),
        ClassRuleSpec("early", weekday=2, pair_number=1),
        ClassRuleSpec("thu", weekday=4, pair_number=2),
    ]
    window = DateRange(date(2026, 9, 7), date(2026, 9, 13))
    occ = expand_class_rules(rules, FALL, BELLS, MSK, window=window)
    assert [(o.key, o.date) for o in occ] == [
        ("early", date(2026, 9, 8)),
        ("late", date(2026, 9, 8)),
        ("thu", date(2026, 9, 10)),
    ]


# ---------- RRULE ----------


def test_rrule_weekly_tue_thu():
    occ = expand_rrule(
        "FREQ=WEEKLY;BYDAY=TU,TH",
        dtstart=date(2026, 10, 6),
        start_time=time(19),
        end_time=time(20, 30),
        tz=MSK,
        window=DateRange(date(2026, 10, 1), date(2026, 10, 18)),
    )
    assert dates(occ) == [
        date(2026, 10, 6),
        date(2026, 10, 8),
        date(2026, 10, 13),
        date(2026, 10, 15),
    ]
    assert (occ[0].start, occ[0].end) == (utc(2026, 10, 6, 16), utc(2026, 10, 6, 17, 30))


def test_rrule_until_and_count():
    common = {
        "dtstart": date(2026, 10, 5),
        "start_time": time(8),
        "end_time": time(9),
        "tz": MSK,
        "window": DateRange(date(2026, 10, 1), date(2026, 12, 31)),
    }
    assert len(expand_rrule("FREQ=DAILY", until=date(2026, 10, 9), **common)) == 5
    assert len(expand_rrule("RRULE:FREQ=WEEKLY;COUNT=3", **common)) == 3


def test_rrule_overnight_and_dst():
    occ = expand_rrule(
        "FREQ=WEEKLY;BYDAY=SA",
        dtstart=date(2026, 10, 17),
        start_time=time(23),
        end_time=time(1),
        tz=BERLIN,
        window=DateRange(date(2026, 10, 17), date(2026, 10, 31)),
    )
    # 23:00 по Берлину: летом 21:00Z, после 25.10 — 22:00Z; конец — на следующий день
    assert [o.start for o in occ] == [
        utc(2026, 10, 17, 21),
        utc(2026, 10, 24, 21),
        utc(2026, 10, 31, 22),
    ]
    assert occ[0].end == utc(2026, 10, 17, 23)


@pytest.mark.parametrize(
    "value",
    ["", "FREQ=HOURLY", "FREQ=WEEKLY;BYHOUR=10", "DTSTART:20260101\nRRULE:FREQ=DAILY", "bogus"],
)
def test_parse_rrule_rejects(value):
    with pytest.raises(ValueError):
        parse_rrule(value)
