"""Занятость и расписание (Part 2, M17): типы занятости, периоды, сетки слотов,
исключения и правила расписания (сферы — schemas/area.py).

`*Update` — частичные: все поля необязательны. Сервис накладывает их на текущие
значения и валидирует итог через `*Create`, так что межполевые проверки
(начало < конца и т. п.) работают и при PATCH.
"""

import uuid
from datetime import date
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.domain.enums import CategoryIcon
from app.domain.recurrence import MAX_CYCLE_WEEKS, MAX_DAY_CYCLE, parse_rrule
from app.schemas.area import FieldDefRead, FieldDefs, FieldValues
from app.schemas.common import (
    MAX_PERIOD,
    HexColor,
    InputModel,
    ReadModel,
    SaneDate,
    WallTime,
    Weekday,
)
from app.schemas.settings import Channel

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Note = Annotated[str, StringConstraints(max_length=5000)]
LocationLabel = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]
BufferMin = Annotated[int, Field(ge=0, le=240, description="Минут")]
RemindMin = Annotated[
    int, Field(ge=0, le=1440, description="За сколько минут; null — не напоминать")
]
SlotNumber = Annotated[int, Field(ge=1, le=20)]
CycleWeek = Annotated[int, Field(ge=1, le=MAX_CYCLE_WEEKS)]

MAX_GRID_DAYS = 8  # общая строка + 7 дней недели


def _channels(value: list[Channel] | None) -> list[Channel] | None:
    return list(dict.fromkeys(value)) if value is not None else None


# ---------- типы занятости ----------


class EventTypeCreate(InputModel):
    name: Name = Field(description="В единственном числе: «Смена»")
    name_plural: Name | None = Field(
        default=None, description="Во множественном — заголовок в сводке; null — как name"
    )
    icon: CategoryIcon = CategoryIcon.calendar
    color: HexColor = "#64748b"
    buffer_before_min: BufferMin = 0
    buffer_after_min: BufferMin = 0
    merge_buffers: bool = Field(
        default=False,
        description="Подряд в день с тем же местом — буфер до первого и после последнего",
    )
    remind_before_min: RemindMin | None = None
    remind_channels: list[Channel] = Field(
        default_factory=lambda: [Channel.push, Channel.telegram], max_length=len(Channel)
    )
    show_now_next: bool = Field(default=False, description="Карточка «Сейчас / Дальше»")
    is_rest: bool = Field(default=False, description="Защищённый отдых")
    supports_prep: bool = Field(default=False, description="Подготовка к событию")
    location_label: LocationLabel = Field(
        default="", description="Подпись перед местом в текстах: «ауд.» → «ауд. 1801»"
    )
    default_area_type_id: uuid.UUID | None = None
    fields: FieldDefs = Field(default_factory=list)

    _ch = field_validator("remind_channels")(_channels)


class EventTypeUpdate(InputModel):
    name: Name | None = None
    name_plural: Name | None = None
    icon: CategoryIcon | None = None
    color: HexColor | None = None
    buffer_before_min: BufferMin | None = None
    buffer_after_min: BufferMin | None = None
    merge_buffers: bool | None = None
    remind_before_min: RemindMin | None = Field(default=None, description="null — не напоминать")
    remind_channels: list[Channel] | None = Field(default=None, max_length=len(Channel))
    show_now_next: bool | None = None
    is_rest: bool | None = None
    supports_prep: bool | None = None
    location_label: LocationLabel | None = None
    default_area_type_id: uuid.UUID | None = None
    fields: FieldDefs | None = Field(default=None, description="Полный список полей")
    position: int | None = Field(default=None, ge=0, le=1000)

    _ch = field_validator("remind_channels")(_channels)


class EventTypeRead(ReadModel):
    id: uuid.UUID
    key: str | None = Field(description="Ключ сида/миграции; у своих типов — null")
    name: str
    name_plural: str
    icon: CategoryIcon
    color: str
    buffer_before_min: int
    buffer_after_min: int
    merge_buffers: bool
    remind_before_min: int | None
    remind_channels: list[Channel]
    show_now_next: bool
    is_rest: bool
    supports_prep: bool
    location_label: str
    default_area_type_id: uuid.UUID | None
    fields: list[FieldDefRead] = Field(description="Живые поля (удалённые не показываются)")
    position: int

    @field_validator("fields", mode="before")
    @classmethod
    def _live(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [f for f in value if not (isinstance(f, dict) and f.get("deleted"))]
        return value


# ---------- периоды ----------


class Pause(InputModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: SaneDate = Field(alias="from")
    to: SaneDate
    title: ShortText = ""

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.to < self.from_:
            raise ValueError("Пауза: конец раньше начала")
        return self


class PeriodCreate(InputModel):
    name: Name
    start_date: SaneDate
    end_date: SaneDate = Field(description="Последний день периода")
    cycle_weeks: int = Field(default=1, ge=1, le=MAX_CYCLE_WEEKS, description="1 — без цикла")
    first_cycle_week: int = Field(
        default=1, ge=1, le=MAX_CYCLE_WEEKS, description="Неделя цикла, куда попадает начало"
    )
    pauses: list[Pause] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("Конец периода раньше начала")
        if self.end_date - self.start_date > MAX_PERIOD:
            raise ValueError("Период — не длиннее года")
        if self.first_cycle_week > self.cycle_weeks:
            raise ValueError("Неделя цикла больше длины цикла")
        for p in self.pauses:
            if p.from_ < self.start_date or p.to > self.end_date:
                raise ValueError("Пауза выходит за границы периода")
        self.pauses.sort(key=lambda p: p.from_)
        return self


class PeriodUpdate(InputModel):
    name: Name | None = None
    start_date: SaneDate | None = None
    end_date: SaneDate | None = None
    cycle_weeks: int | None = Field(default=None, ge=1, le=MAX_CYCLE_WEEKS)
    first_cycle_week: int | None = Field(default=None, ge=1, le=MAX_CYCLE_WEEKS)
    pauses: list[Pause] | None = Field(default=None, max_length=20)


class PauseRead(ReadModel):
    from_: date = Field(alias="from")
    to: date
    title: str


class PeriodRead(ReadModel):
    id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    cycle_weeks: int
    first_cycle_week: int
    pauses: list[PauseRead]


# ---------- сетки слотов ----------


class SlotIn(InputModel):
    number: SlotNumber
    start: WallTime
    end: WallTime

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"Слот {self.number}: конец должен быть позже начала")
        return self


class SlotGridDay(InputModel):
    weekday: Weekday | None = Field(default=None, description="null — общие слоты")
    slots: list[SlotIn] = Field(max_length=20)

    @model_validator(mode="after")
    def _check_slots(self) -> Self:
        numbers = [s.number for s in self.slots]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Номера слотов повторяются")
        self.slots.sort(key=lambda s: s.number)
        for prev, cur in zip(self.slots, self.slots[1:], strict=False):
            if cur.start < prev.end:
                raise ValueError(f"Слоты {prev.number} и {cur.number} пересекаются")
        return self


class SlotGridPut(InputModel):
    """Сетка целиком: общие слоты + переопределения дней. `id` — общая строка
    существующей сетки (переименовать, перенести в другой период); без него сетка
    ищется по (period_id, name), нет такой — создаётся."""

    id: uuid.UUID | None = None
    period_id: uuid.UUID | None = None
    name: Name
    schedules: list[SlotGridDay] = Field(max_length=MAX_GRID_DAYS)

    @model_validator(mode="after")
    def _check_unique(self) -> Self:
        days = [s.weekday for s in self.schedules]
        if len(days) != len(set(days)):
            raise ValueError("День недели указан дважды")
        if None not in days:
            self.schedules.insert(0, SlotGridDay(weekday=None, slots=[]))
        return self


class SlotRead(ReadModel):
    number: int
    start: WallTime
    end: WallTime


class SlotGridRead(ReadModel):
    id: uuid.UUID
    period_id: uuid.UUID | None
    name: str
    weekday: int | None
    slots: list[SlotRead]


# ---------- исключения ----------


class DayOffCreate(InputModel):
    period_id: uuid.UUID | None = Field(default=None, description="null — во всех периодах")
    date_from: SaneDate
    date_to: SaneDate
    title: ShortText = ""

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.date_to < self.date_from:
            raise ValueError("Конец раньше начала")
        if self.date_to - self.date_from > MAX_PERIOD:
            raise ValueError("Исключение — не дольше года подряд")
        return self


class DayOffUpdate(InputModel):
    period_id: uuid.UUID | None = None
    date_from: SaneDate | None = None
    date_to: SaneDate | None = None
    title: str | None = None


class DayOffRead(ReadModel):
    id: uuid.UUID
    period_id: uuid.UUID | None
    date_from: date
    date_to: date
    title: str


# ---------- правила расписания ----------


class WeeklyPatternIn(InputModel):
    kind: Literal["weekly"]
    weekdays: list[Weekday] = Field(min_length=1, max_length=7)
    cycle_weeks: list[CycleWeek] | None = Field(
        default=None, max_length=MAX_CYCLE_WEEKS, description="Недели цикла; null — каждую"
    )

    @model_validator(mode="after")
    def _norm(self) -> Self:
        self.weekdays = sorted(set(self.weekdays))
        if self.cycle_weeks is not None:
            self.cycle_weeks = sorted(set(self.cycle_weeks)) or None
        return self


class DayCyclePatternIn(InputModel):
    kind: Literal["day_cycle"]
    on: int = Field(ge=1, le=MAX_DAY_CYCLE, description="Рабочих дней подряд")
    off: int = Field(ge=0, le=MAX_DAY_CYCLE, description="Дней перерыва")
    anchor: SaneDate = Field(description="Первый рабочий день цикла")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.on + self.off > MAX_DAY_CYCLE:
            raise ValueError("Цикл смен — не длиннее года")
        return self


class RRulePatternIn(InputModel):
    kind: Literal["rrule"]
    rrule: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]

    @field_validator("rrule")
    @classmethod
    def _check(cls, value: str) -> str:
        parse_rrule(value)
        return value.removeprefix("RRULE:")


class OncePatternIn(InputModel):
    kind: Literal["once"]
    date: SaneDate


PatternIn = Annotated[
    WeeklyPatternIn | DayCyclePatternIn | RRulePatternIn | OncePatternIn,
    Field(discriminator="kind"),
]


class ScheduleRuleCreate(InputModel):
    event_type_id: uuid.UUID
    area_id: uuid.UUID | None = None
    period_id: uuid.UUID | None = Field(default=None, description="null — без периода (90 дней)")
    slot_grid_id: uuid.UUID | None = Field(default=None, description="Общая строка сетки")
    pattern: PatternIn
    start_time: WallTime | None = Field(default=None, description="Своё время вместо слотов")
    end_time: WallTime | None = Field(default=None, description="<= start_time — через полночь")
    slot_from: SlotNumber | None = None
    slot_to: SlotNumber | None = None
    valid_from: SaneDate | None = None
    valid_to: SaneDate | None = None
    title: Title | None = Field(default=None, description="null — название сферы или типа")
    location: ShortText | None = None
    color: HexColor | None = None
    fields: FieldValues = Field(default_factory=dict)
    note: Note = ""

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("Укажите и начало, и конец")
        if self.start_time is not None and self.start_time == self.end_time:
            raise ValueError("Конец должен отличаться от начала")
        if self.start_time is None and self.slot_from is None:
            raise ValueError("Укажите время или слоты")
        if self.start_time is None and self.slot_grid_id is None:
            raise ValueError("Для слотов нужна сетка")
        if self.slot_to is not None and (self.slot_from is None or self.slot_to < self.slot_from):
            raise ValueError("Последний слот раньше первого")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("«Действует до» раньше «действует с»")
        weekly = isinstance(self.pattern, WeeklyPatternIn)
        if weekly and self.pattern.cycle_weeks and self.period_id is None:  # type: ignore[union-attr]
            raise ValueError("Недели цикла задаются только в периоде")
        return self


class ScheduleRuleUpdate(InputModel):
    event_type_id: uuid.UUID | None = None
    area_id: uuid.UUID | None = None
    period_id: uuid.UUID | None = None
    slot_grid_id: uuid.UUID | None = None
    pattern: PatternIn | None = None
    start_time: WallTime | None = None
    end_time: WallTime | None = None
    slot_from: SlotNumber | None = None
    slot_to: SlotNumber | None = None
    valid_from: SaneDate | None = None
    valid_to: SaneDate | None = None
    title: Title | None = None
    location: ShortText | None = None
    color: HexColor | None = None
    fields: FieldValues | None = None
    note: Note | None = None


class ScheduleRuleRead(ReadModel):
    id: uuid.UUID
    event_type_id: uuid.UUID
    area_id: uuid.UUID | None
    period_id: uuid.UUID | None
    slot_grid_id: uuid.UUID | None
    pattern: WeeklyPatternIn | DayCyclePatternIn | RRulePatternIn | OncePatternIn = Field(
        discriminator="kind"
    )
    start_time: WallTime | None
    end_time: WallTime | None
    slot_from: int | None
    slot_to: int | None
    valid_from: date | None
    valid_to: date | None
    title: str | None
    location: str | None
    color: str | None
    fields: dict[str, Any]
    note: str
