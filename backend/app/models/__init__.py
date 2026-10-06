"""Импорт всех моделей, чтобы они попали в Base.metadata (Alembic, тесты)."""

from app.models.catalog import ActionType, Category
from app.models.event import Event, RecurringEvent
from app.models.schedule import BellSchedule, ClassRule, DayOff, Semester, Subject
from app.models.session import UserSession
from app.models.task import Subtask, Task
from app.models.telegram import TelegramLinkCode
from app.models.user import User

__all__ = [
    "ActionType",
    "BellSchedule",
    "Category",
    "ClassRule",
    "DayOff",
    "Event",
    "RecurringEvent",
    "Semester",
    "Subject",
    "Subtask",
    "Task",
    "TelegramLinkCode",
    "User",
    "UserSession",
]
