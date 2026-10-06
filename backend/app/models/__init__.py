"""Импорт всех моделей, чтобы они попали в Base.metadata (Alembic, тесты)."""

from app.models.event import Event, RecurringEvent
from app.models.schedule import BellSchedule, ClassRule, DayOff, Semester, Subject
from app.models.session import UserSession
from app.models.telegram import TelegramLinkCode
from app.models.user import User

__all__ = [
    "BellSchedule",
    "ClassRule",
    "DayOff",
    "Event",
    "RecurringEvent",
    "Semester",
    "Subject",
    "TelegramLinkCode",
    "User",
    "UserSession",
]
