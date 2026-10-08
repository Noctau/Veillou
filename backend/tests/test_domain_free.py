"""M11.4: «У меня есть N минут»."""

from datetime import date, time

from app.core.time import get_tz, wall_to_utc
from app.domain.free import FreeCandidate, pick, window_open
from app.domain.planner import Window

TZ = get_tz("Europe/Moscow")
MON = date(2026, 10, 12)
WEEKDAYS = frozenset({1, 2, 3, 4, 5})
PEOPLE = (Window(WEEKDAYS, time(9), time(19)),)


def at(d: date, h: int, m: int = 0):
    return wall_to_utc(d, time(h, m), TZ)


def c(id, minutes, kind="subtask", **kw) -> FreeCandidate:
    return FreeCandidate(kind=kind, id=id, title=str(id), minutes=minutes, **kw)


def ids(result) -> list:
    return [x.id for x in result]


def test_window_open():
    local = at(MON, 18).astimezone(TZ)
    assert window_open(PEOPLE, local, 60)
    assert not window_open(PEOPLE, local, 61)
    assert window_open((), local, 600)


def test_window_open_across_sunday_midnight():
    sun = date(2026, 10, 18)
    night = (Window(frozenset({7}), time(22), time(2)),)
    assert window_open(night, at(sun, 23, 30).astimezone(TZ), 90)
    assert not window_open(night, at(sun, 23, 30).astimezone(TZ), 180)


def test_only_what_fits():
    result = pick([c("long", 90), c("short", 30)], 60, at(MON, 10), TZ)
    assert ids(result) == ["short"]


def test_window_respected():
    late = at(MON, 18, 30)
    result = pick([c("mail", 45, windows=PEOPLE), c("read", 45)], 60, late, TZ)
    assert ids(result) == ["read"]


def test_days_respected():
    result = pick([c("shop", 30, kind="backlog", days=frozenset({MON}))], 60, at(MON, 10), TZ)
    assert ids(result) == ["shop"]
    assert pick([c("shop", 30, kind="backlog", days=frozenset())], 60, at(MON, 10), TZ) == []


def test_subtasks_first_then_rank_then_bigger():
    result = pick(
        [
            c("box", 30, kind="backlog", rank=(0,)),
            c("b", 30, rank=(2,)),
            c("a", 20, rank=(1,)),
            c("a2", 40, rank=(1,)),
        ],
        60,
        at(MON, 10),
        TZ,
    )
    assert ids(result) == ["a2", "a", "box"]


def test_backlog_shown_as_alternative():
    subtasks = [c(f"s{i}", 30, rank=(i,)) for i in range(5)]
    box = c("box", 15, kind="backlog")
    assert ids(pick([*subtasks, box], 60, at(MON, 10), TZ)) == ["s0", "s1", "box"]


def test_only_backlog():
    boxes = [c("x", 60, kind="backlog", rank=(1,)), c("y", 15, kind="backlog", rank=(0,))]
    assert ids(pick(boxes, 60, at(MON, 10), TZ)) == ["y", "x"]


def test_zero_minutes_candidates_skipped():
    assert pick([c("z", 0)], 60, at(MON, 10), TZ) == []
