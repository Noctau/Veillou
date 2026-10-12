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
from app.domain.tasks import find_cycle

MAX_STEPS = 15

# «Нет значения» от модели — пустая строка (или «null», «нет»): Pydantic превращает в None
_EMPTY = frozenset({"", "null", "none", "нет", "-"})


def _blank(value: Any) -> Any:
    if isinstance(value, str) and value.strip().lower() in _EMPTY:
        return None
    return value.strip() if isinstance(value, str) else value


# Названия из справочников пользователя. Без справочника — свободная строка;
# with_choices сужает до названий пользователя (enum)
def _schema(description: str) -> WithJsonSchema:
    return WithJsonSchema({"type": "string", "description": description})


TaskTypeName = Annotated[
    str | None, BeforeValidator(_blank), _schema("Тип задачи из списка или пустая строка")
]
ActionTypeName = Annotated[
    str | None, BeforeValidator(_blank), _schema("Тип действия из списка или пустая строка")
]
CategoryName = Annotated[
    str | None, BeforeValidator(_blank), _schema("Категория из списка или пустая строка")
]
AreaName = Annotated[
    str | None, BeforeValidator(_blank), _schema("Сфера из списка или пустая строка")
]


class AIStep(BaseModel):
    order: int = Field(description="Номер шага, с 1")
    title: str = Field(description="Что сделать, глагол в начале", max_length=200)
    estimate_min: int = Field(description=f"Минуты, {MIN_STEP_MIN}–{MAX_STEP_MIN}")
    action_type: ActionTypeName = Field(description="Тип действия из списка")
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
    task_type: TaskTypeName = Field(description="Тип задачи из списка или пустая строка")
    category: CategoryName = Field(description="Категория задания из списка")
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
        description="task — задача с результатом; backlog — бытовое или личное дело; "
        "event — встреча с точным временем"
    )
    title: Title = Field(description="Короткое название, до 80 символов", max_length=200)
    task_type: TaskTypeName = Field(description="Тип задачи из списка; пустая строка — не задача")
    area: AreaName
    deadline_date: DeadlineDate
    deadline_time: DeadlineTime
    action_type: ActionTypeName
    description: str = Field(
        description="Требования из сообщения или пустая строка", max_length=5000
    )


class AIPhoto(_Deadline, BaseModel):
    text: str = Field(description="Весь текст задания с фото, как написан", max_length=10_000)
    title: Title = Field(description="Короткое название задания, до 80 символов", max_length=200)
    task_type: TaskTypeName
    area: AreaName
    deadline_date: DeadlineDate
    deadline_time: DeadlineTime


def _choice(names: list[str], what: str) -> Any:
    """Строка из списка `names` или пустая строка (→ None). Пустой список — всегда None."""

    def check(value: str | None) -> str | None:
        if value is None or not names:
            return None
        if value not in names:
            raise ValueError(f"{what} не из списка")
        return value

    return Annotated[
        str | None,
        BeforeValidator(_blank),
        AfterValidator(check),
        WithJsonSchema({"type": "string", "enum": [*names, ""]}),
    ]


CHOICES = {
    "area": ("сфера", "Сфера из списка или пустая строка"),
    "task_type": ("тип задачи", "Тип задачи из списка или пустая строка"),
    "action_type": ("тип действия", "Тип действия из списка или пустая строка"),
    "category": ("категория", "Категория из списка или пустая строка"),
}


def with_choices[T: BaseModel](schema: type[T], **choices: list[str]) -> type[T]:
    """Схема, где строковые поля (`area`, `task_type`, `action_type`, `category`) — одно из
    названий справочника пользователя или пустая строка. Поля, которых в схеме нет,
    пропускаются; `action_type` сужается и у шагов разбивки. Порядок полей и
    валидаторы схемы сохраняются."""
    fields: dict[str, Any] = {}
    for name, names in choices.items():
        if name not in schema.model_fields:
            continue
        what, description = CHOICES[name]
        fields[name] = (_choice(names, what), Field(description=description))
    if "subtasks" in schema.model_fields and "action_type" in choices:
        step = with_choices(AIStep, action_type=choices["action_type"])
        fields["subtasks"] = (list[step], Field(min_length=1, max_length=MAX_STEPS))  # type: ignore[valid-type]
    if not fields:
        return schema
    return create_model(schema.__name__, __base__=schema, **fields)


# ---------- этапы проекта (M13.2) ----------

MAX_MILESTONES = 12


class AIMilestone(BaseModel):
    title: Title = Field(
        description="Этап — результат, а не действие: «Обзор литературы готов»", max_length=200
    )
    date: DeadlineDate
    note: str = Field(description="Что входит в этап, коротко, или пустая строка", max_length=500)

    @field_validator("note")
    @classmethod
    def _strip(cls, value: str) -> str:
        return " ".join(value.split())


class AIMilestones(BaseModel):
    milestones: list[AIMilestone] = Field(min_length=1, max_length=MAX_MILESTONES)
    warning: str = Field(
        description="Что уточнить, если описания мало для плана, или пустая строка", max_length=500
    )

    @field_validator("warning")
    @classmethod
    def _blank(cls, value: str) -> str:
        return (_blank(value) or "").strip()


# ---------- ИИ-настройка (M21.4) ----------
#
# Упрощённая сборка для модели: ссылки — названиями, «нет» — пустая строка или 0,
# паттерн — плоские поля. В `ConfigBundle` её переводит domain/bundle.normalize_setup.

MAX_SETUP_ITEMS = 20
HHMM = WithJsonSchema({"type": "string", "description": "ЧЧ:ММ или пустая строка"})


def _setup_text(value: Any) -> str:
    return " ".join(str(value or "").split())


SetupText = Annotated[str, BeforeValidator(_setup_text)]
SetupTime = Annotated[str, BeforeValidator(_setup_text), HHMM]


class AISetupAreaType(BaseModel):
    name: SetupText = Field(description="Тип сферы в единственном числе: «Ученик», «Предмет»")
    name_plural: SetupText = Field(description="Во множественном: «Ученики»")
    fields: list[SetupText] = Field(
        description="Подписи полей карточки сферы: «Класс», «Телефон родителя»", max_length=10
    )


class AISetupArea(BaseModel):
    name: SetupText = Field(description="Сфера: ученик, предмет, клиент, место работы, кружок")
    type: SetupText = Field(description="Название типа сферы")


class AISetupEventType(BaseModel):
    name: SetupText = Field(description="Тип занятости: «Смена», «Урок», «Встреча»")
    name_plural: SetupText
    travel_min: int = Field(description="Дорога до и после, минут; 0 — без дороги")
    remind_min: int = Field(description="Напомнить за N минут; 0 — не напоминать")
    is_rest: bool = Field(description="Это отдых, который нельзя занимать делами")
    show_now_next: bool = Field(description="Показывать на «Сегодня» как «Сейчас / Дальше»")


Weekday = Literal["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


class AISetupRule(BaseModel):
    event_type: SetupText = Field(description="Название типа занятости")
    area: SetupText = Field(description="Название сферы из areas или пустая строка")
    title: SetupText = Field(description="Название событий или пустая строка")
    pattern: Literal["weekly", "shifts", "once"] = Field(
        description="weekly — по дням недели; shifts — смены N через M; once — один раз"
    )
    weekdays: list[Weekday] = Field(description="weekly: дни недели")
    on_days: int = Field(description="shifts: рабочих дней подряд")
    off_days: int = Field(description="shifts: дней отдыха")
    anchor: SetupText = Field(description="shifts: дата первой смены ГГГГ-ММ-ДД или пусто")
    date: SetupText = Field(description="once: дата ГГГГ-ММ-ДД")
    start: SetupTime
    end: SetupTime = Field(description="ЧЧ:ММ; раньше начала — через полночь")


class AISetupDayProfile(BaseModel):
    name: SetupText = Field(description="Режим дня: «Будни», «Смена», «После ночной»")
    wake: SetupTime
    sleep: SetupTime
    work_start: SetupTime = Field(description="С какого времени можно ставить дела")
    work_end: SetupTime
    weekdays: list[Weekday] = Field(description="По каким дням недели или пусто")
    on_event_type: SetupText = Field(description="В дни событий этого типа или пусто")
    after_event_type: SetupText = Field(description="На следующий день после события или пусто")


class AISetupBudget(BaseModel):
    name: SetupText = Field(description="Лимит: «Работа», «Учёба»")
    minutes_per_day: int = Field(description="Не больше минут в день")
    event_types: list[SetupText] = Field(description="Типы занятости, идущие в лимит")
    action_types: list[SetupText] = Field(description="Типы действий, идущие в лимит")


class AISetupTaskType(BaseModel):
    name: SetupText = Field(description="Тип задачи: «ДЗ», «Отчёт»")
    synonyms: list[SetupText] = Field(description="Слова для быстрого ввода", max_length=10)


class AISetup(BaseModel):
    about: SetupText = Field(description="О пользователе одной-двумя фразами", max_length=1000)
    area_types: list[AISetupAreaType] = Field(max_length=MAX_SETUP_ITEMS)
    areas: list[AISetupArea] = Field(max_length=MAX_SETUP_ITEMS * 2)
    event_types: list[AISetupEventType] = Field(max_length=MAX_SETUP_ITEMS)
    rules: list[AISetupRule] = Field(max_length=MAX_SETUP_ITEMS * 2)
    day_profiles: list[AISetupDayProfile] = Field(max_length=MAX_SETUP_ITEMS)
    budgets: list[AISetupBudget] = Field(max_length=MAX_SETUP_ITEMS)
    task_types: list[AISetupTaskType] = Field(max_length=MAX_SETUP_ITEMS)
    warning: SetupText = Field(description="Что уточнить, или пустая строка", max_length=500)
