"""Вопросы к экзамену из вставленного текста (M12.1).

Понимает «1. …», «1) …», «1 - …», «№ 1 …», «Вопрос 1: …», «Билет 1. …». Если
нумерованных строк нет — каждая непустая строка становится вопросом
(маркеры списка «- », «• », «* » срезаются). В нумерованном списке строка без
номера продолжает предыдущий вопрос.
"""

import re
from dataclasses import dataclass

from app.domain.enums import ExamSessionKind

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
class ParsedQuestion:
    number: int
    text: str


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:MAX_TEXT]


def parse_questions(raw: str, start_number: int = 1) -> list[ParsedQuestion]:
    """Список вопросов. `start_number` — с какого номера считать ненумерованные."""
    lines = [line for line in raw.splitlines() if line.strip()]
    matches = [_NUMBERED.match(line) for line in lines]
    if any(m and m.group(3).strip() for m in matches):
        result: list[ParsedQuestion] = []
        for line, m in zip(lines, matches, strict=True):
            if m and m.group(3).strip():
                result.append(ParsedQuestion(int(m.group(2)), _clean(m.group(3))))
            elif result:
                last = result[-1]
                result[-1] = ParsedQuestion(last.number, _clean(f"{last.text} {line}"))
            # строки до первого номера («Вопросы к экзамену:») — заголовок, пропускаем
        return [q for q in result if q.text]

    result = []
    for line in lines:
        text = _clean(_BULLET.sub("", line))
        if text:
            result.append(ParsedQuestion(start_number + len(result), text))
    return result


# ---------- названия ----------

SESSION_VERB = {
    ExamSessionKind.learn: "выучить",
    ExamSessionKind.review: "повторить",
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


def session_title(kind: ExamSessionKind, subject: str, numbers: list[int]) -> str:
    if kind == ExamSessionKind.run:
        return f"{subject}: общий прогон билетов"
    return f"{subject}: {SESSION_VERB[kind]} {numbers_text(numbers)}".rstrip()


def exam_title(title: str, subject: str | None) -> str:
    return title.strip() or (f"Экзамен: {subject}" if subject else "Экзамен")
