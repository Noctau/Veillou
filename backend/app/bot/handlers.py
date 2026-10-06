"""Команды и кнопки бота.

- /today, /week — план на сегодня и неделю;
- /add <текст> и любой текст без команды — задание / дело в ящик / событие по
  разбору quickparse, с кнопкой «Изменить» (сменить тип или удалить);
- кнопки на напоминаниях: «Сделано», «+15 мин», «На завтра».
"""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import cards
from app.core.exceptions import AppError
from app.core.time import get_tz, now_utc
from app.models import User
from app.services import quickadd, reminder_actions, telegram
from app.services.digest import Digest

HELP = (
    "Пишите мне что угодно — я разберу и сохраню:\n"
    "• «реферат климатология до 15 окт» — задание с дедлайном\n"
    "• «записаться к стоматологу» — дело в долгий ящик\n"
    "• «кино в пт в 19» — событие в календаре\n\n"
    "/today — план на сегодня\n"
    "/week — план на неделю\n"
    "/add <текст> — то же, что просто написать\n\n"
    "Напоминания и утренняя сводка тоже приходят сюда."
)


async def start_with_code(
    message: Message, command: CommandObject, db: AsyncSession, user: User | None
) -> None:
    assert message.from_user is not None and command.args is not None
    try:
        linked = await telegram.link_by_code(db, command.args, tg_user_id=message.from_user.id)
    except telegram.LinkError as exc:
        await message.answer(exc.message)
        return
    await message.answer(f"Готово, Telegram привязан к {linked.email}.\n\n{HELP}")


async def start(message: Message) -> None:
    # Сюда доходят только привязанные: остальных отсекает AccessMiddleware
    await message.answer(f"Привет! {HELP}")


async def help_(message: Message) -> None:
    await message.answer(HELP)


async def today(message: Message, db: AsyncSession, user: User) -> None:
    digest = Digest(db, user)
    msg = await digest.day(digest.today)
    await message.answer(msg.telegram_html(), parse_mode="HTML")


async def week(message: Message, db: AsyncSession, user: User) -> None:
    digest = Digest(db, user)
    msg = await digest.week(digest.today)
    await message.answer(msg.telegram_html(), parse_mode="HTML")


async def _create(message: Message, db: AsyncSession, user: User, text: str) -> None:
    try:
        created = await quickadd.create_from_text(db, user, text)
    except AppError as exc:
        await message.reply(exc.message)
        return
    await message.reply(
        cards.created_text(created, get_tz(user.timezone), now_utc()),
        parse_mode="HTML",
        reply_markup=cards.created_keyboard(created),
    )


async def add(message: Message, command: CommandObject, db: AsyncSession, user: User) -> None:
    if not command.args or not command.args.strip():
        await message.answer("Что добавить? Например: /add записаться к стоматологу")
        return
    await _create(message, db, user, command.args)


async def free_text(message: Message, db: AsyncSession, user: User) -> None:
    text = message.text or message.caption
    if not text or not text.strip():
        await message.answer(HELP)
        return
    await _create(message, db, user, text)


# ---------- кнопки карточки «Создано» ----------


def _source_text(callback: CallbackQuery) -> str | None:
    """Исходный текст — в сообщении, на которое ответила карточка."""
    msg = callback.message
    original = getattr(msg, "reply_to_message", None)
    if original is None:
        return None
    text = original.text or original.caption or ""
    if text.startswith("/add"):
        text = text.split(maxsplit=1)[1] if " " in text else ""
    return text.strip() or None


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


async def quick_add_callback(callback: CallbackQuery, db: AsyncSession, user: User) -> None:
    data = cards.parse_quick_add(callback.data or "")
    if data is None:
        await callback.answer()
        return
    tz, now = get_tz(user.timezone), now_utc()

    if data.op == "edit":
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(
                reply_markup=cards.edit_keyboard(data.kind, data.id)
            )
        return

    if data.op == "back":
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(
                reply_markup=cards.back_keyboard(data.kind, data.id)
            )
        return

    if data.op == "del":
        try:
            await quickadd.delete_created(db, user, data.kind, data.id)
        except AppError as exc:
            await callback.answer(exc.message, show_alert=True)
            return
        await callback.answer("Удалено")
        await _edit(callback, "Удалено.", None)
        return

    # op == "to": сменить тип — пересоздать из исходного текста
    assert data.target is not None
    text = _source_text(callback)
    if text is None:
        await callback.answer("Не нашёл исходное сообщение — напишите заново", show_alert=True)
        return
    try:
        created = await quickadd.create_from_text(db, user, text, kind=data.target)
    except AppError as exc:
        await callback.answer(exc.message, show_alert=True)
        return
    try:
        await quickadd.delete_created(db, user, data.kind, data.id)
    except AppError:
        pass  # старое уже удалено в приложении — не страшно
    await callback.answer(cards.KIND_DONE[data.target])
    await _edit(callback, cards.created_text(created, tz, now), cards.created_keyboard(created))


# ---------- кнопки напоминаний ----------


async def reminder_callback(callback: CallbackQuery, db: AsyncSession, user: User) -> None:
    parsed = cards.parse_reminder(callback.data or "")
    if parsed is None:
        await callback.answer()
        return
    action, reminder_id = parsed
    try:
        result = await reminder_actions.perform_by_id(db, user, reminder_id, action)
    except AppError as exc:
        await callback.answer(exc.message, show_alert=True)
        return
    await callback.answer(result.message)
    if isinstance(callback.message, Message):
        # Кнопки действий убираем, «Открыть» оставляем
        await callback.message.edit_reply_markup(
            reply_markup=cards.without_actions(callback.message.reply_markup)
        )
        await callback.message.reply(f"✓ {result.message}")


def create_router() -> Router:
    """Новый роутер на каждый Dispatcher (aiogram не даёт подключить один дважды)."""
    router = Router(name="core")
    router.message.register(start_with_code, CommandStart(deep_link=True))
    router.message.register(start, CommandStart())
    router.message.register(help_, Command("help"))
    router.message.register(today, Command("today"))
    router.message.register(week, Command("week"))
    router.message.register(add, Command("add"))
    router.message.register(help_, F.text.startswith("/"))  # неизвестная команда
    router.message.register(free_text)
    router.callback_query.register(quick_add_callback, F.data.startswith(cards.QA_PREFIX))
    router.callback_query.register(reminder_callback, F.data.startswith(cards.RA_PREFIX))
    return router
