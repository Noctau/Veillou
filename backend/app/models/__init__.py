"""Импорт всех моделей, чтобы они попали в Base.metadata (Alembic, тесты)."""

from app.models.ai import AILog, BreakdownTemplate
from app.models.attachment import Attachment
from app.models.backlog import BacklogItem
from app.models.catalog import ActionType, Category
from app.models.event import Event, RecurringEvent
from app.models.exam import Exam, ExamQuestion, ExamSession
from app.models.note import Note
from app.models.notify import Job, PushSubscription, Reminder
from app.models.plan import Calibration, PlanRevision, StudyDayLimit
from app.models.project import Milestone, Project
from app.models.schedule import BellSchedule, ClassRule, DayOff, Semester, Subject
from app.models.session import LoginFailure, UserSession
from app.models.source import Source
from app.models.task import Subtask, Task
from app.models.telegram import TelegramLinkCode
from app.models.user import User

__all__ = [
    "AILog",
    "ActionType",
    "Attachment",
    "BacklogItem",
    "BellSchedule",
    "BreakdownTemplate",
    "Calibration",
    "Category",
    "ClassRule",
    "DayOff",
    "Event",
    "Exam",
    "ExamQuestion",
    "ExamSession",
    "Job",
    "LoginFailure",
    "Milestone",
    "Note",
    "PlanRevision",
    "Project",
    "PushSubscription",
    "RecurringEvent",
    "Reminder",
    "Semester",
    "Source",
    "StudyDayLimit",
    "Subject",
    "Subtask",
    "Task",
    "TelegramLinkCode",
    "User",
    "UserSession",
]

# Пересчёт напоминаний и превью плана при изменениях — во всех процессах (api, worker, bot, тесты)
from app.notify import triggers
from app.services import plan_triggers

triggers.install()
plan_triggers.install()
