import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.domain.enums import ProjectStatus
from app.schemas.project import (
    MilestoneCreate,
    MilestoneRead,
    MilestoneUpdate,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectUpdate,
)
from app.services.projects import ProjectService


def get_service(db: SessionDep, user: CurrentUser) -> ProjectService:
    return ProjectService(db, user)


Service = Annotated[ProjectService, Depends(get_service)]

router = APIRouter(tags=["projects"])
NO_CONTENT = status.HTTP_204_NO_CONTENT


@router.get("/projects")
async def list_projects(
    svc: Service,
    status: Annotated[list[ProjectStatus], Query()] = [],  # noqa: B006
) -> list[ProjectRead]:
    """Ближайший итоговый срок первым. Прогресс — по разовым заданиям и этапам."""
    return await svc.list(status)


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, svc: Service) -> ProjectDetail:
    return await svc.create(data)


@router.get("/projects/{project_id}")
async def read_project(project_id: uuid.UUID, svc: Service) -> ProjectDetail:
    return await svc.get_detail(project_id)


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: uuid.UUID, patch: ProjectUpdate, svc: Service
) -> ProjectDetail:
    """is_work_default=true снимает флаг с остальных проектов."""
    return await svc.update(project_id, patch)


@router.delete("/projects/{project_id}", status_code=NO_CONTENT)
async def delete_project(project_id: uuid.UUID, svc: Service) -> None:
    """Задания проекта остаются, но без проекта."""
    await svc.delete(project_id)


@router.post("/projects/{project_id}/milestones", status_code=status.HTTP_201_CREATED)
async def create_milestone(
    project_id: uuid.UUID, data: MilestoneCreate, svc: Service
) -> MilestoneRead:
    return await svc.add_milestone(project_id, data)


@router.patch("/milestones/{milestone_id}")
async def update_milestone(
    milestone_id: uuid.UUID, patch: MilestoneUpdate, svc: Service
) -> MilestoneRead:
    return await svc.update_milestone(milestone_id, patch)


@router.delete("/milestones/{milestone_id}", status_code=NO_CONTENT)
async def delete_milestone(milestone_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_milestone(milestone_id)
