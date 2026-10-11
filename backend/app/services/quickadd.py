"""Быстрый ввод: разбор строки (domain/quickparse) со сферами и словарями типов
задач и действий пользователя (`catalog.parse_words`)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.time import get_tz, now_utc, wall_to_utc
from app.domain.enums import EventKind
from app.domain.quickparse import KindHint, ParseResult, parse
from app.models import Area, User
from app.schemas.backlog import BacklogCreate
from app.schemas.event import EventCreate
from app.schemas.task import TaskCreate
from app.services.areas import area_refs_for_parse
from app.services.backlog import BacklogService
from app.services.catalog import default_action_type, ensure_defaults, parse_words
from app.services.events import EventService
from app.services.tasks import TaskService


@dataclass(frozen=True)
class QuickParse:
    """Разбор строки + типы задачи и действия из справочников пользователя."""

    result: ParseResult
    task_type_id: uuid.UUID | None
    action_type_id: uuid.UUID | None


def _id(value: object) -> uuid.UUID | None:
    return value if isinstance(value, uuid.UUID) else None


async def parse_text(db: AsyncSession, user: User, text: str) -> QuickParse:
    now = now_utc().astimezone(get_tz(user.timezone))
    if await ensure_defaults(db, user.id):
        await db.flush()
    words = await parse_words(db, user.id)
    p = parse(text, now, await area_refs_for_parse(db, user, now.date()), words.task, words.action)
    action_type_id = _id(p.action_type)
    if action_type_id is None and p.default_action:
        default = await default_action_type(db, user)
        action_type_id = default.id if default else None
    return QuickParse(p, _id(p.task_type), action_type_id)


# ---------- создание из текста (бот) ----------

DEFAULT_EVENT = timedelta(hours=1)


@dataclass(frozen=True)
class Created:
    kind: KindHint
    id: uuid.UUID
    title: str
    deadline: datetime | None = None  # задание
    desired_by: date | None = None  # дело в ящике
    start: datetime | None = None  # событие
    end: datetime | None = None
    area: str | None = None


class NeedsTimeError(AppError):
    code = "needs_time"
    message = "Для события нужно время: «завтра в 14», «в пт с 10 до 12»"


def _event_bounds(p: ParseResult, tz: ZoneInfo) -> tuple[datetime, datetime]:
    if p.date is None or p.time is None:
        raise NeedsTimeError()
    start = wall_to_utc(p.date, p.time, tz)
    if p.end_time is not None:
        end = wall_to_utc(p.date, p.end_time, tz)
        if end <= start:  # «с 23 до 1» — до следующего дня
            end += timedelta(days=1)
        return start, end
    return start, start + (timedelta(minutes=p.duration_min) if p.duration_min else DEFAULT_EVENT)


def resolve_kind(p: ParseResult, kind: KindHint | None) -> KindHint:
    kind = kind or p.kind_hint
    if kind == KindHint.event and (p.date is None or p.time is None):
        return KindHint.task if p.task_type is not None or p.is_deadline else KindHint.backlog
    return kind


async def create_from_text(
    db: AsyncSession, user: User, text: str, kind: KindHint | None = None
) -> Created:
    """Создаёт задание / дело в ящике / событие по строке быстрого ввода.

    `kind` — явный выбор («Изменить» в боте); без него — подсказка разбора.
    """
    text = text.strip()[:500]
    parsed = await parse_text(db, user, text)
    p = parsed.result
    if kind == KindHint.event and (p.date is None or p.time is None):
        raise NeedsTimeError()
    kind = resolve_kind(p, kind)
    title = (p.title or text)[:300]
    area_id = p.area_id if isinstance(p.area_id, uuid.UUID) else None
    area = await db.get(Area, area_id) if area_id else None
    action_type_id = parsed.action_type_id
    tz = get_tz(user.timezone)

    if kind == KindHint.event:
        start, end = _event_bounds(p, tz)
        event = await EventService(db, user).create(
            EventCreate(kind=EventKind.personal, title=title, start=start, end=end, area_id=area_id)
        )
        return Created(
            kind, event.id, title, start=start, end=end, area=area.name if area else None
        )

    if kind == KindHint.backlog:
        item = await BacklogService(db, user).create(
            BacklogCreate(title=title, desired_by=p.date, action_type_id=action_type_id)
        )
        return Created(kind, item.id, title, desired_by=p.date)

    deadline = p.deadline if p.date else None
    task = await TaskService(db, user).create(
        TaskCreate(
            title=title,
            task_type_id=parsed.task_type_id,
            area_id=area_id,
            action_type_id=action_type_id,
            deadline=deadline,
        )
    )
    return Created(kind, task.id, title, deadline=deadline, area=area.name if area else None)


async def delete_created(db: AsyncSession, user: User, kind: KindHint, id: uuid.UUID) -> None:
    if kind == KindHint.task:
        await TaskService(db, user).delete(id)
    elif kind == KindHint.backlog:
        await BacklogService(db, user).delete(id)
    else:
        await EventService(db, user).delete(id)
