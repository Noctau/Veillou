"""Календарь в боте: день по событиям, карточка события, отметки и перенос.

Кнопки (`m:…`):
- `d:<ГГГГММДД>` — день (без даты — сегодня);
- `e:<id>` — карточка события; `ed` — сделано; `ec` — отменить (жёсткое);
  `eu` — вернуть «запланировано»; `ex` / `eX` — удалить (вопрос / да);
- `ask:mv:<id>` — перенести (ввод: «завтра в 15»); `ask:ne:<ГГГГММДД>` — новое событие.
"""

import uuid
from datetime import date, datetime, time, timedelta

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
    short,
    uid,
)
from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc, wall_to_utc
from app.domain.enums import EventKind, EventStatus
from app.domain.quickparse import KindHint
from app.models import Area, EventType
from app.notify.message import fmt_day, fmt_day_full, fmt_range
from app.schemas.event import EventUpdate
from app.services import quickadd
from app.services.events import EventService

# Сколько событий дня показывать кнопками
DAY_BUTTONS = 20
STATUS_MARK = {
    EventStatus.done: "✓",
    EventStatus.cancelled: "✗",
    EventStatus.missed: "⏭",
}


def day_code(d: date) -> str:
    return d.strftime("%Y%m%d")


def _parse_day(raw: str | None, today: date) -> date:
    if not raw:
        return today
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return today


def _today(ctx: Ctx) -> date:
    return local_date(now_utc(), get_tz(ctx.user.timezone))


async def day_screen(ctx: Ctx, day: date) -> Screen:
    tz = get_tz(ctx.user.timezone)
    today = _today(ctx)
    start = wall_to_utc(day, time(0), tz)
    end = wall_to_utc(day + timedelta(days=1), time(0), tz)
    events, days_off = await EventService(ctx.db, ctx.user).calendar(start, end)
    head = fmt_day_full(day)
    if day == today:
        head += " · сегодня"
    lines = [f"<b>{esc(head)}</b>"]
    for off in days_off:
        lines.append(f"🏖 {esc(off.title or 'Выходной')}")
    rows: list[list[Button]] = []
    if not events:
        lines.append("\nСобытий и блоков нет.")
    for e in events:
        mark = STATUS_MARK.get(EventStatus(e.status), "")
        when = fmt_range(e.start, e.end, tz)
        line = f"{when} {mark} {esc(e.title)}".replace("  ", " ")
        lines.append(f"<s>{line}</s>" if e.status == EventStatus.cancelled else line)
    for e in events[:DAY_BUTTONS]:
        mark = STATUS_MARK.get(EventStatus(e.status), "•")
        rows.append(
            [btn(f"{mark} {fmt_range(e.start, e.end, tz)} {short(e.title, 28)}", "e", e.id)]
        )
    rows.append(
        [
            btn("◀", "d", day_code(day - timedelta(days=1))),
            None if day == today else btn("Сегодня", "d", day_code(today)),
            btn("▶", "d", day_code(day + timedelta(days=1))),
        ]
    )
    rows.append([btn("➕ Событие", "ask", "ne", day_code(day)), btn("☰ Меню", "menu")])
    rows.append([link("/calendar")])
    return clip("\n".join(lines)), kb(*rows)


@on_callback("d")
async def _d(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await day_screen(ctx, _parse_day(args[0] if args else None, _today(ctx)))


# ---------- событие ----------


async def event_card(ctx: Ctx, event_id: uuid.UUID, *, confirm_delete: bool = False) -> Screen:
    e = await EventService(ctx.db, ctx.user).get(event_id)
    tz = get_tz(ctx.user.timezone)
    day = local_date(e.start, tz)
    status = EventStatus(e.status)
    lines = [f"<b>{esc(e.title)}</b>"]
    lines.append(f"🕒 {fmt_day(day, _today(ctx))}, {fmt_range(e.start, e.end, tz)}")
    info = []
    if e.event_type_id and (et := await ctx.db.get(EventType, e.event_type_id)):
        info.append(et.name)
    if e.area_id and (area := await ctx.db.get(Area, e.area_id)):
        info.append(area.name)
    if e.location:
        info.append(f"📍 {e.location}")
    if info:
        lines.append(esc(" · ".join(info)))
    if status != EventStatus.planned:
        lines.append(
            {
                EventStatus.done: "✓ Сделано",
                EventStatus.cancelled: "✗ Отменено",
                EventStatus.missed: "⏭ Не сделано",
            }[status]
        )
    if not e.is_fixed:
        lines.append("📌 Закреплено" if e.is_pinned else "Блок плана — планировщик может сдвинуть")
    if e.note.strip():
        lines.append(f"\n{esc(short(e.note, 400))}")

    if confirm_delete:
        what = "Отменить это вхождение расписания?" if e.template_id else "Удалить событие?"
        lines.append(f"\n<b>{what}</b>")
        return clip("\n".join(lines)), kb([btn("Да", "eX", e.id), btn("Нет", "e", e.id)])

    busy = e.kind == EventKind.busy
    rows: list[list[Button]] = [
        [
            btn("✓ Сделано", "ed", e.id) if status == EventStatus.planned else None,
            btn("✗ Отменить", "ec", e.id) if busy and status == EventStatus.planned else None,
            btn("↩ Вернуть", "eu", e.id) if status != EventStatus.planned else None,
        ],
        [
            btn("🕒 Перенести", "ask", "mv", e.id) if status == EventStatus.planned else None,
            btn("🗑 Удалить", "ex", e.id) if busy else None,
        ],
        [btn("← День", "d", day_code(day)), link("/calendar")],
    ]
    return clip("\n".join(lines)), kb(*rows)


@on_callback("e")
async def _e(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await event_card(ctx, uid(args[0]))


async def _status(
    ctx: Ctx, callback: CallbackQuery, args: list[str], status: EventStatus, note: str
) -> Screen:
    event_id = uid(args[0])
    await EventService(ctx.db, ctx.user).update(event_id, EventUpdate(status=status))
    ctx.say(note)
    return await event_card(ctx, event_id)


@on_callback("ed")
async def _ed(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    return await _status(ctx, callback, args, EventStatus.done, "Сделано ✓")


@on_callback("ec")
async def _ec(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    return await _status(ctx, callback, args, EventStatus.cancelled, "Отменено")


@on_callback("eu")
async def _eu(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    return await _status(ctx, callback, args, EventStatus.planned, "Вернул в план")


@on_callback("ex")
async def _ex(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await event_card(ctx, uid(args[0]), confirm_delete=True)


@on_callback("eX")
async def _eX(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:  # noqa: N802
    svc = EventService(ctx.db, ctx.user)
    event = await svc.get(uid(args[0]))
    day = local_date(event.start, get_tz(ctx.user.timezone))
    await svc.delete(event.id)
    ctx.say("Готово")
    return await day_screen(ctx, day)


@on_input("mv", "Куда перенести? «завтра в 15», «в пт в 10:30», «16 окт в 9».")
async def _move(ctx: Ctx, message: Message, arg: str) -> Screen:
    svc = EventService(ctx.db, ctx.user)
    event = await svc.get(uid(arg))
    p = (await quickadd.parse_text(ctx.db, ctx.user, (message.text or "")[:200])).result
    if p.time is None:
        raise InvalidDataError("Нужно время: «завтра в 15», «в пт в 10:30»")
    tz = get_tz(ctx.user.timezone)
    day = p.date or local_date(event.start, tz)
    start = wall_to_utc(day, p.time, tz)
    await svc.update(event.id, EventUpdate(start=start, end=start + (event.end - event.start)))
    return await event_card(ctx, event.id)


@on_input(
    "ne",
    "Что и когда? «созвон в 15», «кино с 19 до 21». Время без даты — в выбранный день.",
)
async def _new_event(ctx: Ctx, message: Message, arg: str) -> Screen:
    today = _today(ctx)
    day = _parse_day(arg, today)
    # Выбран другой день — время без даты и «завтра» считаются от его начала
    now = None if day == today else wall_to_utc(day, time(0), get_tz(ctx.user.timezone))
    created = await quickadd.create_from_text(
        ctx.db, ctx.user, (message.text or "").strip(), kind=KindHint.event, now=now
    )
    return await event_card(ctx, created.id)
