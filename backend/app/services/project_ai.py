"""ИИ предлагает этапы проекта (M13.2).

«Предложить этапы» ставит джобу `ai.milestones`; воркер собирает контекст
(описание, итоговый срок, уже существующие этапы и задания проекта), зовёт ИИ
и кладёт черновик в `jobs.result`. Проект при этом не меняется. Экран проверки
правит черновик у себя и шлёт «Сохранить»: этапы добавляются к уже
существующим (их ИИ видит и не повторяет).
"""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import ExistingMilestone, MilestonesContext, milestones_messages
from app.ai.schemas import AIMilestones
from app.core.config import settings
from app.core.time import get_tz, local_date, now_utc
from app.domain.enums import AIPurpose, JobKind, JobStatus, MilestoneStatus, TaskStatus
from app.domain.projects import RawMilestone, normalize_milestones
from app.models import Job, Milestone, Project, Task, User
from app.schemas.ai import MilestonesApply, MilestonesDraft, MilestonesRequest, MilestoneSuggestion
from app.schemas.project import ProjectDetail
from app.services import jobs
from app.services.ai import call_llm
from app.services.projects import ProjectService

# Сколько заданий проекта показать ИИ
MAX_TASKS = 30


class ProjectAIService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.projects = ProjectService(db, user)

    async def _milestones(self, project_id: uuid.UUID) -> list[Milestone]:
        return list(
            await self.db.scalars(
                select(Milestone)
                .where(
                    Milestone.user_id == self.user_id,
                    Milestone.project_id == project_id,
                    Milestone.deleted_at.is_(None),
                )
                .order_by(Milestone.date.asc().nulls_last(), Milestone.position)
            )
        )

    # ---------- джоба ----------

    async def start(self, project_id: uuid.UUID, data: MilestonesRequest) -> uuid.UUID:
        await self.projects.projects.get_or_404(project_id)
        payload: dict[str, Any] = {
            "project_id": str(project_id),
            "comment": data.comment,
            "previous": [m.model_dump(mode="json") for m in data.previous],
        }
        job_id = await jobs.enqueue(
            self.db, JobKind.ai_milestones, user_id=self.user_id, payload=payload, max_attempts=1
        )
        await self.db.commit()
        assert job_id is not None
        return job_id

    async def context(self, project: Project, request: MilestonesRequest) -> MilestonesContext:
        existing = await self._milestones(project.id)
        tasks = await self.db.scalars(
            select(Task.title)
            .where(
                Task.user_id == self.user_id,
                Task.deleted_at.is_(None),
                Task.project_id == project.id,
                Task.status != TaskStatus.cancelled,
                Task.recurrence.is_(None),
            )
            .order_by(Task.deadline.asc().nulls_last(), Task.created_at)
            .limit(MAX_TASKS)
        )
        return MilestonesContext(
            title=project.title,
            today=local_date(now_utc(), self.tz),
            description=project.description,
            deadline=project.deadline,
            weekly_norm_min=project.weekly_norm_min,
            existing=[
                ExistingMilestone(m.title, m.date, m.status == MilestoneStatus.done)
                for m in existing
            ],
            tasks=list(tasks),
            previous=[
                f"{m.title} — {m.date.isoformat() if m.date else 'без даты'}"
                for m in request.previous
            ],
            comment=request.comment,
        )

    async def run(self, job: Job) -> MilestonesDraft:
        """Обработчик джобы: черновик в `job.result`."""
        payload = job.payload
        project = await self.projects.projects.get(uuid.UUID(payload["project_id"]))
        if project is None:
            raise jobs.JobFailedError("Проект удалён")
        request = MilestonesRequest(
            comment=payload.get("comment"),
            previous=[MilestoneSuggestion.model_validate(m) for m in payload.get("previous") or []],
        )
        ctx = await self.context(project, request)
        answer = await call_llm(
            self.db,
            self.user_id,
            AIPurpose.milestones,
            milestones_messages(ctx),
            AIMilestones,
            job_id=job.id,
        )
        normalized = normalize_milestones(
            (RawMilestone(m.title, m.date, m.note) for m in answer.milestones),
            today=ctx.today,
            deadline=project.deadline,
            existing=[m.title for m in ctx.existing],
        )
        if not normalized:
            raise jobs.JobFailedError("ИИ не предложил новых этапов — попробуйте с комментарием")
        draft = MilestonesDraft(
            project_id=project.id,
            milestones=[
                MilestoneSuggestion(title=m.title, date=m.date, note=m.note) for m in normalized
            ],
            warning=answer.warning or None,
        )
        job.result = draft.model_dump(mode="json")
        return draft

    async def latest_job(self, project_id: uuid.UUID) -> Job | None:
        """Последний черновик этапов, который ещё не сохранили: ждёт ИИ, считается или готов."""
        await self.projects.projects.get_or_404(project_id)
        since = now_utc() - timedelta(hours=settings.LLM_QUEUE_MAX_HOURS)
        job = await self.db.scalar(
            select(Job)
            .where(
                Job.user_id == self.user_id,
                Job.kind == JobKind.ai_milestones,
                Job.payload["project_id"].astext == str(project_id),
                Job.created_at >= since,
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        if job is None or job.status == JobStatus.failed:
            return None
        if job.status == JobStatus.done and (job.result or {}).get("applied"):
            return None
        return job

    async def dismiss(self, job_id: uuid.UUID) -> None:
        """«Отмена» на экране проверки: черновик больше не предлагается."""
        await self._mark_applied(job_id, {"dismissed": True})
        await self.db.commit()

    async def _mark_applied(self, job_id: uuid.UUID, extra: dict[str, Any] | None = None) -> None:
        job = await self.db.scalar(
            select(Job).where(
                Job.id == job_id, Job.user_id == self.user_id, Job.kind == JobKind.ai_milestones
            )
        )
        if job is not None and job.result is not None:
            job.result = {**job.result, "applied": True, **(extra or {})}

    # ---------- «Сохранить» ----------

    async def apply(self, project_id: uuid.UUID, data: MilestonesApply) -> ProjectDetail:
        """Добавляет этапы к существующим. Коммитит."""
        await self.projects.projects.get_or_404(project_id)
        last = await self.db.scalar(
            select(func.max(Milestone.position)).where(
                Milestone.project_id == project_id, Milestone.deleted_at.is_(None)
            )
        )
        position = (last if last is not None else -1) + 1
        for i, m in enumerate(data.milestones):
            self.db.add(
                Milestone(
                    user_id=self.user_id,
                    project_id=project_id,
                    title=m.title,
                    note=m.note,
                    date=m.date,
                    status=MilestoneStatus.planned,
                    position=position + i,
                )
            )
        if data.job_id is not None:
            await self._mark_applied(data.job_id)
        await self.db.commit()
        return await self.projects.get_detail(project_id)


async def handle_milestones_job(db: AsyncSession, job: Job) -> None:
    user = await db.get(User, job.user_id)
    if user is None:
        raise jobs.JobFailedError("Пользователь удалён")
    await ProjectAIService(db, user).run(job)
