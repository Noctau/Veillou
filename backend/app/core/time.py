"""Работа со временем.

Правила проекта:
- в БД только timestamptz (UTC), naive datetime запрещены;
- шаблоны (пары, звонки, окна) — «настенное» время в TZ пользователя,
  в UTC переводятся через `wall_to_utc`.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class NaiveDatetimeError(ValueError):
    pass


def now_utc() -> datetime:
    return datetime.now(UTC)


def get_tz(name: str) -> ZoneInfo:
    """IANA-зона по имени. Бросает ValueError на неизвестную зону."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone: {name!r}") from exc


def is_valid_tz(name: str) -> bool:
    try:
        get_tz(name)
    except ValueError:
        return False
    return True


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise NaiveDatetimeError(f"Naive datetime is not allowed: {dt!r}")
    return dt


def to_utc(dt: datetime) -> datetime:
    return ensure_aware(dt).astimezone(UTC)


def to_local(dt: datetime, tz: ZoneInfo) -> datetime:
    return ensure_aware(dt).astimezone(tz)


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    """Календарная дата момента `dt` в зоне `tz`."""
    return to_local(dt, tz).date()


def wall_to_utc(d: date, t: time, tz: ZoneInfo) -> datetime:
    """Настенное время `t` в день `d` в зоне `tz` -> момент в UTC.

    Переходы на летнее/зимнее время:
    - несуществующее время (весенний «пропуск») сдвигается вперёд на величину
      пропуска: 02:30 в день перехода 02:00→03:00 становится 03:30;
    - неоднозначное время (осенний «повтор») берётся в первом вхождении (fold=0).
    """
    if t.tzinfo is not None:
        raise ValueError("Wall time must be naive (без tzinfo)")
    local = datetime.combine(d, t.replace(fold=0), tzinfo=tz)
    return local.astimezone(UTC)


def day_bounds_utc(d: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[начало дня, начало следующего дня) локальной даты `d` в UTC."""
    return wall_to_utc(d, time(0), tz), wall_to_utc(d + timedelta(days=1), time(0), tz)
