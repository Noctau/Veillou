"""ИИ в боте (M10.5–M10.6): разбор свободного текста, фото задания, разбивка.

Бот только ставит джобу и отвечает «Разбираю…»; карточку с результатом
присылает воркер (`make_handlers`) — правкой того же сообщения.

callback_data `ai:<op>:<hex>` (лимит Telegram — 64 байта):
- по джобе разбора текста (hex — id джобы): mk — создать и разбить, cr — создать
  как предложено, ed — «Изменить», tt — как задание, tb — в ящик, raw — как написано
  (без ИИ), bk — назад;
- по заданию (hex — id задания): bt — разбить на шаги, dt — удалить;
- по джобе разбивки (hex — id джобы): ap — запланировать шаги как есть;
- по ревизии плана (hex — её id): pa — применить план.
"""

import html
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import cards
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.time import get_tz, now_utc
from app.domain.breakdown import fmt_minutes
from app.domain.enums import AIOrigin, JobKind, JobStatus, TaskType
from app.domain.quickparse import KindHint
from app.models import Job, Subject, User
from app.notify.message import fmt_moment
from app.schemas.ai import (
    BreakdownApply,
    BreakdownDraft,
    BreakdownRequest,
    ParseDraft,
    PhotoDraft,
)
from app.schemas.plan import PlanState
from app.services import jobs
from app.services.ai_parse import AIParseService, create_from_draft
from app.services.breakdown import BreakdownService
from app.services.quickadd import create_from_text
from app.services.replan import ReplanService, plan_state
from app.services.tasks import TaskService

log = logging.getLogger(__name__)

AI_PREFIX = "ai:"
THINKING = "🤖 Разбираю…"
TASK_TYPE_TITLE = {
    TaskType.homework: "ДЗ",
    TaskType.report: "Доклад",
    TaskType.essay: "Реферат",
    TaskType.lab: "Лабораторная",
    TaskType.coursework: "Курсовая",
    TaskType.reading: "Чтение",
    TaskType.exam_prep: "Подготовка к экзамену",
    TaskType.other: "Другое",
}
KIND_TITLE = {KindHint.task: "Задание", KindHint.backlog: "В ящик", KindHint.event: "Событие"}


def _cb(op: str, id: uuid.UUID) -> str:
    return f"{AI_PREFIX}{op}:{id.hex}"


def _button(text: str, op: str, id: uuid.UUID) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=_cb(op, id))


def _open(path: str, text: str = "Открыть") -> InlineKeyboardButton | None:
    if not settings.APP_URL:
        return None
    return InlineKeyboardButton(text=text, url=f"{settings.APP_URL}{path}")


def _rows(*rows: list[InlineKeyboardButton | None]) -> InlineKeyboardMarkup:
    clean = [[b for b in row if b is not None] for row in rows]
    return InlineKeyboardMarkup(inline_keyboard=[row for row in clean if row])


@dataclass(frozen=True)
class AIData:
    op: str
    id: uuid.UUID


def parse_callback(data: str) -> AIData | None:
    parts = data.removeprefix(AI_PREFIX).split(":")
    if len(parts) != 2:
        return None
    try:
        return AIData(parts[0], uuid.UUID(hex=parts[1]))
    except ValueError:
        return None


# ---------- тексты ----------


def _details(
    deadline: datetime | None, subject: str | None, task_type: TaskType | None, user: User
) -> str:
    tz = get_tz(user.timezone)
    today = now_utc().astimezone(tz).date()
    parts = []
    if deadline:
        parts.append(f"до {fmt_moment(deadline, tz, today)}")
    if subject:
        parts.append(subject)
    if task_type and task_type != TaskType.other:
        parts.append(TASK_TYPE_TITLE[task_type])
    return html.escape(" · ".join(parts))


def _snippet(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return html.escape(text if len(text) <= limit else text[: limit - 1] + "…")


async def _subject_name(db: AsyncSession, subject_id: uuid.UUID | None) -> str | None:
    subject = await db.get(Subject, subject_id) if subject_id else None
    return subject.name if subject else None


async def parse_card(db: AsyncSession, user: User, draft: ParseDraft) -> str:
    subject = await _subject_name(db, draft.subject_id)
    lines = [f"🤖 <b>{KIND_TITLE[draft.kind]}:</b> {html.escape(draft.title)}"]
    if details := _details(draft.deadline, subject, draft.task_type, user):
        lines.append(details)
    if draft.description:
        lines.append(f"<i>{_snippet(draft.description)}</i>")
    return "\n".join(lines)


def parse_keyboard(job_id: uuid.UUID, draft: ParseDraft) -> InlineKeyboardMarkup:
    if draft.kind == KindHint.task:
        return _rows(
            [_button("Создать и разбить", "mk", job_id)],
            [_button("Создать", "cr", job_id), _button("Изменить", "ed", job_id)],
        )
    return _rows([_button("Создать", "cr", job_id), _button("Изменить", "ed", job_id)])


def edit_keyboard(job_id: uuid.UUID, draft: ParseDraft) -> InlineKeyboardMarkup:
    switch = [
        _button("→ Задание", "tt", job_id) if draft.kind != KindHint.task else None,
        _button("→ В ящик", "tb", job_id) if draft.kind != KindHint.backlog else None,
    ]
    return _rows(
        switch,
        [_button("Как написано, без ИИ", "raw", job_id)],
        [_button("← Назад", "bk", job_id)],
    )


async def photo_card(db: AsyncSession, user: User, draft: PhotoDraft) -> str:
    subject = await _subject_name(db, draft.subject_id)
    task = await TaskService(db, user).get_detail(draft.task_id)
    lines = [f"📷 <b>Задание:</b> {html.escape(task.title)}"]
    if details := _details(task.deadline, subject, task.task_type, user):
        lines.append(details)
    if draft.text:
        lines.append(f"<i>{_snippet(draft.text)}</i>")
    else:
        lines.append("Текста на фото не разобрал — допишите задание в приложении.")
    return "\n".join(lines)


def task_keyboard(task_id: uuid.UUID) -> InlineKeyboardMarkup:
    return _rows(
        [_button("Разбить на шаги", "bt", task_id), _open(f"/tasks/{task_id}")],
        [_button("Удалить", "dt", task_id)],
    )


def breakdown_card(title: str, draft: BreakdownDraft) -> str:
    lines = [f"🧩 <b>Шаги для «{html.escape(title)}»</b>"]
    for i, s in enumerate(draft.steps, 1):
        after = ""
        if s.depends_on:
            after = " (после " + ", ".join(str(d + 1) for d in s.depends_on) + ")"
        lines.append(f"{i}. {html.escape(s.title)} — {fmt_minutes(s.estimate_min)}{after}")
    lines.append(f"Итого ~{fmt_minutes(draft.total_estimate_min)}")
    for warning in dict.fromkeys(w for w in (draft.time_warning, draft.warning) if w):
        lines.append(f"⚠️ {html.escape(warning)}")
    return "\n".join(lines)


def breakdown_keyboard(job_id: uuid.UUID, task_id: uuid.UUID) -> InlineKeyboardMarkup:
    return _rows(
        [_button("Запланировать", "ap", job_id)],
        [_open(f"/tasks/{task_id}/breakdown?job={job_id}", "Поправить в приложении")],
    )


def plan_text(state: PlanState) -> str:
    rev = state.proposal
    if rev is None:
        return "План уже учитывает эти шаги — менять нечего."
    parts = []
    if rev.added:
        parts.append(f"новых блоков: {rev.added}")
    if rev.moved:
        parts.append(f"перенесено: {rev.moved}")
    if rev.removed:
        parts.append(f"убрано: {rev.removed}")
    text = "Превью плана: " + (", ".join(parts) if parts else "без переносов")
    if rev.at_risk:
        titles = dict.fromkeys(r.task_title for r in rev.at_risk)
        text += "\n⚠️ Под угрозой: " + html.escape(", ".join(titles))
    return text


# ---------- отправка из воркера ----------


async def _deliver(
    bot: Bot, job: Job, text: str, markup: InlineKeyboardMarkup | None = None
) -> None:
    """Правит сообщение «Разбираю…», если оно есть, иначе шлёт новое. Сбой Telegram
    не роняет джобу — результат уже сохранён."""
    chat_id = job.payload.get("chat_id")
    if chat_id is None:
        return
    message_id = job.payload.get("message_id")
    try:
        if message_id is not None:
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="HTML",
                reply_markup=markup,
            )
        else:
            await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
    except TelegramAPIError:
        log.exception("Не удалось отправить результат джобы %s в Telegram", job.id)


Run = Callable[[AsyncSession, User, Job], Awaitable[Any]]
Reply = Callable[[Bot, AsyncSession, User, Job, Any], Awaitable[None]]


async def _user(db: AsyncSession, job: Job) -> User:
    user = await db.get(User, job.user_id)
    if user is None:
        raise jobs.JobFailedError("Пользователь удалён")
    return user


def _handler(run: Run, reply: Reply, bot: Bot | None) -> jobs.Handler:
    async def handle(db: AsyncSession, job: Job) -> None:
        user = await _user(db, job)
        to_chat = bot is not None and job.payload.get("origin") == AIOrigin.telegram
        # До rollback в обработчике очереди: потом атрибуты джобы истекут
        already_waiting = bool((job.result or {}).get("waiting"))
        created_at = job.created_at
        try:
            result = await run(db, user, job)
        except jobs.JobDeferredError as exc:
            if to_chat:
                assert bot is not None
                if exc.max_wait is not None and created_at < now_utc() - exc.max_wait:
                    await _deliver(bot, job, f"🤖 {html.escape(exc.expired_message)}")
                elif not already_waiting:
                    # Один раз: «в очереди»; результат потом заменит это сообщение
                    await _deliver(bot, job, f"🤖 {html.escape(exc.message)}")
            raise
        except jobs.JobFailedError as exc:
            if to_chat:
                assert bot is not None
                await _deliver(bot, job, f"🤖 {html.escape(exc.message)}")
            raise
        if to_chat:
            assert bot is not None
            await reply(bot, db, user, job, result)

    return handle


async def _run_parse(db: AsyncSession, user: User, job: Job) -> ParseDraft:
    return await AIParseService(db, user).run_parse(job)


async def _reply_parse(bot: Bot, db: AsyncSession, user: User, job: Job, draft: Any) -> None:
    await _deliver(bot, job, await parse_card(db, user, draft), parse_keyboard(job.id, draft))


async def _run_photo(db: AsyncSession, user: User, job: Job) -> PhotoDraft:
    return await AIParseService(db, user).run_photo(job)


async def _reply_photo(bot: Bot, db: AsyncSession, user: User, job: Job, draft: Any) -> None:
    await db.flush()
    await _deliver(bot, job, await photo_card(db, user, draft), task_keyboard(draft.task_id))


async def _run_breakdown(db: AsyncSession, user: User, job: Job) -> BreakdownDraft:
    return await BreakdownService(db, user).run(job)


async def _reply_breakdown(bot: Bot, db: AsyncSession, user: User, job: Job, draft: Any) -> None:
    task = await TaskService(db, user).get_detail(draft.task_id)
    await _deliver(
        bot, job, breakdown_card(task.title, draft), breakdown_keyboard(job.id, draft.task_id)
    )


def make_handlers(bot: Bot | None) -> dict[str, jobs.Handler]:
    """Обработчики ИИ-джоб для воркера: с ботом — ещё и ответ в Telegram."""
    return {
        JobKind.ai_parse: _handler(_run_parse, _reply_parse, bot),
        JobKind.ai_photo: _handler(_run_photo, _reply_photo, bot),
        JobKind.ai_breakdown: _handler(_run_breakdown, _reply_breakdown, bot),
    }


# ---------- кнопки ----------


async def _job(db: AsyncSession, user: User, id: uuid.UUID) -> Job | None:
    return await db.scalar(select(Job).where(Job.id == id, Job.user_id == user.id))


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


async def _start_breakdown(
    callback: CallbackQuery, db: AsyncSession, user: User, task_id: uuid.UUID, head: str
) -> None:
    """Ставит разбивку; шаги пришлёт воркер новым сообщением."""
    assert callback.message is not None
    await BreakdownService(db, user).start(
        task_id, BreakdownRequest(), origin=AIOrigin.telegram, chat_id=callback.message.chat.id
    )
    await _edit(callback, f"{head}\n🧩 Разбиваю на шаги…", _rows([_open(f"/tasks/{task_id}")]))


async def _on_parse_job(
    callback: CallbackQuery, db: AsyncSession, user: User, data: AIData
) -> None:
    job = await _job(db, user, data.id)
    if job is None or job.status != JobStatus.done or not job.result:
        await callback.answer("Карточка устарела — напишите заново", show_alert=True)
        return
    draft = ParseDraft.model_validate(job.result)
    if data.op == "ed":
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(reply_markup=edit_keyboard(job.id, draft))
        return
    if data.op == "bk":
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(reply_markup=parse_keyboard(job.id, draft))
        return
    if job.result.get("created"):
        await callback.answer("Уже создано")
        return

    kind = {"tt": KindHint.task, "tb": KindHint.backlog}.get(data.op)
    if data.op == "raw":
        created = await create_from_text(db, user, draft.text)
    else:
        created = await create_from_draft(db, user, draft, kind)
    job.result = {**job.result, "created": str(created.id)}
    await db.commit()
    tz = get_tz(user.timezone)
    head = cards.created_text(created, tz, now_utc())
    if data.op == "mk" and created.kind == KindHint.task:
        await callback.answer("Создано")
        await _start_breakdown(callback, db, user, created.id, head)
        return
    await callback.answer(cards.KIND_DONE.get(created.kind, "Создано"))
    await _edit(callback, head, cards.created_keyboard(created))


async def ai_callback(callback: CallbackQuery, db: AsyncSession, user: User) -> None:
    data = parse_callback(callback.data or "")
    if data is None:
        await callback.answer()
        return
    try:
        if data.op in ("mk", "cr", "ed", "tt", "tb", "raw", "bk"):
            await _on_parse_job(callback, db, user, data)
        elif data.op == "bt":
            task = await TaskService(db, user).get_detail(data.id)
            await callback.answer()
            await _start_breakdown(
                callback, db, user, data.id, f"✓ <b>Задание:</b> {html.escape(task.title)}"
            )
        elif data.op == "dt":
            await TaskService(db, user).delete(data.id)
            await callback.answer("Удалено")
            await _edit(callback, "Удалено.", None)
        elif data.op == "ap":
            await _apply_breakdown(callback, db, user, data.id)
        elif data.op == "pa":
            await ReplanService(db, user).apply(data.id)
            await callback.answer("План применён")
            if isinstance(callback.message, Message):
                await callback.message.edit_reply_markup(reply_markup=None)
                await callback.message.reply("✓ План применён. Отменить можно в приложении.")
        else:
            await callback.answer()
    except AppError as exc:
        await callback.answer(exc.message, show_alert=True)


async def _apply_breakdown(
    callback: CallbackQuery, db: AsyncSession, user: User, job_id: uuid.UUID
) -> None:
    job = await _job(db, user, job_id)
    if job is None or job.status != JobStatus.done or not job.result:
        await callback.answer("Шаги устарели — разбейте заново", show_alert=True)
        return
    if job.result.get("applied"):
        await callback.answer("Уже запланировано")
        return
    draft = BreakdownDraft.model_validate(job.result)
    svc = BreakdownService(db, user)
    await svc.apply_and_preview(
        draft.task_id,
        BreakdownApply(
            steps=draft.steps,
            task_type=draft.task_type,
            category_id=draft.category_id,
            job_id=job_id,
        ),
    )
    state = await plan_state(ReplanService(db, user))
    await callback.answer("Шаги добавлены")
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        markup = None
        if state.proposal is not None:
            markup = _rows([_button("Применить план", "pa", state.proposal.id), _open("/calendar")])
        await callback.message.reply(plan_text(state), parse_mode="HTML", reply_markup=markup)


# ---------- вход: текст и фото ----------


async def start_text(message: Message, db: AsyncSession, user: User, text: str) -> None:
    """Сообщение, которое quickparse не уверенно разобрал, — в ИИ."""
    placeholder = await message.reply(THINKING)
    await AIParseService(db, user).start_parse(
        text,
        origin=AIOrigin.telegram,
        chat_id=message.chat.id,
        message_id=placeholder.message_id,
    )
