"""Быстрый ввод: разбор строки (domain/quickparse) с предметами пользователя."""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import get_tz, now_utc
from app.domain.quickparse import ParseResult, SubjectRef, parse
from app.models import Semester, Subject, User


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
