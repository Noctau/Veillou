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


Interval = tuple[datetime, datetime]


@dataclass(frozen=True)
class DaySpec:
    """Сутки по режиму дня (domain/dayprofile.py): день планировщика — от подъёма
    `wake` до подъёма следующего дня; сон — от отбоя `sleep` до него же.

    Ночь «после ночной смены» — это хвост предыдущего дня (до позднего подъёма).
    """

    date: date
    wake: datetime
    sleep: datetime  # отбой (может быть после полуночи)
    lunch: Interval | None = None
    # Общие окна для дел; блок без своих окон ставится только сюда
    work: tuple[Interval, ...] = ()
    # Может ли этот день дать свободный вечер / половину выходного (минимум отдыха)
    rest_evening_ok: bool = True
    rest_halfday_ok: bool = False


@dataclass(frozen=True)
class PlanSettings:
    """Срез настроек пользователя, нужный планировщику (schemas/settings.py).

    Сон, обед и рабочие окна — по дням (`PlanInput.days`, режимы дня)."""

    deadline_buffer_days: int = 1
    max_subtasks_per_task_per_day: int = 2
    # Минимум отдыха в неделю: свободные вечера (evening_start → отбой, в дни с
    # `rest_evening_ok`) и половины выходных (подъём → half_day_split,
    # half_day_split → отбой, в дни с `rest_halfday_ok`)
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
class Budget:
    """Лимит нагрузки: блоков с этим лимитом — не больше `minutes_per_day` в день.

    `overrides` — разовый лимит на день (дата дня планировщика → минут). Блок
    в двух лимитах учитывается в обоих; id, которого нет в `PlanInput.budgets`,
    ничего не ограничивает.
    """

    id: BlockId
    minutes_per_day: int
    overrides: tuple[tuple[date, int], ...] = ()


@dataclass(frozen=True)
class Busy:
    """Жёсткий интервал (событие типа занятости): планировщик туда ничего не ставит."""

    start: datetime
    end: datetime
    # Дорога, мин: вычитается до начала и после конца
    buffer_before: int = 0
    buffer_after: int = 0
    # Склейка: интервалы одного дня с одним ключом получают буфер только до первого
    # и после последнего (тип занятости + место). None — буфер у каждого свой
    merge_key: str | None = None
    # Лимиты, в которые засчитывается (по типу занятости, M17)
    budgets: frozenset[BlockId] = frozenset()


@dataclass(frozen=True)
class FixedBlock:
    """Гибкий блок, который не двигаем (закреплён, уже идёт, выполнен сегодня).

    Занимает время и учитывается в дневных лимитах; от него можно зависеть.
    """

    id: BlockId
    start: datetime
    end: datetime
    group_id: BlockId | None = None  # задание
    budgets: frozenset[BlockId] = frozenset()
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
    # Окна типа действия или свои окна задачи; пусто — общие рабочие окна дня
    windows: tuple[Window, ...] = ()
    # Окна — только в пределах рабочих окон дня (чипы дела из ящика без своих окон)
    within_work: bool = False
    # id блоков (или FixedBlock), которые должны закончиться раньше начала этого
    depends_on: tuple[BlockId, ...] = ()
    splittable: bool = False
    # Лимиты нагрузки, в которые засчитывается время блока (по типу действия)
    budgets: frozenset[BlockId] = frozenset()
    # Лёгкое предпочтение утра (флаг типа действия)
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
    # Сутки по режимам дня; даты без своего DaySpec — по умолчанию (dayprofile.FALLBACK)
    days: tuple[DaySpec, ...] = ()
    budgets: tuple[Budget, ...] = ()
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
