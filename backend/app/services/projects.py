"""Проекты и этапы. Задания проекта — обычные Task с project_id (services/tasks.py)."""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import time, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc, wall_to_utc
from app.domain.backlog import week_start
from app.domain.enums import (
    AttachmentOwner,
    CategoryKey,
    EventStatus,
    MilestoneStatus,
    ProjectStatus,
    SourceType,
    TaskStatus,
)
from app.domain.projects import MilestoneDates, behind_days
from app.models import Category, Event, Milestone, Project, Subtask, Task, User
from app.schemas.project import (
    MilestoneCreate,
    MilestoneRead,
    MilestoneUpdate,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectUpdate,
)
from app.services.attachments import delete_for_owners
from app.services.base import UserScopedRepository
from app.services.catalog import ensure_defaults


class ProjectRepo(UserScopedRepository[Project]):
    model = Project
    not_found_message = "Проект не найден"


class MilestoneRepo(UserScopedRepository[Milestone]):
    model = Milestone
    not_found_message = "Этап не найден"


class _CategoryRepo(UserScopedRepository[Category]):
    model = Category
    not_found_message = "Категория не найдена"


_PROJECT_REQUIRED = {"title", "description", "contacts", "links", "is_work_default", "status"}
_MILESTONE_ORDER = [Milestone.date.asc().nulls_last(), Milestone.position, Milestone.created_at]


class ProjectService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.projects = ProjectRepo(db, user.id)
        self.milestones = MilestoneRepo(db, user.id)
        self.categories = _CategoryRepo(db, user.id)

    # ---------- чтение ----------

    async def _task_counts(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        """Сколько разовых заданий в проекте и сколько сдано (регулярные не считаются)."""
        if not ids:
            return {}
        rows = await self.db.execute(
            select(
                Task.project_id,
                func.count(),
                func.count().filter(Task.status == TaskStatus.done),
            )
            .where(
                Task.user_id == self.user_id,
                Task.deleted_at.is_(None),
                Task.project_id.in_(ids),
                Task.status != TaskStatus.cancelled,
                Task.recurrence.is_(None),
            )
            .group_by(Task.project_id)
        )
        return {pid: (total, done) for pid, total, done in rows.all()}

    async def _week_minutes(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        """Проект → (сделано, сделано + запланировано) минут на этой неделе.

        Считаются блоки работы над проектом и блоки шагов / заданий проекта.
        """
        if not ids:
            return {}
        week = week_start(local_date(now_utc(), self.tz))
        start = wall_to_utc(week, time(0), self.tz)
        end = wall_to_utc(week + timedelta(days=7), time(0), self.tz)
        task_project = dict(
            (
                await self.db.execute(
                    select(Task.id, Task.project_id).where(
                        Task.user_id == self.user_id,
                        Task.deleted_at.is_(None),
                        Task.project_id.in_(ids),
                    )
                )
            ).all()
        )
        sub_task = (
            dict(
                (
                    await self.db.execute(
                        select(Subtask.id, Subtask.task_id).where(
                            Subtask.user_id == self.user_id,
                            Subtask.task_id.in_(task_project),
                        )
                    )
                ).all()
            )
            if task_project
            else {}
        )
        rows = await self.db.execute(
            select(Event.source_type, Event.source_id, Event.status, Event.start, Event.end).where(
                Event.user_id == self.user_id,
                Event.deleted_at.is_(None),
                Event.status.in_([EventStatus.planned, EventStatus.done]),
                Event.start >= start,
                Event.start < end,
                Event.source_id.in_([*ids, *task_project, *sub_task]),
                Event.source_type.in_([SourceType.project, SourceType.task, SourceType.subtask]),
            )
        )
        done: dict[uuid.UUID, int] = defaultdict(int)
        planned: dict[uuid.UUID, int] = defaultdict(int)
        for kind, sid, status, e_start, e_end in rows.all():
            if kind == SourceType.project:
                pid = sid
            elif kind == SourceType.task:
                pid = task_project.get(sid)
            else:
                pid = task_project.get(sub_task.get(sid))
            if pid is None:
                continue
            minutes = round((e_end - e_start).total_seconds() / 60)
            planned[pid] += minutes
            if status == EventStatus.done:
                done[pid] += minutes
        return {pid: (done[pid], planned[pid]) for pid in planned}

    async def _milestones_by_project(
        self, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[Milestone]]:
        result: dict[uuid.UUID, list[Milestone]] = {}
        if not ids:
            return result
        for m in await self.milestones.find_all(
            Milestone.project_id.in_(ids), order_by=_MILESTONE_ORDER
        ):
            result.setdefault(m.project_id, []).append(m)
        return result

    def _read(
        self,
        project: Project,
        counts: tuple[int, int] | None,
        milestones: list[Milestone],
        week: tuple[int, int] | None,
    ) -> ProjectRead:
        read = ProjectRead.model_validate(project)
        read.week_done_min, read.week_planned_min = week or (0, 0)
        read.behind_days = behind_days(
            (MilestoneDates(m.date, m.status == MilestoneStatus.done) for m in milestones),
            local_date(now_utc(), self.tz),
        )
        read.tasks_total, read.tasks_done = counts or (0, 0)
        read.milestones_total = len(milestones)
        read.milestones_done = sum(m.status == MilestoneStatus.done for m in milestones)
        upcoming = next((m for m in milestones if m.status == MilestoneStatus.planned), None)
        read.next_milestone = MilestoneRead.model_validate(upcoming) if upcoming else None
        return read

    async def list(self, statuses: Sequence[ProjectStatus] = ()) -> list[ProjectRead]:
        where = [Project.status.in_(statuses)] if statuses else []
        projects = await self.projects.find_all(
            *where, order_by=[Project.deadline.asc().nulls_last(), Project.created_at]
        )
        ids = [p.id for p in projects]
        counts = await self._task_counts(ids)
        milestones = await self._milestones_by_project(ids)
        weeks = await self._week_minutes(ids)
        return [
            self._read(p, counts.get(p.id), milestones.get(p.id, []), weeks.get(p.id))
            for p in projects
        ]

    async def get_detail(self, id: uuid.UUID) -> ProjectDetail:
        project = await self.projects.get_or_404(id)
        counts = await self._task_counts([id])
        milestones = (await self._milestones_by_project([id])).get(id, [])
        weeks = await self._week_minutes([id])
        return ProjectDetail(
            **self._read(project, counts.get(id), milestones, weeks.get(id)).model_dump(),
            milestones=[MilestoneRead.model_validate(m) for m in milestones],
        )

    # ---------- проекты ----------

    async def _unset_work_default(self, keep: uuid.UUID | None) -> None:
        await self.db.execute(
            update(Project)
            .where(
                Project.user_id == self.user_id,
                Project.is_work_default.is_(True),
                Project.id != keep if keep else True,
            )
            .values(is_work_default=False)
        )
        await self.db.flush()

    async def create(self, data: ProjectCreate) -> ProjectDetail:
        fields = data.model_dump(mode="json")
        fields["category_id"] = data.category_id
        fields["deadline"] = data.deadline
        if data.category_id:
            await self.categories.get_or_404(data.category_id)
        else:
            if await ensure_defaults(self.db, self.user_id):
                await self.db.flush()
            study = await self.db.scalar(
                self.categories.select().where(Category.key == CategoryKey.study)
            )
            fields["category_id"] = study.id if study else None
        if data.is_work_default:
            await self._unset_work_default(None)
        project = Project(status=ProjectStatus.active, **fields)
        self.projects.add(project)
        await self.db.commit()
        return await self.get_detail(project.id)

    async def update(self, id: uuid.UUID, patch: ProjectUpdate) -> ProjectDetail:
        project = await self.projects.get_or_404(id)
        changes: dict[str, Any] = patch.model_dump(mode="json", exclude_unset=True)
        for name in _PROJECT_REQUIRED & changes.keys():
            if changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if "category_id" in changes:
            changes["category_id"] = patch.category_id
            if patch.category_id:
                await self.categories.get_or_404(patch.category_id)
        if "deadline" in changes:
            changes["deadline"] = patch.deadline
        if changes.get("is_work_default"):
            await self._unset_work_default(id)
        for name, value in changes.items():
            setattr(project, name, value)
        await self.db.commit()
        return await self.get_detail(id)

    async def delete(self, id: uuid.UUID) -> None:
        """Проект удаляется с этапами, файлами и запланированной работой над ним;
        задания остаются, но без проекта."""
        project = await self.projects.get_or_404(id)
        for m in await self.milestones.find_all(Milestone.project_id == id):
            self.milestones.soft_delete(m)
        await self.db.execute(
            update(Task)
            .where(Task.user_id == self.user_id, Task.project_id == id)
            .values(project_id=None, milestone_id=None)
        )
        # Запланированные блоки работы над проектом больше не к чему относить
        await self.db.execute(
            update(Event)
            .where(
                Event.user_id == self.user_id,
                Event.deleted_at.is_(None),
                Event.source_type == SourceType.project,
                Event.source_id == id,
                Event.status == EventStatus.planned,
            )
            .values(deleted_at=now_utc())
        )
        await delete_for_owners(self.db, self.user_id, AttachmentOwner.project, [id])
        self.projects.soft_delete(project)
        await self.db.commit()

    # ---------- этапы ----------

    async def add_milestone(self, project_id: uuid.UUID, data: MilestoneCreate) -> MilestoneRead:
        await self.projects.get_or_404(project_id)
        last = await self.db.scalar(
            select(func.max(Milestone.position)).where(
                Milestone.project_id == project_id, Milestone.deleted_at.is_(None)
            )
        )
        milestone = Milestone(
            project_id=project_id,
            title=data.title,
            note=data.note,
            date=data.date,
            status=MilestoneStatus.planned,
            position=(last if last is not None else -1) + 1,
        )
        self.milestones.add(milestone)
        await self.db.commit()
        return MilestoneRead.model_validate(milestone)

    async def update_milestone(self, id: uuid.UUID, patch: MilestoneUpdate) -> MilestoneRead:
        milestone = await self.milestones.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name in {"title", "note", "status", "position"} & changes.keys():
            if changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if (status := changes.get("status")) and status != milestone.status:
            changes["done_at"] = now_utc() if status == MilestoneStatus.done else None
        for name, value in changes.items():
            setattr(milestone, name, value)
        await self.db.commit()
        return MilestoneRead.model_validate(milestone)

    async def delete_milestone(self, id: uuid.UUID) -> None:
        milestone = await self.milestones.get_or_404(id)
        self.milestones.soft_delete(milestone)
        await self.db.execute(
            update(Task)
            .where(Task.user_id == self.user_id, Task.milestone_id == id)
            .values(milestone_id=None)
        )
        await self.db.commit()
