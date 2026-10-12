"""Импорт всех моделей, чтобы они попали в Base.metadata (Alembic, тесты)."""

from app.models.ai import AILog, BreakdownTemplate
from app.models.area import Area, AreaType
from app.models.attachment import Attachment
from app.models.backlog import BacklogItem
from app.models.budget import BudgetDayOverride, LoadBudget, LoadBudgetMember
from app.models.catalog import ActionType, Category, TaskType
from app.models.day_profile import DayProfile, DayProfileRule
from app.models.event import Event
from app.models.exam import Exam, ExamQuestion, ExamSession
from app.models.note import Note
from app.models.notify import Job, PushSubscription, Reminder
from app.models.plan import Calibration, PlanRevision
from app.models.project import Milestone, Project
from app.models.schedule import DayOff, EventType, Period, ScheduleRule, SlotGrid
from app.models.session import LoginFailure, UserSession
from app.models.source import Source
from app.models.task import Subtask, Task
from app.models.telegram import TelegramLinkCode
from app.models.user import User

__all__ = [
    "AILog",
    "ActionType",
    "Area",
    "AreaType",
    "Attachment",
    "BacklogItem",
    "BreakdownTemplate",
    "BudgetDayOverride",
    "Calibration",
    "Category",
    "DayOff",
    "DayProfile",
    "DayProfileRule",
    "Event",
    "EventType",
    "Exam",
    "ExamQuestion",
    "ExamSession",
    "Job",
    "LoadBudget",
    "LoadBudgetMember",
    "LoginFailure",
    "Milestone",
    "Note",
    "Period",
    "PlanRevision",
    "Project",
    "PushSubscription",
    "Reminder",
    "ScheduleRule",
    "SlotGrid",
    "Source",
    "Subtask",
    "Task",
    "TaskType",
    "TelegramLinkCode",
    "User",
    "UserSession",
]

# Пересчёт напоминаний и превью плана при изменениях — во всех процессах (api, worker, bot, тесты)
from app.notify import triggers
from app.services import plan_triggers

triggers.install()
plan_triggers.install()
