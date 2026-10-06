"""Быстрый ввод: разбор строки (domain/quickparse) с предметами пользователя."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.time import get_tz, now_utc, wall_to_utc
from app.domain.enums import EventKind, TaskType
from app.domain.quickparse import KindHint, ParseResult, SubjectRef, parse
from app.models import ActionType, Semester, Subject, User
from app.schemas.backlog import BacklogCreate
from app.schemas.event import EventCreate
from app.schemas.task import TaskCreate
from app.services.backlog import BacklogService
from app.services.catalog import ensure_defaults
from app.services.events import EventService
from app.services.tasks import TaskService


async def subject_refs(db: AsyncSession, user: User, today: date) -> list[SubjectRef]:
    """Предметы текущих семестров (и без семестра). Если текущих нет — все:
    так одинаковые названия из прошлых семестров не делают разбор неоднозначным."""
    current = select(Semester.id).where(
        Semester.user_id == user.id,
        Semester.deleted_at.is_(None),
        Semester.start_date <= today,
        or_(
            Semester.session_end >= today,
            Semester.session_end.is_(None) & (Semester.classes_end >= today),
        ),
    )
    base = select(Subject).where(Subject.user_id == user.id, Subject.deleted_at.is_(None))
    subjects = list(
        await db.scalars(
            base.where(or_(Subject.semester_id.in_(current), Subject.semester_id.is_(None)))
        )
    )
    if not subjects:
        subjects = list(await db.scalars(base))
    return [
        SubjectRef(s.id, tuple(n for n in (s.name, s.short_name, *s.synonyms) if n))
        for s in subjects
    ]


async def parse_text(db: AsyncSession, user: User, text: str) -> ParseResult:
    now = now_utc().astimezone(get_tz(user.timezone))
    return parse(text, now, await subject_refs(db, user, now.date()))


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
    subject: str | None = None


class NeedsTimeError(AppError):
    code = "needs_time"
    message = "Для события нужно время: «завтра в 14», «в пт с 10 до 12»"


def _event_bounds(p: ParseResult, tz: ZoneInfo) -> tuple[datetime, datetime]:
    assert p.date is not None and p.time is not None
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
        return KindHint.task if p.task_type or p.is_deadline else KindHint.backlog
    return kind


async def create_from_text(
    db: AsyncSession, user: User, text: str, kind: KindHint | None = None
) -> Created:
    """Создаёт задание / дело в ящике / событие по строке быстрого ввода.

    `kind` — явный выбор («Изменить» в боте); без него — подсказка разбора.
    """
    text = text.strip()[:500]
    p = await parse_text(db, user, text)
    if kind == KindHint.event and (p.date is None or p.time is None):
        raise NeedsTimeError()
    kind = resolve_kind(p, kind)
    title = (p.title or text)[:300]
    subject_id = p.subject_id if isinstance(p.subject_id, uuid.UUID) else None
    subject = await db.get(Subject, subject_id) if subject_id else None
    action_type_id = None
    if p.action_type is not None:
        if await ensure_defaults(db, user.id):
            await db.flush()
        action_type_id = await db.scalar(
            select(ActionType.id).where(
                ActionType.user_id == user.id,
                ActionType.deleted_at.is_(None),
                ActionType.key == p.action_type,
            )
        )
    tz = get_tz(user.timezone)

    if kind == KindHint.event:
        start, end = _event_bounds(p, tz)
        event = await EventService(db, user).create(
            EventCreate(
                kind=EventKind.personal, title=title, start=start, end=end, subject_id=subject_id
            )
        )
        return Created(
            kind, event.id, title, start=start, end=end, subject=subject and subject.name
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
            task_type=p.task_type or TaskType.other,
            subject_id=subject_id,
            action_type_id=action_type_id,
            deadline=deadline,
        )
    )
    return Created(kind, task.id, title, deadline=deadline, subject=subject and subject.name)


async def delete_created(db: AsyncSession, user: User, kind: KindHint, id: uuid.UUID) -> None:
    if kind == KindHint.task:
        await TaskService(db, user).delete(id)
    elif kind == KindHint.backlog:
        await BacklogService(db, user).delete(id)
    else:
        await EventService(db, user).delete(id)
