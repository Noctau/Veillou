"""Пункты подготовки из вставленного текста (M12.1, M20: билеты, темы, части
выступления) и названия дней подготовки.

Понимает «1. …», «1) …», «1 - …», «№ 1 …», «Вопрос 1: …», «Билет 1. …». Если
нумерованных строк нет — каждая непустая строка становится вопросом
(маркеры списка «- », «• », «* » срезаются). В нумерованном списке строка без
номера продолжает предыдущий вопрос.
"""

import re
from dataclasses import dataclass

from app.domain.enums import PrepSessionKind

MAX_TEXT = 2000

_NUMBERED = re.compile(
    r"""^\s*
    ((?:вопрос|билет)\s*(?:№\s*)?|№\s*)?  # «Вопрос 3», «Билет № 3», «№ 3»
    (\d{1,3})
    (?:\s*(?:\.(?!\d)|[)\]:]|\s-|\s–|\s—)  # 1.  1)  1]  1:  1 -  1 — (но не «1.5»)
      |(?(1)\s|(?!)))                       # после «№» / «Вопрос» хватит пробела
    \s*(.*)$""",
    re.IGNORECASE | re.VERBOSE,
)
_BULLET = re.compile(r"^\s*(?:[-•*·–—]\s+)")


@dataclass(frozen=True)
class ParsedItem:
    number: int
    text: str


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:MAX_TEXT]


def parse_items(raw: str, start_number: int = 1) -> list[ParsedItem]:
    """Список пунктов. `start_number` — с какого номера считать ненумерованные."""
    lines = [line for line in raw.splitlines() if line.strip()]
    matches = [_NUMBERED.match(line) for line in lines]
    if any(m and m.group(3).strip() for m in matches):
        result: list[ParsedItem] = []
        for line, m in zip(lines, matches, strict=True):
            if m and m.group(3).strip():
                result.append(ParsedItem(int(m.group(2)), _clean(m.group(3))))
            elif result:
                last = result[-1]
                result[-1] = ParsedItem(last.number, _clean(f"{last.text} {line}"))
            # строки до первого номера («Вопросы к экзамену:») — заголовок, пропускаем
        return [q for q in result if q.text]

    result = []
    for line in lines:
        text = _clean(_BULLET.sub("", line))
        if text:
            result.append(ParsedItem(start_number + len(result), text))
    return result


# ---------- названия ----------

SESSION_VERB = {
    PrepSessionKind.learn: "выучить",
    PrepSessionKind.review: "повторить",
}


def numbers_text(numbers: list[int]) -> str:
    """[1, 2, 3, 4, 7, 9, 10] → «№1–4, 7, 9–10»."""
    nums = sorted(set(numbers))
    parts: list[str] = []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        parts.append(f"{nums[i]}–{nums[j]}" if j - i >= 2 else ", ".join(map(str, nums[i : j + 1])))
        i = j + 1
    return "№" + ", ".join(parts) if parts else ""


def session_title(kind: PrepSessionKind, name: str, numbers: list[int]) -> str:
    """«Климатология: выучить №1–4». Прогон — без номеров (все пункты)."""
    if kind == PrepSessionKind.run:
        return f"{name}: общий прогон билетов"
    return f"{name}: {SESSION_VERB[kind]} {numbers_text(numbers)}".rstrip()


def plan_title(title: str, event: str | None, area: str | None) -> str:
    """Название плана: своё → событие → сфера → «Подготовка»."""
    return title.strip() or event or (f"Подготовка: {area}" if area else "Подготовка")
