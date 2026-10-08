"""Сообщение уведомления — одно на канал, независимо от канала по форме.

Telegram рисует заголовки разделов жирным (HTML), push — простым текстом.
"""

import html
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.domain.enums import ReminderAction, ReminderKind

ACTION_TITLES = {
    ReminderAction.done: "Сделано",
    ReminderAction.snooze: "+15 мин",
    ReminderAction.tomorrow: "На завтра",
    ReminderAction.reschedule: "Перенести всё",
    ReminderAction.pick: "По одному",
    ReminderAction.accept: "Взять на неделю",
}
# Только в Telegram: в пуше раскрывать нечего
TELEGRAM_ONLY = frozenset({ReminderAction.pick})

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WEEKDAYS_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
MONTHS_FULL = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


@dataclass(frozen=True)
class Section:
    heading: str | None
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Message:
    title: str
    sections: tuple[Section, ...] = ()
    url: str = "/"  # путь в приложении
    actions: tuple[ReminderAction, ...] = ()
    kind: ReminderKind | None = None
    # Напоминание, к которому относятся кнопки (только у одиночного сообщения)
    reminder_id: uuid.UUID | None = None
    # Одноразовый токен для кнопок пуша (выставляет отправитель)
    action_token: str | None = None
    tag: str | None = None  # одинаковый tag заменяет прежний пуш

    def plain_body(self) -> str:
        parts = []
        for s in self.sections:
            block = "\n".join(s.lines)
            parts.append(f"{s.heading}\n{block}" if s.heading else block)
        return "\n\n".join(p for p in parts if p)

    def telegram_html(self) -> str:
        parts = [f"<b>{html.escape(self.title)}</b>"]
        for s in self.sections:
            lines = "\n".join(html.escape(line) for line in s.lines)
            parts.append(f"<b>{html.escape(s.heading)}</b>\n{lines}" if s.heading else lines)
        return "\n\n".join(p for p in parts if p)


def lines(*items: str | None) -> tuple[str, ...]:
    return tuple(i for i in items if i)


def combine(messages: list[Message]) -> Message:
    """Склейка совпавших по времени напоминаний в одно сообщение."""
    if len(messages) == 1:
        return messages[0]
    digest = next((m for m in messages if m.kind == ReminderKind.morning_digest), None)
    others = [m for m in messages if m is not digest]
    if digest is not None:
        extra = Section("Не забыть", tuple(_one_line(m) for m in others))
        return replace(digest, sections=(extra, *digest.sections), reminder_id=None, actions=())
    return Message(
        title=f"Напоминания: {len(messages)}",
        sections=tuple(Section(m.title, _flat(m)) for m in messages),
        url="/",
    )


def _flat(m: Message) -> tuple[str, ...]:
    return tuple(line for s in m.sections for line in s.lines)


def _one_line(m: Message) -> str:
    first = _flat(m)[:1]
    return f"{m.title} — {first[0]}" if first else m.title


# ---------- даты по-русски ----------


def fmt_time(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%H:%M")


def fmt_range(start: datetime, end: datetime, tz: ZoneInfo) -> str:
    return f"{fmt_time(start, tz)}–{fmt_time(end, tz)}"


def fmt_day(d: date, today: date | None = None) -> str:
    """«сегодня», «завтра» или «пт, 10 окт»."""
    if today is not None:
        delta = (d - today).days
        if delta == 0:
            return "сегодня"
        if delta == 1:
            return "завтра"
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def fmt_day_full(d: date) -> str:
    """«Вторник, 7 октября»."""
    return f"{WEEKDAYS_FULL[d.weekday()]}, {d.day} {MONTHS_FULL[d.month - 1]}"


def fmt_moment(dt: datetime, tz: ZoneInfo, today: date | None = None) -> str:
    local = dt.astimezone(tz)
    return f"{fmt_day(local.date(), today)} {local.strftime('%H:%M')}"


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
