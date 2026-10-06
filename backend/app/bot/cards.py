"""Тексты и клавиатуры бота; разбор callback_data (лимит Telegram — 64 байта).

Форматы:
- `qa:<op>:<kind>:<id>[:<target>]` — карточка созданного из текста
  (op: edit / back / del / to; kind и target: t — задание, b — ящик, e — событие);
- `ra:<action>:<reminder id>` — кнопки напоминаний.
"""

import html
import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.config import settings
from app.domain.enums import ReminderAction
from app.domain.quickparse import KindHint
from app.notify.message import fmt_day, fmt_moment, fmt_range
from app.services.quickadd import Created

QA_PREFIX = "qa:"
RA_PREFIX = "ra:"

KIND_CODE = {KindHint.task: "t", KindHint.backlog: "b", KindHint.event: "e"}
CODE_KIND = {v: k for k, v in KIND_CODE.items()}
KIND_TITLE = {KindHint.task: "Задание", KindHint.backlog: "В ящике", KindHint.event: "Событие"}
KIND_BUTTON = {KindHint.task: "Задание", KindHint.backlog: "В ящик", KindHint.event: "Событие"}
KIND_DONE = {
    KindHint.task: "Теперь это задание",
    KindHint.backlog: "Перенесено в ящик",
    KindHint.event: "Теперь это событие",
}


def _url(created_kind: KindHint, id: uuid.UUID) -> str | None:
    if not settings.APP_URL:
        return None
    path = {KindHint.task: f"/tasks/{id}", KindHint.backlog: "/inbox", KindHint.event: "/calendar"}
    return f"{settings.APP_URL}{path[created_kind]}"


def created_text(c: Created, tz: ZoneInfo, now: datetime) -> str:
    today = now.astimezone(tz).date()
    details = []
    if c.deadline:
        details.append(f"до {fmt_moment(c.deadline, tz, today)}")
    if c.desired_by:
        details.append(f"хорошо бы до {fmt_day(c.desired_by, today)}")
    if c.start and c.end:
        details.append(
            f"{fmt_day(c.start.astimezone(tz).date(), today)} {fmt_range(c.start, c.end, tz)}"
        )
    if c.subject:
        details.append(c.subject)
    head = f"✓ <b>{KIND_TITLE[c.kind]}:</b> {html.escape(c.title)}"
    return "\n".join([head, html.escape(" · ".join(details))]) if details else head


def _qa(op: str, kind: KindHint, id: uuid.UUID, target: KindHint | None = None) -> str:
    data = f"{QA_PREFIX}{op}:{KIND_CODE[kind]}:{id.hex}"
    return f"{data}:{KIND_CODE[target]}" if target else data


def back_keyboard(kind: KindHint, id: uuid.UUID) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text="Изменить", callback_data=_qa("edit", kind, id))]
    if url := _url(kind, id):
        row.append(InlineKeyboardButton(text="Открыть", url=url))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def created_keyboard(c: Created) -> InlineKeyboardMarkup:
    return back_keyboard(c.kind, c.id)


def edit_keyboard(kind: KindHint, id: uuid.UUID) -> InlineKeyboardMarkup:
    switch = [
        InlineKeyboardButton(text=f"→ {KIND_BUTTON[k]}", callback_data=_qa("to", kind, id, k))
        for k in KIND_CODE
        if k != kind
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            switch,
            [
                InlineKeyboardButton(text="Удалить", callback_data=_qa("del", kind, id)),
                InlineKeyboardButton(text="← Назад", callback_data=_qa("back", kind, id)),
            ],
        ]
    )


@dataclass(frozen=True)
class QuickAddData:
    op: str
    kind: KindHint
    id: uuid.UUID
    target: KindHint | None = None


def parse_quick_add(data: str) -> QuickAddData | None:
    parts = data.removeprefix(QA_PREFIX).split(":")
    if len(parts) not in (3, 4) or parts[0] not in ("edit", "back", "del", "to"):
        return None
    try:
        kind = CODE_KIND[parts[1]]
        id = uuid.UUID(hex=parts[2])
        target = CODE_KIND[parts[3]] if len(parts) == 4 else None
    except (KeyError, ValueError):
        return None
    if parts[0] == "to" and target is None:
        return None
    return QuickAddData(parts[0], kind, id, target)


def parse_reminder(data: str) -> tuple[ReminderAction, uuid.UUID] | None:
    parts = data.removeprefix(RA_PREFIX).split(":")
    if len(parts) != 2:
        return None
    try:
        return ReminderAction(parts[0]), uuid.UUID(hex=parts[1])
    except ValueError:
        return None


def without_actions(markup: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup | None:
    """Убирает кнопки действий напоминания, оставляя ссылки."""
    if markup is None:
        return None
    rows = [
        row
        for row in markup.inline_keyboard
        if not any((b.callback_data or "").startswith(RA_PREFIX) for b in row)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
