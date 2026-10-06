import uuid
from datetime import date, datetime, time, timedelta

from app.core.time import get_tz, wall_to_utc
from app.domain.enums import ReminderKind
from app.notify.builder import (
    BlockInfo,
    Candidate,
    ClassInfo,
    DeadlineInfo,
    Planned,
    TimeRange,
    Window,
    adjust,
    build,
    class_candidates,
    deadline_candidates,
    digest_candidates,
    merge_close,
    next_allowed,
    subtask_candidates,
    windows_from_json,
)

TZ = get_tz("Europe/Moscow")
QUIET = TimeRange(time(22, 30), time(8, 0))
CH = ("push", "telegram")
WEEKDAYS = frozenset({1, 2, 3, 4, 5})
PEOPLE = (Window(WEEKDAYS, time(9, 0), time(19, 0)),)

# 2026-10-06 — вторник
TUE = date(2026, 10, 6)


def at(d: date, h: int, m: int = 0) -> datetime:
    return wall_to_utc(d, time(h, m), TZ)


def local(dt: datetime) -> tuple[date, time]:
    loc = dt.astimezone(TZ)
    return loc.date(), loc.time().replace(second=0, microsecond=0)


def cand(fire_at: datetime, **kw) -> Candidate:
    return Candidate(
        kind=ReminderKind.test, key=kw.pop("key", "k"), fire_at=fire_at, channels=CH, **kw
    )


# ---------- тихие часы ----------


def test_outside_quiet_hours_unchanged():
    assert adjust(cand(at(TUE, 12)), QUIET, TZ) == at(TUE, 12)


def test_late_evening_moves_to_quiet_end():
    assert adjust(cand(at(TUE, 23)), QUIET, TZ) == at(TUE + timedelta(days=1), 8)


def test_after_midnight_moves_to_same_morning():
    assert adjust(cand(at(TUE, 3)), QUIET, TZ) == at(TUE, 8)


def test_quiet_end_is_allowed_start_is_not():
    assert adjust(cand(at(TUE, 8)), QUIET, TZ) == at(TUE, 8)
    assert adjust(cand(at(TUE, 22, 30)), QUIET, TZ) == at(TUE + timedelta(days=1), 8)


def test_no_quiet_hours():
    assert adjust(cand(at(TUE, 3)), None, TZ) == at(TUE, 3)


def test_daytime_quiet_hours():
    quiet = TimeRange(time(13, 0), time(14, 0))
    assert adjust(cand(at(TUE, 13, 30)), quiet, TZ) == at(TUE, 14)


def test_expired_after_quiet_hours_is_dropped():
    # Пара в 8:00, напоминание в 7:45 — в тихие часы; к их концу пара уже началась
    c = cand(at(TUE, 7, 45), expires_at=at(TUE, 8))
    assert adjust(c, QUIET, TZ) is None


# ---------- окна типа действия ----------


def test_people_at_22_moves_to_next_morning():
    """«Написать научруку» в 22:00 вторника → среда 9:00."""
    c = cand(at(TUE, 22), windows=PEOPLE)
    assert adjust(c, QUIET, TZ) == at(TUE + timedelta(days=1), 9)


def test_people_on_friday_evening_moves_to_monday():
    fri = date(2026, 10, 9)
    c = cand(at(fri, 20), windows=PEOPLE)
    assert adjust(c, QUIET, TZ) == at(date(2026, 10, 12), 9)


def test_window_and_quiet_combine():
    # Окно 7:00–01:00, тихие часы до 8:00 → 8:00
    study = (Window(frozenset(range(1, 8)), time(7, 0), time(1, 0)),)
    assert adjust(cand(at(TUE, 7, 10), windows=study), QUIET, TZ) == at(TUE, 8)


def test_window_crossing_midnight_belongs_to_start_day():
    # Окно «только пн 20:00–02:00»: вторник 00:30 ещё внутри
    w = (Window(frozenset({1}), time(20, 0), time(2, 0)),)
    assert adjust(cand(at(TUE, 0, 30), windows=w), None, TZ) == at(TUE, 0, 30)


def test_moves_earlier_when_later_is_too_late():
    # Дедлайн в сб 12:00, напоминание в сб 8:00 для «связи с людьми» → пт 18:59
    sat = date(2026, 10, 10)
    c = cand(at(sat, 8), windows=PEOPLE, expires_at=at(sat, 12), allow_earlier=True)
    assert adjust(c, QUIET, TZ) == at(date(2026, 10, 9), 18, 59)


def test_without_allow_earlier_is_dropped():
    sat = date(2026, 10, 10)
    c = cand(at(sat, 8), windows=PEOPLE, expires_at=at(sat, 12))
    assert adjust(c, QUIET, TZ) is None


def test_windows_from_json():
    raw = [{"weekdays": [1, 2], "start": "09:00", "end": "19:00"}]
    assert windows_from_json(raw) == (Window(frozenset({1, 2}), time(9), time(19)),)
    assert windows_from_json(None) == ()


# ---------- склейка ----------


def _p(key: str, fire_at: datetime) -> Planned:
    return Planned(ReminderKind.test, key, fire_at, CH, None, None, None, {})


def test_merge_within_minute():
    base = at(TUE, 9)
    merged = merge_close([_p("a", base), _p("b", base + timedelta(seconds=40))])
    assert {p.fire_at for p in merged} == {base}


def test_merge_keeps_far_apart():
    base = at(TUE, 9)
    merged = merge_close([_p("a", base), _p("b", base + timedelta(minutes=2))])
    assert sorted(p.fire_at for p in merged) == [base, base + timedelta(minutes=2)]


def test_merge_does_not_chain():
    # 9:00, 9:00:50, 9:01:40 — третье дальше минуты от начала группы
    base = at(TUE, 9)
    merged = merge_close(
        [
            _p("a", base),
            _p("b", base + timedelta(seconds=50)),
            _p("c", base + timedelta(seconds=100)),
        ]
    )
    by_key = {p.key: p.fire_at for p in merged}
    assert by_key["a"] == by_key["b"] == base
    assert by_key["c"] == base + timedelta(seconds=100)


def test_deadline_merges_with_digest():
    t = DeadlineInfo(uuid.uuid4(), at(TUE + timedelta(days=3), 23, 59))
    cands = deadline_candidates([t], [3], time(8), TZ, CH) + digest_candidates(
        [TUE], time(8), TZ, CH
    )
    planned = build(cands, QUIET, TZ)
    assert len(planned) == 2
    assert {p.fire_at for p in planned} == {at(TUE, 8)}


# ---------- кандидаты ----------


def test_before_class_15_min():
    eid = uuid.uuid4()
    [p] = build(class_candidates([ClassInfo(eid, at(TUE, 10, 45))], 15, CH), QUIET, TZ)
    assert p.fire_at == at(TUE, 10, 30)
    assert p.expires_at == at(TUE, 10, 45)
    assert p.entity_id == eid
    assert p.key.startswith(f"before_class:{eid}:")


def test_moved_class_gets_new_key():
    eid = uuid.uuid4()
    a = class_candidates([ClassInfo(eid, at(TUE, 9))], 15, CH)[0]
    b = class_candidates([ClassInfo(eid, at(TUE, 12))], 15, CH)[0]
    assert a.key != b.key


def test_deadline_days_before_at_digest_time():
    due = at(date(2026, 10, 15), 23, 59)
    cands = deadline_candidates([DeadlineInfo(uuid.uuid4(), due)], [3, 1, 0], time(8), TZ, CH)
    assert sorted(local(c.fire_at) for c in cands) == [
        (date(2026, 10, 12), time(8)),
        (date(2026, 10, 14), time(8)),
        (date(2026, 10, 15), time(8)),
    ]
    assert len({c.key for c in cands}) == 3


def test_deadline_before_morning_skips_same_day():
    # Сдать в 7:00 — напоминание «в день сдачи» в 8:00 уже поздно
    due = at(TUE, 7)
    cands = deadline_candidates([DeadlineInfo(uuid.uuid4(), due)], [0], time(8), TZ, CH)
    assert build(cands, QUIET, TZ) == []


def test_changed_deadline_gets_new_keys():
    tid = uuid.uuid4()
    a = deadline_candidates([DeadlineInfo(tid, at(TUE, 23))], [1], time(8), TZ, CH)[0]
    b = deadline_candidates([DeadlineInfo(tid, at(TUE, 22))], [1], time(8), TZ, CH)[0]
    assert a.key != b.key


def test_digest_daily():
    cands = digest_candidates([TUE, TUE + timedelta(days=1)], time(8), TZ, CH)
    assert [c.key for c in cands] == ["morning_digest:2026-10-06", "morning_digest:2026-10-07"]
    assert cands[0].fire_at == at(TUE, 8)


def test_subtask_start_respects_action_window():
    block = BlockInfo(uuid.uuid4(), at(TUE, 22), at(TUE, 23), PEOPLE)
    # Окно наступает только завтра, а блок кончается в 23:00 — смысла нет
    assert build(subtask_candidates([block], CH), QUIET, TZ) == []
    block = BlockInfo(uuid.uuid4(), at(TUE, 22), at(TUE + timedelta(days=2), 10), PEOPLE)
    [p] = build(subtask_candidates([block], CH), QUIET, TZ)
    assert p.fire_at == at(TUE + timedelta(days=1), 9)


def test_next_allowed_skips_quiet():
    assert next_allowed(at(TUE, 22, 40), QUIET, TZ) == at(TUE + timedelta(days=1), 8)
    assert next_allowed(at(TUE, 15), QUIET, TZ) == at(TUE, 15)


def test_dst_safe_wall_times():
    # В зоне с переходом на зимнее время дневное окно не «съезжает»
    berlin = get_tz("Europe/Berlin")
    d = date(2026, 10, 25)  # переход 03:00 → 02:00
    c = Candidate(ReminderKind.test, "k", wall_to_utc(d, time(2, 30), berlin), CH)
    quiet = TimeRange(time(22, 0), time(7, 0))
    assert adjust(c, quiet, berlin) == wall_to_utc(d, time(7), berlin)
