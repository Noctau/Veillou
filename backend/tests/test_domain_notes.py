import time
from datetime import date

import pytest

from app.domain.notes import default_title, excerpt, short_date


def test_short_date():
    assert short_date(date(2026, 10, 6)) == "6 окт"
    assert short_date(date(2026, 5, 1)) == "1 мая"


def test_default_title():
    assert default_title(date(2026, 10, 6), "Климатология") == "Климатология · 6 окт"
    assert default_title(date(2026, 10, 6)) == "Конспект 6 окт"


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("", ""),
        ("# Лекция 3\n\nУравнение **состояния**", "Лекция 3 Уравнение состояния"),
        ("- первое\n- второе\n1. третье", "первое второе третье"),
        ("> цитата _курсив_", "цитата курсив"),
        ("Давление $p = \\rho R T$ растёт", "Давление … растёт"),
        ("До\n$$\n\\int_0^1 x\\,dx\n$$\nпосле", "До после"),
        ("См. [учебник](https://example.com) и ![схема](a.png)", "См. учебник и схема"),
        ("```python\nprint(1)\n```\nкод", "код"),
        ("Незакрытая $$ формула", "Незакрытая"),
    ],
)
def test_excerpt(markdown, expected):
    assert excerpt(markdown) == expected


def test_excerpt_cuts_on_word():
    text = "слово " * 50
    result = excerpt(text, limit=20)
    assert result == "слово слово слово…"
    assert len(result) <= 21


def test_excerpt_long_word():
    assert excerpt("а" * 30, limit=10) == "а" * 10 + "…"


@pytest.mark.parametrize(
    "unit",
    ["[", "![](", "[](", "[a](", "[a](b(", "$", "```", "$$"],
)
def test_excerpt_is_linear_on_pathological_input(unit):
    """M-04: тело конспекта до 200 000 символов не должно вешать сервер."""
    markdown = unit * (200_000 // len(unit))
    started = time.perf_counter()
    excerpt(markdown)
    assert time.perf_counter() - started < 0.5


def test_excerpt_strips_links_with_parentheses_in_url():
    text = "см. [учебник](https://example.com) и [вики](https://w.org/a_(b))"
    assert excerpt(text) == "см. учебник и вики"
