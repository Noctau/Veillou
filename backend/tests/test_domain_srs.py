"""M12.2: интервальные повторения билетов."""

from datetime import date, timedelta

from app.domain.enums import ExamQuestionStatus as S
from app.domain.enums import ExamSessionKind as K
from app.domain.srs import DayPlan, Params, Question, build, prep_start, review_dates

TODAY = date(2026, 12, 1)
P = Params(learn_min=45, review_min=15, run_min=5, prep_days=7)


def day(n: int) -> date:
    return TODAY + timedelta(days=n)


def qs(n: int) -> list[Question]:
    return [Question(f"q{i}", i, S.not_started) for i in range(1, n + 1)]


def by_kind(plans: list[DayPlan], kind: K) -> dict[date, tuple[str, ...]]:
    return {p.date: p.question_ids for p in plans if p.kind == kind}


def test_prep_start():
    assert prep_start(TODAY, day(20), 7) == day(13)
    assert prep_start(TODAY, day(3), 7) == TODAY


def test_review_dates():
    assert review_dates(day(0), 0, TODAY) == [day(1), day(3), day(7)]
    assert review_dates(day(0), 2, TODAY) == [day(7)]
    assert review_dates(day(0), 3, TODAY) == []
    # просроченное — сегодня, следующие не в тот же день
    assert review_dates(day(-5), 0, TODAY) == [day(0), day(1), day(2)]


def test_exam_today_or_past_gives_nothing():
    assert build(qs(5), TODAY, TODAY, P) == []
    assert build(qs(5), TODAY, day(-1), P) == []
    assert build([], TODAY, day(5), P) == []


def test_week_plan_learn_reviews_and_run():
    plans = build(qs(6), TODAY, day(7), P)
    learn = by_kind(plans, K.learn)
    # 7 дней до экзамена: 6 дней учёбы (0..5) и прогон в день 6
    assert sorted(learn) == [day(i) for i in range(6)]
    assert all(len(ids) == 1 for ids in learn.values())
    run = by_kind(plans, K.run)
    assert run == {day(6): tuple(f"q{i}" for i in range(1, 7))}
    reviews = by_kind(plans, K.review)
    # q1 выучен в день 0: повторения 1, 3 (7 — после прогона, отброшено)
    assert "q1" in reviews[day(1)]
    assert "q1" in reviews[day(3)]
    assert all(d < day(6) for d in reviews)
    minutes = {(p.date, p.kind): p.minutes for p in plans}
    assert minutes[(day(0), K.learn)] == 45
    assert minutes[(day(6), K.run)] == 6 * 5


def test_uneven_spread_front_loads():
    plans = build(qs(8), TODAY, day(4), P)
    learn = by_kind(plans, K.learn)
    assert [len(learn[day(i)]) for i in range(3)] == [3, 3, 2]
    assert [q for d in sorted(learn) for q in learn[d]] == [f"q{i}" for i in range(1, 9)]


def test_far_exam_starts_prep_days_before():
    plans = build(qs(3), TODAY, day(30), P)
    assert min(p.date for p in plans) == day(23)


def test_one_day_left_learn_without_run():
    plans = build(qs(3), TODAY, day(1), P)
    assert [(p.date, p.kind) for p in plans] == [(TODAY, K.learn)]


def test_one_day_left_all_learned_is_run():
    learned = [Question(f"q{i}", i, S.learned, learned_on=day(-3)) for i in range(1, 4)]
    plans = build(learned, TODAY, day(1), P)
    assert [(p.date, p.kind) for p in plans] == [(TODAY, K.run)]


def test_learned_questions_only_get_reviews():
    questions = [
        Question("a", 1, S.learned, learned_on=day(-1), reviews_done=0),
        Question("b", 2, S.learned, learned_on=day(-3), reviews_done=1),
        Question("c", 3, S.not_started),
    ]
    plans = build(questions, TODAY, day(10), P)
    learn = by_kind(plans, K.learn)
    assert [q for ids in learn.values() for q in ids] == ["c"]
    reviews = by_kind(plans, K.review)
    assert "a" in reviews[TODAY]  # +1 от вчера
    assert "b" in reviews[TODAY]  # +3 от позавчера-позавчера
    assert "a" in reviews[day(2)]


def test_review_status_restarts_cycle_from_mark_day():
    q = Question("a", 1, S.review, learned_on=TODAY, reviews_done=0)
    reviews = by_kind(build([q], TODAY, day(10), P), K.review)
    assert sorted(reviews) == [day(1), day(3), day(7)]


def test_overdue_review_moves_to_today():
    q = Question("a", 1, S.learned, learned_on=day(-10), reviews_done=1)
    reviews = by_kind(build([q], TODAY, day(10), P), K.review)
    assert sorted(reviews) == [TODAY, day(1)]


def test_deterministic_order_by_number():
    questions = [Question("x", 2, S.not_started), Question("y", 1, S.not_started)]
    learn = by_kind(build(questions, TODAY, day(3), P), K.learn)
    assert learn[TODAY] == ("y",)
    assert learn[day(1)] == ("x",)


def test_closed_learn_day_moves_learning_to_tomorrow():
    closed = frozenset({(TODAY, K.learn)})
    learn = by_kind(build(qs(4), TODAY, day(5), P, closed), K.learn)
    assert TODAY not in learn
    assert sorted(learn) == [day(1), day(2), day(3)]


def test_closed_review_day_shifts_reviews():
    q = Question("a", 1, S.learned, learned_on=day(-1))
    closed = frozenset({(TODAY, K.review)})
    reviews = by_kind(build([q], TODAY, day(10), P, closed), K.review)
    assert TODAY not in reviews
    assert day(1) in reviews


def test_closed_run_is_not_planned_again():
    learned = [Question("a", 1, S.learned, learned_on=day(-5), reviews_done=3)]
    closed = frozenset({(TODAY, K.run)})
    assert build(learned, TODAY, day(1), P, closed) == []
