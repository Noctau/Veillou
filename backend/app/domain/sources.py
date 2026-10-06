"""Чистая логика литературы: задание чтения из источника."""

TITLE_MAX = 300


def reading_title(title: str, chapters: str = "") -> str:
    """«Прочитать главы 3–5 — Курс метеорологии» / «Прочитать: Курс метеорологии»."""
    title = title.strip()
    chapters = chapters.strip()
    text = f"Прочитать {chapters} — {title}" if chapters else f"Прочитать: {title}"
    return text if len(text) <= TITLE_MAX else text[: TITLE_MAX - 1].rstrip() + "…"


def reading_description(title: str, author: str = "", url: str | None = None) -> str:
    """Откуда читать: «Матвеев Л. Т. — Курс общей метеорологии» и ссылка."""
    lines = [f"{author.strip()} — {title.strip()}" if author.strip() else title.strip()]
    if url:
        lines.append(url)
    return "\n".join(lines)
