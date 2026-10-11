"""Справочники: категории, типы действий, типы задач + сид дефолтов из ТЗ §4.8.

Категории и типы действий засеваются один раз (при первом обращении); свои типы
действий пользователь добавляет и удаляет сам. Типы задач не засеваются: у
пользователей Part 1 их создала миграция, пустой справочник — нормальное состояние.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import TaskTypeHint
from app.core.exceptions import ConflictError, InvalidDataError
from app.core.time import now_utc
from app.domain.enums import ActionTypeKey, CategoryIcon, CategoryKey, TaskTypeKey
from app.models import (
    ActionType,
    BacklogItem,
    BreakdownTemplate,
    Category,
    LoadBudgetMember,
    Project,
    Subtask,
    Task,
    TaskType,
    User,
)
from app.schemas.catalog import (
    ActionTypeCreate,
    ActionTypeUpdate,
    CategoryCreate,
    CategoryUpdate,
    TaskTypeCreate,
    TaskTypeUpdate,
)
from app.services.base import UserScopedRepository
from app.services.calibration import recalibrate
from app.services.settings import effective_settings


@dataclass(frozen=True)
class DefaultCategory:
    key: CategoryKey
    name: str
    color: str
    icon: CategoryIcon


@dataclass(frozen=True)
class DefaultActionType:
    key: ActionTypeKey
    name: str
    category: CategoryKey
    windows: list[dict[str, Any]]
    prefer_morning: bool = False


# Тип действия по умолчанию у засеянного справочника
DEFAULT_ACTION_TYPE_KEY = ActionTypeKey.study

WEEKDAYS = [1, 2, 3, 4, 5]
ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]


def _w(days: list[int], start: str, end: str) -> dict[str, Any]:
    return {"weekdays": days, "start": start, "end": end}


DEFAULT_CATEGORIES = [
    DefaultCategory(CategoryKey.study, "Учёба", "#3b82f6", CategoryIcon.graduation_cap),
    DefaultCategory(CategoryKey.work, "Работа", "#8b5cf6", CategoryIcon.briefcase),
    DefaultCategory(CategoryKey.home, "Быт", "#f59e0b", CategoryIcon.house),
    DefaultCategory(CategoryKey.personal, "Личное", "#ec4899", CategoryIcon.heart),
]

DEFAULT_ACTION_TYPES = [
    DefaultActionType(
        ActionTypeKey.people,
        "Связь с людьми",
        CategoryKey.study,
        [_w(WEEKDAYS, "09:00", "19:00")],
        prefer_morning=True,
    ),
    DefaultActionType(
        ActionTypeKey.institutions,
        "Учреждения",
        CategoryKey.home,
        [_w(WEEKDAYS, "10:00", "18:00")],
    ),
    # Любое время, кроме сна (его вычитает планировщик); ночью — до 01:00
    DefaultActionType(
        ActionTypeKey.study,
        "Самостоятельная учёба",
        CategoryKey.study,
        [_w(ALL_DAYS, "07:00", "01:00")],
    ),
    DefaultActionType(
        ActionTypeKey.outside, "Вне дома", CategoryKey.home, [_w(ALL_DAYS, "09:00", "21:00")]
    ),
    DefaultActionType(
        ActionTypeKey.home, "Домашние дела", CategoryKey.home, [_w(ALL_DAYS, "08:00", "22:00")]
    ),
    DefaultActionType(
        ActionTypeKey.personal,
        "Личное",
        CategoryKey.personal,
        [_w(WEEKDAYS, "18:00", "23:00"), _w([6, 7], "10:00", "23:00")],
    ),
]

DEFAULT_ACTION_TYPE_BY_KEY = {d.key: d for d in DEFAULT_ACTION_TYPES}

# Словари быстрого ввода Part 1 по ключам сида (до M21.1, где их заменят синонимы
# справочников). Сервис переводит ключи в id типов пользователя (`parse_words`).
TASK_TYPE_WORDS: list[tuple[TaskTypeKey, str]] = [
    (TaskTypeKey.exam_prep, r"подготов[а-я]*\s+к\s+(?:экзамен|зачет|коллоквиум|контрольн)[а-я]*"),
    (TaskTypeKey.exam_prep, r"(?:экзамен|зачет|коллоквиум|контрольн)[а-я]*"),
    (TaskTypeKey.essay, r"реферат[а-я]*|эссе"),
    (TaskTypeKey.report, r"доклад[а-я]*|презентаци[а-я]*|выступлени[а-я]*"),
    (TaskTypeKey.coursework, r"курсов(?:ая|ую|ой)|курсач[а-я]*"),
    (TaskTypeKey.lab, r"лаб[а-я]*|практикум[а-я]*"),
    (TaskTypeKey.homework, r"дз|домашк[а-я]*|домашн[а-я]*\s+задани[а-я]*|упражнени[а-я]*"),
    (TaskTypeKey.reading, r"(?:про|до)?чит[а-я]*|прочест[а-я]*|глав[а-я]*"),
]

# Порядок важен: первое совпадение побеждает
ACTION_TYPE_WORDS: list[tuple[ActionTypeKey, str]] = [
    (
        ActionTypeKey.institutions,
        r"деканат[а-я]*|библиотек[а-я]*|врач[а-я]*|стоматолог[а-я]*|поликлиник[а-я]*|"
        r"больниц[а-я]*|мфц|банк[а-я]*|паспорт[а-я]*|справк[а-я]*|военкомат[а-я]*|"
        r"налогов[а-я]*|нотариус[а-я]*|записаться|запись",
    ),
    (
        ActionTypeKey.people,
        r"научрук[а-я]*|руководител[а-я]*|препод[а-я]*|старост[а-я]*|куратор[а-я]*|"
        r"одногруппник[а-я]*|позвонить|созвониться|спросить|договориться|согласовать",
    ),
    (
        ActionTypeKey.outside,
        r"купить|магазин[а-я]*|аптек[а-я]*|посылк[а-я]*|почт[а-я]*|забрать|отнести|"
        r"химчистк[а-я]*|ремонт[а-я]*",
    ),
    (
        ActionTypeKey.home,
        r"убра[а-я]*|уборк[а-я]*|постира[а-я]*|стирк[а-я]*|приготовить|готовк[а-я]*|"
        r"помыть|пропылесосить|разобрать|погладить|полить|вынести",
    ),
    (
        ActionTypeKey.personal,
        r"спорт[а-я]*|зал|бассейн[а-я]*|йог[а-я]*|пробежк[а-я]*|кино|прогулк[а-я]*|"
        r"погулять|подруг[а-я]*|друз[а-я]*|день\s+рождения",
    ),
]


@dataclass(frozen=True)
class ParseWords:
    """Словари быстрого ввода пользователя: (id типа, regex слов)."""

    task: list[tuple[uuid.UUID, str]]
    action: list[tuple[uuid.UUID, str]]


async def parse_words(db: AsyncSession, user_id: uuid.UUID) -> ParseWords:
    """Ключи словарей сида → id типов пользователя (у своих и удалённых слов нет)."""

    async def ids(model: type[ActionType] | type[TaskType]) -> dict[str, uuid.UUID]:
        rows = await db.execute(
            select(model.key, model.id).where(
                model.user_id == user_id, model.deleted_at.is_(None), model.key.is_not(None)
            )
        )
        return {key: id for key, id in rows.all() if key}

    tasks, actions = await ids(TaskType), await ids(ActionType)
    return ParseWords(
        [(tasks[k], pattern) for k, pattern in TASK_TYPE_WORDS if k in tasks],
        [(actions[k], pattern) for k, pattern in ACTION_TYPE_WORDS if k in actions],
    )


async def ensure_defaults(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Засевает системные категории и типы действий, если у пользователя ещё не было ни
    одного типа действия (удалённые тоже считаются: удалённое не возвращается). Тип по
    умолчанию в настройках — «Самостоятельная учёба». Идемпотентно и безопасно при
    параллельных запросах (ON CONFLICT DO NOTHING). Не коммитит.

    Возвращает True, если что-то добавлено.
    """
    seeded = await db.scalar(select(ActionType.id).where(ActionType.user_id == user_id).limit(1))
    if seeded is not None:
        return False

    await db.execute(
        insert(Category)
        .values(
            [
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "key": d.key,
                    "name": d.name,
                    "color": d.color,
                    "icon": d.icon,
                    "position": i,
                }
                for i, d in enumerate(DEFAULT_CATEGORIES)
            ]
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "key"],
            index_where=Category.deleted_at.is_(None) & Category.key.is_not(None),
        )
    )
    rows = await db.execute(
        select(Category.key, Category.id).where(
            Category.user_id == user_id,
            Category.deleted_at.is_(None),
            Category.key.is_not(None),
        )
    )
    category_ids: dict[str | None, uuid.UUID] = {key: id for key, id in rows.all()}
    await db.execute(
        insert(ActionType)
        .values(
            [
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "key": d.key,
                    "name": d.name,
                    "default_category_id": category_ids.get(d.category),
                    "windows": d.windows,
                    "prefer_morning": d.prefer_morning,
                    "position": i,
                }
                for i, d in enumerate(DEFAULT_ACTION_TYPES)
            ]
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "key"],
            index_where=ActionType.deleted_at.is_(None) & ActionType.key.is_not(None),
        )
    )
    default_id = await db.scalar(
        select(ActionType.id).where(
            ActionType.user_id == user_id,
            ActionType.deleted_at.is_(None),
            ActionType.key == DEFAULT_ACTION_TYPE_KEY,
        )
    )
    if default_id is not None:
        await db.execute(
            text(
                "UPDATE users SET settings = jsonb_set(COALESCE(settings, '{}'::jsonb), "
                "'{default_action_type_id}', to_jsonb(CAST(:type_id AS text))) "
                "WHERE id = :user_id "
                "AND NOT (COALESCE(settings, '{}'::jsonb) ? 'default_action_type_id')"
            ),
            {"type_id": str(default_id), "user_id": user_id},
        )
    return True


async def default_action_type(db: AsyncSession, user: User) -> ActionType | None:
    """Тип действия задач и дел без своего типа (`settings.default_action_type_id`).

    Засевает справочник, если его ещё не было. None — тип по умолчанию не выбран.
    """
    if await ensure_defaults(db, user.id):
        await db.flush()
        await db.refresh(user, ["settings"])
    type_id = effective_settings(user).default_action_type_id
    if type_id is None:
        return None
    return await db.scalar(
        select(ActionType).where(
            ActionType.id == type_id,
            ActionType.user_id == user.id,
            ActionType.deleted_at.is_(None),
        )
    )


@dataclass
class TaskTypes:
    """Типы задач пользователя для ИИ, быстрого ввода и подписей."""

    items: list[TaskType] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.by_id = {t.id: t for t in self.items}
        self.by_name = {t.name: t.id for t in self.items}
        # Словарь быстрого ввода Part 1 отдаёт ключи сида (до M21.1)
        self.by_key = {t.key: t.id for t in self.items if t.key}

    def names(self) -> list[str]:
        return list(self.by_name)

    def hints(self) -> list[TaskTypeHint]:
        return [TaskTypeHint(t.name, tuple(t.synonyms)) for t in self.items]

    def name_of(self, id: uuid.UUID | None) -> str | None:
        t = self.by_id.get(id) if id else None
        return t.name if t else None

    def id_of(self, name: str | None) -> uuid.UUID | None:
        return self.by_name.get(name) if name else None


async def load_task_types(db: AsyncSession, user_id: uuid.UUID) -> TaskTypes:
    rows = await db.scalars(
        select(TaskType)
        .where(TaskType.user_id == user_id, TaskType.deleted_at.is_(None))
        .order_by(TaskType.position, TaskType.created_at)
    )
    return TaskTypes(list(rows))


class CategoryRepo(UserScopedRepository[Category]):
    model = Category
    not_found_message = "Категория не найдена"


class ActionTypeRepo(UserScopedRepository[ActionType]):
    model = ActionType
    not_found_message = "Тип действия не найден"


class TaskTypeRepo(UserScopedRepository[TaskType]):
    model = TaskType
    not_found_message = "Тип задачи не найден"


class _ProjectRepo(UserScopedRepository[Project]):
    model = Project
    not_found_message = "Проект не найден"


class _TemplateRepo(UserScopedRepository[BreakdownTemplate]):
    model = BreakdownTemplate
    not_found_message = "Шаблон не найден"


class SystemCategoryError(ConflictError):
    code = "system_category"
    message = "Системную категорию нельзя удалить — её можно переименовать"


class CatalogService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.categories = CategoryRepo(db, user.id)
        self.action_types = ActionTypeRepo(db, user.id)
        self.task_types = TaskTypeRepo(db, user.id)
        self.projects = _ProjectRepo(db, user.id)
        self.templates = _TemplateRepo(db, user.id)

    async def _ensure(self) -> None:
        if await ensure_defaults(self.db, self.user_id):
            await self.db.commit()

    # ---------- категории ----------

    async def list_categories(self) -> list[Category]:
        await self._ensure()
        return await self.categories.find_all(order_by=[Category.position, Category.created_at])

    async def create_category(self, data: CategoryCreate) -> Category:
        last = await self.db.scalar(
            select(func.max(Category.position)).where(
                Category.user_id == self.user_id, Category.deleted_at.is_(None)
            )
        )
        category = Category(
            key=None,
            name=data.name,
            color=data.color,
            icon=data.icon,
            position=(last or 0) + 1,
        )
        self.categories.add(category)
        await self.db.commit()
        return category

    async def update_category(self, id: uuid.UUID, patch: CategoryUpdate) -> Category:
        category = await self.categories.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name, value in changes.items():
            if value is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
            setattr(category, name, value)
        await self.db.commit()
        return category

    async def delete_category(self, id: uuid.UUID) -> None:
        """Своя категория удаляется; дела с ней остаются без категории."""
        category = await self.categories.get_or_404(id)
        if category.key is not None:
            raise SystemCategoryError()
        self.categories.soft_delete(category)
        for owner in (ActionType, TaskType):
            await self.db.execute(
                update(owner)
                .where(owner.user_id == self.user_id, owner.default_category_id == id)
                .values(default_category_id=None)
            )
        for model in CATEGORY_USERS:
            await self.db.execute(
                update(model)
                .where(model.user_id == self.user_id, model.category_id == id)
                .values(category_id=None)
            )
        await self.db.commit()

    # ---------- типы действий ----------

    async def list_action_types(self) -> list[ActionType]:
        await self._ensure()
        return await self.action_types.find_all(
            order_by=[ActionType.position, ActionType.created_at]
        )

    async def _next_position(self, model: type[ActionType] | type[TaskType]) -> int:
        last = await self.db.scalar(
            select(func.max(model.position)).where(
                model.user_id == self.user_id, model.deleted_at.is_(None)
            )
        )
        return (last if last is not None else -1) + 1

    async def create_action_type(self, data: ActionTypeCreate) -> ActionType:
        if await ensure_defaults(self.db, self.user_id):
            await self.db.flush()
        if data.default_category_id:
            await self.categories.get_or_404(data.default_category_id)
        action_type = ActionType(
            key=None,
            name=data.name,
            windows=data.model_dump(mode="json")["windows"],
            default_category_id=data.default_category_id,
            prefer_morning=data.prefer_morning,
            position=await self._next_position(ActionType),
        )
        self.action_types.add(action_type)
        await self.db.commit()
        return action_type

    async def update_action_type(self, id: uuid.UUID, patch: ActionTypeUpdate) -> ActionType:
        action_type = await self.action_types.get_or_404(id)
        changes = patch.model_dump(mode="json", exclude_unset=True)
        for name in ("name", "windows", "prefer_morning", "position"):
            if name in changes and changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if category_id := patch.default_category_id:
            await self.categories.get_or_404(category_id)
            changes["default_category_id"] = category_id
        for name, value in changes.items():
            setattr(action_type, name, value)
        await self.db.commit()
        return action_type

    async def delete_action_type(self, id: uuid.UUID) -> None:
        """Дела с этим типом получают тип по умолчанию; удалили сам тип по умолчанию —
        его больше нет (дела остаются без типа). Из лимитов тип выходит."""
        action_type = await self.action_types.get_or_404(id)
        default_id = effective_settings(self.user).default_action_type_id
        replacement = None if default_id == id else default_id
        if default_id == id:
            overrides = dict(self.user.settings or {})
            overrides.pop("default_action_type_id", None)
            self.user.settings = overrides
        for model in (Task, Subtask, BacklogItem):
            await self.db.execute(
                update(model)
                .where(model.user_id == self.user_id, model.action_type_id == id)
                .values(action_type_id=replacement)
            )
        await self.db.execute(
            update(BacklogItem)
            .where(BacklogItem.user_id == self.user_id, BacklogItem.hours_action_type_id == id)
            .values(hours_action_type_id=None)
        )
        await self.db.execute(
            update(TaskType)
            .where(TaskType.user_id == self.user_id, TaskType.default_action_type_id == id)
            .values(default_action_type_id=None)
        )
        for member in await self.db.scalars(
            select(LoadBudgetMember).where(
                LoadBudgetMember.user_id == self.user_id,
                LoadBudgetMember.deleted_at.is_(None),
                LoadBudgetMember.action_type_id == id,
            )
        ):
            member.deleted_at = now_utc()
        self.action_types.soft_delete(action_type)
        await recalibrate(self.db, self.user_id)
        await self.db.commit()

    async def reset_action_type(self, id: uuid.UUID) -> ActionType:
        """Вернуть название, окна, утро и категорию по умолчанию (только у засеянных)."""
        action_type = await self.action_types.get_or_404(id)
        if action_type.key is None:
            raise InvalidDataError("У своего типа нет значений по умолчанию")
        default = DEFAULT_ACTION_TYPE_BY_KEY[ActionTypeKey(action_type.key)]
        category = await self.db.scalar(
            self.categories.select().where(Category.key == default.category)
        )
        action_type.name = default.name
        action_type.windows = default.windows
        action_type.prefer_morning = default.prefer_morning
        action_type.default_category_id = category.id if category else None
        await self.db.commit()
        return action_type

    # ---------- типы задач ----------

    async def list_task_types(self) -> list[TaskType]:
        return await self.task_types.find_all(order_by=[TaskType.position, TaskType.created_at])

    async def _check_task_type_refs(self, data: dict[str, Any]) -> None:
        if data.get("default_action_type_id"):
            await self.action_types.get_or_404(data["default_action_type_id"])
        if data.get("default_category_id"):
            await self.categories.get_or_404(data["default_category_id"])
        if data.get("default_project_id"):
            await self.projects.get_or_404(data["default_project_id"])
        if data.get("default_template_id"):
            await self.templates.get_or_404(data["default_template_id"])

    async def create_task_type(self, data: TaskTypeCreate) -> TaskType:
        fields = data.model_dump()
        await self._check_task_type_refs(fields)
        fields["deadline_rule"] = data.model_dump(mode="json")["deadline_rule"]
        task_type = TaskType(key=None, position=await self._next_position(TaskType), **fields)
        self.task_types.add(task_type)
        await self.db.commit()
        return task_type

    async def update_task_type(self, id: uuid.UUID, patch: TaskTypeUpdate) -> TaskType:
        task_type = await self.task_types.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name in ("name", "icon", "synonyms", "position"):
            if name in changes and changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        await self._check_task_type_refs(changes)
        if "deadline_rule" in changes:
            changes["deadline_rule"] = patch.model_dump(mode="json")["deadline_rule"]
        for name, value in changes.items():
            setattr(task_type, name, value)
        await self.db.commit()
        return task_type

    async def delete_task_type(self, id: uuid.UUID) -> None:
        """Задачи и шаблоны этого типа остаются — без типа."""
        task_type = await self.task_types.get_or_404(id)
        for model in (Task, BreakdownTemplate):
            await self.db.execute(
                update(model)
                .where(model.user_id == self.user_id, model.task_type_id == id)
                .values(task_type_id=None)
            )
        self.task_types.soft_delete(task_type)
        await recalibrate(self.db, self.user_id)
        await self.db.commit()


# Модели с полем category_id: при удалении категории ссылки обнуляются
CATEGORY_USERS: tuple[Any, ...] = (Task, Subtask, BacklogItem, Project)
