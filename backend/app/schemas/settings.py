"""Настройки пользователя.

В `users.settings` (JSONB) лежат только переопределения пользователя; итоговые
настройки = дефолты отсюда, глубоко смёрженные с переопределениями. Так новые
поля и изменённые дефолты применяются автоматически.

Время везде — «настенное» в TZ пользователя, формат "HH:MM".
"""

from datetime import time
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    create_model,
    model_validator,
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


class DayRange(TimeRange):
    """Интервал, который не переходит через полночь."""

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if self.end <= self.start:
            raise ValueError("Конец должен быть позже начала")
        return self


class WorkHours(_Model):
    weekdays: DayRange = DayRange(start=time(9, 0), end=time(21, 0))
    weekends: DayRange = DayRange(start=time(11, 0), end=time(19, 0))


class ReminderRule(_Model):
    enabled: bool = True
    channels: list[Channel] = Field(default_factory=lambda: [Channel.push, Channel.telegram])


class BeforeClassRule(ReminderRule):
    minutes_before: int = Field(default=15, ge=0, le=180)


class Reminders(_Model):
    morning_digest: ReminderRule = ReminderRule()
    before_class: BeforeClassRule = BeforeClassRule()
    deadlines: ReminderRule = ReminderRule()
    evening_review: ReminderRule = ReminderRule()
    weekly_review: ReminderRule = ReminderRule()
    subtask_start: ReminderRule = ReminderRule(enabled=False)


class Schedule(_Model):
    """Когда приходят сводка и разборы."""

    morning_digest: WallTime = time(8, 0)
    evening_review: WallTime = time(21, 30)
    weekly_review_weekday: int = Field(default=7, ge=1, le=7, description="ISO: 1 = Пн, 7 = Вс")
    weekly_review: WallTime = time(19, 0)


class Rest(_Model):
    """Минимум отдыха в неделю: планировщик не ставит сюда гибкие блоки."""

    free_evenings_per_week: int = Field(default=2, ge=0, le=7)
    weekend_half_days: int = Field(default=1, ge=0, le=4)


class UserSettings(_Model):
    work_hours: WorkHours = WorkHours()
    sleep: TimeRange = TimeRange(start=time(23, 30), end=time(7, 30))
    lunch: DayRange = DayRange(start=time(13, 0), end=time(14, 0))
    travel_buffer_min: int = Field(
        default=60, ge=0, le=240, description="Дорога до университета и обратно, мин"
    )
    study_limit_min_per_day: int = Field(default=360, ge=30, le=960)
    deadline_buffer_days: int = Field(
        default=1, ge=0, le=14, description="Закончить за N дней до дедлайна"
    )
    quiet_hours: TimeRange = TimeRange(start=time(22, 30), end=time(8, 0))
    schedule: Schedule = Schedule()
    reminders: Reminders = Reminders()
    rest: Rest = Rest()


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
    partial = create_model(  # type: ignore[call-overload]
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
