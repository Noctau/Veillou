"""Семестр, звонки, выходные, предметы, правила пар.

`*Update` — частичные: все поля необязательны. Сервис накладывает их на текущие
значения и валидирует итог через `*Create`, так что межполевые проверки
(начало < конца и т. п.) работают и при PATCH.
"""

import uuid
from datetime import date
from typing import Annotated, Self

from pydantic import Field, HttpUrl, StringConstraints, field_serializer, model_validator

from app.domain.enums import ClassType, ControlForm, Parity, RuleParity
from app.schemas.common import HexColor, InputModel, ReadModel, WallTime, Weekday

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


# ---------- семестр ----------


class SemesterCreate(InputModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    start_date: date
    classes_end: date = Field(description="Последний день занятий")
    session_start: date | None = None
    session_end: date | None = None
    first_week_parity: Parity = Parity.odd

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.classes_end < self.start_date:
            raise ValueError("Конец занятий раньше начала семестра")
        if (self.session_start is None) != (self.session_end is None):
            raise ValueError("Укажите и начало, и конец сессии")
        if self.session_start and self.session_end:
            if self.session_end < self.session_start:
                raise ValueError("Конец сессии раньше начала")
            # Пары генерируются до classes_end включительно — в сессии их быть не должно
            if self.session_start <= self.classes_end:
                raise ValueError("Сессия должна начинаться после последнего дня занятий")
        return self


class SemesterUpdate(InputModel):
    name: str | None = None
    start_date: date | None = None
    classes_end: date | None = None
    session_start: date | None = None
    session_end: date | None = None
    first_week_parity: Parity | None = None


class SemesterRead(ReadModel):
    id: uuid.UUID
    name: str
    start_date: date
    classes_end: date
    session_start: date | None
    session_end: date | None
    first_week_parity: Parity


# ---------- звонки ----------


class BellSlot(InputModel):
    number: int = Field(ge=1, le=12)
    start: WallTime
    end: WallTime

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"Пара {self.number}: конец должен быть позже начала")
        return self


class BellScheduleIn(InputModel):
    weekday: Weekday | None = Field(default=None, description="null — общие звонки")
    slots: list[BellSlot]

    @model_validator(mode="after")
    def _check_slots(self) -> Self:
        numbers = [s.number for s in self.slots]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Номера пар повторяются")
        self.slots.sort(key=lambda s: s.number)
        for prev, cur in zip(self.slots, self.slots[1:], strict=False):
            if cur.start < prev.end:
                raise ValueError(f"Пары {prev.number} и {cur.number} пересекаются")
        return self


class BellsReplace(InputModel):
    """Полный набор звонков семестра: общие + переопределения дней."""

    schedules: list[BellScheduleIn]

    @model_validator(mode="after")
    def _check_unique(self) -> Self:
        days = [s.weekday for s in self.schedules]
        if len(days) != len(set(days)):
            raise ValueError("День недели указан дважды")
        return self


class BellScheduleRead(ReadModel):
    weekday: int | None
    slots: list[BellSlot]


# ---------- выходные ----------


class DayOffCreate(InputModel):
    date_from: date
    date_to: date
    title: ShortText = ""

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.date_to < self.date_from:
            raise ValueError("Конец раньше начала")
        return self


class DayOffUpdate(InputModel):
    date_from: date | None = None
    date_to: date | None = None
    title: str | None = None


class DayOffRead(ReadModel):
    id: uuid.UUID
    date_from: date
    date_to: date
    title: str


# ---------- предметы ----------


class Teacher(InputModel):
    name: Name
    role: ShortText = ""  # лектор, семинарист…
    contact: ShortText = ""


class SubjectLink(InputModel):
    title: ShortText = ""
    url: HttpUrl

    @field_serializer("url")
    def _url(self, url: HttpUrl) -> str:
        return str(url)


class SubjectCreate(InputModel):
    semester_id: uuid.UUID | None = None
    name: Name
    short_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = (
        None
    )
    color: HexColor = "#3b82f6"
    control_form: ControlForm = ControlForm.exam
    teachers: list[Teacher] = Field(default_factory=list)
    links: list[SubjectLink] = Field(default_factory=list)
    synonyms: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = Field(
        default_factory=list
    )
    notes: str = ""


class SubjectUpdate(InputModel):
    semester_id: uuid.UUID | None = None
    name: str | None = None
    short_name: str | None = None
    color: str | None = None
    control_form: ControlForm | None = None
    teachers: list[Teacher] | None = None
    links: list[SubjectLink] | None = None
    synonyms: list[str] | None = None
    notes: str | None = None


class SubjectRead(ReadModel):
    id: uuid.UUID
    semester_id: uuid.UUID | None
    name: str
    short_name: str | None
    color: str
    control_form: ControlForm
    teachers: list[Teacher]
    links: list[SubjectLink]
    synonyms: list[str]
    notes: str


# ---------- правила пар ----------


class ClassRuleCreate(InputModel):
    semester_id: uuid.UUID
    subject_id: uuid.UUID
    weekday: Weekday
    pair_number: int | None = Field(default=None, ge=1, le=12)
    start_time: WallTime | None = Field(default=None, description="Своё время вместо звонков")
    end_time: WallTime | None = None
    parity: RuleParity = RuleParity.all
    class_type: ClassType = ClassType.lecture
    location: ShortText | None = None
    teacher: ShortText | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("Укажите и начало, и конец")
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("Конец должен быть позже начала")
        if self.pair_number is None and self.start_time is None:
            raise ValueError("Укажите номер пары или своё время")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("«Действует до» раньше «действует с»")
        return self


class ClassRuleUpdate(InputModel):
    subject_id: uuid.UUID | None = None
    weekday: Weekday | None = None
    pair_number: int | None = None
    start_time: WallTime | None = None
    end_time: WallTime | None = None
    parity: RuleParity | None = None
    class_type: ClassType | None = None
    location: str | None = None
    teacher: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class ClassRuleRead(ReadModel):
    id: uuid.UUID
    semester_id: uuid.UUID
    subject_id: uuid.UUID
    weekday: int
    pair_number: int | None
    start_time: WallTime | None
    end_time: WallTime | None
    parity: RuleParity
    class_type: ClassType
    location: str | None
    teacher: str | None
    valid_from: date | None
    valid_to: date | None
