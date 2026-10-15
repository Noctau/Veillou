"""Управление из бота: меню, план, вечерний разбор, настройки и маршрутизация.

Команды: /menu, /tasks, /inbox, /day [дата], /projects, /notes, /note <текст>,
/search <слова>, /plan, /review, /settings, /cancel. Экраны заданий, календаря,
ящика, проектов и заметок — в *_ui.py; общие кнопки и ввод текстом — bot/kit.py.

Кнопки (`m:…`): `menu`; `plan` — состояние плана, `pp` — пересчитать, `pa:<id>` —
применить, `pu` — отменить последнее; `rv` — вечерний разбор, `rd:<id>` — блок
сделан, `rr` — перенести неотмеченное; `set` — настройки, `sr:<напоминание>` — вкл/выкл,
`sb:<±1>` — «закончить за N дней»; `ask:<что>:<arg>` — ввод текстом; `noop` — ничего.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

# Экраны регистрируют свои кнопки и ввод при импорте
from app.bot import calendar_ui, inbox_ui, notes_ui, projects_ui, tasks_ui
from app.bot.ai import plan_text
from app.bot.kit import (
    CALLBACKS,
    INPUTS,
    M_PREFIX,
    PROMPTS,
    Ask,
    Button,
    Ctx,
    Screen,
    ask,
    btn,
    esc,
    kb,
    link,
    on_callback,
    parse,
    short,
    show,
    uid,
)
from app.core.exceptions import AppError
from app.core.time import get_tz, local_date, now_utc
from app.domain.enums import EventStatus
from app.models import User
from app.notify.message import fmt_range
from app.schemas.event import EventUpdate
from app.schemas.settings import UserSettingsPatch
from app.services import quickadd
from app.services import settings as settings_service
from app.services.events import EventService
from app.services.replan import ReplanService, plan_state
from app.services.review import ReviewService

# ---------- меню ----------


def menu_screen() -> Screen:
    text = (
        "<b>Меню</b>\n"
        "Всё основное из приложения — здесь. Новое дело или задание можно просто написать "
        "сообщением."
    )
    return text, kb(
        [btn("📅 Сегодня", "d"), btn("📋 Задания", "tl", 0)],
        [btn("📥 Ящик", "bl", 0), btn("🗂 Проекты", "pl", 0)],
        [btn("📝 Заметки", "nl", 0), btn("🔎 Поиск", "ask", "q", "-")],
        [btn("🧭 План", "plan"), btn("🌙 Разбор дня", "rv")],
        [btn("⚙️ Настройки", "set"), link("/")],
    )


@on_callback("menu")
async def _menu(ctx: Ctx, _: CallbackQuery, __: list[str]) -> Screen:
    return menu_screen()


@on_callback("noop")
async def _noop(ctx: Ctx, callback: CallbackQuery, __: list[str]) -> None:
    return None


@on_callback("ask")
async def _ask(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> None:
    what = args[0] if args else ""
    if what not in PROMPTS:
        return
    await ask(ctx, callback, what, args[1] if len(args) > 1 else "-", PROMPTS[what])


# ---------- план ----------


async def plan_screen(ctx: Ctx) -> Screen:
    state = await plan_state(ReplanService(ctx.db, ctx.user))
    text = plan_text(state) if state.proposal else "Нового превью нет — план актуален."
    if state.undoable:
        text += "\n\nПоследнее применение можно отменить в течение суток."
    rows: list[list[Button]] = [
        [btn("✓ Применить", "pa", state.proposal.id) if state.proposal else None],
        [btn("🔄 Пересчитать", "pp")],
        [btn("↩ Отменить последнее", "pu") if state.undoable else None],
        [btn("☰ Меню", "menu"), link("/")],
    ]
    return text, kb(*rows)


@on_callback("plan")
async def _plan(ctx: Ctx, _: CallbackQuery, __: list[str]) -> Screen:
    return await plan_screen(ctx)


@on_callback("pp")
async def _preview(ctx: Ctx, callback: CallbackQuery, __: list[str]) -> Screen:
    ctx.say("Считаю…")
    await ReplanService(ctx.db, ctx.user).preview(force=True)
    return await plan_screen(ctx)


@on_callback("pa")
async def _apply(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    await ReplanService(ctx.db, ctx.user).apply(uid(args[0]))
    ctx.say("План применён ✓")
    return await plan_screen(ctx)


@on_callback("pu")
async def _undo(ctx: Ctx, callback: CallbackQuery, __: list[str]) -> Screen:
    _, restored, skipped = await ReplanService(ctx.db, ctx.user).undo()
    note = f"Откатил блоков: {restored}" + (f", не тронул правленых: {skipped}" if skipped else "")
    ctx.say(note, alert=True)
    return await plan_screen(ctx)


# ---------- вечерний разбор ----------


async def review_screen(ctx: Ctx) -> Screen:
    items, done = await ReviewService(ctx.db, ctx.user).evening_items()
    tz = get_tz(ctx.user.timezone)
    if not items:
        text = "🌙 Всё отмечено." + (f" Сделано блоков сегодня: {done}." if done else "")
        return text, kb([btn("🧭 План", "plan"), btn("☰ Меню", "menu")])
    text = (
        f"🌙 <b>Разбор дня</b>\nНе отмечено: {len(items)}. Отметьте сделанное — "
        "остальное перенесу на другие дни."
    )
    rows: list[list[Button]] = [
        [btn(f"✓ {fmt_range(e.start, e.end, tz)} {short(e.title, 30)}", "rd", e.id)]
        for e in items[:20]
    ]
    rows.append([btn("Перенести остальное", "rr")])
    rows.append([btn("☰ Меню", "menu"), link("/review")])
    return text, kb(*rows)


@on_callback("rv")
async def _review(ctx: Ctx, _: CallbackQuery, __: list[str]) -> Screen:
    return await review_screen(ctx)


@on_callback("rd")
async def _review_done(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    await EventService(ctx.db, ctx.user).update(uid(args[0]), EventUpdate(status=EventStatus.done))
    ctx.say("Отмечено ✓")
    return await review_screen(ctx)


@on_callback("rr")
async def _reschedule(ctx: Ctx, callback: CallbackQuery, __: list[str]) -> Screen:
    moved, _ = await ReviewService(ctx.db, ctx.user).reschedule()
    ctx.say(f"Перенесу: {moved}")
    return await plan_screen(ctx)


# ---------- настройки ----------

REMINDERS = {
    "morning_digest": "Утренняя сводка",
    "deadlines": "Дедлайны",
    "evening_review": "Вечерний разбор",
    "weekly_review": "Недельный разбор",
    "subtask_start": "Начало шага",
}


async def settings_screen(ctx: Ctx) -> Screen:
    s = settings_service.effective_settings(ctx.user)
    quiet = s.quiet_hours
    lines = [
        "<b>Настройки</b>",
        f"Часовой пояс: {esc(ctx.user.timezone)}",
        f"Тихие часы: {quiet.start:%H:%M}–{quiet.end:%H:%M}",
        f"Закончить за {s.deadline_buffer_days} дн. до дедлайна",
        "\nНапоминания (нажмите, чтобы включить или выключить):",
    ]
    rows: list[list[Button]] = []
    for key, label in REMINDERS.items():
        rule = getattr(s.reminders, key)
        rows.append([btn(f"{'🔔' if rule.enabled else '🔕'} {label}", "sr", key)])
    rows.append(
        [
            btn("− день", "sb", -1),
            btn(f"Запас: {s.deadline_buffer_days} дн.", "noop"),
            btn("+ день", "sb", 1),
        ]
    )
    rows.append([btn("☰ Меню", "menu"), link("/settings?tab=notifications")])
    return "\n".join(lines), kb(*rows)


async def _patch_settings(ctx: Ctx, data: dict[str, Any]) -> None:
    await settings_service.update_settings(ctx.db, ctx.user, UserSettingsPatch.model_validate(data))


@on_callback("set")
async def _settings(ctx: Ctx, _: CallbackQuery, __: list[str]) -> Screen:
    return await settings_screen(ctx)


@on_callback("sr")
async def _toggle_reminder(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    key = args[0] if args else ""
    if key not in REMINDERS:
        raise ValueError(key)
    rule = getattr(settings_service.effective_settings(ctx.user).reminders, key)
    await _patch_settings(ctx, {"reminders": {key: {"enabled": not rule.enabled}}})
    ctx.say(f"{REMINDERS[key]}: {'выкл' if rule.enabled else 'вкл'}")
    return await settings_screen(ctx)


@on_callback("sb")
async def _buffer(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    current = settings_service.effective_settings(ctx.user).deadline_buffer_days
    value = min(max(current + (1 if args and args[0] == "1" else -1), 0), 14)
    if value != current:
        await _patch_settings(ctx, {"deadline_buffer_days": value})
    return await settings_screen(ctx)


# ---------- маршрутизация ----------


async def on_m_callback(
    callback: CallbackQuery, db: AsyncSession, user: User, state: FSMContext
) -> None:
    parsed = parse(callback.data or "")
    handler = CALLBACKS.get(parsed[0]) if parsed else None
    if parsed is None or handler is None:
        await callback.answer()
        return
    ctx = Ctx(db, user, state)
    try:
        screen = await handler(ctx, callback, parsed[1])
    except AppError as exc:
        await db.rollback()
        await callback.answer(exc.message, show_alert=True)
        return
    except (ValueError, IndexError):
        # Кривые данные кнопки (старое сообщение, ручной ввод) — молча
        await callback.answer()
        return
    if screen is not None:
        await show(callback, screen)
    await callback.answer(ctx.notice, show_alert=ctx.alert)


async def on_input(message: Message, db: AsyncSession, user: User, state: FSMContext) -> None:
    data = await state.get_data()
    handler = INPUTS.get(str(data.get("what")))
    if handler is None:
        await state.clear()
        return
    if not (message.text or "").strip():
        await message.answer("Жду текст. /cancel — отмена.")
        return
    try:
        screen = await handler(Ctx(db, user, state), message, str(data.get("arg", "-")))
    except AppError as exc:
        await db.rollback()
        # Состояние остаётся: можно сразу исправиться
        await message.reply(f"{exc.message}\n\n<i>/cancel — отмена</i>", parse_mode="HTML")
        return
    except ValueError:
        await state.clear()
        await message.reply("Не получилось — откройте экран заново: /menu")
        return
    await state.clear()
    await show(message, screen)


async def cancel(message: Message, state: FSMContext) -> None:
    had = await state.get_state() is not None
    await state.clear()
    await message.answer("Отменил." if had else "Нечего отменять.", reply_markup=None)


Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


async def drop_pending_input(handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
    """Любая команда отменяет ожидание ввода: дальше текст снова — быстрый ввод."""
    state: FSMContext | None = data.get("state")
    if (
        state is not None
        and isinstance(event, Message)
        and (event.text or "").startswith("/")
        and not (event.text or "").startswith("/cancel")
        and await state.get_state() is not None
    ):
        await state.clear()
    return await handler(event, data)


def _screen_command(
    build: Callable[[Ctx, CommandObject], Awaitable[Screen]],
) -> Callable[..., Awaitable[None]]:
    async def handler(
        message: Message,
        command: CommandObject,
        db: AsyncSession,
        user: User,
        state: FSMContext,
    ) -> None:
        try:
            screen = await build(Ctx(db, user, state), command)
        except AppError as exc:
            await db.rollback()
            await message.reply(exc.message)
            return
        await show(message, screen)

    return handler


async def _menu_cmd(ctx: Ctx, _: CommandObject) -> Screen:
    return menu_screen()


async def _tasks_cmd(ctx: Ctx, _: CommandObject) -> Screen:
    return await tasks_ui.task_list(ctx)


async def _inbox_cmd(ctx: Ctx, _: CommandObject) -> Screen:
    return await inbox_ui.inbox_list(ctx)


async def _day_cmd(ctx: Ctx, command: CommandObject) -> Screen:
    tz = get_tz(ctx.user.timezone)
    day = local_date(now_utc(), tz)
    if command.args and command.args.strip():
        p = (await quickadd.parse_text(ctx.db, ctx.user, command.args[:100])).result
        day = p.date or day
    return await calendar_ui.day_screen(ctx, day)


async def _projects_cmd(ctx: Ctx, _: CommandObject) -> Screen:
    return await projects_ui.project_list(ctx)


async def _notes_cmd(ctx: Ctx, _: CommandObject) -> Screen:
    return await notes_ui.note_list(ctx)


async def _note_cmd(ctx: Ctx, command: CommandObject) -> Screen:
    return await notes_ui.create_note(ctx, command.args or "")


async def _search_cmd(ctx: Ctx, command: CommandObject) -> Screen:
    return await notes_ui.search_screen(ctx, command.args or "")


async def _plan_cmd(ctx: Ctx, _: CommandObject) -> Screen:
    return await plan_screen(ctx)


async def _review_cmd(ctx: Ctx, _: CommandObject) -> Screen:
    return await review_screen(ctx)


async def _settings_cmd(ctx: Ctx, _: CommandObject) -> Screen:
    return await settings_screen(ctx)


COMMANDS: dict[str, Callable[[Ctx, CommandObject], Awaitable[Screen]]] = {
    "menu": _menu_cmd,
    "tasks": _tasks_cmd,
    "inbox": _inbox_cmd,
    "day": _day_cmd,
    "calendar": _day_cmd,
    "projects": _projects_cmd,
    "notes": _notes_cmd,
    "note": _note_cmd,
    "search": _search_cmd,
    "plan": _plan_cmd,
    "review": _review_cmd,
    "settings": _settings_cmd,
}


def register(router: Router) -> None:
    """Команды, кнопки `m:` и ввод текстом — в роутер бота (до свободного текста)."""
    router.message.outer_middleware(drop_pending_input)
    router.message.register(cancel, Command("cancel"))
    for name, build in COMMANDS.items():
        router.message.register(_screen_command(build), Command(name))
    router.message.register(on_input, StateFilter(Ask.input), F.text, ~F.text.startswith("/"))
    router.callback_query.register(on_m_callback, F.data.startswith(M_PREFIX))
