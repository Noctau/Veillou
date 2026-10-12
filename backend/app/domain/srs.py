"""Стратегии подготовки к событию (M12.2, M20). Детерминированно, без ИИ.

`spaced` — интервальные повторения. Пункт: выучить → повторить через +1, +3, +7
дней от дня, когда выучен. Подготовка идёт с `start` (за N дней до события, но не
раньше сегодня) до накануне. Последний день — общий прогон всех пунктов;
повторения, которые попадают на него или позже, не нужны (прогон их покрывает).
Невыученные пункты распределяются по дням поровну (раньше — больше, если не
делится). Просроченное повторение (день прошёл, не сделано) переносится на
сегодня. «Повторить» (статус review) — цикл начинается заново с дня отметки.

`even` — равномерно: непройденные пункты поровну по дням, без повторов; накануне —
прогон, если у плана есть минуты на прогон (`run_min > 0`).

Дни, где этот вид уже закрыт (сделан или пропущен), заново не планируются:
учёба начинается со следующего дня, повторения сдвигаются на день.

Результат — дни плана: (дата, вид, вопросы, минуты).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.enums import PrepItemStatus, PrepSessionKind, PrepStrategy

OFFSETS = (1, 3, 7)


@dataclass(frozen=True)
class Item:
    id: str
    number: int
    status: PrepItemStatus
    # Выучен (или отмечен «повторить») в этот день; None — ещё не выучен
    learned_on: date | None = None
    reviews_done: int = 0


@dataclass(frozen=True)
class Params:
    learn_min: int = 45
    review_min: int = 15
    run_min: int = 5
    start_days_before: int = 7


DEFAULT_PARAMS = Params()


@dataclass(frozen=True)
class DayPlan:
    date: date
    kind: PrepSessionKind
    item_ids: tuple[str, ...]
    minutes: int


def prep_start(today: date, target_day: date, days_before: int) -> date:
    return max(today, target_day - timedelta(days=days_before))


def review_dates(learned_on: date, reviews_done: int, today: date) -> list[date]:
    """Оставшиеся повторения: просроченное — сегодня, следующие — не раньше чем через день."""
    result: list[date] = []
    for offset in OFFSETS[reviews_done:]:
        d = max(learned_on + timedelta(days=offset), today)
        if result and d <= result[-1]:
            d = result[-1] + timedelta(days=1)
        result.append(d)
    return result


def _spread(items: Sequence[str], days: Sequence[date]) -> dict[date, list[str]]:
    """Поровну по дням, остаток — в первые дни."""
    result: dict[date, list[str]] = {}
    if not days:
        return result
    base, extra = divmod(len(items), len(days))
    i = 0
    for k, d in enumerate(days):
        n = base + (1 if k < extra else 0)
        if n:
            result[d] = list(items[i : i + n])
        i += n
    return result


Closed = frozenset[tuple[date, PrepSessionKind]]


def build(
    items: Sequence[Item],
    today: date,
    target_day: date,
    params: Params = DEFAULT_PARAMS,
    closed: Closed = frozenset(),
) -> list[DayPlan]:
    """`spaced`: план с сегодняшнего дня. Пусто, если событие сегодня или прошло.

    `closed` — (день, вид), которые уже сделаны или пропущены."""
    if target_day <= today or not items:
        return []
    start = prep_start(today, target_day, params.start_days_before)
    run_day = target_day - timedelta(days=1)
    ordered = sorted(items, key=lambda q: (q.number, q.id))
    learned_on: dict[str, date] = {}
    to_learn: list[str] = []
    for q in ordered:
        if q.status == PrepItemStatus.not_started or q.learned_on is None:
            to_learn.append(q.id)
        else:
            learned_on[q.id] = q.learned_on

    # Дни учёбы — до прогона; если день один, учим в него же (без прогона)
    all_days = [start + timedelta(days=i) for i in range((run_day - start).days)]
    learn_days = [d for d in all_days if (d, PrepSessionKind.learn) not in closed]
    with_run = params.run_min > 0 and (bool(all_days) or not to_learn)
    if not learn_days and (run_day, PrepSessionKind.learn) not in closed:
        learn_days = [run_day]
    learn = _spread(to_learn, learn_days)
    for d, ids in learn.items():
        for qid in ids:
            learned_on[qid] = d

    reviews: dict[date, list[str]] = defaultdict(list)
    done = {q.id: q.reviews_done for q in ordered}
    for q in ordered:
        first = learned_on[q.id]
        for d in review_dates(first, 0 if q.id in to_learn else done[q.id], today):
            while (d, PrepSessionKind.review) in closed:
                d += timedelta(days=1)
            if d >= run_day:
                break
            reviews[d].append(q.id)

    plans: list[DayPlan] = []
    for d in sorted(set(learn) | set(reviews)):
        if new := learn.get(d):
            plans.append(DayPlan(d, PrepSessionKind.learn, tuple(new), len(new) * params.learn_min))
        if repeat := reviews.get(d):
            plans.append(
                DayPlan(d, PrepSessionKind.review, tuple(repeat), len(repeat) * params.review_min)
            )
    if with_run and run_day >= today and (run_day, PrepSessionKind.run) not in closed:
        everything = tuple(q.id for q in ordered)
        plans.append(
            DayPlan(run_day, PrepSessionKind.run, everything, len(everything) * params.run_min)
        )
    return plans


def build_even(
    items: Sequence[Item],
    today: date,
    target_day: date,
    params: Params = DEFAULT_PARAMS,
    closed: Closed = frozenset(),
) -> list[DayPlan]:
    """`even`: непройденные пункты поровну по дням до накануне, без повторов; накануне —
    прогон всех пунктов, если `run_min > 0` и дней больше одного."""
    if target_day <= today or not items:
        return []
    start = prep_start(today, target_day, params.start_days_before)
    run_day = target_day - timedelta(days=1)
    ordered = sorted(items, key=lambda q: (q.number, q.id))
    to_learn = [q.id for q in ordered if q.status == PrepItemStatus.not_started]
    all_days = [start + timedelta(days=i) for i in range((target_day - start).days)]
    with_run = params.run_min > 0 and (len(all_days) > 1 or not to_learn)
    days = all_days[:-1] if with_run and len(all_days) > 1 else all_days
    learn_days = [d for d in days if (d, PrepSessionKind.learn) not in closed]
    plans = [
        DayPlan(d, PrepSessionKind.learn, tuple(ids), len(ids) * params.learn_min)
        for d, ids in sorted(_spread(to_learn, learn_days).items())
    ]
    if with_run and run_day >= today and (run_day, PrepSessionKind.run) not in closed:
        everything = tuple(q.id for q in ordered)
        plans.append(
            DayPlan(run_day, PrepSessionKind.run, everything, len(everything) * params.run_min)
        )
    return plans


def plan(
    strategy: PrepStrategy,
    items: Sequence[Item],
    today: date,
    target_day: date,
    params: Params = DEFAULT_PARAMS,
    closed: Closed = frozenset(),
) -> list[DayPlan]:
    builder = build_even if strategy == PrepStrategy.even else build
    return builder(items, today, target_day, params, closed)
