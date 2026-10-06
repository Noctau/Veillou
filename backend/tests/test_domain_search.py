import pytest

from app.domain.search import MAX_TERMS, build_tsquery


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", None),
        ("   ", None),
        ("!!! & | :*", None),
        ("климат", "климат:*"),
        ("Уравнение состоян", "уравнение:* & состоян:*"),
        ("ЁЛКА ёж", "елка:* & еж:*"),
        ("p = ρRT", "p:* & ρrt:*"),
        ("лекция 3", "лекция:* & 3:*"),
        ("a'b & c|d !e (f)", "a:* & b:* & c:* & d:* & e:* & f:*"),
        ("snake_case", "snake:* & case:*"),
        ("лекция лекция", "лекция:*"),  # повторы — один раз
    ],
)
def test_build_tsquery(text, expected):
    assert build_tsquery(text) == expected


def test_terms_limited():
    query = build_tsquery(" ".join(f"слово{i}" for i in range(20)))
    assert query is not None
    assert query.count("&") == MAX_TERMS - 1
