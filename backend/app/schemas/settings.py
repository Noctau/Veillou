"""Настройки пользователя.

В `users.settings` (JSONB) лежат только переопределения пользователя; итоговые
настройки = дефолты отсюда, глубоко смёрженные с переопределениями. Так новые
поля и изменённые дефолты применяются автоматически.

Время везде — «настенное» в TZ пользователя, формат "HH:MM".
"""

import uuid
from datetime import time
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    create_model,
    field_validator,
)

from app.schemas.common import WallTime


class Channel(StrEnum):
    push = "push"
    telegram = "telegram"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class TimeRange(_Model):
    """Интервал внутри дня. end < start означает переход через полночь (сон, тихие часы)."""

    start: WallTime
    end: WallTime


class ReminderRule(_Model):
    enabled: bool = True
    channels: list[Channel] = Field(
        default_factory=lambda: [Channel.push, Channel.telegram], max_length=len(Channel)
    )

    @field_validator("channels", mode="before")
    @classmethod
    def _unique_channels(cls, value: Any) -> Any:
        # Повторы схлопываются до проверки длины: ["push", "push"] — это просто push
        return list(dict.fromkeys(value)) if isinstance(value, list) and len(value) <= 10 else value


DaysBefore = Annotated[int, Field(ge=0, le=14)]


class DeadlineRule(ReminderRule):
    """Приходит во время утренней сводки (и склеивается с ней)."""

    days_before: list[DaysBefore] = Field(
        default_factory=lambda: [3, 1, 0],
        max_length=5,
        description="За сколько дней до дедлайна; 0 — утром в день сдачи",
    )

    @field_validator("days_before")
    @classmethod
    def _unique_desc(cls, value: list[int]) -> list[int]:
        return sorted(set(value), reverse=True)


class Reminders(_Model):
    morning_digest: ReminderRule = ReminderRule()
    deadlines: DeadlineRule = DeadlineRule()
    evening_review: ReminderRule = ReminderRule()
    weekly_review: ReminderRule = ReminderRule()
    subtask_start: ReminderRule = ReminderRule(enabled=False)


# Смещение от подъёма / отбоя режима дня, минут (отрицательное — в другую сторону)
OffsetMin = Annotated[int, Field(ge=-720, le=720)]


class Schedule(_Model):
    """Когда приходят сводка и разборы. Сводка и вечерний разбор — по режиму дня:
    после ночной смены с подъёмом в 15:00 сводка придёт после 15:00."""

    morning_digest_after_wake_min: OffsetMin = Field(
        default=30, description="Утренняя сводка — через N минут после подъёма"
    )
    evening_review_before_sleep_min: OffsetMin = Field(
        default=120, description="Вечерний разбор — за N минут до отбоя"
    )
    weekly_review_weekday: int = Field(default=7, ge=1, le=7, description="ISO: 1 = Пн, 7 = Вс")
    weekly_review: WallTime = time(19, 0)


class Rest(_Model):
    """Минимум отдыха в неделю: планировщик не ставит сюда гибкие блоки."""

    free_evenings_per_week: int = Field(default=2, ge=0, le=7)
    weekend_half_days: int = Field(default=1, ge=0, le=4)


About = Annotated[str, StringConstraints(max_length=1000)]

# Вкладка навигации (M22.2): раздел или конкретная сфера / тип сфер
NavItem = Annotated[
    str,
    StringConstraints(
        pattern=r"^(areas|tasks|projects|notes|inbox|(area|area_type):[0-9a-f-]{36})$"
    ),
]
MAX_NAV = 6


class TodayCard(StrEnum):
    """Карточки «Сегодня», которые можно выключить."""

    now_next = "now_next"  # «Сейчас / Дальше»
    progress = "progress"  # прогресс дня
    review = "review"  # «Не отмечено — разобрать», разбор недели
    day = "day"  # лента дня
    free = "free"  # «Есть время»
    deadlines = "deadlines"  # ближайшие дедлайны


class UserSettings(_Model):
    """Сон, обед и рабочие часы — в режимах дня (`day_profiles`, M18)."""

    about: About = Field(
        default="",
        description="О себе — для ИИ: чем занят, где учится или работает (до 1000 символов)",
    )
    default_action_type_id: uuid.UUID | None = Field(
        default=None, description="Тип действия задач и дел без своего типа; null — без типа"
    )
    deadline_buffer_days: int = Field(
        default=1, ge=0, le=14, description="Закончить за N дней до дедлайна"
    )
    quiet_hours: TimeRange = Field(
        default=TimeRange(start=time(22, 30), end=time(8, 0)),
        description="Для режимов дня без «тихие часы — сон режима»",
    )
    schedule: Schedule = Schedule()
    reminders: Reminders = Reminders()
    rest: Rest = Rest()
    backlog_per_week: int = Field(
        default=3, ge=0, le=7, description="Сколько дел из ящика брать на неделю"
    )
    onboarding_done: bool = Field(
        default=False, description="Первичная настройка пройдена или пропущена"
    )
    nav: list[NavItem] = Field(
        default_factory=lambda: ["areas", "inbox"],
        max_length=MAX_NAV,
        description="Вкладки после закреплённых «Сегодня», «Календарь», «＋»: areas, tasks, "
        "projects, notes, inbox, area:<id>, area_type:<id>",
    )
    today_cards: list[TodayCard] = Field(
        default_factory=lambda: list(TodayCard), description="Включённые карточки «Сегодня»"
    )

    @field_validator("nav", "today_cards")
    @classmethod
    def _unique(cls, value: list[Any]) -> list[Any]:
        return list(dict.fromkeys(value))


# ---------- частичное обновление ----------


def _partial(model: type[BaseModel], cache: dict[type, type[BaseModel]]) -> type[BaseModel]:
    """Копия модели, где все поля необязательны, а вложенные модели тоже частичные.

    Валидаторы не переносятся: целостность проверяется на итоговых настройках.
    """
    if model in cache:
        return cache[model]
    fields: dict[str, Any] = {}
    for name, info in model.model_fields.items():
        annotation: Any = info.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            annotation = _partial(annotation, cache)
        elif info.metadata:
            # сохраняем ограничения (ge/le) и сериализатор времени
            annotation = Annotated[annotation, *info.metadata]
        fields[name] = (annotation | None, Field(default=None, description=info.description))
    partial = create_model(
        f"{model.__name__}Patch",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
    cache[model] = partial
    return partial


UserSettingsPatch: type[BaseModel] = _partial(UserSettings, {})


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Рекурсивный мёрж словарей.

    Списки и скаляры заменяются целиком; `None` удаляет ключ (= вернуть дефолт).
    """
    result = dict(base)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            merged = deep_merge(result[key], value)
            if merged:
                result[key] = merged
            else:
                result.pop(key)
        elif isinstance(value, dict):
            cleaned = deep_merge({}, value)
            if cleaned:
                result[key] = cleaned
        else:
            result[key] = value
    return result
