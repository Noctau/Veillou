"""Заметки и поиск в боте.

/note <текст> — новая заметка (первая строка многострочного текста — название);
/search <слова> — поиск по заметкам (полнотекстовый) и названиям заданий.

Кнопки (`m:…`): `nl:<стр>` — последние заметки; `n:<id>` — заметка;
`nx` / `nX` — удалить (вопрос / да); `ask:na:<id>` — дописать в конец;
`ask:nn:-` — новая заметка; `ask:q:-` — поиск.
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
    short,
    to_int,
    uid,
)
from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc
from app.domain.enums import NoteKind, TaskStatus
from app.notify.message import fmt_day
from app.schemas.note import NoteCreate, NoteUpdate
from app.services.notes import NoteService
from app.services.search import SearchService
from app.services.tasks import TaskService

# Сколько последних заметок листать в боте
RECENT_NOTES = 80
NOTE_BODY_LIMIT = 3000
SEARCH_LIMIT = 10
# Однострочная заметка не длиннее — только название
SHORT_NOTE = 120


async def note_list(ctx: Ctx, page: int = 0) -> Screen:
    notes = await NoteService(ctx.db, ctx.user).list(limit=RECENT_NOTES)
    shown, page = page_of(notes, page)
    today = local_date(now_utc(), get_tz(ctx.user.timezone))
    text = "<b>Заметки</b>" if notes else "<b>Заметки</b>\n\nПока пусто. /note текст — новая."
    rows: list[list[Button]] = []
    for n in shown:
        when = f" · {fmt_day(n.class_date, today)}" if n.class_date else ""
        rows.append([btn(short(n.title, 34) + when, "n", n.id)])
    rows.append(pager("nl", page, len(notes)))
    rows.append([btn("➕ Новая", "ask", "nn", "-"), btn("🔎 Поиск", "ask", "q", "-")])
    rows.append([btn("☰ Меню", "menu"), link("/notes")])
    return text, kb(*rows)


@on_callback("nl")
async def _nl(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await note_list(ctx, to_int(args[0] if args else None))


async def note_card(ctx: Ctx, note_id: uuid.UUID, *, confirm_delete: bool = False) -> Screen:
    n = await NoteService(ctx.db, ctx.user).get(note_id)
    today = local_date(now_utc(), get_tz(ctx.user.timezone))
    lines = [f"<b>{esc(n.title)}</b>"]
    if n.class_date:
        lines.append(fmt_day(n.class_date, today))
    body = n.body_md.strip()
    if body:
        lines.append("")
        lines.append(esc(body[:NOTE_BODY_LIMIT] + ("…" if len(body) > NOTE_BODY_LIMIT else "")))
    elif n.kind != NoteKind.text or n.attachments_count:
        lines.append(f"\n📎 Файлов: {n.attachments_count} — откройте в приложении")
    if confirm_delete:
        lines.append("\n<b>Удалить заметку?</b>")
        return clip("\n".join(lines)), kb([btn("Да", "nX", n.id), btn("Нет", "n", n.id)])
    return clip("\n".join(lines)), kb(
        [btn("➕ Дописать", "ask", "na", n.id), btn("🗑 Удалить", "nx", n.id)],
        [btn("← Заметки", "nl", 0), link(f"/notes/{n.id}")],
    )


@on_callback("n")
async def _n(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await note_card(ctx, uid(args[0]))


@on_callback("nx")
async def _delete_ask(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await note_card(ctx, uid(args[0]), confirm_delete=True)


@on_callback("nX")
async def _delete(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    await NoteService(ctx.db, ctx.user).delete(uid(args[0]))
    ctx.say("Удалено")
    return await note_list(ctx)


async def create_note(ctx: Ctx, text: str) -> Screen:
    text = text.strip()
    if not text:
        raise InvalidDataError("Напишите текст заметки: /note купить билеты на 20-е")
    first, _, rest = text.partition("\n")
    if rest.strip():
        title, body = first.strip()[:300], rest.strip()
    elif len(text) <= SHORT_NOTE:
        title, body = text, ""  # короткая строка — сама себе название
    else:
        title, body = None, text
    note = await NoteService(ctx.db, ctx.user).create(NoteCreate(title=title, body_md=body))
    return await note_card(ctx, note.id)


@on_input("nn", "Текст заметки (первая строка станет названием):")
async def _new(ctx: Ctx, message: Message, _: str) -> Screen:
    return await create_note(ctx, message.text or "")


@on_input("na", "Что дописать в заметку?")
async def _append(ctx: Ctx, message: Message, arg: str) -> Screen:
    svc = NoteService(ctx.db, ctx.user)
    note = await svc.get(uid(arg))
    addition = (message.text or "").strip()
    if not addition:
        raise InvalidDataError("Пустой текст")
    body = f"{note.body_md.rstrip()}\n\n{addition}" if note.body_md.strip() else addition
    await svc.update(note.id, NoteUpdate(body_md=body))
    return await note_card(ctx, note.id)


# ---------- поиск ----------


async def search_screen(ctx: Ctx, query: str) -> Screen:
    query = " ".join(query.split())[:200]
    if not query:
        raise InvalidDataError("Что искать? /search курсовая")
    found = await SearchService(ctx.db, ctx.user).search(query, limit=SEARCH_LIMIT)
    needle = query.casefold()
    tasks = [
        t
        for t in await TaskService(ctx.db, ctx.user).list_tasks(
            statuses=[TaskStatus.active, TaskStatus.done]
        )
        if needle in t.title.casefold() or needle in t.description.casefold()
    ][:SEARCH_LIMIT]
    rows: list[list[Button]] = [[btn(f"📋 {short(t.title, 40)}", "t", t.id)] for t in tasks]
    rows += [[btn(f"📝 {short(n.title, 40)}", "n", n.id)] for n in found.notes]
    total = len(tasks) + len(found.notes) + len(found.sources)
    lines = [f"🔎 <b>{esc(query)}</b>: " + (f"найдено {total}" if total else "ничего не нашёл")]
    for s in found.sources[:SEARCH_LIMIT]:
        lines.append(f"📚 {esc(short(s.title, 60))}")
    rows.append([btn("🔎 Ещё поиск", "ask", "q", "-"), btn("☰ Меню", "menu")])
    return clip("\n".join(lines)), kb(*rows)


@on_input("q", "Что найти? Ищу в заметках, источниках и заданиях.")
async def _search(ctx: Ctx, message: Message, _: str) -> Screen:
    return await search_screen(ctx, message.text or "")
