"""Чистая логика поиска: строка из поля ввода → запрос Postgres FTS (`to_tsquery`)."""

import re

MAX_TERMS = 8
# Только буквы и цифры: всё остальное (кавычки, &, |, !, :, скобки) — синтаксис tsquery
_WORD = re.compile(r"[^\W_]+")

# Маркеры совпадений в сниппете (ts_headline) — управляющие символы, в тексте их нет
HIT_START = "\x02"
HIT_END = "\x03"


def normalize(text: str) -> str:
    """Регистр и «ё» → «е»: так же нормализуется индексируемый текст."""
    return text.lower().replace("ё", "е")


def build_tsquery(text: str) -> str | None:
    """«уравнение состоян» → «уравнение:* & состоян:*» (все слова, каждое — как префикс,
    чтобы искать по мере набора). Пустой ввод — None."""
    terms = list(dict.fromkeys(_WORD.findall(normalize(text))))[:MAX_TERMS]
    if not terms:
        return None
    return " & ".join(f"{t}:*" for t in terms)
