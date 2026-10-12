"""Жёсткое событие в текстах (сводка, напоминания, бот).

Всё берётся из данных: место — с подписью типа занятости (`location_label`), поля —
с флагом `show_in_reminder`. Значения выбора («Вид занятия») идут в строку события,
остальные поля — строками «Подпись: значение» в напоминании.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from app.domain.enums import EventStatus
from app.domain.fields import parse_defs, render_split
from app.models import Event, EventType
from app.notify.message import fmt_range


@dataclass(frozen=True)
class EventParts:
    inline: tuple[str, ...]  # значения выбора: «лекция»
    details: tuple[tuple[str, str], ...]  # остальные поля: («Преподаватель», «Иванов»)
    place: str | None  # «ауд. 1801» / «СК МГУ»


def place(e: Event, event_type: EventType | None) -> str | None:
    if not e.location:
        return None
    label = event_type.location_label if event_type else ""
    return f"{label} {e.location}" if label else e.location


def event_parts(e: Event, event_type: EventType | None) -> EventParts:
    if event_type is None:
        return EventParts((), (), place(e, None))
    inline, details = render_split(parse_defs(event_type.fields), e.fields, only_reminder=True)
    return EventParts(tuple(inline), tuple(details), place(e, event_type))


def busy_line(e: Event, event_type: EventType | None, tz: ZoneInfo) -> str:
    """Строка события секции типа: «09:00–10:35 Климатология (лекция) · ауд. 1801»."""
    parts = event_parts(e, event_type)
    head = f"{fmt_range(e.start, e.end, tz)} {e.title}"
    if parts.inline:
        head += f" ({', '.join(parts.inline)})"
    line = " · ".join(p for p in (head, parts.place) if p)
    return f"{line} — отменена" if e.status == EventStatus.cancelled else line
