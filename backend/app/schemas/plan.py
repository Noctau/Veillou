"""Перепланирование: превью, применение, откат, разовые лимиты дня, калибровка."""

import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import ActionTypeKey, EventKind, PlanReason, PlanRevisionStatus, TaskType
from app.domain.planner import RiskReason
from app.schemas.common import InputModel, ReadModel, UTCMoment


class PlanSlot(BaseModel):
    start: UTCMoment
    end: UTCMoment


class PlanChange(ReadModel):
    """Что произойдёт с блоком. move — перенос, add — новый, remove — убран,
    miss — неотмеченный блок прошлого дня станет «не сделано»."""

    op: Literal["move", "add", "remove", "miss"]
    event_id: uuid.UUID | None
    task_id: uuid.UUID | None
    kind: EventKind = EventKind.subtask
    title: str
    source_type: str | None
    source_id: uuid.UUID | None
    before: PlanSlot | None
    after: PlanSlot | None


class PlanRisk(ReadModel):
    """Под угрозой. no_slots / no_time — не влезает до дедлайна; dependency — не
    поставлено то, от чего зависит; late — позже внутреннего срока; overdue — просрочено;
    rest — влезло бы, если отдать минимум отдыха.

    Группа — к чему относится блок: задание, дело из ящика (не влезло в неделю)
    или экзамен (день подготовки)."""

    group_kind: Literal["task", "backlog", "exam"]
    group_id: uuid.UUID
    group_title: str
    task_id: uuid.UUID | None
    source_type: str
    source_id: uuid.UUID
    title: str
    reason: RiskReason
    deadline: UTCMoment | None

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data: Any) -> Any:
        """Ревизии до M11 хранили только task_id / task_title."""
        if isinstance(data, dict) and "group_id" not in data and data.get("task_id"):
            data = {
                **data,
                "group_kind": "task",
                "group_id": data["task_id"],
                "group_title": data.get("task_title", ""),
            }
        return data


class PlanRevisionRead(ReadModel):
    id: uuid.UUID
    status: PlanRevisionStatus
    reasons: list[PlanReason]
    created_at: UTCMoment
    applied_at: UTCMoment | None
    changes: list[PlanChange] = Field(validation_alias="ops")
    at_risk: list[PlanRisk]
    moved: int = 0
    added: int = 0
    removed: int = 0
    missed: int = 0


class PlanState(BaseModel):
    proposal: PlanRevisionRead | None = Field(description="Превью, ждущее «Применить / Отменить»")
    undoable: PlanRevisionRead | None = Field(
        description="Последнее применение за сутки — его можно откатить"
    )


class PlanUndoResult(BaseModel):
    revision: PlanRevisionRead
    restored: int
    skipped: int = Field(description="Блоки, которые после применения правили руками")


# ---------- разовый лимит учёбы ----------


class StudyDayLimitPut(InputModel):
    minutes: int = Field(ge=0, le=960)


class StudyDayLimitRead(ReadModel):
    date: date
    minutes: int


# ---------- калибровка ----------


class CalibrationRead(ReadModel):
    task_type: TaskType
    action_type: ActionTypeKey
    coef: float = Field(description="Множитель оценок: 1.2 — делаешь на 20% дольше")
    samples: int
