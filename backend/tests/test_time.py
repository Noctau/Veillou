from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest

from app.core.time import (
    NaiveDatetimeError,
    day_bounds_utc,
    ensure_aware,
    get_tz,
    is_valid_tz,
    local_date,
    now_utc,
    to_local,
    to_utc,
    wall_to_utc,
)

MSK = get_tz("Europe/Moscow")
BERLIN = get_tz("Europe/Berlin")


def test_now_utc_is_aware_utc():
    now = now_utc()
    assert now.tzinfo is UTC


def test_get_tz_unknown():
    with pytest.raises(ValueError, match="Unknown timezone"):
        get_tz("Mars/Olympus")
    assert not is_valid_tz("")
    assert is_valid_tz("Europe/Moscow")


@pytest.mark.parametrize("fn", [ensure_aware, to_utc, lambda dt: to_local(dt, MSK)])
def test_naive_rejected(fn):
    with pytest.raises(NaiveDatetimeError):
        fn(datetime(2026, 9, 1, 9, 0))


def test_to_utc_from_other_offset():
    dt = datetime(2026, 9, 1, 9, 0, tzinfo=timezone(timedelta(hours=3)))
    assert to_utc(dt) == datetime(2026, 9, 1, 6, 0, tzinfo=UTC)
    assert to_utc(dt).tzinfo is UTC


def test_wall_to_utc_moscow():
    # Первая пара 9:00 по Москве = 6:00 UTC
    assert wall_to_utc(date(2026, 9, 1), time(9, 0), MSK) == datetime(2026, 9, 1, 6, 0, tzinfo=UTC)


def test_wall_to_utc_crosses_utc_midnight():
    # 01:30 МСК 2 сентября — это ещё 1 сентября по UTC
    assert wall_to_utc(date(2026, 9, 2), time(1, 30), MSK) == datetime(
        2026, 9, 1, 22, 30, tzinfo=UTC
    )


def test_wall_to_utc_rejects_aware_time():
    with pytest.raises(ValueError, match="naive"):
        wall_to_utc(date(2026, 9, 1), time(9, 0, tzinfo=UTC), MSK)


def test_wall_to_utc_dst_gap_shifts_forward():
    # 29.03.2026 в Берлине 02:00 -> 03:00; 02:30 не существует
    result = wall_to_utc(date(2026, 3, 29), time(2, 30), BERLIN)
    assert result == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    assert to_local(result, BERLIN).time() == time(3, 30)


def test_wall_to_utc_dst_overlap_takes_first():
    # 25.10.2026 в Берлине 03:00 -> 02:00; 02:30 бывает дважды
    result = wall_to_utc(date(2026, 10, 25), time(2, 30), BERLIN)
    assert result == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_local_date_differs_from_utc_date():
    dt = datetime(2026, 9, 1, 22, 30, tzinfo=UTC)
    assert local_date(dt, MSK) == date(2026, 9, 2)


def test_day_bounds_moscow():
    start, end = day_bounds_utc(date(2026, 9, 1), MSK)
    assert start == datetime(2026, 8, 31, 21, 0, tzinfo=UTC)
    assert end - start == timedelta(hours=24)


def test_day_bounds_dst_day_is_23h():
    start, end = day_bounds_utc(date(2026, 3, 29), BERLIN)
    assert end - start == timedelta(hours=23)
