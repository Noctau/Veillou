from app.domain.sources import TITLE_MAX, reading_description, reading_title


def test_reading_title():
    assert reading_title("Курс метеорологии") == "Прочитать: Курс метеорологии"
    assert reading_title(" Курс ", " главы 3–5 ") == "Прочитать главы 3–5 — Курс"


def test_reading_title_truncated():
    title = reading_title("а" * 400, "гл. 1")
    assert len(title) == TITLE_MAX
    assert title.endswith("…")


def test_reading_description():
    assert reading_description("Курс", "Матвеев Л. Т.") == "Матвеев Л. Т. — Курс"
    assert reading_description("Статья", "", "https://x.ru/a") == "Статья\nhttps://x.ru/a"
