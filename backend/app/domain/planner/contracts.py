"""Вход и выход планировщика. Только dataclass'ы, без логики.

Все моменты — aware datetime (UTC или с зоной). «Настенное» время (окна,
сон, обед, рабочие часы) — в зоне `PlanInput.tz`.
"""

from collections.abc import Hashable
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

BlockId = Hashable


@dataclass(frozen=True)
class Window:
    """Дни недели (ISO 1–7) × интервал. `end <= start` — до следующего дня.

    День недели — по началу окна: «Пн 07:00–01:00» заканчивается во вторник.
    """

    weekdays: frozenset[int]
    start: time
    end: time


@dataclass(frozen=True)
class TimeRange:
    """Ежедневный интервал. `end <= start` — через полночь (сон)."""

    start: time
    end: time


@dataclass(frozen=True)
class PlanSettings:
    """Срез настроек пользователя, нужный планировщику (schemas/settings.py)."""

    work_weekdays: TimeRange = TimeRange(time(9, 0), time(21, 0))
    work_weekends: TimeRange = TimeRange(time(11, 0), time(19, 0))
    sleep: TimeRange = TimeRange(time(23, 30), time(7, 30))
    lunch: TimeRange | None = TimeRange(time(13, 0), time(14, 0))
    # Вычитается целиком до первой и после последней пары дня
    travel_buffer_min: int = 60
    study_limit_min_per_day: int = 360
    deadline_buffer_days: int = 1
    max_subtasks_per_task_per_day: int = 2
    # Минимум отдыха в неделю: свободные вечера (evening_start → сон, любой день)
    # и половины выходных (подъём → half_day_split, half_day_split → сон в Сб/Вс)
    free_evenings_per_week: int = 2
    weekend_half_days: int = 1
    evening_start: time = time(18, 0)
    half_day_split: time = time(14, 0)
    # После блока длиннее long_block_min — перерыв break_min (на сетке округляется вверх)
    long_block_min: int = 60
    break_min: int = 10
    # Минимальная часть разрезанного блока
    min_part_min: int = 30


@dataclass(frozen=True)
class Busy:
    """Жёсткий интервал (пара, личное, отдых): планировщик туда ничего не ставит."""

    start: datetime
    end: datetime
    # Пара: в её день вычитается буфер дороги до первой и после последней пары
    is_class: bool = False


@dataclass(frozen=True)
class FixedBlock:
    """Гибкий блок, который не двигаем (закреплён, уже идёт, выполнен сегодня).

    Занимает время и учитывается в дневных лимитах; от него можно зависеть.
    """

    id: BlockId
    start: datetime
    end: datetime
    group_id: BlockId | None = None  # задание
    counts_as_study: bool = True
    # Метка нормы (проект): засчитывается в `Quota` с этой меткой
    quota: BlockId | None = None


@dataclass(frozen=True)
class Block:
    """Гибкий блок, который надо разместить (подзадача, дело из ящика, подготовка)."""

    id: BlockId
    duration_min: int
    group_id: BlockId | None = None  # задание: ≤ N подзадач одного задания в день
    deadline: datetime | None = None
    # Вес: и в «раньше закончить», и в штрафе за непостановку. normal = 1, high = 3
    priority: int = 1
    # Окна типа действия или свои окна задачи; пусто — общие рабочие часы
    windows: tuple[Window, ...] = ()
    # id блоков (или FixedBlock), которые должны закончиться раньше начала этого
    depends_on: tuple[BlockId, ...] = ()
    splittable: bool = False
    counts_as_study: bool = True
    # Лёгкое предпочтение утра («связь с людьми»)
    prefer_morning: bool = False
    # Не раньше этого момента
    earliest: datetime | None = None
    # Свой «закончить за N дней до дедлайна»; None — из настроек
    buffer_days: int | None = None
    # Порядок внутри задания (group_id): мягко — шаг с меньшим номером лучше раньше
    sequence: int | None = None
    # Дело из ящика: ставится только в то, что осталось после основных блоков
    # (штраф за непостановку на порядки меньше — ради него основное не сдвинется)
    filler: bool = False
    # Только в эти дни (дата дня планировщика); None — в любые
    days: frozenset[date] | None = None
    # Метка нормы (проект): время блока засчитывается в `Quota` с этой меткой
    quota: BlockId | None = None
    # Резерв нормы: ставится, только если норма иначе не набирается
    # (штрафа за непостановку нет — только за недобор нормы)
    reserve: bool = False


@dataclass(frozen=True)
class Quota:
    """Норма (M13.1): в дни [start, end) блоков с меткой `tag` — не меньше `minutes`.

    Мягко, с высоким весом: важнее дел из ящика, но задание, которое без
    нормы встаёт до внутреннего срока, ради неё не опаздывает. Дни — даты
    дней планировщика; закреплённое (`FixedBlock.quota`) в эти дни уже засчитано.
    """

    id: BlockId
    tag: BlockId
    start: date
    end: date
    minutes: int


@dataclass(frozen=True)
class Placement:
    """Размещённая часть блока. part = 0, у разрезанного блока ещё part = 1."""

    block_id: BlockId
    part: int
    start: datetime
    end: datetime


@dataclass(frozen=True)
class PlanInput:
    now: datetime
    tz: ZoneInfo
    blocks: tuple[Block, ...]
    busy: tuple[Busy, ...] = ()
    fixed: tuple[FixedBlock, ...] = ()
    previous: tuple[Placement, ...] = ()
    settings: PlanSettings = PlanSettings()
    # Разовый лимит учёбы на день (дата дня планировщика → минут) вместо общего
    study_limits: tuple[tuple[date, int], ...] = ()
    quotas: tuple[Quota, ...] = ()
    # Горизонт: от now до самого дальнего дедлайна, но не меньше min и не больше max
    max_horizon_days: int = 60
    min_horizon_days: int = 14
    time_limit_s: float = 2.0
    grid_min: int = 15


class RiskReason(StrEnum):
    no_slots = "no_slots"  # до дедлайна нет ни одного допустимого окна нужной длины
    no_time = "no_time"  # окна есть, но всё занято другими блоками / лимитами
    dependency = "dependency"  # не размещено то, от чего блок зависит
    late = "late"  # размещено, но позже внутреннего срока (дедлайн − буфер)
    overdue = "overdue"  # дедлайн уже прошёл — ставим как можно раньше
    rest = "rest"  # влезло бы, если отдать минимум отдыха (no_time / late из-за отдыха)
    quota = "quota"  # норма недели не набирается (block_id — id нормы, group_id — метка)


@dataclass(frozen=True)
class AtRisk:
    block_id: BlockId
    group_id: BlockId | None
    reason: RiskReason


@dataclass(frozen=True)
class PlanDiff:
    added: tuple[Placement, ...] = ()
    removed: tuple[Placement, ...] = ()
    moved: tuple[tuple[Placement, Placement], ...] = ()  # (было, стало)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.moved)


@dataclass(frozen=True)
class PlanStats:
    engine: str  # "cp_sat" | "greedy"
    status: str  # статус CP-SAT или "greedy"
    blocks: int
    placed: int
    split: int
    elapsed_ms: int
    horizon_start: datetime
    horizon_end: datetime


@dataclass(frozen=True)
class PlanResult:
    placements: tuple[Placement, ...]
    at_risk: tuple[AtRisk, ...]
    diff: PlanDiff
    stats: PlanStats
