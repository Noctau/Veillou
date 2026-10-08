"""Разборы (M11.1, M11.3) и «У меня есть N минут» (M11.4)."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.backlog import BacklogRead
from app.schemas.common import InputModel, UTCMoment
from app.schemas.event import EventRead
from app.schemas.plan import PlanState


class EveningReview(BaseModel):
    date: date
    items: list[EventRead] = Field(description="Начатые и прошедшие блоки дня без отметки")
    done: int = Field(description="Сколько блоков дня уже отмечено «сделано»")


class RescheduleRequest(InputModel):
    event_ids: list[uuid.UUID] | None = Field(
        default=None, description="Что перенести; пусто — всё неотмеченное за день"
    )


class RescheduleResult(BaseModel):
    moved: int = Field(description="Сколько блоков отмечено «не сделано»")
    plan: PlanState


class WeekStats(BaseModel):
    week_start: date
    blocks_planned: int = Field(description="Гибких блоков на неделе (шаги, ящик, экзамены)")
    blocks_done: int
    blocks_missed: int
    done_minutes: int
    tasks_done: int
    backlog_done: int


class WeeklyReview(BaseModel):
    week_start: date = Field(description="Неделя, на которую берём дела (понедельник)")
    per_week: int = Field(description="Сколько дел из ящика брать на неделю")
    stats: WeekStats = Field(description="Итоги прошедшей (или текущей) недели")
    planned: list[BacklogRead] = Field(description="Уже взятые на эту неделю")
    suggestions: list[BacklogRead]


class WeekConfirm(InputModel):
    item_ids: list[uuid.UUID] = Field(
        max_length=7, description="Дела на неделю целиком: остальные с неё снимаются"
    )


class FreeSuggestion(BaseModel):
    kind: Literal["subtask", "task", "backlog"]
    id: uuid.UUID
    title: str
    minutes: int
    subtitle: str | None = Field(description="Задание шага или «Из ящика»")
    task_id: uuid.UUID | None
    deadline: UTCMoment | None


class FreeStart(InputModel):
    kind: Literal["subtask", "task", "backlog"]
    id: uuid.UUID
