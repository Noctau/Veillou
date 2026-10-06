"""События календаря: разовые личные блоки и правка вхождений шаблонов."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz
from app.domain.enums import FIXED_KINDS, EventStatus, TemplateType
from app.models import ClassRule, Event, Subject, User
from app.schemas.event import EventCreate, EventUpdate
from app.services.base import UserScopedRepository, apply_fields
from app.services.schedule_sync import SeriesSync


class EventRepo(UserScopedRepository[Event]):
    model = Event
    not_found_message = "Событие не найдено"


class SubjectRefRepo(UserScopedRepository[Subject]):
    model = Subject
    not_found_message = "Предмет не найден"


class NotFromTemplateError(InvalidDataError):
    code = "not_from_template"
    message = "Событие не из расписания"


class EventService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.events = EventRepo(db, user.id)

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
        start = changes.get("start", event.start)
        end = changes.get("end", event.end)
        if end <= start:
            raise InvalidDataError("Конец должен быть позже начала")
        for name, value in changes.items():
            setattr(event, name, value)
        if changes and event.template_id is not None:
            # Регенерация серии больше не трогает это вхождение
            event.detached = True
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
        event.detached = False
        event.status = EventStatus.planned
        await self.db.flush()
        sync = SeriesSync(self.db, self.user_id, self.tz)
        if event.template_type == TemplateType.class_rule:
            rule = await self.db.get(ClassRule, event.template_id)
            if rule is not None:
                await sync.sync_class_rules([rule])
        await self.db.commit()
        await self.db.refresh(event)
        return event
