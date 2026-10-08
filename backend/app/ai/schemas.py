"""Схемы ответов ИИ. JSON Schema из них уходит в провайдер (`format` / `response_format`),
ответ проверяется ими же; при ошибке — один повтор с текстом ошибки.

Мелкие огрехи (оценка 10 или 180 минут, лишние пробелы) не стоят повтора — их
поправляют валидаторы; повтор — только когда ответ по смыслу сломан
(ссылка на несуществующий шаг, цикл зависимостей, пустой список).
"""

import re
from datetime import date, time
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    WithJsonSchema,
    create_model,
    field_validator,
    model_validator,
)

from app.domain.breakdown import MAX_STEP_MIN, MIN_STEP_MIN, round_estimate
from app.domain.enums import ActionTypeKey, CategoryKey, TaskType
from app.domain.tasks import find_cycle

MAX_STEPS = 15


class AIStep(BaseModel):
    order: int = Field(description="Номер шага, с 1")
    title: str = Field(description="Что сделать, глагол в начале", max_length=200)
    estimate_min: int = Field(description=f"Минуты, {MIN_STEP_MIN}–{MAX_STEP_MIN}")
    action_type: ActionTypeKey
    depends_on: list[int] = Field(description="Номера шагов, которые нужно сделать раньше")
    note: str = Field(description="Подсказка к шагу или пустая строка", max_length=500)

    @field_validator("title", "note")
    @classmethod
    def _strip(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("title")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("пустое название шага")
        return value

    @field_validator("estimate_min")
    @classmethod
    def _clamp(cls, value: int) -> int:
        return round_estimate(value)


class AIBreakdown(BaseModel):
    task_type: TaskType = Field(description="Тип самого задания")
    category: CategoryKey = Field(description="Категория задания")
    subtasks: list[AIStep] = Field(min_length=1, max_length=MAX_STEPS)
    total_estimate_min: int = Field(description="Сумма оценок шагов")
    warning: str | None = Field(
        default=None, description="Что уточнить, если задание непонятно; иначе null"
    )

    @field_validator("warning")
    @classmethod
    def _blank(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @model_validator(mode="after")
    def _deps(self) -> Self:
        orders = [s.order for s in self.subtasks]
        if len(set(orders)) != len(orders):
            raise ValueError("номера шагов (order) повторяются")
        known = set(orders)
        for s in self.subtasks:
            if s.order in s.depends_on:
                raise ValueError(f"шаг {s.order} зависит сам от себя")
            if unknown := set(s.depends_on) - known:
                raise ValueError(
                    f"шаг {s.order} ссылается на несуществующие шаги {sorted(unknown)}"
                )
        if find_cycle({s.order: s.depends_on for s in self.subtasks}):
            raise ValueError("зависимости шагов образуют цикл")
        return self


# ---------- разбор текста и фото ----------
#
# Все поля обязательные, «нет значения» — пустая строка (или `other`): с
# необязательными полями модель под грамматикой почти всегда выбирает null.
# Pydantic превращает пустое в None; схема для модели — простые строки.

_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_EMPTY = frozenset({"", "null", "none", "нет", "-"})


def _blank(value: Any) -> Any:
    if isinstance(value, str) and value.strip().lower() in _EMPTY:
        return None
    return value.strip() if isinstance(value, str) else value


def _hhmm(value: Any) -> str | None:
    value = _blank(value)
    if value is None:
        return None
    match = _HHMM.match(str(value))
    if not match:
        raise ValueError("время в формате ЧЧ:ММ или пустая строка")
    return f"{int(match[1]):02d}:{match[2]}"


DeadlineDate = Annotated[
    date | None,
    BeforeValidator(_blank),
    WithJsonSchema({"type": "string", "description": "ГГГГ-ММ-ДД или пустая строка"}),
]
DeadlineTime = Annotated[
    str | None,
    BeforeValidator(_hhmm),
    WithJsonSchema(
        {"type": "string", "description": "ЧЧ:ММ, только если время названо; иначе пустая строка"}
    ),
]
Subject = Annotated[
    str | None,
    BeforeValidator(_blank),
    WithJsonSchema({"type": "string", "description": "Предмет из списка или пустая строка"}),
]


def _title(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("пустое название")
    return value


Title = Annotated[str, AfterValidator(_title)]


class _Deadline:
    """Примесь без полей (иначе Pydantic поставит их первыми — модель заполняет по порядку)."""

    def deadline_wall(self) -> tuple[date, time | None] | None:
        day: date | None = getattr(self, "deadline_date", None)
        at: str | None = getattr(self, "deadline_time", None)
        if day is None:
            return None
        return day, time.fromisoformat(at) if at else None


class AIParsed(_Deadline, BaseModel):
    kind: Literal["task", "backlog", "event"] = Field(
        description="task — учебное/рабочее задание; backlog — бытовое или личное дело; "
        "event — встреча с точным временем"
    )
    title: Title = Field(description="Короткое название, до 80 символов", max_length=200)
    task_type: TaskType = Field(description="Тип задания; other — если не задание")
    subject: Subject
    deadline_date: DeadlineDate
    deadline_time: DeadlineTime
    action_type: ActionTypeKey
    description: str = Field(
        description="Требования из сообщения или пустая строка", max_length=5000
    )


class AIPhoto(_Deadline, BaseModel):
    text: str = Field(description="Весь текст задания с фото, как написан", max_length=10_000)
    title: Title = Field(description="Короткое название задания, до 80 символов", max_length=200)
    task_type: TaskType
    subject: Subject
    deadline_date: DeadlineDate
    deadline_time: DeadlineTime


def with_subjects[T: BaseModel](schema: type[T], names: list[str]) -> type[T]:
    """Схема, где `subject` — одно из названий предметов пользователя или пустая строка."""
    if not names:
        return schema
    subject: Any = Annotated[
        str | None,
        BeforeValidator(_blank),
        AfterValidator(lambda v: _one_of(v, names)),
        WithJsonSchema({"type": "string", "enum": [*names, ""]}),
    ]
    fields = {name: (info.annotation, info) for name, info in schema.model_fields.items()}
    fields["subject"] = (subject, Field(description="Предмет из списка или пустая строка"))
    # Порядок полей сохраняем — модель заполняет их по порядку
    return create_model(schema.__name__, __base__=_base_of(schema), **fields)  # type: ignore[call-overload,no-any-return]


def _one_of(value: str | None, names: list[str]) -> str | None:
    if value is not None and value not in names:
        raise ValueError("предмет не из списка")
    return value


def _base_of(schema: type[BaseModel]) -> tuple[type, ...]:
    """Без самого BaseModel-класса со старыми полями: только примеси (`_Deadline`)."""
    return (*(b for b in schema.__bases__ if b is not BaseModel), BaseModel)
