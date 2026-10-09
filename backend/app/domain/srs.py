"""Интервальные повторения для билетов (M12.2). Детерминированно, без ИИ.

Вопрос: выучить → повторить через +1, +3, +7 дней от дня, когда выучен.
Подготовка идёт с `start` (за N дней до экзамена, но не раньше сегодня) до
накануне экзамена. Последний день — общий прогон всех вопросов; повторения,
которые попадают на него или позже, не нужны (прогон их покрывает).

Невыученные вопросы распределяются по дням учёбы поровну (раньше — больше, если
не делится). Просроченное повторение (день прошёл, не сделано) переносится на
сегодня. «Повторить» (статус review) — цикл начинается заново с дня отметки.

Дни, где этот вид уже закрыт (сделан или пропущен), заново не планируются:
учёба начинается со следующего дня, повторения сдвигаются на день.

Результат — дни плана: (дата, вид, вопросы, минуты).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.enums import ExamQuestionStatus, ExamSessionKind

OFFSETS = (1, 3, 7)


@dataclass(frozen=True)
class Question:
    id: str
    number: int
    status: ExamQuestionStatus
    # Выучен (или отмечен «повторить») в этот день; None — ещё не выучен
    learned_on: date | None = None
    reviews_done: int = 0


@dataclass(frozen=True)
class Params:
    learn_min: int = 45
    review_min: int = 15
    run_min: int = 5
    prep_days: int = 7


DEFAULT_PARAMS = Params()


@dataclass(frozen=True)
class DayPlan:
    date: date
    kind: ExamSessionKind
    question_ids: tuple[str, ...]
    minutes: int


def prep_start(today: date, exam_day: date, prep_days: int) -> date:
    return max(today, exam_day - timedelta(days=prep_days))


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


def build(
    questions: Sequence[Question],
    today: date,
    exam_day: date,
    params: Params = DEFAULT_PARAMS,
    closed: frozenset[tuple[date, ExamSessionKind]] = frozenset(),
) -> list[DayPlan]:
    """План подготовки с сегодняшнего дня. Пусто, если экзамен сегодня или прошёл.

    `closed` — (день, вид), которые уже сделаны или пропущены."""
    if exam_day <= today or not questions:
        return []
    start = prep_start(today, exam_day, params.prep_days)
    run_day = exam_day - timedelta(days=1)
    ordered = sorted(questions, key=lambda q: (q.number, q.id))
    learned_on: dict[str, date] = {}
    to_learn: list[str] = []
    for q in ordered:
        if q.status == ExamQuestionStatus.not_started or q.learned_on is None:
            to_learn.append(q.id)
        else:
            learned_on[q.id] = q.learned_on

    # Дни учёбы — до прогона; если день один, учим в него же (без прогона)
    all_days = [start + timedelta(days=i) for i in range((run_day - start).days)]
    learn_days = [d for d in all_days if (d, ExamSessionKind.learn) not in closed]
    with_run = bool(all_days) or not to_learn
    if not learn_days and (run_day, ExamSessionKind.learn) not in closed:
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
            while (d, ExamSessionKind.review) in closed:
                d += timedelta(days=1)
            if d >= run_day:
                break
            reviews[d].append(q.id)

    plans: list[DayPlan] = []
    for d in sorted(set(learn) | set(reviews)):
        if new := learn.get(d):
            plans.append(DayPlan(d, ExamSessionKind.learn, tuple(new), len(new) * params.learn_min))
        if repeat := reviews.get(d):
            plans.append(
                DayPlan(d, ExamSessionKind.review, tuple(repeat), len(repeat) * params.review_min)
            )
    if with_run and run_day >= today and (run_day, ExamSessionKind.run) not in closed:
        everything = tuple(q.id for q in ordered)
        plans.append(
            DayPlan(run_day, ExamSessionKind.run, everything, len(everything) * params.run_min)
        )
    return plans
