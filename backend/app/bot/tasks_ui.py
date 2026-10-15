"""Задания в боте: список, карточка, правки, шаги.

Кнопки (`m:…`):
- `tl:<стр>[:d]` — список активных (`d` — сделанные);
- `t:<id>` — карточка; `td` — готово / вернуть; `tp` — важность; `tx` / `tX` — удалить
  (вопрос / да);
- `ask:<что>:<id>` — ввод текстом: `dl` срок, `est` время, `ttl` название,
  `dsc` описание, `st` новый шаг;
- `ts:<id>` — шаги задания; `sd:<id шага>` — шаг сделан / не сделан;
  `sx:<id шага>` — удалить шаг.
"""

import uuid
from datetime import datetime

from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.ai import _button as ai_button
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
    split_step,
    to_int,
    uid,
)
from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, now_utc
from app.domain.breakdown import fmt_minutes
from app.domain.enums import Priority, SubtaskStatus, TaskStatus
from app.domain.quickparse import KindHint
from app.models import Area, TaskType, User
from app.notify.message import fmt_moment
from app.schemas.task import SubtaskCreate, SubtaskUpdate, TaskDetail, TaskUpdate
from app.services import quickadd
from app.services.tasks import TaskService

STEP_DEFAULT_MIN = 30
NO_VALUE = {"нет", "-", "—", "убрать", "без срока", "очистить"}


def _deadline(deadline: datetime | None, user: User) -> str | None:
    if deadline is None:
        return None
    tz = get_tz(user.timezone)
    return fmt_moment(deadline, tz, now_utc().astimezone(tz).date())


async def _names(db: AsyncSession, task: TaskDetail) -> list[str]:
    names = []
    if task.task_type_id and (tt := await db.get(TaskType, task.task_type_id)):
        names.append(tt.name)
    if task.area_id and (area := await db.get(Area, task.area_id)):
        names.append(area.name)
    return names


# ---------- список ----------


async def task_list(ctx: Ctx, page: int = 0, done: bool = False) -> Screen:
    statuses = [TaskStatus.done] if done else [TaskStatus.active]
    tasks = await TaskService(ctx.db, ctx.user).list_tasks(statuses=statuses)
    if done:  # последние сделанные — первыми
        tasks.sort(key=lambda t: t.done_at or t.created_at, reverse=True)
    shown, page = page_of(tasks, page)
    title = "Сделанные задания" if done else "Задания"
    if not tasks:
        text = f"<b>{title}</b>\n\nПусто." + (
            "" if done else " Напишите мне задание текстом — я его добавлю."
        )
    else:
        text = f"<b>{title}</b> ({len(tasks)})"
    rows: list[list[Button]] = []
    for t in shown:
        bits = [short(t.title, 34)]
        if (due := _deadline(t.deadline, ctx.user)) and not done:
            bits.append(due)
        if t.subtasks_total:
            bits.append(f"{t.subtasks_done}/{t.subtasks_total}")
        mark = "⭐ " if t.priority == Priority.high and not done else ""
        rows.append([btn(mark + " · ".join(bits), "t", t.id)])
    flag = ("d",) if done else ()
    rows.append(pager("tl", page, len(tasks), *flag))
    rows.append(
        [
            btn("➕ Новое", "ask", "nt", "-"),
            btn("Активные" if done else "✓ Сделанные", "tl", 0, *(() if done else ("d",))),
        ]
    )
    rows.append([btn("☰ Меню", "menu"), link("/tasks")])
    return text, kb(*rows)


@on_callback("tl")
async def _tl(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await task_list(ctx, to_int(args[0] if args else None), "d" in args[1:])


@on_input(
    "nt",
    "Что за задание? Например: «реферат по истории до 20 окт».",
)
async def _new_task(ctx: Ctx, message: Message, _: str) -> Screen:
    # «Новое задание» — значит задание, даже если похоже на дело в ящик
    created = await quickadd.create_from_text(
        ctx.db, ctx.user, message.text or "", kind=KindHint.task
    )
    return await task_card(ctx, created.id)


# ---------- карточка ----------


async def task_card(ctx: Ctx, task_id: uuid.UUID, *, confirm_delete: bool = False) -> Screen:
    task = await TaskService(ctx.db, ctx.user).get_detail(task_id)
    done = task.status == TaskStatus.done
    lines = [f"{'✅ ' if done else ''}<b>{esc(task.title)}</b>"]
    info = await _names(ctx.db, task)
    if due := _deadline(task.deadline, ctx.user):
        info.insert(0, f"📅 до {due}")
    if info:
        lines.append(esc(" · ".join(info)))
    has_steps = bool(task.subtasks) and not task.recurrence
    if task.total_estimate_min:
        source = " (сумма шагов)" if has_steps else ""
        lines.append(f"⏱ {fmt_minutes(task.total_estimate_min)}{source}")
    elif not has_steps and not done:
        lines.append("⏱ время не указано — планировщик не поставит задание")
    if task.priority == Priority.high:
        lines.append("⭐ высокая важность")
    if task.subtasks:
        lines.append(f"\n<b>Шаги</b> — {task.subtasks_done} из {task.subtasks_total}:")
        for s in task.subtasks[:15]:
            mark = "✓" if s.status == SubtaskStatus.done else "○"
            lines.append(f"{mark} {esc(short(s.title, 60))} — {fmt_minutes(s.estimate_min)}")
        if len(task.subtasks) > 15:
            lines.append(f"… и ещё {len(task.subtasks) - 15}")
    if task.description.strip():
        lines.append(f"\n{esc(short(task.description, 400))}")

    if confirm_delete:
        lines.append("\n<b>Удалить задание вместе с шагами?</b>")
        return clip("\n".join(lines)), kb(
            [btn("🗑 Да, удалить", "tX", task.id), btn("Отмена", "t", task.id)]
        )

    rows: list[list[Button]] = [
        [
            btn("↩ Вернуть" if done else "✓ Готово", "td", task.id),
            btn("☆ Обычная" if task.priority == Priority.high else "⭐ Важное", "tp", task.id),
        ],
        [
            btn("📅 Срок", "ask", "dl", task.id),
            None if has_steps else btn("⏱ Время", "ask", "est", task.id),
        ],
        [
            btn("➕ Шаг", "ask", "st", task.id),
            btn("☑ Отметить шаги", "ts", task.id) if task.subtasks else None,
        ],
        [btn("✏ Название", "ask", "ttl", task.id), btn("📝 Описание", "ask", "dsc", task.id)],
        [
            # Разбивка — тот же сценарий, что после разбора текста (bot/ai.py)
            None if task.recurrence or done else ai_button("🤖 Разбить с ИИ", "bt", task.id),
            btn("🗑 Удалить", "tx", task.id),
        ],
        [btn("← Задания", "tl", 0), link(f"/tasks/{task.id}")],
    ]
    return clip("\n".join(lines)), kb(*rows)


@on_callback("t")
async def _t(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await task_card(ctx, uid(args[0]))


async def _patch(ctx: Ctx, task_id: uuid.UUID, body: TaskUpdate) -> None:
    await TaskService(ctx.db, ctx.user).update(task_id, body)


@on_callback("td")
async def _done(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    task_id = uid(args[0])
    task = await TaskService(ctx.db, ctx.user).get_detail(task_id)
    done = task.status == TaskStatus.done
    await _patch(ctx, task_id, TaskUpdate(status=TaskStatus.active if done else TaskStatus.done))
    ctx.say("Вернул в работу" if done else "Готово ✓")
    return await task_card(ctx, task_id)


@on_callback("tp")
async def _priority(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    task_id = uid(args[0])
    task = await TaskService(ctx.db, ctx.user).get_detail(task_id)
    high = task.priority == Priority.high
    await _patch(ctx, task_id, TaskUpdate(priority=Priority.normal if high else Priority.high))
    ctx.say("Обычная важность" if high else "Важное ⭐")
    return await task_card(ctx, task_id)


@on_callback("tx")
async def _delete_ask(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await task_card(ctx, uid(args[0]), confirm_delete=True)


@on_callback("tX")
async def _delete(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    await TaskService(ctx.db, ctx.user).delete(uid(args[0]))
    ctx.say("Удалено")
    return await task_list(ctx)


# ---------- ввод текстом ----------


@on_input(
    "dl",
    "Напишите срок: «завтра», «15 окт в 18:00», «в пятницу». «нет» — убрать срок.",
)
async def _set_deadline(ctx: Ctx, message: Message, arg: str) -> Screen:
    text = (message.text or "").strip()
    if text.casefold() in NO_VALUE:
        await _patch(ctx, uid(arg), TaskUpdate(deadline=None))
    else:
        p = (await quickadd.parse_text(ctx.db, ctx.user, text[:200])).result
        if p.date is None or p.deadline is None:
            raise InvalidDataError("Не понял дату. Пример: «15 окт в 18:00» или «завтра»")
        await _patch(ctx, uid(arg), TaskUpdate(deadline=p.deadline))
    return await task_card(ctx, uid(arg))


@on_input(
    "est",
    "Сколько займёт задание? «90», «1.5 ч», «1 ч 30 мин».",
)
async def _set_estimate(ctx: Ctx, message: Message, arg: str) -> Screen:
    minutes = parse_minutes(message.text or "")
    if minutes is None or not 5 <= minutes <= 10_000:
        raise InvalidDataError("Не понял время. Пример: «90», «1.5 ч», «1 ч 30 мин» (от 5 мин)")
    await _patch(ctx, uid(arg), TaskUpdate(estimate_min=minutes))
    return await task_card(ctx, uid(arg))


@on_input(
    "ttl",
    "Новое название задания:",
)
async def _set_title(ctx: Ctx, message: Message, arg: str) -> Screen:
    title = " ".join((message.text or "").split())[:300]
    if not title:
        raise InvalidDataError("Название не может быть пустым")
    await _patch(ctx, uid(arg), TaskUpdate(title=title))
    return await task_card(ctx, uid(arg))


@on_input(
    "dsc",
    "Новое описание задания (заменит старое). «нет» — очистить.",
)
async def _set_description(ctx: Ctx, message: Message, arg: str) -> Screen:
    text = (message.text or "").strip()
    await _patch(ctx, uid(arg), TaskUpdate(description="" if text.casefold() in NO_VALUE else text))
    return await task_card(ctx, uid(arg))


@on_input(
    "st",
    "Новый шаг: название и, если хотите, время — «Найти источники, 40 мин».",
)
async def _add_step(ctx: Ctx, message: Message, arg: str) -> Screen:
    title, minutes = split_step(message.text or "")
    if not title:
        raise InvalidDataError("Напишите название шага")
    minutes = STEP_DEFAULT_MIN if minutes is None else min(max(minutes, 5), 600)
    await TaskService(ctx.db, ctx.user).add_subtask(
        uid(arg), SubtaskCreate(title=title[:300], estimate_min=minutes)
    )
    return await task_card(ctx, uid(arg))


# ---------- шаги ----------


async def steps_screen(ctx: Ctx, task_id: uuid.UUID) -> Screen:
    task = await TaskService(ctx.db, ctx.user).get_detail(task_id)
    rows: list[list[Button]] = []
    for s in task.subtasks[:40]:
        mark = "✓" if s.status == SubtaskStatus.done else "○"
        rows.append(
            [
                btn(f"{mark} {short(s.title, 30)} · {fmt_minutes(s.estimate_min)}", "sd", s.id),
                btn("🗑", "sx", s.id),
            ]
        )
    rows.append([btn("➕ Шаг", "ask", "st", task.id), btn("← К заданию", "t", task.id)])
    text = (
        f"<b>{esc(task.title)}</b>\nШаги — {task.subtasks_done} из {task.subtasks_total}. "
        "Нажмите на шаг, чтобы отметить."
    )
    return text, kb(*rows)


@on_callback("ts")
async def _ts(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await steps_screen(ctx, uid(args[0]))


@on_callback("sd")
async def _step_done(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    svc = TaskService(ctx.db, ctx.user)
    step = await svc.get_subtask(uid(args[0]))
    done = step.status == SubtaskStatus.done
    await svc.update_subtask(
        step.id, SubtaskUpdate(status=SubtaskStatus.todo if done else SubtaskStatus.done)
    )
    ctx.say("Не сделано" if done else "Сделано ✓")
    return await steps_screen(ctx, step.task_id)


@on_callback("sx")
async def _step_delete(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    svc = TaskService(ctx.db, ctx.user)
    step = await svc.get_subtask(uid(args[0]))
    await svc.delete_subtask(step.id)
    ctx.say("Шаг удалён")
    return await steps_screen(ctx, step.task_id)
