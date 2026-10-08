"""ИИ: джобы, черновик разбивки, шаблоны, разбор текста и фото."""

import datetime as dt
import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.domain.enums import JobStatus, TaskType
from app.domain.quickparse import KindHint
from app.domain.tasks import find_cycle
from app.schemas.common import InputModel, ReadModel, UTCMoment
from app.schemas.plan import PlanState
from app.schemas.task import Description, SubtaskEstimate, TaskDetail, Title

Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
MAX_STEPS = 50


class JobStarted(BaseModel):
    job_id: uuid.UUID


# ---------- шаги ----------


class BreakdownStep(InputModel):
    """Шаг черновика. `depends_on` — индексы шагов этого же списка."""

    title: Title
    estimate_min: SubtaskEstimate
    action_type_id: uuid.UUID | None = None
    depends_on: list[int] = Field(default_factory=list, max_length=MAX_STEPS)
    note: Description = ""


def check_steps(steps: list[BreakdownStep]) -> None:
    for i, s in enumerate(steps):
        if i in s.depends_on:
            raise ValueError(f"Шаг {i + 1} зависит сам от себя")
        if any(d < 0 or d >= len(steps) for d in s.depends_on):
            raise ValueError(f"Шаг {i + 1}: зависимость от несуществующего шага")
    if find_cycle({i: s.depends_on for i, s in enumerate(steps)}):
        raise ValueError("Зависимости шагов образуют цикл")


class BreakdownDraft(BaseModel):
    """Черновик разбивки от ИИ — ничего не сохранено, пока не нажали «Запланировать»."""

    type: Literal["breakdown"] = "breakdown"
    task_id: uuid.UUID
    task_type: TaskType
    category_id: uuid.UUID | None
    steps: list[BreakdownStep]
    total_estimate_min: int
    warning: str | None = Field(description="Предупреждение ИИ")
    time_warning: str | None = Field(description="Не хватает времени до дедлайна (расчёт)")
    free_minutes: int | None = Field(description="Свободно до дедлайна, минут; null — без дедлайна")
    coef: float = Field(description="Калибровка: оценки × coef = сколько займёт на деле")


class ParseDraft(BaseModel):
    """Разбор свободного текста ИИ — карточка «Создать и разбить / Изменить»."""

    type: Literal["parse"] = "parse"
    kind: KindHint
    title: str
    description: str
    task_type: TaskType | None
    subject_id: uuid.UUID | None
    deadline: UTCMoment | None
    action_type_id: uuid.UUID | None
    text: str = Field(description="Исходный текст")


class PhotoDraft(BaseModel):
    """Распознанное фото задания; поля задания уже обновлены (см. `updated`)."""

    type: Literal["photo"] = "photo"
    task_id: uuid.UUID
    title: str
    text: str
    task_type: TaskType | None
    subject_id: uuid.UUID | None
    deadline: UTCMoment | None
    updated: list[str] = Field(description="Какие поля задания заполнены с фото")


class MilestoneSuggestion(InputModel):
    """Этап черновика: на экране проверки правится и уходит в «Сохранить»."""

    title: Title
    date: dt.date | None = None
    note: Description = ""


class MilestonesDraft(BaseModel):
    """Этапы проекта от ИИ — ничего не сохранено, пока не нажали «Сохранить»."""

    type: Literal["milestones"] = "milestones"
    project_id: uuid.UUID
    milestones: list[MilestoneSuggestion]
    warning: str | None = Field(description="Что уточнить в описании проекта")


JobResult = Annotated[
    BreakdownDraft | ParseDraft | PhotoDraft | MilestonesDraft, Field(discriminator="type")
]


class JobRead(BaseModel):
    id: uuid.UUID
    kind: str
    status: JobStatus
    error: str | None = Field(default=None, description="Почему не вышло — для пользователя")
    waiting: str | None = Field(
        default=None, description="ИИ недоступен — запрос ждёт в очереди (status=pending)"
    )
    result: JobResult | None = None


# ---------- разбивка ----------


class BreakdownRequest(InputModel):
    """«Разбить на шаги» / «Перегенерировать с комментарием»."""

    comment: Comment | None = None
    previous: list[BreakdownStep] = Field(
        default_factory=list,
        max_length=MAX_STEPS,
        description="Прошлый вариант — для перегенерации",
    )


class BreakdownApply(InputModel):
    """«Запланировать»: несделанные шаги задания заменяются этими, считается превью плана."""

    steps: list[BreakdownStep] = Field(min_length=1, max_length=MAX_STEPS)
    task_type: TaskType | None = None
    category_id: uuid.UUID | None = None
    plan: bool = Field(default=True, description="Сразу посчитать превью плана")
    job_id: uuid.UUID | None = Field(
        default=None, description="Джоба черновика — пометить применённой (баннер на задании)"
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        check_steps(self.steps)
        return self


class BreakdownApplied(BaseModel):
    task: TaskDetail
    plan: PlanState | None


# ---------- шаблоны ----------


class TemplateCreate(InputModel):
    name: Name
    task_type: TaskType | None = None
    steps: list[BreakdownStep] = Field(min_length=1, max_length=MAX_STEPS)

    @model_validator(mode="after")
    def _check(self) -> Self:
        check_steps(self.steps)
        return self


class TemplateUpdate(InputModel):
    name: Name | None = None
    task_type: TaskType | None = None


class TemplateRead(ReadModel):
    id: uuid.UUID
    name: str
    task_type: TaskType | None
    steps: list[BreakdownStep]
    total_estimate_min: int
    created_at: UTCMoment


# ---------- разбор текста ----------


class AIParseRequest(InputModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]


# ---------- этапы проекта (M13.2) ----------

MAX_MILESTONES = 30


class MilestonesRequest(InputModel):
    """«Предложить этапы» / «Перегенерировать с комментарием»."""

    comment: Comment | None = None
    previous: list[MilestoneSuggestion] = Field(
        default_factory=list,
        max_length=MAX_MILESTONES,
        description="Прошлый вариант — для перегенерации",
    )


class MilestonesApply(InputModel):
    """«Сохранить»: этапы добавляются к уже существующим."""

    milestones: list[MilestoneSuggestion] = Field(min_length=1, max_length=MAX_MILESTONES)
    job_id: uuid.UUID | None = Field(
        default=None, description="Джоба черновика — пометить применённой"
    )
