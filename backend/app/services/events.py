"""События календаря: разовые личные блоки и правка вхождений шаблонов."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz
from app.domain.enums import FIXED_KINDS, EventStatus, SourceType
from app.models import DayOff, Event, RecurringEvent, Subject, User
from app.schemas.event import (
    EventCreate,
    EventUpdate,
    RecurringEventCreate,
    RecurringEventUpdate,
    check_event_bounds,
)
from app.services.backlog import on_backlog_event_status
from app.services.base import UserScopedRepository, apply_fields, validate_patch
from app.services.exams import ExamService
from app.services.recurring_tasks import ensure_has_occurrences
from app.services.schedule_sync import SeriesSync
from app.services.tasks import on_subtask_event_status


class EventRepo(UserScopedRepository[Event]):
    model = Event
    not_found_message = "Событие не найдено"


class SubjectRefRepo(UserScopedRepository[Subject]):
    model = Subject
    not_found_message = "Предмет не найден"


class RecurringRepo(UserScopedRepository[RecurringEvent]):
    model = RecurringEvent
    not_found_message = "Повтор не найден"


class DayOffRefRepo(UserScopedRepository[DayOff]):
    model = DayOff


MAX_CALENDAR_RANGE = timedelta(days=400)


class NotFromTemplateError(InvalidDataError):
    code = "not_from_template"
    message = "Событие не из расписания"


def _is_manual_edit(changes: dict[str, Any]) -> bool:
    """Отметки «сделано / не сделано», закрепление и заметка — не правка вхождения:
    серия по-прежнему обновляет время, аудиторию и т. п. (статус она не трогает)."""
    if changes.get("status") == EventStatus.cancelled:
        return True
    return bool(changes.keys() - {"status", "is_pinned", "note"})


class EventService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.events = EventRepo(db, user.id)
        self.recurring = RecurringRepo(db, user.id)
        self.sync = SeriesSync(db, user.id, self.tz)

    # ---------- календарь ----------

    async def calendar(self, start: datetime, end: datetime) -> tuple[list[Event], list[DayOff]]:
        """События, пересекающие [start, end), и выходные в этом диапазоне."""
        if end <= start:
            raise InvalidDataError("to должно быть позже from")
        if end - start > MAX_CALENDAR_RANGE:
            raise InvalidDataError("Слишком большой диапазон (максимум 400 дней)")
        events = await self.events.find_all(
            Event.start < end, Event.end > start, order_by=[Event.start, Event.title]
        )
        first = start.astimezone(self.tz).date()
        # `end` не входит в диапазон: [пн 00:00, вт 00:00) — это только понедельник
        last = (end - timedelta(microseconds=1)).astimezone(self.tz).date()
        days_off = await DayOffRefRepo(self.db, self.user_id).find_all(
            DayOff.date_from <= last, DayOff.date_to >= first, order_by=[DayOff.date_from]
        )
        return events, days_off

    async def get(self, id: uuid.UUID) -> Event:
        return await self.events.get_or_404(id)

    async def create(self, data: EventCreate) -> Event:
        if data.subject_id:
            await SubjectRefRepo(self.db, self.user_id).get_or_404(data.subject_id)
        event = Event(is_fixed=data.kind in FIXED_KINDS, status=EventStatus.planned)
        apply_fields(event, data)
        self.events.add(event)
        await self.db.commit()
        return event

    async def update(self, id: uuid.UUID, patch: EventUpdate) -> Event:
        event = await self.events.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name in ("title", "start", "end", "status", "is_pinned", "note"):
            if name in changes and changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        try:
            check_event_bounds(changes.get("start", event.start), changes.get("end", event.end))
        except ValueError as exc:
            raise InvalidDataError(str(exc)) from exc
        for name, value in changes.items():
            setattr(event, name, value)
        if event.template_id is not None and _is_manual_edit(changes):
            # Регенерация серии больше не трогает это вхождение
            event.detached = True
        if not event.is_fixed and changes.keys() & {"start", "end"}:
            # Гибкий блок, перенесённый руками, планировщик больше не двигает
            event.is_pinned = True
        if "status" in changes:
            await on_event_status(self.db, self.user, event)
        await self.db.commit()
        return event

    async def delete(self, id: uuid.UUID) -> None:
        """Разовое событие удаляется. Вхождение шаблона — отменяется (иначе серия
        создала бы его заново)."""
        event = await self.events.get_or_404(id)
        if event.template_id is not None:
            event.status = EventStatus.cancelled
            event.detached = True
        else:
            self.events.soft_delete(event)
        await self.db.commit()

    async def reset(self, id: uuid.UUID) -> Event:
        """«Вернуть как в расписании»: снимает detached и пересобирает вхождение по шаблону."""
        event = await self.events.get_or_404(id)
        if event.template_id is None:
            raise NotFromTemplateError()
        await self.sync.restore_occurrence(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    # ---------- личные повторы ----------

    async def list_recurring(self) -> list[RecurringEvent]:
        return await self.recurring.find_all(order_by=[RecurringEvent.start_time])

    async def create_recurring(self, data: RecurringEventCreate) -> RecurringEvent:
        await ensure_has_occurrences(data.rrule)
        rec = RecurringEvent()
        apply_fields(rec, data)
        self.recurring.add(rec)
        await self.db.flush()
        await self.sync.sync_recurring(rec)
        await self.db.commit()
        return rec

    async def update_recurring(self, id: uuid.UUID, patch: RecurringEventUpdate) -> RecurringEvent:
        rec = await self.recurring.get_or_404(id)
        data = validate_patch(rec, patch, RecurringEventCreate)
        if data.rrule != rec.rrule:
            await ensure_has_occurrences(data.rrule)
        apply_fields(rec, data)
        await self.db.flush()
        await self.sync.sync_recurring(rec)
        await self.db.commit()
        return rec

    async def delete_recurring(self, id: uuid.UUID) -> None:
        rec = await self.recurring.get_or_404(id)
        self.recurring.soft_delete(rec)
        await self.sync.remove_series(rec)
        await self.db.commit()


async def on_event_status(db: AsyncSession, user: User, event: Event) -> None:
    """Отметка на гибком блоке → та же отметка у его источника. Не коммитит."""
    if event.source_id is None:
        return
    if event.source_type == SourceType.subtask:
        await on_subtask_event_status(db, user.id, event.source_id, event.status)
    elif event.source_type == SourceType.backlog_item:
        await on_backlog_event_status(db, user.id, event.source_id, event.status)
    elif event.source_type == SourceType.exam_session:
        await ExamService(db, user).on_session_status(event.source_id, event.status)
