"""Разбивка задания на шаги (M10.2): чистая обработка ответа ИИ.

ИИ нумерует шаги (`order`) и ссылается на номера; черновик — список по
порядку, где зависимости — индексы в этом списке. Порядок топологический:
шаг всегда после тех, от кого зависит (ИИ иногда ставит «написать» до
«найти источники»). Оценки — 15–120 минут, кратно 5.

Предупреждение о времени детерминированное: сумма оценок × коэффициент
калибровки против свободных минут до дедлайна. ИИ своё `warning` тоже может
написать — показываем оба, если они разные по смыслу (решает сервис).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

MIN_STEP_MIN = 15
MAX_STEP_MIN = 120
STEP_ROUND = 5
# Свободного времени меньше чем «нужно × запас» — предупреждаем, что впритык
TIGHT_FACTOR = 1.25


def round_estimate(minutes: int | float) -> int:
    """15–120 минут, кратно 5."""
    value = int(STEP_ROUND * round(float(minutes) / STEP_ROUND))
    return max(MIN_STEP_MIN, min(MAX_STEP_MIN, value))


@dataclass(frozen=True)
class RawStep:
    """Шаг как его вернул ИИ: зависимости — номера `order` других шагов."""

    order: int
    title: str
    estimate_min: int
    action_type: str
    depends_on: tuple[int, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class DraftStep:
    """Шаг черновика: зависимости — индексы в списке черновика (раньше этого шага)."""

    title: str
    estimate_min: int
    action_type: str
    depends_on: tuple[int, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class Draft:
    steps: list[DraftStep] = field(default_factory=list)
    total_estimate_min: int = 0


def normalize_steps(raw: Sequence[RawStep]) -> Draft:
    """Шаги по `order` (повторы — по месту в ответе), зависимости → индексы.

    Порядок топологический и устойчивый: шаг ставится как можно раньше по
    своему номеру, но после всех своих зависимостей. Ссылки на себя и на
    несуществующие шаги отбрасываются; рёбра, замыкающие цикл, — тоже;
    косвенные зависимости (через другой шаг) убираются.
    """
    ordered = sorted(enumerate(raw), key=lambda p: (p[1].order, p[0]))
    # Первый шаг с таким номером — адресат ссылок
    by_order: dict[int, int] = {}
    for pos, (_, step) in enumerate(ordered):
        by_order.setdefault(step.order, pos)
    deps: list[list[int]] = []
    for pos, (_, step) in enumerate(ordered):
        own = []
        for d in step.depends_on:
            target = by_order.get(d)
            if target is not None and target != pos and target not in own:
                own.append(target)
        deps.append(own)

    # Kahn по возрастанию позиции; при цикле берём шаг с наименьшей позицией и рвём его входящие
    n = len(ordered)
    placed: list[int] = []
    done = [False] * n
    while len(placed) < n:
        ready = [i for i in range(n) if not done[i] and all(done[d] for d in deps[i])]
        if not ready:
            stuck = min(i for i in range(n) if not done[i])
            deps[stuck] = [d for d in deps[stuck] if done[d]]
            ready = [stuck]
        i = ready[0]
        done[i] = True
        placed.append(i)

    _reduce(deps)
    index = {pos: k for k, pos in enumerate(placed)}
    steps = []
    for pos in placed:
        step = ordered[pos][1]
        steps.append(
            DraftStep(
                title=step.title,
                estimate_min=round_estimate(step.estimate_min),
                action_type=step.action_type,
                depends_on=tuple(sorted(index[d] for d in deps[pos])),
                note=step.note,
            )
        )
    return Draft(steps, sum(s.estimate_min for s in steps))


def _reduce(deps: list[list[int]]) -> None:
    """Транзитивное сокращение: «3 после 1 и 2», а 2 уже после 1 → «3 после 2».

    Граф уже без циклов. На экране проверки и в планировщике лишние стрелки
    только мешают.
    """
    memo: dict[int, set[int]] = {}

    def reach(i: int) -> set[int]:
        if i not in memo:
            memo[i] = set()
            for d in deps[i]:
                memo[i] |= {d, *reach(d)}
        return memo[i]

    for i, own in enumerate(deps):
        indirect = set().union(*(reach(d) for d in own)) if own else set()
        deps[i] = [d for d in own if d not in indirect]


def fmt_minutes(minutes: int) -> str:
    """«45 мин», «2 ч», «3 ч 30 мин»."""
    h, m = divmod(max(0, int(minutes)), 60)
    if not h:
        return f"{m} мин"
    return f"{h} ч {m} мин" if m else f"{h} ч"


def time_warning(total_min: int, free_min: int | None, coef: float = 1.0) -> str | None:
    """Хватает ли времени до дедлайна. `free_min` None — дедлайна нет."""
    if free_min is None or total_min <= 0:
        return None
    need = round(total_min * coef)
    if free_min <= 0:
        return "До дедлайна свободного времени не осталось"
    if need > free_min:
        return (
            f"Нужно ~{fmt_minutes(need)}, а до дедлайна свободно ~{fmt_minutes(free_min)} "
            "— не всё успеется"
        )
    if need * TIGHT_FACTOR > free_min:
        return f"Впритык: нужно ~{fmt_minutes(need)} из ~{fmt_minutes(free_min)} свободных"
    return None
