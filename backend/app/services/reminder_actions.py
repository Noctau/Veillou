"""Кнопки на напоминаниях: «Сделано», «+15 мин», «На завтра».

Из Telegram действие приходит от привязанного пользователя (callback), из пуша —
по одноразовому токену без сессии (service worker шлёт его в фоне). Каждое
напоминание принимает одно действие.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.core.security import hash_token
from app.core.time import get_tz, now_utc
from app.domain.enums import (
    EventStatus,
    ReminderAction,
    ReminderKind,
    ReminderStatus,
    SourceType,
    SubtaskStatus,
    TaskStatus,
)
from app.models import Event, Reminder, Subtask, Task, User
from app.notify.builder import next_allowed
from app.notify.message import fmt_moment, plural
from app.schemas.task import SubtaskSchedule, SubtaskUpdate, TaskUpdate
from app.services.reminders import quiet_range
from app.services.settings import effective_settings
from app.services.tasks import TaskService

SNOOZE = timedelta(minutes=15)
# Сколько живёт токен кнопок пуша после срока напоминания
TOKEN_TTL = timedelta(days=7)


class ReminderActionError(AppError):
    status_code = 409
    code = "reminder_action_failed"


@dataclass(frozen=True)
class ActionResult:
    message: str
    url: str | None = None
    # Действие посчитало превью плана — бот предложит «Применить план»
    proposal_id: uuid.UUID | None = None


async def _subtask_event(db: AsyncSession, r: Reminder) -> tuple[Event, Subtask]:
    e = await db.get(Event, r.entity_id) if r.entity_id else None
    if (
        e is None
        or e.user_id != r.user_id
        or e.deleted_at is not None
        or e.source_type != SourceType.subtask
        or e.source_id is None
    ):
        raise ReminderActionError("Блок уже удалён")
    st = await db.get(Subtask, e.source_id)
    if st is None or st.deleted_at is not None:
        raise ReminderActionError("Подзадача уже удалена")
    return e, st


async def _task(db: AsyncSession, r: Reminder) -> Task:
    t = await db.get(Task, r.entity_id) if r.entity_id else None
    if t is None or t.user_id != r.user_id or t.deleted_at is not None:
        raise ReminderActionError("Задание уже удалено")
    return t


def _snooze(db: AsyncSession, user: User, r: Reminder, at: datetime) -> datetime:
    tz = get_tz(user.timezone)
    fire_at = next_allowed(at, quiet_range(effective_settings(user)), tz)
    if r.expires_at is not None and fire_at >= r.expires_at:
        raise ReminderActionError("Позже напоминать уже поздно — срок раньше")
    db.add(
        Reminder(
            user_id=r.user_id,
            kind=r.kind,
            fire_at=fire_at,
            due_at=fire_at,
            expires_at=r.expires_at,
            channels=list(r.channels),
            payload=dict(r.payload),
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            dedupe_key=f"{r.dedupe_key}:snooze:{uuid.uuid4().hex[:8]}",
            is_auto=False,
            status=ReminderStatus.pending,
            sent_channels=[],
            attempts=0,
        )
    )
    return fire_at


async def perform(
    db: AsyncSession, user: User, r: Reminder, action: ReminderAction, now: datetime | None = None
) -> ActionResult:
    now = now or now_utc()
    tz = get_tz(user.timezone)
    today = now.astimezone(tz).date()
    if r.action_used_at is not None:
        raise ReminderActionError("Уже сделано")
    kind = ReminderKind(r.kind)
    tasks = TaskService(db, user)

    if kind == ReminderKind.deadline:
        task = await _task(db, r)
        url = f"/tasks/{task.id}"
        r.action_used_at = now
        if action == ReminderAction.done:
            if task.status != TaskStatus.done:
                await tasks.update(task.id, TaskUpdate(status=TaskStatus.done))
            else:
                await db.commit()
            return ActionResult(f"Готово: «{task.title}» закрыто", url)
        at = now + (SNOOZE if action == ReminderAction.snooze else timedelta(days=1))
        fire_at = _snooze(db, user, r, at)
        await db.commit()
        return ActionResult(f"Напомню {fmt_moment(fire_at, tz, today)}", url)

    if kind == ReminderKind.subtask_start:
        event, st = await _subtask_event(db, r)
        url = f"/tasks/{st.task_id}"
        r.action_used_at = now
        if action == ReminderAction.done:
            if st.status != SubtaskStatus.done:
                await tasks.update_subtask(st.id, SubtaskUpdate(status=SubtaskStatus.done))
            else:
                await db.commit()
            return ActionResult(f"Готово: «{st.title}»", url)
        if action == ReminderAction.snooze:
            fire_at = _snooze(db, user, r, now + SNOOZE)
            await db.commit()
            return ActionResult(f"Напомню {fmt_moment(fire_at, tz, today)}", url)
        if event.status != EventStatus.planned:
            raise ReminderActionError("Блок уже отмечен")
        day = timedelta(days=1)
        await tasks.schedule(st.id, SubtaskSchedule(start=event.start + day, end=event.end + day))
        return ActionResult(f"Перенесено на {fmt_moment(event.start + day, tz, today)}", url)

    if kind == ReminderKind.evening_review and action == ReminderAction.reschedule:
        from app.services.review import ReviewService

        day = date.fromisoformat(r.payload["date"])
        moved, rev = await ReviewService(db, user, now).reschedule(day=day)
        r.action_used_at = now
        await db.commit()
        if not moved:
            return ActionResult("Переносить нечего — всё отмечено", "/")
        text = f"Перенесла: {moved} {plural(moved, 'блок', 'блока', 'блоков')}. "
        text += "Проверьте превью плана" if rev else "План уже учитывает это"
        return ActionResult(text, "/", rev.id if rev else None)

    if kind == ReminderKind.weekly_review and action == ReminderAction.accept:
        from app.services.review import ReviewService

        review = ReviewService(db, user, now)
        week = await review.weekly()
        ids = [i.id for i in week.planned] + [i.id for i in week.suggestions]
        if not week.suggestions:
            raise ReminderActionError("Предлагать нечего — ящик пуст или неделя уже набрана")
        rev = await review.confirm_week(ids)
        r.action_used_at = now
        await db.commit()
        n = len(week.suggestions)
        text = f"Взяла на неделю {n} {plural(n, 'дело', 'дела', 'дел')}"
        text += ". Проверьте превью плана" if rev else ""
        return ActionResult(text, "/", rev.id if rev else None)

    raise ReminderActionError("У этого напоминания нет действий")


async def perform_by_token(db: AsyncSession, token: str, action: ReminderAction) -> ActionResult:
    """Кнопка пуша: токен одноразовый и живёт `TOKEN_TTL`."""
    r = await db.scalar(
        select(Reminder).where(
            Reminder.action_token_hash == hash_token(token),
            Reminder.deleted_at.is_(None),
        )
    )
    # Срок — от времени отправки, а не создания: напоминания создаются за 8 дней вперёд
    if r is None or r.fire_at < now_utc() - TOKEN_TTL:
        raise NotFoundError("Ссылка устарела")
    user = await db.get(User, r.user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("Ссылка устарела")
    return await perform(db, user, r, action)


async def perform_by_id(
    db: AsyncSession, user: User, reminder_id: uuid.UUID, action: ReminderAction
) -> ActionResult:
    """Кнопка в Telegram: пользователь уже известен боту."""
    r = await db.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == user.id,
            Reminder.deleted_at.is_(None),
        )
    )
    if r is None:
        raise NotFoundError("Напоминание не найдено")
    return await perform(db, user, r, action)
