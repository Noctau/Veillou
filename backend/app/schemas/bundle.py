"""Сборка (`ConfigBundle`, M21.3): вся конфигурация пользователя одним JSON.

Кирпичи ссылаются друг на друга локальными строками `ref` (уникальны в своём
разделе), а не UUID: сборку можно перенести другому пользователю, отдать ИИ на
правку или хранить как стартовую. Порядок элементов раздела — порядок в интерфейсе.

Форма полей — как у `*Create` соответствующих API; при импорте каждый кирпич
проверяется той же схемой `*Create` (с подставленными id), так что правила
валидации одни. Задачи, события, заметки и прочие данные в сборку не входят.
"""

from typing import Annotated, Any, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from app.domain.enums import AreaSection, CategoryIcon, DayRuleKind, EventRuleWhen
from app.schemas.area import FieldDefIn, FieldValues, ShortName, Synonyms
from app.schemas.area import Name as AreaName
from app.schemas.area import TypeName as AreaTypeName
from app.schemas.catalog import CatalogName, DeadlineRule, Synonym, TimeWindow
from app.schemas.common import HexColor, InputModel, ReadModel, SaneDate, WallTime, Weekday
from app.schemas.day_profile import Lunch, Span
from app.schemas.schedule import (
    BufferMin,
    LocationLabel,
    Note,
    PatternIn,
    Pause,
    RemindMin,
    ShortText,
    SlotGridDay,
    SlotNumber,
    Title,
)
from app.schemas.schedule import Name as ScheduleName
from app.schemas.settings import Channel

BUNDLE_VERSION = 1
MAX_ITEMS = 200

Ref = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    Field(description="Локальная ссылка внутри сборки (уникальна в разделе)"),
]
OptRef = Ref | None
Items: Any = Field(default_factory=list, max_length=MAX_ITEMS)


class _Item(InputModel):
    ref: Ref


class BundleCategory(_Item):
    name: CatalogName
    color: HexColor
    icon: CategoryIcon = CategoryIcon.tag


class BundleActionType(_Item):
    name: CatalogName
    windows: list[TimeWindow] = Field(min_length=1, max_length=14)
    category: OptRef = None
    prefer_morning: bool = False
    synonyms: list[Synonym] = Field(default_factory=list, max_length=30)


class BundleTaskType(_Item):
    name: CatalogName
    icon: CategoryIcon = CategoryIcon.tag
    synonyms: list[Synonym] = Field(default_factory=list, max_length=30)
    action_type: OptRef = None
    category: OptRef = None
    default_estimate_min: int | None = Field(default=None, ge=5, le=10_000)
    deadline_rule: DeadlineRule | None = None


class BundleAreaType(_Item):
    name: AreaTypeName
    name_plural: AreaTypeName
    icon: CategoryIcon = CategoryIcon.tag
    color: HexColor = "#3b82f6"
    fields: list[FieldDefIn] = Field(default_factory=list, max_length=30)
    sections: list[AreaSection] = Field(
        default_factory=lambda: [AreaSection.schedule, AreaSection.tasks, AreaSection.notes]
    )


class BundlePeriod(_Item):
    name: ScheduleName
    start_date: SaneDate
    end_date: SaneDate
    cycle_weeks: int = Field(default=1, ge=1, le=8)
    first_cycle_week: int = Field(default=1, ge=1, le=8)
    pauses: list[Pause] = Field(default_factory=list, max_length=20)


class BundleDayOff(_Item):
    period: OptRef = None
    date_from: SaneDate
    date_to: SaneDate
    title: ShortText = ""


class BundleSlotGrid(_Item):
    period: OptRef = None
    name: ScheduleName
    schedules: list[SlotGridDay] = Field(max_length=8)


class BundleArea(_Item):
    area_type: Ref
    period: OptRef = None
    name: AreaName
    short_name: ShortName | None = None
    color: HexColor = "#3b82f6"
    synonyms: Synonyms = Field(default_factory=list)
    fields: FieldValues = Field(default_factory=dict)
    notes: str = Field(default="", max_length=10_000)


class BundleEventType(_Item):
    name: ScheduleName
    name_plural: ScheduleName | None = None
    icon: CategoryIcon = CategoryIcon.calendar
    color: HexColor = "#64748b"
    buffer_before_min: BufferMin = 0
    buffer_after_min: BufferMin = 0
    merge_buffers: bool = False
    remind_before_min: RemindMin | None = None
    remind_channels: list[Channel] = Field(
        default_factory=lambda: [Channel.push, Channel.telegram], max_length=len(Channel)
    )
    show_now_next: bool = False
    is_rest: bool = False
    supports_prep: bool = False
    location_label: LocationLabel = ""
    default_area_type: OptRef = None
    fields: list[FieldDefIn] = Field(default_factory=list, max_length=30)
    synonyms: list[Synonym] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def _plural(self) -> Self:
        self.name_plural = self.name_plural or self.name
        return self


class BundleDayProfile(_Item):
    name: CatalogName
    wake: WallTime
    sleep: WallTime
    lunch: Lunch | None = None
    work_windows: list[Span] = Field(default_factory=list, max_length=6)
    rest_evening_ok: bool = True
    rest_halfday_ok: bool = False
    quiet_follows_sleep: bool = True


class BundleDayProfileRule(_Item):
    profile: Ref
    kind: DayRuleKind
    date_from: SaneDate | None = None
    date_to: SaneDate | None = None
    event_type: OptRef = None
    weekdays: list[Weekday] = Field(default_factory=list, max_length=7)


class BundleBudget(_Item):
    name: CatalogName
    minutes_per_day: int = Field(ge=15, le=1440)
    action_types: list[Ref] = Field(default_factory=list, max_length=50)
    event_types: list[Ref] = Field(default_factory=list, max_length=50)


class BundleScheduleRule(_Item):
    event_type: Ref
    area: OptRef = None
    period: OptRef = None
    slot_grid: OptRef = None
    pattern: PatternIn
    start_time: WallTime | None = None
    end_time: WallTime | None = None
    slot_from: SlotNumber | None = None
    slot_to: SlotNumber | None = None
    valid_from: SaneDate | None = None
    valid_to: SaneDate | None = None
    title: Title | None = None
    location: ShortText | None = None
    color: HexColor | None = None
    fields: FieldValues = Field(default_factory=dict)
    note: Note = ""


class BundleEventRule(_Item):
    event_type: OptRef = None
    schedule_rule: OptRef = None
    when: EventRuleWhen = EventRuleWhen.before
    title_template: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    estimate_min: int = Field(default=30, ge=5, le=24 * 60)
    action_type: OptRef = None
    task_type: OptRef = None
    offset_min: int = Field(default=0, ge=0, le=60 * 24 * 14)
    within_days: int | None = Field(default=None, ge=0, le=60)
    until_next: bool = False
    confirm: bool = False


class BundleSettings(InputModel):
    default_action_type: OptRef = Field(
        default=None, description="Тип действия по умолчанию для задач и дел"
    )


class ConfigBundle(InputModel):
    """Конфигурация целиком. Разделы — в порядке зависимостей при импорте."""

    version: Literal[1] = 1
    categories: list[BundleCategory] = Items
    action_types: list[BundleActionType] = Items
    task_types: list[BundleTaskType] = Items
    area_types: list[BundleAreaType] = Items
    periods: list[BundlePeriod] = Items
    days_off: list[BundleDayOff] = Items
    slot_grids: list[BundleSlotGrid] = Items
    areas: list[BundleArea] = Items
    event_types: list[BundleEventType] = Items
    budgets: list[BundleBudget] = Items
    day_profiles: list[BundleDayProfile] = Items
    day_profile_rules: list[BundleDayProfileRule] = Items
    schedule_rules: list[BundleScheduleRule] = Items
    event_rules: list[BundleEventRule] = Items
    settings: BundleSettings = Field(default_factory=BundleSettings)


# ---------- результат импорта ----------


class BundleChange(ReadModel):
    section: str
    ref: str
    name: str = Field(description="Как показать человеку: название кирпича")
    fields: list[str] = Field(default_factory=list, description="changed: какие поля другие")


class BundleImportResult(ReadModel):
    """Что добавится / изменится / уже есть. dry_run — ничего не записано."""

    dry_run: bool
    added: list[BundleChange]
    changed: list[BundleChange]
    skipped: list[BundleChange]


def bundle_json(bundle: ConfigBundle) -> dict[str, Any]:
    return bundle.model_dump(mode="json", by_alias=True)
