"""quickparse на фразах, как их пишут в быстрый ввод.

«Сейчас» — вторник 06.10.2026 15:00 по Москве.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.domain.enums import TaskType
from app.domain.quickparse import KindHint, SubjectRef, parse

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 6, 15, 0, tzinfo=MSK)

SUBJECTS = [
    SubjectRef("clim", ("Климатология", "клим", "климат")),
    SubjectRef("fiz", ("Физика атмосферы", "физат")),
    SubjectRef("dyn", ("Динамическая метеорология", "динмет")),
    SubjectRef("eng", ("Английский язык", "англ")),
    SubjectRef("matan", ("Математический анализ", "матан")),
]


def p(text: str, now: datetime = NOW, subjects=SUBJECTS):
    return parse(text, now, subjects)


def eod(d: date) -> datetime:
    return datetime.combine(d, time(23, 59), tzinfo=MSK)


# ---------- задания ----------


def test_essay_with_subject_and_deadline():
    r = p("реферат климатология до 15 окт")
    assert r.title == "Реферат"
    assert r.subject_id == "clim"
    assert r.task_type == TaskType.essay
    assert r.date == date(2026, 10, 15)
    assert r.deadline == eod(date(2026, 10, 15))
    assert r.is_deadline and r.kind_hint == KindHint.task


def test_report_by_friday_inflected_subject():
    r = p("доклад по физике атмосферы к пятнице")
    assert (r.title, r.subject_id, r.task_type) == ("Доклад", "fiz", TaskType.report)
    assert r.date == date(2026, 10, 9) and r.is_deadline


def test_homework_in_two_weeks():
    r = p("дз по матану через 2 недели")
    assert (r.title, r.subject_id, r.task_type) == ("Дз", "matan", TaskType.homework)
    assert r.date == date(2026, 10, 20)
    assert r.kind_hint == KindHint.task


def test_reading_chapter_numeric_date():
    r = p("прочитать главу 3 учебника по климатологии к 12.10")
    assert r.title == "Прочитать главу 3 учебника"
    assert r.subject_id == "clim" and r.task_type == TaskType.reading
    assert r.date == date(2026, 10, 12) and r.is_deadline


def test_lab_short_name_bare_date():
    r = p("лаба по физат 20.10")
    assert (r.title, r.subject_id, r.task_type) == ("Лаба", "fiz", TaskType.lab)
    assert r.date == date(2026, 10, 20)
    assert r.kind_hint == KindHint.task


def test_submit_coursework_month_name():
    r = p("сдать курсовую 1 декабря")
    assert r.title == "Сдать курсовую"
    assert r.task_type == TaskType.coursework
    assert r.date == date(2026, 12, 1) and r.is_deadline


def test_exam_prep_next_year():
    r = p("подготовиться к экзамену по климатологии до 20 января")
    assert r.task_type == TaskType.exam_prep and r.subject_id == "clim"
    assert r.date == date(2027, 1, 20)
    assert r.title == "Подготовиться к экзамену"


def test_past_day_month_rolls_to_next_year():
    assert p("эссе к 5 окт").date == date(2027, 10, 5)


def test_explicit_year_kept():
    r = p("зачёт по англу 15.10.2026")
    assert r.date == date(2026, 10, 15)
    assert (r.title, r.subject_id, r.task_type) == ("Зачёт", "eng", TaskType.exam_prep)


def test_presentation_day_after_tomorrow():
    r = p("сделать презентацию к докладу послезавтра")
    assert r.task_type == TaskType.report
    assert r.date == date(2026, 10, 8)
    assert r.title == "Сделать презентацию к докладу"


def test_study_by_time_today():
    r = p("решить задачи к 18:00")
    assert r.title == "Решить задачи"
    assert r.deadline == datetime(2026, 10, 6, 18, 0, tzinfo=MSK)
    assert r.is_deadline and r.kind_hint == KindHint.task


def test_end_of_month_deadline():
    r = p("отчёт для работы до конца месяца")
    assert r.title == "Отчёт для работы"
    assert r.date == date(2026, 10, 31) and r.is_deadline
    assert r.kind_hint == KindHint.task


def test_message_supervisor_by_friday():
    r = p("написать научруку до пятницы")
    assert r.title == "Написать научруку"
    assert r.date == date(2026, 10, 9) and r.kind_hint == KindHint.task


def test_word_srok_marks_deadline():
    r = p("лабораторная по физат, срок 30 октября")
    assert r.title == "Лабораторная"
    assert r.subject_id == "fiz" and r.date == date(2026, 10, 30) and r.is_deadline


def test_task_without_date():
    r = p("сдать реферат")
    assert r.date is None and r.deadline is None
    assert r.task_type == TaskType.essay and r.kind_hint == KindHint.task


# ---------- события ----------


def test_tomorrow_at_14_is_event():
    r = p("завтра в 14 консультация по динмету")
    assert r.kind_hint == KindHint.event
    assert r.title == "Консультация" and r.subject_id == "dyn"
    assert (r.date, r.time) == (date(2026, 10, 7), time(14, 0))


def test_weekday_with_time():
    r = p("встреча с научруком в четверг в 15:30")
    assert r.title == "Встреча с научруком"
    assert (r.date, r.time) == (date(2026, 10, 8), time(15, 30))
    assert r.kind_hint == KindHint.event


def test_time_range_today():
    r = p("бассейн с 19 до 20:30")
    assert r.title == "Бассейн"
    assert (r.date, r.time, r.end_time) == (date(2026, 10, 6), time(19, 0), time(20, 30))
    assert r.kind_hint == KindHint.event


def test_past_time_means_tomorrow():
    r = p("врач в 9 утра")
    assert r.title == "Врач"
    assert (r.date, r.time) == (date(2026, 10, 7), time(9, 0))


def test_evening_suffix():
    r = p("в 7 вечера кино")
    assert (r.title, r.date, r.time) == ("Кино", date(2026, 10, 6), time(19, 0))


def test_relative_hours():
    r = p("позвонить маме через 2 часа")
    assert r.title == "Позвонить маме"
    assert (r.date, r.time) == (date(2026, 10, 6), time(17, 0))
    assert r.kind_hint == KindHint.event


def test_slash_date_with_time():
    r = p("консультация 12/10 в 11:00")
    assert (r.date, r.time) == (date(2026, 10, 12), time(11, 0))
    assert r.title == "Консультация"


# ---------- ящик ----------


def test_plain_backlog():
    r = p("записаться к стоматологу")
    assert r.title == "Записаться к стоматологу"
    assert r.date is None and r.kind_hint == KindHint.backlog


def test_backlog_with_desired_date():
    r = p("купить продукты завтра")
    assert r.title == "Купить продукты"
    assert r.date == date(2026, 10, 7)
    assert not r.is_deadline and r.kind_hint == KindHint.backlog


def test_next_week_is_soft():
    r = p("разобрать шкаф на следующей неделе")
    assert r.title == "Разобрать шкаф"
    assert r.date == date(2026, 10, 18)
    assert r.kind_hint == KindHint.backlog


def test_in_a_week_backlog():
    r = p("через неделю вернуть книгу в библиотеку")
    assert r.title == "Вернуть книгу в библиотеку"
    assert r.date == date(2026, 10, 13) and r.kind_hint == KindHint.backlog


def test_duration_and_weekday():
    r = p("убраться дома в субботу на 2 часа")
    assert r.title == "Убраться дома"
    assert r.date == date(2026, 10, 10) and r.time is None
    assert r.duration_min == 120


# ---------- даты и дни недели ----------


def test_this_and_next_weekday():
    assert p("эссе в среду").date == date(2026, 10, 7)
    assert p("эссе в следующую среду").date == date(2026, 10, 14)
    # Понедельник уже прошёл — ближайший следующий
    assert p("эссе в понедельник").date == date(2026, 10, 12)
    assert p("эссе к пт").date == date(2026, 10, 9)


def test_same_weekday_means_next_week():
    friday = datetime(2026, 10, 9, 10, 0, tzinfo=MSK)
    assert p("доклад в пятницу", now=friday).date == date(2026, 10, 16)
    assert p("доклад в эту пятницу", now=friday).date == date(2026, 10, 9)


def test_end_of_week():
    assert p("прибраться до конца недели").date == date(2026, 10, 11)


def test_month_relative_and_half_hour():
    assert p("продлить пропуск через месяц").date == date(2026, 11, 6)
    r = p("выпить таблетку через полчаса")
    assert (r.date, r.time) == (date(2026, 10, 6), time(15, 30))


def test_invalid_date_left_in_title():
    r = p("встреча 31.02")
    assert r.date is None and r.title == "Встреча 31.02"


@pytest.mark.parametrize(
    ("text", "title"),
    [
        ("сходить в 5 магазинов", "Сходить в 5 магазинов"),
        ("в 10 магазинов", "В 10 магазинов"),
        ("на 2 человека забронировать стол", "На 2 человека забронировать стол"),
        ("купить 2 литра молока", "Купить 2 литра молока"),
    ],
)
def test_counts_are_not_times(text, title):
    r = p(text)
    assert r.time is None and r.title == title


def test_hours_word_and_daypart():
    r = p("в 2 часа ночи проснуться")
    assert (r.title, r.date, r.time) == ("Проснуться", date(2026, 10, 7), time(2, 0))


def test_bare_dotted_time_and_latin_c():
    assert p("семинар 14.30").time == time(14, 30)
    r = p("c 10 до 12 библиотека")
    assert (r.title, r.time, r.end_time) == ("Библиотека", time(10, 0), time(12, 0))


# ---------- предметы ----------


def test_ambiguous_subject_ignored():
    subjects = [SubjectRef("a", ("Физика атмосферы",)), SubjectRef("b", ("Физика облаков",))]
    assert p("доклад по физике", subjects=subjects).subject_id is None


def test_longest_subject_wins():
    subjects = [SubjectRef("a", ("Физика",)), SubjectRef("b", ("Физика атмосферы",))]
    assert p("доклад по физике атмосферы", subjects=subjects).subject_id == "b"


def test_short_name_needs_exact_match():
    subjects = [SubjectRef("m", ("мат",))]
    assert p("купить материалы", subjects=subjects).subject_id is None
    assert p("дз по мат", subjects=subjects).subject_id == "m"


def test_subject_kept_in_title_if_nothing_else():
    r = p("климатология завтра")
    assert r.subject_id == "clim" and r.title == "Климатология"


@pytest.mark.parametrize("text", ["", "   ", "до", "завтра"])
def test_degenerate_input(text):
    r = p(text)
    assert isinstance(r.title, str)


def test_naive_now_rejected():
    with pytest.raises(ValueError):
        parse("x", datetime(2026, 10, 6, 15, 0))
