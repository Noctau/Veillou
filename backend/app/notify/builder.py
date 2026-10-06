"""Когда присылать напоминания. Чистая логика, без БД.

На входе — простые описания пар, заданий и блоков; на выходе — список
`Planned` с итоговым временем и ключом дедупликации. Сервис
(services/reminders.py) сверяет этот список с таблицей `reminders`.

Правила:
- перед парой — за N минут (по умолчанию 15), позже начала пары смысла нет;
- дедлайны — за 3 дня, за 1 день и в день сдачи, во время утренней сводки
  (склеиваются с ней в одно сообщение);
- утренняя сводка — каждый день в заданное время;
- начало подзадачи — в момент начала блока (по умолчанию выключено);
- тихие часы: ничего не приходит — переносится на их конец;
- окно типа действия: «написать научруку» в 22:00 переносится на начало
  ближайшего окна (утро буднего дня). Если перенос вперёд опоздал бы к сроку,
  дедлайн-напоминание сдвигается назад — на последний допустимый момент;
- склейка: напоминания в пределах минуты получают одно время, воркер
  отправляет их одним сообщением.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.time import local_date, wall_to_utc
from app.domain.enums import ReminderKind

MERGE_WINDOW = timedelta(minutes=1)
# Сколько дней вперёд/назад искать допустимое время
SEARCH_DAYS = 8
# Сводка, опоздавшая больше чем на 4 часа (воркер лежал), уже не нужна
DIGEST_TTL = timedelta(hours=4)


@dataclass(frozen=True)
class Window:
    """Дни недели (ISO 1–7) × интервал. `end <= start` — до следующего дня."""

    weekdays: frozenset[int]
    start: time
    end: time


@dataclass(frozen=True)
class TimeRange:
    """Интервал внутри дня; `end <= start` — через полночь (тихие часы)."""

    start: time
    end: time


@dataclass(frozen=True)
class Candidate:
    kind: ReminderKind
    key: str
    fire_at: datetime  # желаемое время
    channels: tuple[str, ...]
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    # Допустимые окна (тип действия / своё окно дела); пусто — в любое время
    windows: tuple[Window, ...] = ()
    # Можно ли сдвинуть раньше желаемого, если вперёд — поздно
    allow_earlier: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Planned:
    kind: ReminderKind
    key: str
    fire_at: datetime
    channels: tuple[str, ...]
    entity_type: str | None
    entity_id: uuid.UUID | None
    expires_at: datetime | None
    payload: dict[str, Any]


# ---------- входные описания ----------


@dataclass(frozen=True)
class ClassInfo:
    event_id: uuid.UUID
    start: datetime


@dataclass(frozen=True)
class DeadlineInfo:
    task_id: uuid.UUID
    deadline: datetime
    windows: tuple[Window, ...] = ()


@dataclass(frozen=True)
class BlockInfo:
    """Блок подзадачи в календаре."""

    event_id: uuid.UUID
    start: datetime
    end: datetime
    windows: tuple[Window, ...] = ()


def windows_from_json(raw: Iterable[dict[str, Any]] | None) -> tuple[Window, ...]:
    """Окна из JSONB (`[{"weekdays": [1..5], "start": "09:00", "end": "19:00"}]`)."""
    return tuple(
        Window(
            frozenset(w["weekdays"]), time.fromisoformat(w["start"]), time.fromisoformat(w["end"])
        )
        for w in raw or ()
    )


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%MZ")


def class_candidates(
    classes: Iterable[ClassInfo], minutes_before: int, channels: Sequence[str]
) -> list[Candidate]:
    return [
        Candidate(
            kind=ReminderKind.before_class,
            key=f"before_class:{c.event_id}:{_stamp(c.start)}",
            fire_at=c.start - timedelta(minutes=minutes_before),
            channels=tuple(channels),
            entity_type="event",
            entity_id=c.event_id,
            expires_at=c.start,
            payload={"start": c.start.isoformat()},
        )
        for c in classes
    ]


def deadline_candidates(
    tasks: Iterable[DeadlineInfo],
    days_before: Iterable[int],
    at: time,
    tz: ZoneInfo,
    channels: Sequence[str],
) -> list[Candidate]:
    result = []
    days = sorted(set(days_before), reverse=True)
    for t in tasks:
        due_day = local_date(t.deadline, tz)
        for n in days:
            fire_at = wall_to_utc(due_day - timedelta(days=n), at, tz)
            if fire_at >= t.deadline:  # сдать в 7:00, а сводка в 8:00
                continue
            result.append(
                Candidate(
                    kind=ReminderKind.deadline,
                    key=f"deadline:{t.task_id}:{n}d:{_stamp(t.deadline)}",
                    fire_at=fire_at,
                    channels=tuple(channels),
                    entity_type="task",
                    entity_id=t.task_id,
                    expires_at=t.deadline,
                    windows=t.windows,
                    allow_earlier=True,
                    payload={"deadline": t.deadline.isoformat(), "days_before": n},
                )
            )
    return result


def digest_candidates(
    days: Iterable[date], at: time, tz: ZoneInfo, channels: Sequence[str]
) -> list[Candidate]:
    return [
        Candidate(
            kind=ReminderKind.morning_digest,
            key=f"morning_digest:{d.isoformat()}",
            fire_at=wall_to_utc(d, at, tz),
            channels=tuple(channels),
            expires_at=wall_to_utc(d, at, tz) + DIGEST_TTL,
            payload={"date": d.isoformat()},
        )
        for d in days
    ]


def subtask_candidates(blocks: Iterable[BlockInfo], channels: Sequence[str]) -> list[Candidate]:
    return [
        Candidate(
            kind=ReminderKind.subtask_start,
            key=f"subtask_start:{b.event_id}:{_stamp(b.start)}",
            fire_at=b.start,
            channels=tuple(channels),
            entity_type="event",
            entity_id=b.event_id,
            expires_at=b.end,
            windows=b.windows,
            payload={"start": b.start.isoformat()},
        )
        for b in blocks
    ]


# ---------- допустимое время ----------

Interval = tuple[datetime, datetime]


def _daily(d: date, start: time, end: time, tz: ZoneInfo) -> Interval:
    next_day = d + timedelta(days=1) if end <= start else d
    return wall_to_utc(d, start, tz), wall_to_utc(next_day, end, tz)


def _merge(intervals: list[Interval]) -> list[Interval]:
    result: list[Interval] = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def _subtract(base: list[Interval], holes: list[Interval]) -> list[Interval]:
    result = []
    for start, end in base:
        pieces = [(start, end)]
        for h_start, h_end in holes:
            next_pieces = []
            for p_start, p_end in pieces:
                if h_end <= p_start or h_start >= p_end:
                    next_pieces.append((p_start, p_end))
                    continue
                if p_start < h_start:
                    next_pieces.append((p_start, h_start))
                if h_end < p_end:
                    next_pieces.append((h_end, p_end))
            pieces = next_pieces
        result.extend(pieces)
    return result


def allowed_intervals(
    around: datetime,
    windows: Sequence[Window],
    quiet: TimeRange | None,
    tz: ZoneInfo,
    days: int = SEARCH_DAYS,
) -> list[Interval]:
    """Когда можно присылать в пределах ±`days` дней от `around`, в UTC."""
    center = local_date(around, tz)
    dates = [center + timedelta(days=i) for i in range(-days - 1, days + 1)]
    if windows:
        base = [
            _daily(d, w.start, w.end, tz)
            for d in dates
            for w in windows
            if d.isoweekday() in w.weekdays
        ]
    else:
        base = [(wall_to_utc(dates[0], time(0), tz), wall_to_utc(dates[-1], time(0), tz))]
    holes = [_daily(d, quiet.start, quiet.end, tz) for d in dates] if quiet else []
    return _subtract(_merge(base), _merge(holes))


def adjust(c: Candidate, quiet: TimeRange | None, tz: ZoneInfo) -> datetime | None:
    """Ближайшее допустимое время для напоминания или None, если такого нет до срока."""
    intervals = allowed_intervals(c.fire_at, c.windows, quiet, tz)
    for start, end in intervals:
        if end > c.fire_at:
            moment = max(start, c.fire_at)
            if c.expires_at is None or moment < c.expires_at:
                return moment
            break
    if not c.allow_earlier:
        return None
    # Назад: последний допустимый момент до желаемого (конец окна не входит)
    for start, end in reversed(intervals):
        if start < c.fire_at:
            return min(end - timedelta(minutes=1), c.fire_at)
    return None


def merge_close(planned: list[Planned], window: timedelta = MERGE_WINDOW) -> list[Planned]:
    """Напоминания в пределах `window` от первого в группе получают его время."""
    result: list[Planned] = []
    group_start: datetime | None = None
    for p in sorted(planned, key=lambda p: (p.fire_at, p.key)):
        if group_start is None or p.fire_at - group_start > window:
            group_start = p.fire_at
        result.append(replace(p, fire_at=group_start))
    return result


def build(candidates: Iterable[Candidate], quiet: TimeRange | None, tz: ZoneInfo) -> list[Planned]:
    planned = []
    for c in candidates:
        moment = adjust(c, quiet, tz)
        if moment is None:
            continue
        planned.append(
            Planned(
                kind=c.kind,
                key=c.key,
                fire_at=moment,
                channels=c.channels,
                entity_type=c.entity_type,
                entity_id=c.entity_id,
                expires_at=c.expires_at,
                payload=c.payload,
            )
        )
    return merge_close(planned)


def next_allowed(moment: datetime, quiet: TimeRange | None, tz: ZoneInfo) -> datetime:
    """Ближайший момент не в тихие часы (для «+15 мин» и «На завтра»)."""
    probe = Candidate(kind=ReminderKind.test, key="", fire_at=moment, channels=())
    return adjust(probe, quiet, tz) or moment
