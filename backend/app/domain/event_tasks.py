"""Автозадачи от событий (Part 2, M19): окно задачи и её название. Чисто.

Окно по правилу (`EventRuleWhen`):
- «до» — закончить за `offset_min` минут до начала; начинать не раньше конца
  предыдущего вхождения той же серии, но и не раньше чем за `LOOKAHEAD` до начала
  (иначе подготовку к уроку через два месяца план поставил бы сегодня);
- «после» — не раньше конца события; срок — конец + `within_days` дней и/или
  начало следующего вхождения серии (`until_next`), что раньше. Без обоих — без срока.

Серия вхождения — правило расписания, из которого оно материализовано; разовое
событие — тип занятости + сфера.

Название — шаблон с подстановками `{area}` / `{сфера}`, `{event}` / `{событие}`
(название события), `{field:<id или подпись>}` / `{поле:…}` (значение поля события,
потом — поля сферы). Чего нет —
подставляется пустое, лишние пробелы и висящие тире по краям убираются.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.enums import EventRuleWhen

LOOKAHEAD = timedelta(days=7)
_PLACEHOLDER = re.compile(
    r"\{\s*(area|сфера|event|событие|(?:field|поле)\s*:\s*([^{}]+?))\s*\}", re.IGNORECASE
)
AREA, EVENT = {"area", "сфера"}, {"event", "событие"}
_EDGES = " \t-–—:,·|"


@dataclass(frozen=True)
class RuleWindow:
    when: EventRuleWhen
    offset_min: int = 0
    within_days: int | None = None
    until_next: bool = False


@dataclass(frozen=True)
class Window:
    earliest: datetime | None
    deadline: datetime | None


def window(
    rule: RuleWindow,
    start: datetime,
    end: datetime,
    prev_end: datetime | None = None,
    next_start: datetime | None = None,
) -> Window:
    """Окно задачи вхождения [start, end). `prev_end` / `next_start` — соседние
    вхождения той же серии (None — их нет)."""
    if rule.when == EventRuleWhen.before:
        deadline = start - timedelta(minutes=rule.offset_min)
        earliest = start - LOOKAHEAD
        if prev_end is not None and prev_end > earliest:
            earliest = prev_end
        return Window(earliest if earliest < deadline else None, deadline)
    candidates: list[datetime] = []
    if rule.within_days is not None:
        candidates.append(end + timedelta(days=rule.within_days))
    if rule.until_next and next_start is not None and next_start > end:
        candidates.append(next_start)
    return Window(end, min(candidates) if candidates else None)


def render_title(
    template: str,
    *,
    event: str,
    area: str | None,
    fields: Mapping[str, str] | None = None,
) -> str:
    """Название по шаблону. `fields` — тексты полей по id и по подписи (без регистра)."""
    by_key = {k.casefold(): v for k, v in (fields or {}).items()}

    def sub(m: re.Match[str]) -> str:
        key = m.group(1).casefold()
        if key in AREA:
            return area or ""
        if key in EVENT:
            return event
        return by_key.get((m.group(2) or "").strip().casefold(), "")

    text = re.sub(r"\s{2,}", " ", _PLACEHOLDER.sub(sub, template)).strip(_EDGES)
    return text or event
