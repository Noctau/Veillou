"""Вычитка лексики (M22.3): студенческие слова Part 1 только в данных и миграциях.

    cd backend && uv run python -m scripts.check_lexicon        # make lexicon

Проверяет код бэкенда (`app/`, кроме данных evals) и фронта (`frontend/src`, кроме
тестов):
«пара», «семестр», «научрук», «студент», «ауд.». Законное употребление («через пару
дней» в грамматике быстрого ввода) помечается в строке `lexicon-ok`.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = (ROOT / "backend" / "app", ROOT / "frontend" / "src")
SUFFIXES = {".py", ".ts", ".tsx"}
# Данные, а не код: эталонные кейсы ИИ описывают и студентку
SKIP = (ROOT / "backend" / "app" / "ai" / "evals",)
ALLOW = "lexicon-ok"

FORBIDDEN = re.compile(
    r"(?<![а-яё])(?:пар(?:а|ы|у|е|ой|ам|ами|ах)|семестр[а-яё]*|научрук[а-яё]*|студент[а-яё]*)"
    r"(?![а-яё])|(?<![а-яё])ауд\.",
    re.IGNORECASE,
)


def problems() -> list[str]:
    found = []
    for base in SOURCES:
        for path in sorted(base.rglob("*")):
            if path.suffix not in SUFFIXES or any(path.is_relative_to(s) for s in SKIP):
                continue
            if ".test." in path.name:  # тесты фронта — фикстуры, как backend/tests
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if ALLOW in line:
                    continue
                for m in FORBIDDEN.finditer(line):
                    found.append(f"{path.relative_to(ROOT)}:{n}: «{m.group()}» — {line.strip()}")
    return found


def main() -> int:
    found = problems()
    for line in found:
        print(line)
    if found:
        print(f"\nЛексика Part 1 в коде: {len(found)}. Названия — из настройки пользователя.")
        return 1
    print("Лексика: чисто")
    return 0


if __name__ == "__main__":
    sys.exit(main())
