"""Триггеры перепланирования (M9.2): правки, после которых план может устареть.

Как и пересборка напоминаний (notify/triggers.py), — один обработчик
`after_flush`: если в транзакции поменялось что-то, что влияет на план,
ставится джоба `plan.preview` (с дедупликацией и паузой — серия правок даёт
один пересчёт). Воркер считает превью; применяет его только пользователь.

Дела из ящика (взятые на неделю) и дни подготовки к экзаменам — тоже.

Не триггерят: «сделано» (план остаётся верным, освободившееся время подберёт
следующий пересчёт), заметки, отметки калибровки и правки самого планировщика
(флаг сессии `SKIP_REPLAN`).
"""

import uuid
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, UOWTransaction

from app.domain.enums import EventStatus, PlanReason, SubtaskStatus, TaskStatus
from app.models import (
    ActionType,
    BacklogItem,
    Event,
    Exam,
    ExamSession,
    StudyDayLimit,
    Subtask,
    Task,
    User,
)
from app.services.jobs import enqueue_plan_preview_sync
from app.services.replan import SKIP_REPLAN

TASK_FIELDS = {
    "deadline",
    "priority",
    "estimate_min",
    "time_window",
    "action_type_id",
    "task_type",
    "deadline_buffer_days",
    "deleted_at",
}
SUBTASK_FIELDS = {"estimate_min", "depends_on", "time_window", "action_type_id", "deleted_at"}
EVENT_FIELDS = {"start", "end", "is_pinned", "deleted_at"}
USER_FIELDS = {"settings", "timezone"}
BACKLOG_FIELDS = {
    "planned_week",
    "status",
    "estimate_min",
    "conditions",
    "time_window",
    "action_type_id",
    "deleted_at",
}
EXAM_FIELDS = {"starts_at", "duration_min", "plan_enabled", "deleted_at"}
SESSION_FIELDS = {"question_ids", "minutes", "date", "deleted_at"}
# Статусы события, переход в которые (или из которых) меняет занятость
EVENT_STATUSES = {EventStatus.missed, EventStatus.cancelled}


def _changed(obj: Any, fields: set[str]) -> dict[str, tuple[Any, Any]]:
    """Изменённые поля: имя → (было, стало)."""
    state = inspect(obj)
    result = {}
    for name in fields:
        hist = state.attrs[name].history
        if hist.has_changes():
            old = hist.deleted[0] if hist.deleted else None
            new = hist.added[0] if hist.added else None
            result[name] = (old, new)
    return result


def _relevant(obj: Any, is_new: bool) -> bool:
    if isinstance(obj, Task):
        if is_new:
            return obj.status == TaskStatus.active
        changes = _changed(obj, TASK_FIELDS | {"status"})
        status = changes.pop("status", None)
        return bool(changes) or (status is not None and status[1] == TaskStatus.active)
    if isinstance(obj, Subtask):
        if is_new:
            return True
        changes = _changed(obj, SUBTASK_FIELDS | {"status"})
        status = changes.pop("status", None)
        return bool(changes) or (status is not None and status[1] == SubtaskStatus.todo)
    if isinstance(obj, Event):
        if is_new:
            return True
        changes = _changed(obj, EVENT_FIELDS | {"status"})
        status = changes.pop("status", None)
        return bool(changes) or (status is not None and bool(set(status) & EVENT_STATUSES))
    if isinstance(obj, User):
        return not is_new and bool(_changed(obj, USER_FIELDS))
    if isinstance(obj, ActionType):
        return is_new or bool(_changed(obj, {"windows", "deleted_at"}))
    if isinstance(obj, BacklogItem):
        if is_new:
            return obj.planned_week is not None
        return bool(_changed(obj, BACKLOG_FIELDS))
    if isinstance(obj, Exam):
        return not is_new and bool(_changed(obj, EXAM_FIELDS))
    if isinstance(obj, ExamSession):
        return is_new or bool(_changed(obj, SESSION_FIELDS))
    return isinstance(obj, StudyDayLimit)


def _reason(objs: list[Any]) -> PlanReason:
    for obj in objs:
        if isinstance(obj, Event) and obj.status == EventStatus.missed:
            return PlanReason.missed
    return PlanReason.changes


def _after_flush(session: Session, _: UOWTransaction) -> None:
    if session.info.get(SKIP_REPLAN):
        return
    by_user: dict[uuid.UUID, list[Any]] = {}
    for obj in (*session.new, *session.dirty, *session.deleted):
        is_new = obj in session.new
        if not is_new and obj in session.dirty and not session.is_modified(obj):
            continue
        user_id = obj.id if isinstance(obj, User) else getattr(obj, "user_id", None)
        if user_id is not None and _relevant(obj, is_new):
            by_user.setdefault(user_id, []).append(obj)
    for user_id, objs in by_user.items():
        enqueue_plan_preview_sync(session.connection(), user_id, _reason(objs))


def install() -> None:
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)
