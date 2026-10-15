"""Общее для экранов управления в боте (bot/menu.py и экраны *_ui.py).

Экран — функция, которая возвращает (текст HTML, клавиатуру). Команда присылает
его новым сообщением, кнопка — правит сообщение с кнопкой на месте.

callback_data `m:<op>[:<arg>…]` (лимит Telegram — 64 байта; id — 32 hex).
Ввод текста («напишите срок») — состояние FSM `Ask.input` с полями `what`
(что ждём) и `arg` (к чему относится); /cancel или любая команда — отмена.
"""

import contextlib
import html
import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import User

M_PREFIX = "m:"
PAGE_SIZE = 8
# Лимит Telegram — 4096 символов; запас на разметку
MAX_TEXT = 3800

Screen = tuple[str, InlineKeyboardMarkup | None]
Button = InlineKeyboardButton | None


class Ask(StatesGroup):
    input = State()


@dataclass
class Ctx:
    """Что нужно экрану: сессия БД, пользователь и состояние ввода.

    `say` — всплывашка на нажатую кнопку (на кнопку отвечают один раз — после экрана).
    """

    db: AsyncSession
    user: User
    state: FSMContext
    notice: str | None = None
    alert: bool = False

    def say(self, text: str, *, alert: bool = False) -> None:
        self.notice, self.alert = text, alert


# Кнопка: (ctx, аргументы после op) → экран; None — экран уже показан сам
CallbackHandler = Callable[[Ctx, CallbackQuery, list[str]], Awaitable[Screen | None]]
# Ввод текста: (ctx, сообщение, arg) → экран-ответ
InputHandler = Callable[[Ctx, Message, str], Awaitable[Screen]]

CALLBACKS: dict[str, CallbackHandler] = {}
INPUTS: dict[str, InputHandler] = {}
# Подсказка, с которой бот просит ввод
PROMPTS: dict[str, str] = {}


def on_callback(op: str) -> Callable[[CallbackHandler], CallbackHandler]:
    def register(fn: CallbackHandler) -> CallbackHandler:
        if op in CALLBACKS:
            raise RuntimeError(f"Кнопка m:{op} уже занята")
        CALLBACKS[op] = fn
        return fn

    return register


def on_input(what: str, prompt: str) -> Callable[[InputHandler], InputHandler]:
    """Ввод текстом: кнопка `m:ask:<what>:<arg>` просит `prompt`, ответ — в `fn`."""

    def register(fn: InputHandler) -> InputHandler:
        if what in INPUTS:
            raise RuntimeError(f"Ввод {what} уже занят")
        INPUTS[what] = fn
        PROMPTS[what] = prompt
        return fn

    return register


# ---------- кнопки ----------


def cb(op: str, *args: object) -> str:
    parts = [op, *(a.hex if isinstance(a, uuid.UUID) else str(a) for a in args)]
    data = M_PREFIX + ":".join(parts)
    if len(data.encode()) > 64:
        raise ValueError(f"callback_data длиннее 64 байт: {data}")
    return data


def parse(data: str) -> tuple[str, list[str]] | None:
    if not data.startswith(M_PREFIX):
        return None
    parts = data.removeprefix(M_PREFIX).split(":")
    return (parts[0], parts[1:]) if parts[0] else None


def uid(raw: str) -> uuid.UUID:
    """hex из callback_data → UUID (ValueError — кривые данные)."""
    return uuid.UUID(hex=raw)


def btn(text: str, op: str, *args: object) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb(op, *args))


def link(path: str, text: str = "🌐 Открыть") -> InlineKeyboardButton | None:
    if not settings.APP_URL:
        return None
    return InlineKeyboardButton(text=text, url=f"{settings.APP_URL}{path}")


def kb(*rows: Sequence[Button]) -> InlineKeyboardMarkup:
    clean = [[b for b in row if b is not None] for row in rows]
    return InlineKeyboardMarkup(inline_keyboard=[row for row in clean if row])


def pager(op: str, page: int, total: int, *extra: object) -> list[Button]:
    """◀ N/M ▶ — только если страниц больше одной."""
    pages = max(1, -(-total // PAGE_SIZE))
    if pages <= 1:
        return []
    return [
        btn("◀", op, page - 1, *extra) if page > 0 else None,
        btn(f"{page + 1}/{pages}", "noop"),
        btn("▶", op, page + 1, *extra) if page + 1 < pages else None,
    ]


def page_of[T](items: Sequence[T], page: int) -> tuple[list[T], int]:
    """Срез страницы и её номер (зажат в границы)."""
    pages = max(1, -(-len(items) // PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    return list(items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]), page


def to_int(raw: str | None, default: int = 0) -> int:
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


# ---------- текст ----------


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def short(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def clip(text: str, limit: int = MAX_TEXT) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


_DURATION = re.compile(
    r"(?:(?P<h>\d+(?:[.,]\d+)?)\s*(?:ч|час|часа|часов|h)\.?)?\s*"
    r"(?:(?P<m>\d+)\s*(?:м|мин|минут|минуты|минута|m|min)\.?)?",
    re.IGNORECASE,
)


def parse_minutes(text: str) -> int | None:
    """«90», «1.5 ч», «1 ч 30 мин», «2ч», «45 мин» → минуты; None — не похоже на время."""
    text = text.strip().casefold().removeprefix("на ").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    m = _DURATION.fullmatch(text)
    if m is None or not (m["h"] or m["m"]):
        return None
    hours = float(m["h"].replace(",", ".")) if m["h"] else 0.0
    return round(hours * 60) + (int(m["m"]) if m["m"] else 0)


_TAIL_DURATION = re.compile(
    r"[\s,;—–-]+(?:на\s+)?(\d+(?:[.,]\d+)?\s*(?:ч|час|часа|часов|м|мин|минут|минуты)\.?"
    r"(?:\s*\d+\s*(?:м|мин|минут|минуты)\.?)?|\d+)\s*$",
    re.IGNORECASE,
)


def split_step(text: str) -> tuple[str, int | None]:
    """«Найти источники, 40 мин» → («Найти источники», 40). Без времени — (текст, None)."""
    text = " ".join(text.split())
    m = _TAIL_DURATION.search(text)
    if m and m.start() > 0 and (minutes := parse_minutes(m[1])) is not None:
        return text[: m.start()].strip(" ,;—–-"), minutes
    return text, None


# ---------- показ ----------


async def show(target: Message | CallbackQuery, screen: Screen) -> None:
    """Команда — новое сообщение; кнопка — правка сообщения с кнопкой."""
    text, markup = screen
    if isinstance(target, CallbackQuery):
        if isinstance(target.message, Message):
            # «message is not modified» — тот же экран, не ошибка
            with contextlib.suppress(TelegramBadRequest):
                await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        return
    await target.answer(text, parse_mode="HTML", reply_markup=markup)


async def ask(ctx: Ctx, callback: CallbackQuery, what: str, arg: str, prompt: str) -> None:
    """Ждём текст от пользователя: подсказка — новым сообщением."""
    await ctx.state.set_state(Ask.input)
    await ctx.state.set_data({"what": what, "arg": arg})
    if isinstance(callback.message, Message):
        await callback.message.answer(f"{prompt}\n\n<i>/cancel — отмена</i>", parse_mode="HTML")
