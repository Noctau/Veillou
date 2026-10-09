"""Чистая логика конспектов: название по умолчанию и короткий текст для списка."""

import re
from datetime import date

MONTHS_GEN = (
    "янв",
    "фев",
    "мар",
    "апр",
    "мая",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)


def short_date(day: date) -> str:
    """«6 окт»."""
    return f"{day.day} {MONTHS_GEN[day.month - 1]}"


def default_title(day: date, subject: str | None = None) -> str:
    """«Климатология · 6 окт» или «Конспект 6 окт»."""
    return f"{subject} · {short_date(day)}" if subject else f"Конспект {short_date(day)}"


# Блоки формул и кода в выдержку не попадают — в списке это шум
_FENCED = re.compile(r"```.*?(```|$)|\$\$.*?(\$\$|$)", re.DOTALL)
_INLINE_MATH = re.compile(r"\$[^$\n]+\$")
# Классы символов не пересекаются со скобками-разделителями: без этого незакрытые «[»
# или «(» давали квадратичный откат (тело до 200 000 символов → минуты CPU).
# В адресе допускается одна пара скобок: https://ru.wikipedia.org/wiki/A_(b)
_LINK = re.compile(r"!?\[([^\[\]]*)\]\((?:[^()]|\([^()]*\))*\)")
_MARKUP = re.compile(r"^\s{0,3}(#{1,6}|>|[-*+]|\d+[.)])\s+|[*_`~]+", re.MULTILINE)
_SPACES = re.compile(r"\s+")


def excerpt(markdown: str, limit: int = 160) -> str:
    """Начало текста без разметки Markdown и формул, не длиннее `limit` символов."""
    text = _FENCED.sub(" ", markdown)
    text = _INLINE_MATH.sub("…", text)
    text = _LINK.sub(r"\1", text)
    text = _MARKUP.sub("", text)
    text = _SPACES.sub(" ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip(".,;:—- ") + "…"
