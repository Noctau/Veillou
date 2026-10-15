"""Долгий ящик в боте: список, карточка, «взять на неделю», сделано, в задание.

Кнопки (`m:…`):
- `bl:<стр>` — список; `b:<id>` — карточка;
- `bw` — взять на неделю / снять; `bd` — сделано; `bt` — сделать заданием;
  `bx` / `bX` — удалить (вопрос / да);
- `ask:nb:-` — новое дело; `ask:be:<id>` — время дела.
"""

import uuid

from aiogram.types import CallbackQuery, Message

from app.bot.kit import (
    Button,
    Ctx,
    Screen,
    btn,
    clip,
    esc,
    kb,
    link,
    on_callback,
    on_input,
    page_of,
    pager,
    parse_minutes,
    short,
    to_int,
    uid,
)
from app.bot.tasks_ui import task_card
from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc
from app.domain.breakdown import fmt_minutes
from app.domain.enums import BacklogStatus
from app.domain.quickparse import KindHint
from app.notify.message import fmt_day
from app.schemas.backlog import BacklogUpdate
from app.schemas.task import TaskCreate
from app.services import quickadd
from app.services.backlog import BacklogService
from app.services.tasks import TaskService


async def inbox_list(ctx: Ctx, page: int = 0) -> Screen:
    items = await BacklogService(ctx.db, ctx.user).list()
    shown, page = page_of(items, page)
    if items:
        week = sum(i.planned_week is not None for i in items)
        text = f"<b>Ящик</b> ({len(items)})" + (f", на этой неделе — {week}" if week else "")
    else:
        text = "<b>Ящик</b>\n\nПусто. Дела без срока — «записаться к врачу» — пишите мне текстом."
    rows: list[list[Button]] = []
    for i in shown:
        mark = "📌 " if i.planned_week else ""
        rows.append([btn(mark + short(i.title, 40), "b", i.id)])
    rows.append(pager("bl", page, len(items)))
    rows.append([btn("➕ Новое дело", "ask", "nb", "-"), btn("☰ Меню", "menu")])
    rows.append([link("/inbox")])
    return text, kb(*rows)


@on_callback("bl")
async def _bl(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await inbox_list(ctx, to_int(args[0] if args else None))


async def item_card(ctx: Ctx, item_id: uuid.UUID, *, confirm_delete: bool = False) -> Screen:
    item = await BacklogService(ctx.db, ctx.user).items.get_or_404(item_id)
    today = local_date(now_utc(), get_tz(ctx.user.timezone))
    lines = [f"<b>{esc(item.title)}</b>"]
    if item.status == BacklogStatus.done:
        lines.append("✓ Сделано")
    if item.planned_week:
        lines.append("📌 Взято на неделю — планировщик найдёт время")
    if item.desired_by:
        lines.append(f"Хорошо бы до {fmt_day(item.desired_by, today)}")
    if item.estimate_min:
        lines.append(f"⏱ {fmt_minutes(item.estimate_min)}")
    if item.note.strip():
        lines.append(f"\n{esc(short(item.note, 400))}")
    if confirm_delete:
        lines.append("\n<b>Удалить дело?</b>")
        return clip("\n".join(lines)), kb([btn("Да", "bX", item.id), btn("Нет", "b", item.id)])
    active = item.status == BacklogStatus.active
    rows: list[list[Button]] = [
        [
            btn("Снять с недели" if item.planned_week else "📌 На неделю", "bw", item.id)
            if active
            else None,
            btn("✓ Сделано", "bd", item.id) if active else None,
        ],
        [btn("⏱ Время", "ask", "be", item.id), btn("→ В задание", "bt", item.id)],
        [btn("🗑 Удалить", "bx", item.id), btn("← Ящик", "bl", 0)],
    ]
    return clip("\n".join(lines)), kb(*rows)


@on_callback("b")
async def _b(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await item_card(ctx, uid(args[0]))


@on_callback("bw")
async def _week(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    svc = BacklogService(ctx.db, ctx.user)
    item = await svc.items.get_or_404(uid(args[0]))
    take = item.planned_week is None
    await svc.take_for_week(item.id, take)
    ctx.say("Взято на неделю 📌" if take else "Снято с недели")
    return await item_card(ctx, item.id)


@on_callback("bd")
async def _done(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    await BacklogService(ctx.db, ctx.user).update(
        uid(args[0]), BacklogUpdate(status=BacklogStatus.done)
    )
    ctx.say("Сделано ✓")
    return await inbox_list(ctx)


@on_callback("bt")
async def _to_task(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    """Дело стало заданием: название, заметка и время переезжают, дело удаляется."""
    svc = BacklogService(ctx.db, ctx.user)
    item = await svc.items.get_or_404(uid(args[0]))
    task = await TaskService(ctx.db, ctx.user).create(
        TaskCreate(
            title=item.title,
            description=item.note,
            action_type_id=item.action_type_id,
            category_id=item.category_id,
            estimate_min=item.estimate_min,
        )
    )
    await svc.delete(item.id)
    ctx.say("Теперь это задание")
    return await task_card(ctx, task.id)


@on_callback("bx")
async def _delete_ask(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await item_card(ctx, uid(args[0]), confirm_delete=True)


@on_callback("bX")
async def _delete(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    await BacklogService(ctx.db, ctx.user).delete(uid(args[0]))
    ctx.say("Удалено")
    return await inbox_list(ctx)


@on_input("nb", "Что положить в ящик? Например: «записаться к стоматологу».")
async def _new(ctx: Ctx, message: Message, _: str) -> Screen:
    created = await quickadd.create_from_text(
        ctx.db, ctx.user, message.text or "", kind=KindHint.backlog
    )
    return await item_card(ctx, created.id)


@on_input("be", "Сколько займёт? «15», «1 ч», «2 ч 30 мин» (до 12 ч).")
async def _estimate(ctx: Ctx, message: Message, arg: str) -> Screen:
    minutes = parse_minutes(message.text or "")
    if minutes is None or not 5 <= minutes <= 720:
        raise InvalidDataError("Не понял время: от 5 мин до 12 ч, например «45» или «1.5 ч»")
    await BacklogService(ctx.db, ctx.user).update(uid(arg), BacklogUpdate(estimate_min=minutes))
    return await item_card(ctx, uid(arg))
