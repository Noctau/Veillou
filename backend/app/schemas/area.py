"""Сферы, типы сфер и описания полей (Part 2, M16.2)."""

import uuid
from typing import Annotated, Any

from pydantic import Field, StringConstraints, field_validator

from app.domain.enums import AreaSection, CategoryIcon, FieldType
from app.domain.fields import FIELDS_MAX, LABEL_MAX, OPTION_MAX, OPTIONS_MAX, FieldDef
from app.schemas.common import HexColor, InputModel, ReadModel, UTCMoment

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
TypeName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ShortName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
Synonym = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Option = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=OPTION_MAX)
]


# ---------- поля ----------


class FieldDefIn(InputModel):
    """Поле типа. Без `id` (или с незнакомым) — новое поле; id выдаёт сервер.
    Поле, которого нет в новом списке, считается удалённым: значения сфер остаются."""

    id: str | None = Field(default=None, max_length=40)
    label: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LABEL_MAX)
    ]
    type: FieldType
    options: list[Option] = Field(
        default_factory=list, max_length=OPTIONS_MAX, description="Для select / multiselect"
    )
    multiple: bool = Field(
        default=False, description="Много значений: text, contact, link, area_ref"
    )
    show_in_reminder: bool = False
    required: bool = False

    def to_def(self) -> FieldDef:
        return FieldDef(
            id=self.id or "",
            label=self.label,
            type=self.type,
            options=tuple(self.options),
            multiple=self.multiple,
            show_in_reminder=self.show_in_reminder,
            required=self.required,
        )


class FieldDefRead(ReadModel):
    id: str
    label: str
    type: FieldType
    options: list[str]
    multiple: bool
    show_in_reminder: bool
    required: bool


FieldDefs = Annotated[list[FieldDefIn], Field(max_length=FIELDS_MAX)]


# ---------- типы сфер ----------


def _unique_sections(value: list[AreaSection] | None) -> list[AreaSection] | None:
    return list(dict.fromkeys(value)) if value is not None else None


class AreaTypeCreate(InputModel):
    name: TypeName = Field(description="В единственном числе: «Ученик»")
    name_plural: TypeName = Field(description="Во множественном: «Ученики»")
    icon: CategoryIcon = CategoryIcon.tag
    color: HexColor = "#3b82f6"
    fields: FieldDefs = Field(default_factory=list)
    sections: list[AreaSection] = Field(
        default_factory=lambda: [AreaSection.schedule, AreaSection.tasks, AreaSection.notes],
        description="Разделы страницы сферы по порядку",
    )

    _sections = field_validator("sections")(_unique_sections)


class AreaTypeUpdate(InputModel):
    name: TypeName | None = None
    name_plural: TypeName | None = None
    icon: CategoryIcon | None = None
    color: HexColor | None = None
    fields: FieldDefs | None = Field(default=None, description="Полный список полей")
    sections: list[AreaSection] | None = None
    position: int | None = Field(default=None, ge=0, le=1000)

    _sections = field_validator("sections")(_unique_sections)


class AreaTypeRead(ReadModel):
    id: uuid.UUID
    key: str | None = Field(description="Ключ сида/миграции; у своих типов — null")
    name: str
    name_plural: str
    icon: CategoryIcon
    color: str
    fields: list[FieldDefRead] = Field(description="Живые поля (удалённые не показываются)")
    sections: list[AreaSection]
    position: int

    @field_validator("fields", mode="before")
    @classmethod
    def _live(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [f for f in value if not (isinstance(f, dict) and f.get("deleted"))]
        return value


# ---------- сферы ----------

Synonyms = Annotated[list[Synonym], Field(max_length=30)]
FieldValues = Annotated[dict[str, Any], Field(description="Значения полей типа: {field_id: value}")]


class AreaCreate(InputModel):
    area_type_id: uuid.UUID
    period_id: uuid.UUID | None = Field(default=None, description="Период; null — всегда")
    name: Name
    short_name: ShortName | None = None
    color: HexColor = "#3b82f6"
    synonyms: Synonyms = Field(default_factory=list)
    fields: FieldValues = Field(default_factory=dict)
    notes: str = Field(default="", max_length=10_000)


class AreaUpdate(InputModel):
    period_id: uuid.UUID | None = None
    name: Name | None = None
    short_name: ShortName | None = None
    color: HexColor | None = None
    synonyms: Synonyms | None = None
    fields: FieldValues | None = Field(default=None, description="Все значения полей разом")
    notes: str | None = Field(default=None, max_length=10_000)
    archived: bool | None = Field(default=None, description="В архив / из архива")


class AreaRead(ReadModel):
    id: uuid.UUID
    area_type_id: uuid.UUID
    period_id: uuid.UUID | None
    name: str
    short_name: str | None
    color: str
    synonyms: list[str]
    fields: dict[str, Any]
    notes: str
    archived_at: UTCMoment | None
