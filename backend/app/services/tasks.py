"""Задания и подзадачи: CRUD, прогресс, зависимости, ручная постановка в календарь.

Статус подзадачи и её блоков в календаре синхронизирован в обе стороны:
«сделано» на блоке закрывает подзадачу, «сделано» у подзадачи — её блоки.
"""

import uuid
from collections.abc import Iterable, Sequence
from datetime import date, time, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, now_utc, wall_to_utc
from app.domain.enums import (
    ActionTypeKey,
    AttachmentOwner,
    CategoryKey,
    EventKind,
    EventStatus,
    SourceType,
    SubtaskStatus,
    TaskStatus,
)
from app.domain.tasks import find_cycle, progress
from app.models import (
    ActionType,
    Category,
    Event,
    Milestone,
    Project,
    Subject,
    Subtask,
    Task,
    User,
)
from app.schemas.task import (
    SubtaskCreate,
    SubtaskEvent,
    SubtaskRead,
    SubtaskSchedule,
    SubtaskUpdate,
    TaskCreate,
    TaskDetail,
    TaskRead,
    TaskUpdate,
    WorkTaskCreate,
)
from app.services.attachments import delete_for_owners
from app.services.base import UserScopedRepository
from app.services.calibration import recalibrate
from app.services.catalog import ensure_defaults
from app.services.recurring_tasks import ensure_has_occurrences, sync_recurring_task


class TaskRepo(UserScopedRepository[Task]):
    model = Task
    not_found_message = "Задание не найдено"


class SubtaskRepo(UserScopedRepository[Subtask]):
    model = Subtask
    not_found_message = "Подзадача не найдена"


class _EventRepo(UserScopedRepository[Event]):
    model = Event


class _SubjectRepo(UserScopedRepository[Subject]):
    model = Subject
    not_found_message = "Предмет не найден"


class _CategoryRepo(UserScopedRepository[Category]):
    model = Category
    not_found_message = "Категория не найдена"


class _ActionTypeRepo(UserScopedRepository[ActionType]):
    model = ActionType
    not_found_message = "Тип действия не найден"


class _ProjectRepo(UserScopedRepository[Project]):
    model = Project
    not_found_message = "Проект не найден"


class _MilestoneRepo(UserScopedRepository[Milestone]):
    model = Milestone
    not_found_message = "Этап не найден"


WORK_TASK_DAYS = 14
END_OF_DAY = time(23, 59)
# Правка этих полей пересобирает вхождения регулярного задания
RECURRENCE_FIELDS = {"recurrence", "recurrence_start", "title", "estimate_min", "status"}

# Поля, которые нельзя обнулить через PATCH
_TASK_REQUIRED = {"title", "task_type", "description", "priority", "status"}
_SUBTASK_REQUIRED = {"title", "estimate_min", "depends_on", "status", "note"}


def _reject_nulls(changes: dict[str, Any], required: set[str]) -> None:
    for name in required & changes.keys():
        if changes[name] is None:
            raise InvalidDataError(f"{name}: не может быть пустым")


class TaskService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user.id
        self.tasks = TaskRepo(db, user.id)
        self.subtasks = SubtaskRepo(db, user.id)
        self.events = _EventRepo(db, user.id)
        self.subjects = _SubjectRepo(db, user.id)
        self.categories = _CategoryRepo(db, user.id)
        self.action_types = _ActionTypeRepo(db, user.id)
        self.projects = _ProjectRepo(db, user.id)
        self.milestones = _MilestoneRepo(db, user.id)
        self.tz = get_tz(user.timezone)

    # ---------- чтение ----------

    async def _counts(self, task_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        if not task_ids:
            return {}
        rows = await self.db.execute(
            select(
                Subtask.task_id,
                func.count(),
                func.count().filter(Subtask.status == SubtaskStatus.done),
            )
            .where(
                Subtask.user_id == self.user_id,
                Subtask.deleted_at.is_(None),
                Subtask.task_id.in_(task_ids),
            )
            .group_by(Subtask.task_id)
        )
        return {task_id: (total, done) for task_id, total, done in rows.all()}

    @staticmethod
    def _read(task: Task, counts: tuple[int, int] | None) -> TaskRead:
        total, done = counts or (0, 0)
        read = TaskRead.model_validate(task)
        read.subtasks_total = total
        read.subtasks_done = done
        read.progress = progress(done, total, task_done=task.status == TaskStatus.done)
        return read

    async def list_tasks(
        self,
        *,
        statuses: Sequence[TaskStatus] = (),
        subject_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        due_before: Any = None,
    ) -> list[TaskRead]:
        where: list[ColumnElement[bool]] = []
        if statuses:
            where.append(Task.status.in_(statuses))
        if subject_id:
            where.append(Task.subject_id == subject_id)
        if project_id:
            where.append(Task.project_id == project_id)
        if due_before is not None:
            where.append(Task.deadline < due_before)
        tasks = await self.tasks.find_all(
            *where, order_by=[Task.deadline.asc().nulls_last(), Task.created_at]
        )
        counts = await self._counts([t.id for t in tasks])
        return [self._read(t, counts.get(t.id)) for t in tasks]

    async def get_detail(self, id: uuid.UUID) -> TaskDetail:
        task = await self.tasks.get_or_404(id)
        subtasks = await self.subtasks.find_all(
            Subtask.task_id == id,
            order_by=[
                Subtask.position,
                Subtask.occurrence_date.asc().nulls_last(),
                Subtask.created_at,
            ],
        )
        done = sum(s.status == SubtaskStatus.done for s in subtasks)
        events = await self._events_by_subtask([s.id for s in subtasks])
        return TaskDetail(
            **self._read(task, (len(subtasks), done)).model_dump(),
            subtasks=[self._subtask_read(s, events.get(s.id, [])) for s in subtasks],
        )

    async def get_subtask(self, id: uuid.UUID) -> SubtaskRead:
        subtask = await self.subtasks.get_or_404(id)
        events = await self._events_by_subtask([id])
        return self._subtask_read(subtask, events.get(id, []))

    @staticmethod
    def _subtask_read(subtask: Subtask, events: list[Event]) -> SubtaskRead:
        read = SubtaskRead.model_validate(subtask)
        read.events = [SubtaskEvent.model_validate(e) for e in events]
        return read

    async def _subtask_events(
        self, subtask_ids: Iterable[uuid.UUID], *, statuses: Sequence[EventStatus] = ()
    ) -> list[Event]:
        ids = list(subtask_ids)
        if not ids:
            return []
        where = [Event.source_type == SourceType.subtask, Event.source_id.in_(ids)]
        if statuses:
            where.append(Event.status.in_(statuses))
        return await self.events.find_all(*where, order_by=[Event.start])

    async def _events_by_subtask(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Event]]:
        result: dict[uuid.UUID, list[Event]] = {}
        for e in await self._subtask_events(ids):
            if e.status != EventStatus.cancelled and e.source_id:
                result.setdefault(e.source_id, []).append(e)
        return result

    # ---------- ссылки ----------

    async def _check_refs(self, data: dict[str, Any]) -> None:
        if data.get("subject_id"):
            await self.subjects.get_or_404(data["subject_id"])
        if data.get("category_id"):
            await self.categories.get_or_404(data["category_id"])
        if data.get("action_type_id"):
            await self.action_types.get_or_404(data["action_type_id"])
        if data.get("project_id"):
            await self.projects.get_or_404(data["project_id"])

    async def _resolve_milestone(self, fields: dict[str, Any], current: Task | None) -> None:
        """Этап должен быть из проекта задания. Этап без проекта — проект берётся из
        этапа; смена проекта отвязывает этап старого проекта."""
        project_id = fields.get("project_id", current.project_id if current else None)
        if "milestone_id" not in fields:
            if current and current.milestone_id and "project_id" in fields:
                milestone = await self.milestones.get(current.milestone_id)
                if milestone is None or milestone.project_id != project_id:
                    fields["milestone_id"] = None
            return
        if fields["milestone_id"] is None:
            return
        milestone = await self.milestones.get_or_404(fields["milestone_id"])
        if project_id is None:
            fields["project_id"] = milestone.project_id
        elif milestone.project_id != project_id:
            raise InvalidDataError("Этап из другого проекта")

    def _today(self) -> date:
        return now_utc().astimezone(self.tz).date()

    async def _default_action_type(self) -> ActionType | None:
        if await ensure_defaults(self.db, self.user_id):
            await self.db.flush()
        return await self.db.scalar(
            self.action_types.select().where(ActionType.key == ActionTypeKey.study)
        )

    async def _color(self, subtask: Subtask, task: Task) -> str | None:
        category_id = subtask.category_id or task.category_id
        if not category_id:
            return None
        category = await self.categories.get(category_id)
        return category.color if category else None

    # ---------- задания ----------

    async def create(self, data: TaskCreate) -> TaskDetail:
        fields = data.model_dump(exclude={"subtasks"})
        fields["time_window"] = data.model_dump(mode="json")["time_window"]
        if data.recurrence:
            await ensure_has_occurrences(data.recurrence)
        await self._check_refs(fields)
        await self._resolve_milestone(fields, None)

        if fields["category_id"] is None and fields["project_id"]:
            project = await self.projects.get_or_404(fields["project_id"])
            fields["category_id"] = project.category_id
        if fields["recurrence"] and fields["recurrence_start"] is None:
            fields["recurrence_start"] = self._today()

        if fields["action_type_id"] is None:
            default = await self._default_action_type()
            fields["action_type_id"] = default.id if default else None
            if fields["category_id"] is None and default:
                fields["category_id"] = default.default_category_id
        elif fields["category_id"] is None:
            action_type = await self.action_types.get_or_404(fields["action_type_id"])
            fields["category_id"] = action_type.default_category_id

        task = Task(**fields)
        self.tasks.add(task)
        await self.db.flush()
        for i, item in enumerate(data.subtasks):
            if item.depends_on:
                raise InvalidDataError("Зависимости задаются после создания подзадач")
            await self._check_refs(item.model_dump())
            self.subtasks.add(self._new_subtask(task, item, position=i))
        if task.recurrence:
            await sync_recurring_task(self.db, task, self._today())
        await self.db.commit()
        return await self.get_detail(task.id)

    async def create_work_task(self, data: WorkTaskCreate) -> TaskDetail:
        """«Задание с работы»: категория «Работа», дедлайн = выдача + 14 дней (23:59),
        проект — указанный или проект «по умолчанию для заданий с работы»."""
        today = self._today()
        issued = data.issued_at or today
        deadline = data.deadline or wall_to_utc(
            issued + timedelta(days=WORK_TASK_DAYS), END_OF_DAY, self.tz
        )
        project_id = data.project_id
        if project_id is None and not data.no_project:
            project_id = await self.db.scalar(
                select(Project.id).where(
                    Project.user_id == self.user_id,
                    Project.deleted_at.is_(None),
                    Project.is_work_default.is_(True),
                )
            )
        if await ensure_defaults(self.db, self.user_id):
            await self.db.flush()
        work = await self.db.scalar(
            self.categories.select().where(Category.key == CategoryKey.work)
        )
        return await self.create(
            TaskCreate(
                title=data.title,
                description=data.description,
                issued_at=issued,
                deadline=deadline,
                project_id=project_id,
                category_id=work.id if work else None,
            )
        )

    def _new_subtask(self, task: Task, data: SubtaskCreate, *, position: int) -> Subtask:
        fields = data.model_dump(mode="json")
        fields["category_id"] = data.category_id
        fields["action_type_id"] = data.action_type_id
        return Subtask(task_id=task.id, position=position, status=SubtaskStatus.todo, **fields)

    async def update(self, id: uuid.UUID, patch: TaskUpdate) -> TaskDetail:
        task = await self.tasks.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        _reject_nulls(changes, _TASK_REQUIRED)
        if changes.get("recurrence"):
            await ensure_has_occurrences(changes["recurrence"])
        await self._check_refs(changes)
        await self._resolve_milestone(changes, task)
        if "time_window" in changes:
            changes["time_window"] = patch.model_dump(mode="json")["time_window"]
        if "status" in changes and changes["status"] != task.status:
            changes["done_at"] = now_utc() if changes["status"] == TaskStatus.done else None
        if changes.get("recurrence") and not (
            changes.get("recurrence_start") or task.recurrence_start
        ):
            changes["recurrence_start"] = self._today()
        for name, value in changes.items():
            setattr(task, name, value)
        if changes.keys() & {"category_id", "subject_id"}:
            await self._refresh_events(task)
        if changes.keys() & RECURRENCE_FIELDS and (task.recurrence or "recurrence" in changes):
            await sync_recurring_task(self.db, task, self._today())
        await self.db.commit()
        return await self.get_detail(id)

    async def delete(self, id: uuid.UUID) -> None:
        """Задание удаляется с подзадачами; их будущие блоки исчезают из календаря."""
        task = await self.tasks.get_or_404(id)
        subtasks = await self.subtasks.find_all(Subtask.task_id == id)
        await self._drop_planned_events([s.id for s in subtasks])
        for s in subtasks:
            self.subtasks.soft_delete(s)
        await delete_for_owners(self.db, self.user_id, AttachmentOwner.task, [id])
        self.tasks.soft_delete(task)
        await self.db.commit()

    # ---------- подзадачи ----------

    async def _validate_deps(
        self, task_id: uuid.UUID, subtask_id: uuid.UUID | None, deps: list[uuid.UUID]
    ) -> list[str]:
        siblings = await self.subtasks.find_all(Subtask.task_id == task_id)
        known = {s.id for s in siblings}
        unique = list(dict.fromkeys(deps))
        if subtask_id in unique:
            raise InvalidDataError("Подзадача не может зависеть от самой себя")
        if unknown := set(unique) - known:
            raise InvalidDataError(f"Нет таких подзадач в задании: {len(unknown)}")
        if subtask_id is not None:
            graph = {str(s.id): list(s.depends_on) for s in siblings}
            graph[str(subtask_id)] = [str(d) for d in unique]
            if find_cycle(graph):
                raise InvalidDataError("Зависимости образуют цикл")
        return [str(d) for d in unique]

    async def add_subtask(self, task_id: uuid.UUID, data: SubtaskCreate) -> SubtaskRead:
        task = await self.tasks.get_or_404(task_id)
        await self._check_refs(data.model_dump())
        deps = await self._validate_deps(task_id, None, data.depends_on)
        last = await self.db.scalar(
            select(func.max(Subtask.position)).where(
                Subtask.task_id == task_id, Subtask.deleted_at.is_(None)
            )
        )
        subtask = self._new_subtask(task, data, position=(last if last is not None else -1) + 1)
        subtask.depends_on = deps
        self.subtasks.add(subtask)
        await self.db.commit()
        return self._subtask_read(subtask, [])

    async def update_subtask(self, id: uuid.UUID, patch: SubtaskUpdate) -> SubtaskRead:
        subtask = await self.subtasks.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        _reject_nulls(changes, _SUBTASK_REQUIRED)
        await self._check_refs(changes)
        if "depends_on" in changes:
            changes["depends_on"] = await self._validate_deps(
                subtask.task_id, subtask.id, changes["depends_on"]
            )
        if "time_window" in changes:
            changes["time_window"] = patch.model_dump(mode="json")["time_window"]
        new_status = changes.pop("status", None)
        feel_before = subtask.actual_feel
        for name, value in changes.items():
            setattr(subtask, name, value)
        if new_status is not None and new_status != subtask.status:
            self._set_subtask_status(subtask, new_status)
            await self._sync_events_status(subtask)
        if subtask.status != SubtaskStatus.done:
            subtask.actual_feel = None
        if subtask.actual_feel != feel_before:
            await recalibrate(self.db, self.user_id)
        if changes.keys() & {"title", "category_id"}:
            task = await self.tasks.get_or_404(subtask.task_id)
            await self._refresh_events(task, [subtask])
        await self.db.commit()
        return await self.get_subtask(id)

    @staticmethod
    def _set_subtask_status(subtask: Subtask, status: SubtaskStatus) -> None:
        subtask.status = status
        subtask.done_at = now_utc() if status == SubtaskStatus.done else None
        if status != SubtaskStatus.done:
            subtask.actual_feel = None

    async def _sync_events_status(self, subtask: Subtask) -> None:
        """Подзадача сделана → её запланированные блоки сделаны; и наоборот."""
        if subtask.status == SubtaskStatus.done:
            src, dst = EventStatus.planned, EventStatus.done
        else:
            src, dst = EventStatus.done, EventStatus.planned
        for e in await self._subtask_events([subtask.id], statuses=[src]):
            e.status = dst

    async def delete_subtask(self, id: uuid.UUID) -> None:
        subtask = await self.subtasks.get_or_404(id)
        self.subtasks.soft_delete(subtask)
        await self._drop_planned_events([id])
        for sibling in await self.subtasks.find_all(Subtask.task_id == subtask.task_id):
            if str(id) in sibling.depends_on:
                sibling.depends_on = [d for d in sibling.depends_on if d != str(id)]
        await self.db.commit()

    async def reorder(self, task_id: uuid.UUID, ids: list[uuid.UUID]) -> TaskDetail:
        await self.tasks.get_or_404(task_id)
        subtasks = {s.id: s for s in await self.subtasks.find_all(Subtask.task_id == task_id)}
        if len(ids) != len(set(ids)) or set(ids) != subtasks.keys():
            raise InvalidDataError("Нужен полный список подзадач задания без повторов")
        for position, sid in enumerate(ids):
            subtasks[sid].position = position
        await self.db.commit()
        return await self.get_detail(task_id)

    # ---------- календарь ----------

    async def schedule(self, id: uuid.UUID, data: SubtaskSchedule) -> SubtaskRead:
        """Ставит подзадачу в календарь вручную (закреплённым блоком).

        Если блок уже есть — переносит его (лишние части убирает).
        """
        subtask = await self.subtasks.get_or_404(id)
        task = await self.tasks.get_or_404(subtask.task_id)
        end = data.end or data.start + timedelta(minutes=subtask.estimate_min)
        planned = await self._subtask_events([id], statuses=[EventStatus.planned])
        event = planned[0] if planned else None
        for extra in planned[1:]:
            self.events.soft_delete(extra)
        if event is None:
            event = Event(
                kind=EventKind.subtask,
                is_fixed=False,
                status=EventStatus.planned,
                source_type=SourceType.subtask,
                source_id=subtask.id,
            )
            self.events.add(event)
        event.start = data.start
        event.end = end
        event.is_pinned = True
        event.title = subtask.title
        event.subject_id = task.subject_id
        event.color = await self._color(subtask, task)
        await self.db.commit()
        return await self.get_subtask(id)

    async def unschedule(self, id: uuid.UUID) -> SubtaskRead:
        await self.subtasks.get_or_404(id)
        await self._drop_planned_events([id])
        await self.db.commit()
        return await self.get_subtask(id)

    async def _drop_planned_events(self, subtask_ids: list[uuid.UUID]) -> None:
        for e in await self._subtask_events(subtask_ids, statuses=[EventStatus.planned]):
            self.events.soft_delete(e)

    async def _refresh_events(self, task: Task, subtasks: list[Subtask] | None = None) -> None:
        """Название, цвет и предмет блоков следуют за подзадачей и заданием."""
        if subtasks is None:
            subtasks = await self.subtasks.find_all(Subtask.task_id == task.id)
        by_id = {s.id: s for s in subtasks}
        for e in await self._subtask_events(by_id, statuses=[EventStatus.planned]):
            if e.source_id is None:
                continue
            subtask = by_id[e.source_id]
            e.title = subtask.title
            e.subject_id = task.subject_id
            e.color = await self._color(subtask, task)


async def on_subtask_event_status(
    db: AsyncSession, user_id: uuid.UUID, subtask_id: uuid.UUID, status: str
) -> None:
    """Блок подзадачи отметили в календаре → та же отметка у подзадачи.

    «Сделано» закрывает подзадачу; снятие отметки (planned) — открывает.
    """
    if status == EventStatus.done:
        values: dict[str, Any] = {"status": SubtaskStatus.done, "done_at": now_utc()}
        current = SubtaskStatus.todo
    elif status == EventStatus.planned:
        values = {"status": SubtaskStatus.todo, "done_at": None, "actual_feel": None}
        current = SubtaskStatus.done
    else:
        return
    result = await db.execute(
        update(Subtask)
        .where(
            Subtask.id == subtask_id,
            Subtask.user_id == user_id,
            Subtask.deleted_at.is_(None),
            Subtask.status == current,
        )
        .values(**values)
        .returning(Subtask.id)
    )
    if status == EventStatus.planned and result.first() is not None:
        # Сняли «сделано» — отметка «быстрее / дольше» больше не в счёт
        await recalibrate(db, user_id)
