"""Импорт всех моделей, чтобы они попали в Base.metadata (Alembic, тесты)."""

from app.models.attachment import Attachment
from app.models.backlog import BacklogItem
from app.models.catalog import ActionType, Category
from app.models.event import Event, RecurringEvent
from app.models.note import Note
from app.models.project import Milestone, Project
from app.models.schedule import BellSchedule, ClassRule, DayOff, Semester, Subject
from app.models.session import UserSession
from app.models.source import Source
from app.models.task import Subtask, Task
from app.models.telegram import TelegramLinkCode
from app.models.user import User

__all__ = [
    "ActionType",
    "Attachment",
    "BacklogItem",
    "BellSchedule",
    "Category",
    "ClassRule",
    "DayOff",
    "Event",
    "Milestone",
    "Note",
    "Project",
    "RecurringEvent",
    "Semester",
    "Source",
    "Subject",
    "Subtask",
    "Task",
    "TelegramLinkCode",
    "User",
    "UserSession",
]
