import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.domain.enums import TaskStatus
from app.schemas.common import Moment
from app.schemas.task import (
    SubtaskCreate,
    SubtaskOrder,
    SubtaskRead,
    SubtaskSchedule,
    SubtaskUpdate,
    TaskCreate,
    TaskDetail,
    TaskRead,
    TaskUpdate,
)
from app.services.tasks import TaskService


def get_service(db: SessionDep, user: CurrentUser) -> TaskService:
    return TaskService(db, user)


Service = Annotated[TaskService, Depends(get_service)]

router = APIRouter(tags=["tasks"])
NO_CONTENT = status.HTTP_204_NO_CONTENT


# ---------- задания ----------


@router.get("/tasks")
async def list_tasks(
    svc: Service,
    status: Annotated[list[TaskStatus], Query()] = [],  # noqa: B006
    subject_id: uuid.UUID | None = None,
    due_before: Moment | None = None,
) -> list[TaskRead]:
    """Сортировка: ближайший дедлайн первым, без дедлайна — в конце.
    `due_before` — только с дедлайном раньше этого момента (просроченные тоже)."""
    return await svc.list_tasks(statuses=status, subject_id=subject_id, due_before=due_before)


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(data: TaskCreate, svc: Service) -> TaskDetail:
    return await svc.create(data)


@router.get("/tasks/{task_id}")
async def read_task(task_id: uuid.UUID, svc: Service) -> TaskDetail:
    return await svc.get_detail(task_id)


@router.patch("/tasks/{task_id}")
async def update_task(task_id: uuid.UUID, patch: TaskUpdate, svc: Service) -> TaskDetail:
    return await svc.update(task_id, patch)


@router.delete("/tasks/{task_id}", status_code=NO_CONTENT)
async def delete_task(task_id: uuid.UUID, svc: Service) -> None:
    await svc.delete(task_id)


# ---------- подзадачи ----------


@router.post("/tasks/{task_id}/subtasks", status_code=status.HTTP_201_CREATED)
async def create_subtask(task_id: uuid.UUID, data: SubtaskCreate, svc: Service) -> SubtaskRead:
    return await svc.add_subtask(task_id, data)


@router.put("/tasks/{task_id}/subtasks/order")
async def reorder_subtasks(task_id: uuid.UUID, data: SubtaskOrder, svc: Service) -> TaskDetail:
    return await svc.reorder(task_id, data.ids)


@router.get("/subtasks/{subtask_id}")
async def read_subtask(subtask_id: uuid.UUID, svc: Service) -> SubtaskRead:
    return await svc.get_subtask(subtask_id)


@router.patch("/subtasks/{subtask_id}")
async def update_subtask(subtask_id: uuid.UUID, patch: SubtaskUpdate, svc: Service) -> SubtaskRead:
    """«Сделано» у подзадачи отмечает и её блоки в календаре."""
    return await svc.update_subtask(subtask_id, patch)


@router.delete("/subtasks/{subtask_id}", status_code=NO_CONTENT)
async def delete_subtask(subtask_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_subtask(subtask_id)


@router.post("/subtasks/{subtask_id}/schedule")
async def schedule_subtask(
    subtask_id: uuid.UUID, data: SubtaskSchedule, svc: Service
) -> SubtaskRead:
    """Поставить в календарь вручную (закреплённым блоком) или перенести."""
    return await svc.schedule(subtask_id, data)


@router.delete("/subtasks/{subtask_id}/schedule")
async def unschedule_subtask(subtask_id: uuid.UUID, svc: Service) -> SubtaskRead:
    return await svc.unschedule(subtask_id)
