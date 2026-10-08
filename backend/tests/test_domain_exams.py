"""M12.1: вопросы к экзамену из вставленного списка."""

import pytest

from app.domain.exams import ParsedQuestion, parse_questions


def pq(*items: tuple[int, str]) -> list[ParsedQuestion]:
    return [ParsedQuestion(n, t) for n, t in items]


@pytest.mark.parametrize(
    "text",
    [
        "1. Циклоны\n2. Антициклоны",
        "1) Циклоны\n2) Антициклоны",
        "1 - Циклоны\n2 — Антициклоны",
        "№1. Циклоны\n№ 2 Антициклоны",
        "Вопрос 1: Циклоны\nВопрос 2: Антициклоны",
        "Билет 1. Циклоны\nБилет 2. Антициклоны",
    ],
)
def test_numbered_formats(text):
    assert parse_questions(text) == pq((1, "Циклоны"), (2, "Антициклоны"))


def test_line_by_line():
    text = "Циклоны\n\n  Антициклоны  \n- Фронты\n• Туман"
    assert parse_questions(text) == pq(
        (1, "Циклоны"), (2, "Антициклоны"), (3, "Фронты"), (4, "Туман")
    )


def test_line_by_line_continues_numbering():
    assert parse_questions("Циклоны\nФронты", start_number=11) == pq(
        (11, "Циклоны"), (12, "Фронты")
    )


def test_continuation_lines_join_previous_question():
    text = "Вопросы к экзамену:\n1. Уравнение состояния\nсухого воздуха.\n2. Адиабаты"
    assert parse_questions(text) == pq((1, "Уравнение состояния сухого воздуха."), (2, "Адиабаты"))


def test_keeps_source_numbers_and_gaps():
    assert parse_questions("5. A\n7. B") == pq((5, "A"), (7, "B"))


def test_decimal_is_not_a_number():
    text = "1. Термодинамика\n1.5 Влажность — подпункт"
    assert parse_questions(text) == pq((1, "Термодинамика 1.5 Влажность — подпункт"))


def test_empty():
    assert parse_questions("") == []
    assert parse_questions("\n  \n") == []


def test_whitespace_collapsed_and_trimmed():
    assert parse_questions("1.   Тепловой   баланс  \n") == pq((1, "Тепловой баланс"))
