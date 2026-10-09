"""«У меня есть N минут» / `/free` (M11.4): что сделать прямо сейчас.

Кандидаты — шаги заданий (сначала те, что ближе по плану/сроку) и дела из
ящика (сначала взятые на неделю, дальше по приоритету). Подходит то, что
влезает в N минут и чьё окно (тип действия, условия) открыто с этого момента
и до конца. Ответ — лучшее и до двух альтернатив; если среди них нет дела из
ящика, а подходящее есть, оно занимает последнее место.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.domain.backlog import DAY, WEEK, merge, week_intervals
from app.domain.planner import Window

LIMIT = 3


@dataclass(frozen=True)
class FreeCandidate:
    kind: Literal["subtask", "task", "backlog"]
    id: uuid.UUID
    title: str
    minutes: int
    windows: tuple[Window, ...] = ()  # пусто — в любое время
    days: frozenset[date] | None = None  # только в эти дни
    # Меньше — лучше (сервис: время в плане / дедлайн / приоритет ящика)
    rank: tuple[Any, ...] = ()


def window_open(windows: Sequence[Window], local: datetime, minutes: int) -> bool:
    """Окна открыты весь отрезок [local, local + minutes)."""
    if not windows:
        return True
    m = (local.isoweekday() - 1) * DAY + local.hour * 60 + local.minute
    spans = week_intervals(windows)
    # Вторая неделя подряд: окно «Вс 22:00 → Пн 01:00» склеивается через границу
    spans = merge([*spans, *((lo + WEEK, hi + WEEK) for lo, hi in spans)])
    return any(lo <= m and m + minutes <= hi for lo, hi in spans)


def pick(
    candidates: Iterable[FreeCandidate], minutes: int, now: datetime, tz: ZoneInfo
) -> list[FreeCandidate]:
    local = now.astimezone(tz)
    fitting = [
        c
        for c in candidates
        if 0 < c.minutes <= minutes
        and (c.days is None or local.date() in c.days)
        and window_open(c.windows, local, c.minutes)
    ]
    # Шаги заданий раньше ящика; внутри — порядок сервиса, потом крупнее (полнее занять время)
    fitting.sort(key=lambda c: (c.kind == "backlog", c.rank, -c.minutes, str(c.id)))
    result = fitting[:LIMIT]
    if result and all(c.kind != "backlog" for c in result):
        box = next((c for c in fitting if c.kind == "backlog"), None)
        if box is not None:
            result = [*result[: LIMIT - 1], box]
    return result
