"""ИИ: джобы (поллинг), разбивка, шаблоны, разбор текста и фото, этапы проекта.

Все вызовы ИИ — джобы в воркере: ручка отдаёт `job_id`, фронт поллит
`GET /jobs/{id}` до `done` / `failed`.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.exceptions import NotFoundError
from app.domain.enums import JobStatus
from app.models import Job
from app.schemas.ai import (
    AIParseRequest,
    BreakdownApplied,
    BreakdownApply,
    BreakdownRequest,
    JobRead,
    JobStarted,
    MilestonesApply,
    MilestonesRequest,
    TemplateCreate,
    TemplateRead,
    TemplateUpdate,
)
from app.schemas.project import ProjectDetail
from app.services.ai_parse import AIParseService
from app.services.breakdown import BreakdownService
from app.services.project_ai import ProjectAIService
from app.services.replan import ReplanService, plan_state
from app.services.tasks import TaskService


def get_service(db: SessionDep, user: CurrentUser) -> BreakdownService:
    return BreakdownService(db, user)


Service = Annotated[BreakdownService, Depends(get_service)]

router = APIRouter(tags=["ai"])
NO_CONTENT = status.HTTP_204_NO_CONTENT
ACCEPTED = status.HTTP_202_ACCEPTED


def job_read(job: Job) -> JobRead:
    result = job.result if job.status == JobStatus.done else None
    error = None
    if job.status == JobStatus.failed:
        error = (job.result or {}).get("error") or "Не получилось — попробуйте ещё раз"
    waiting = (job.result or {}).get("waiting") if job.status == JobStatus.pending else None
    return JobRead.model_validate(
        {
            "id": job.id,
            "kind": job.kind,
            "status": job.status,
            "error": error,
            "waiting": waiting,
            "result": result if result and "type" in result else None,
        }
    )


@router.get("/jobs/{job_id}")
async def read_job(job_id: uuid.UUID, db: SessionDep, user: CurrentUser) -> JobRead:
    """Статус фоновой джобы. `result` — когда `done`, `error` — когда `failed`,
    `waiting` — ИИ недоступен и запрос ждёт в очереди."""
    job = await db.scalar(select(Job).where(Job.id == job_id, Job.user_id == user.id))
    if job is None:
        raise NotFoundError("Задача не найдена")
    return job_read(job)


# ---------- разбивка ----------


@router.post("/tasks/{task_id}/breakdown", status_code=ACCEPTED)
async def start_breakdown(task_id: uuid.UUID, data: BreakdownRequest, svc: Service) -> JobStarted:
    """«Разбить на шаги» / «Перегенерировать»: черновик придёт в `GET /jobs/{id}`.
    Задание не меняется, пока не нажали «Запланировать»."""
    return JobStarted(job_id=await svc.start(task_id, data))


@router.get("/tasks/{task_id}/breakdown/latest")
async def latest_breakdown(task_id: uuid.UUID, svc: Service) -> JobRead | None:
    """Неприменённая разбивка задания (ждёт ИИ, считается или готова) — или null."""
    job = await svc.latest_job(task_id)
    return job_read(job) if job else None


@router.post("/tasks/{task_id}/breakdown/apply")
async def apply_breakdown(
    task_id: uuid.UUID, data: BreakdownApply, svc: Service, db: SessionDep, user: CurrentUser
) -> BreakdownApplied:
    """«Запланировать»: несделанные шаги задания заменяются этими (их блоки
    убираются), сделанные остаются. С `plan` — сразу превью плана."""
    planned = await svc.apply_and_preview(task_id, data)
    task = await TaskService(db, user).get_detail(task_id)
    plan = await plan_state(ReplanService(db, user)) if planned else None
    return BreakdownApplied(task=task, plan=plan)


# ---------- шаблоны ----------


@router.get("/breakdown-templates")
async def list_templates(svc: Service) -> list[TemplateRead]:
    return await svc.list_templates()


@router.post("/breakdown-templates", status_code=status.HTTP_201_CREATED)
async def create_template(data: TemplateCreate, svc: Service) -> TemplateRead:
    return await svc.create_template(data)


@router.patch("/breakdown-templates/{template_id}")
async def update_template(
    template_id: uuid.UUID, data: TemplateUpdate, svc: Service
) -> TemplateRead:
    return await svc.update_template(template_id, data)


@router.delete("/breakdown-templates/{template_id}", status_code=NO_CONTENT)
async def delete_template(template_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_template(template_id)


# ---------- разбор текста и фото ----------


@router.post("/quick-add/ai-parse", status_code=ACCEPTED)
async def ai_parse(data: AIParseRequest, db: SessionDep, user: CurrentUser) -> JobStarted:
    """Разобрать текст ИИ (когда quickparse не уверен). Ничего не создаёт —
    в результате карточка: что это, название, предмет, тип, дедлайн."""
    return JobStarted(job_id=await AIParseService(db, user).start_parse(data.text))


@router.post("/tasks/{task_id}/recognize", status_code=ACCEPTED)
async def recognize_photo(task_id: uuid.UUID, db: SessionDep, user: CurrentUser) -> JobStarted:
    """Распознать фото задания (его вложения-картинки): текст — в описание,
    дедлайн, предмет и тип — если их ещё нет."""
    return JobStarted(job_id=await AIParseService(db, user).start_photo(task_id))


# ---------- этапы проекта ----------


def get_project_ai(db: SessionDep, user: CurrentUser) -> ProjectAIService:
    return ProjectAIService(db, user)


ProjectAI = Annotated[ProjectAIService, Depends(get_project_ai)]


@router.post("/projects/{project_id}/milestones/suggest", status_code=ACCEPTED)
async def suggest_milestones(
    project_id: uuid.UUID, data: MilestonesRequest, svc: ProjectAI
) -> JobStarted:
    """«Предложить этапы» / «Перегенерировать»: черновик придёт в `GET /jobs/{id}`.
    Проект не меняется, пока не нажали «Сохранить»."""
    return JobStarted(job_id=await svc.start(project_id, data))


@router.get("/projects/{project_id}/milestones/suggest/latest")
async def latest_milestones(project_id: uuid.UUID, svc: ProjectAI) -> JobRead | None:
    """Несохранённый черновик этапов (ждёт ИИ, считается или готов) — или null."""
    job = await svc.latest_job(project_id)
    return job_read(job) if job else None


@router.post("/projects/{project_id}/milestones/suggest/{job_id}/dismiss", status_code=NO_CONTENT)
async def dismiss_milestones(project_id: uuid.UUID, job_id: uuid.UUID, svc: ProjectAI) -> None:
    """«Отмена» на экране проверки — черновик больше не предлагается."""
    await svc.dismiss(project_id, job_id)


@router.post("/projects/{project_id}/milestones/bulk")
async def apply_milestones(
    project_id: uuid.UUID, data: MilestonesApply, svc: ProjectAI
) -> ProjectDetail:
    """«Сохранить»: этапы добавляются к уже существующим."""
    return await svc.apply(project_id, data)
