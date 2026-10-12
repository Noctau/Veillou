"""Триггер автозадач (M19): правки жёстких событий и правил автозадач ставят джобу
`event_tasks.sync` (с дедупликацией и паузой — серия правок даёт один пересчёт).

Задачи автозадач меняет сама джоба — событий она не трогает, так что петли нет.
"""

import uuid
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, UOWTransaction

from app.domain.enums import EventKind
from app.models import Event, EventRule
from app.services.jobs import enqueue_event_tasks_sync

EVENT_FIELDS = ("start", "end", "status", "deleted_at", "area_id", "event_type_id", "title")


def _relevant(obj: Any, is_new: bool) -> bool:
    if isinstance(obj, EventRule):
        return True
    if isinstance(obj, Event) and obj.kind == EventKind.busy:
        if is_new:
            return True
        state = inspect(obj)
        return any(state.attrs[name].history.has_changes() for name in EVENT_FIELDS)
    return False


def _after_flush(session: Session, _: UOWTransaction) -> None:
    users: set[uuid.UUID] = set()
    for obj in (*session.new, *session.dirty, *session.deleted):
        is_new = obj in session.new
        if not is_new and obj in session.dirty and not session.is_modified(obj):
            continue
        user_id = getattr(obj, "user_id", None)
        if user_id is not None and _relevant(obj, is_new):
            users.add(user_id)
    if users:
        enqueue_event_tasks_sync(session.connection(), users)


def install() -> None:
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)
