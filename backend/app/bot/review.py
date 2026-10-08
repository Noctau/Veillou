"""Разборы и `/free` в боте (M11.1, M11.3, M11.4).

callback_data (лимит Telegram — 64 байта):
- `rv:d:<event hex>` — вечерний разбор «по одному»: блок сделан;
- `fr:m:<минут>` — `/free` без числа: выбор, сколько есть времени;
- `fr:s:<s|t|b>:<hex>` — «Начать»: шаг / задание / дело из ящика.
"""

import html
import uuid

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.ai import _open, _rows, plan_keyboard, plan_text
from app.core.exceptions import AppError
from app.core.time import get_tz
from app.domain.enums import EventStatus, ReminderAction
from app.models import Reminder, User
from app.notify.message import fmt_range, fmt_time
from app.notify.notifier import reminder_callback
from app.schemas.event import EventUpdate
from app.services.events import EventService
from app.services.free import FreeService
from app.services.replan import ReplanService, plan_state
from app.services.review import ReviewService

RV_PREFIX = "rv:"
FR_PREFIX = "fr:"
FREE_CHOICES = (15, 30, 60, 90, 120)
KIND_CODE = {"subtask": "s", "task": "t", "backlog": "b"}
CODE_KIND = {v: k for k, v in KIND_CODE.items()}


def _short(text: str, limit: int = 40) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------- после действия: превью плана ----------


async def reply_plan(message: Message, db: AsyncSession, user: User) -> None:
    state = await plan_state(ReplanService(db, user))
    markup = plan_keyboard(state.proposal.id) if state.proposal else None
    await message.reply(plan_text(state), parse_mode="HTML", reply_markup=markup)


# ---------- вечерний разбор: по одному ----------


async def show_pick(
    callback: CallbackQuery, db: AsyncSession, user: User, reminder_id: uuid.UUID
) -> None:
    r = await db.get(Reminder, reminder_id)
    if r is None or r.user_id != user.id or "date" not in r.payload:
        await callback.answer("Разбор устарел", show_alert=True)
        return
    from datetime import date

    items, _ = await ReviewService(db, user).evening_items(date.fromisoformat(r.payload["date"]))
    if not items:
        await callback.answer("Всё уже отмечено")
        return
    tz = get_tz(user.timezone)
    rows = [
        [
            InlineKeyboardButton(
                text=f"✓ {fmt_time(e.start, tz)} {_short(e.title)}",
                callback_data=f"{RV_PREFIX}d:{e.id.hex}",
            )
        ]
        for e in items
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="Перенести остальное",
                callback_data=reminder_callback(ReminderAction.reschedule, reminder_id),
            )
        ]
    )
    await callback.answer("Отметьте сделанное, остальное перенесу")
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )


def _without(markup: InlineKeyboardMarkup | None, data: str) -> InlineKeyboardMarkup | None:
    if markup is None:
        return None
    rows = [row for row in markup.inline_keyboard if not any(b.callback_data == data for b in row)]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def review_callback(callback: CallbackQuery, db: AsyncSession, user: User) -> None:
    data = callback.data or ""
    parts = data.removeprefix(RV_PREFIX).split(":")
    if len(parts) != 2 or parts[0] != "d":
        await callback.answer()
        return
    try:
        event_id = uuid.UUID(hex=parts[1])
        await EventService(db, user).update(event_id, EventUpdate(status=EventStatus.done))
    except (ValueError, AppError) as exc:
        await callback.answer(getattr(exc, "message", "Не получилось"), show_alert=True)
        return
    await callback.answer("Отмечено ✓")
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=_without(callback.message.reply_markup, data)
        )


# ---------- /free ----------


def minutes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{m} мин" if m < 60 else f"{m // 60} ч" + (" 30" if m % 60 else ""),
                    callback_data=f"{FR_PREFIX}m:{m}",
                )
                for m in FREE_CHOICES
            ]
        ]
    )


async def free_reply(
    db: AsyncSession, user: User, minutes: int
) -> tuple[str, InlineKeyboardMarkup | None]:
    items = await FreeService(db, user).suggest(minutes)
    if not items:
        return (
            f"На {minutes} мин подходящего сейчас нет: шаги не влезают или их время не сейчас.",
            _rows([_open("/inbox")]),
        )
    lines = [f"<b>Есть {minutes} мин — можно:</b>"]
    rows: list[list[InlineKeyboardButton | None]] = []
    for i, item in enumerate(items):
        sub = f" · {html.escape(item.subtitle)}" if item.subtitle else ""
        lines.append(
            f"{'⭐' if i == 0 else '•'} {html.escape(item.title)} — {item.minutes} мин{sub}"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"▶ {_short(item.title, 30)}",
                    callback_data=f"{FR_PREFIX}s:{KIND_CODE[item.kind]}:{item.id.hex}",
                )
            ]
        )
    return "\n".join(lines), _rows(*rows)


async def free_command(message: Message, db: AsyncSession, user: User, args: str | None) -> None:
    text = (args or "").strip().split()
    if text and text[0].isdigit() and 5 <= int(text[0]) <= 480:
        body, markup = await free_reply(db, user, int(text[0]))
        await message.answer(body, parse_mode="HTML", reply_markup=markup)
        return
    await message.answer("Сколько есть времени?", reply_markup=minutes_keyboard())


async def free_callback(callback: CallbackQuery, db: AsyncSession, user: User) -> None:
    parts = (callback.data or "").removeprefix(FR_PREFIX).split(":")
    try:
        if parts[0] == "m" and len(parts) == 2:
            body, markup = await free_reply(db, user, int(parts[1]))
            await callback.answer()
            if isinstance(callback.message, Message):
                await callback.message.edit_text(body, parse_mode="HTML", reply_markup=markup)
            return
        if parts[0] == "s" and len(parts) == 3:
            kind = CODE_KIND[parts[1]]
            event = await FreeService(db, user).start(kind, uuid.UUID(hex=parts[2]))
            tz = get_tz(user.timezone)
            await callback.answer("Поехали!")
            if isinstance(callback.message, Message):
                await callback.message.edit_reply_markup(reply_markup=None)
                await callback.message.reply(
                    f"▶ {html.escape(event.title)}: {fmt_range(event.start, event.end, tz)}. "
                    "Отметьте «сделано», когда закончите.",
                    parse_mode="HTML",
                )
            return
    except (KeyError, ValueError):
        pass
    except AppError as exc:
        await callback.answer(exc.message, show_alert=True)
        return
    await callback.answer()
