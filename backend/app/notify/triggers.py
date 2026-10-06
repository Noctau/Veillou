"""Пересчёт напоминаний при любом изменении плана, расписания и настроек.

Вместо вызовов в каждом сервисе — один обработчик `after_flush` на всех
сессиях: если в транзакции менялись события, задания, подзадачи, типы действий
или сам пользователь (настройки, TZ, Telegram), ставится джоба
`reminders.sync` для этого пользователя. Джоба дедуплицируется и стартует с
небольшой паузой, так что серия правок — одна пересборка. Откат транзакции
откатывает и джобу.
"""

import uuid

from sqlalchemy import event
from sqlalchemy.orm import Session, UOWTransaction

from app.models import ActionType, Event, Subtask, Task, User
from app.services.jobs import enqueue_reminders_sync_sync

WATCHED = (Event, Task, Subtask, ActionType)


def _changed_users(session: Session) -> set[uuid.UUID]:
    users: set[uuid.UUID] = set()
    for obj in (*session.new, *session.dirty, *session.deleted):
        if obj in session.dirty and not session.is_modified(obj):
            continue
        if isinstance(obj, WATCHED) and obj.user_id is not None:
            users.add(obj.user_id)
        elif isinstance(obj, User) and obj.id is not None:
            users.add(obj.id)
    return users


def _after_flush(session: Session, _: UOWTransaction) -> None:
    if users := _changed_users(session):
        enqueue_reminders_sync_sync(session.connection(), users)


def install() -> None:
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)
