import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.schedule import (
    BellScheduleRead,
    BellsReplace,
    ClassRuleCreate,
    ClassRuleRead,
    ClassRuleUpdate,
    DayOffCreate,
    DayOffRead,
    DayOffUpdate,
    SemesterCreate,
    SemesterRead,
    SemesterUpdate,
    SubjectCreate,
    SubjectRead,
    SubjectUpdate,
)
from app.services.schedule import ScheduleService


def get_service(db: SessionDep, user: CurrentUser) -> ScheduleService:
    return ScheduleService(db, user.id)


Service = Annotated[ScheduleService, Depends(get_service)]

router = APIRouter(tags=["schedule"])
NO_CONTENT = status.HTTP_204_NO_CONTENT


# ---------- семестры ----------


@router.get("/semesters")
async def list_semesters(svc: Service) -> list[SemesterRead]:
    return [SemesterRead.model_validate(s) for s in await svc.list_semesters()]


@router.post("/semesters", status_code=status.HTTP_201_CREATED)
async def create_semester(data: SemesterCreate, svc: Service) -> SemesterRead:
    return SemesterRead.model_validate(await svc.create_semester(data))


@router.patch("/semesters/{semester_id}")
async def update_semester(
    semester_id: uuid.UUID, patch: SemesterUpdate, svc: Service
) -> SemesterRead:
    return SemesterRead.model_validate(await svc.update_semester(semester_id, patch))


@router.delete("/semesters/{semester_id}", status_code=NO_CONTENT)
async def delete_semester(semester_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_semester(semester_id)


# ---------- звонки ----------


@router.get("/semesters/{semester_id}/bells")
async def list_bells(semester_id: uuid.UUID, svc: Service) -> list[BellScheduleRead]:
    return [BellScheduleRead.model_validate(b) for b in await svc.list_bells(semester_id)]


@router.put("/semesters/{semester_id}/bells")
async def replace_bells(
    semester_id: uuid.UUID, data: BellsReplace, svc: Service
) -> list[BellScheduleRead]:
    """Заменяет все звонки семестра: общие (weekday = null) + переопределения дней."""
    rows = await svc.replace_bells(semester_id, data)
    return [BellScheduleRead.model_validate(b) for b in rows]


# ---------- выходные ----------


@router.get("/days-off")
async def list_days_off(svc: Service) -> list[DayOffRead]:
    return [DayOffRead.model_validate(d) for d in await svc.list_days_off()]


@router.post("/days-off", status_code=status.HTTP_201_CREATED)
async def create_day_off(data: DayOffCreate, svc: Service) -> DayOffRead:
    return DayOffRead.model_validate(await svc.create_day_off(data))


@router.patch("/days-off/{day_off_id}")
async def update_day_off(day_off_id: uuid.UUID, patch: DayOffUpdate, svc: Service) -> DayOffRead:
    return DayOffRead.model_validate(await svc.update_day_off(day_off_id, patch))


@router.delete("/days-off/{day_off_id}", status_code=NO_CONTENT)
async def delete_day_off(day_off_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_day_off(day_off_id)


# ---------- предметы ----------


@router.get("/subjects")
async def list_subjects(svc: Service, semester_id: uuid.UUID | None = None) -> list[SubjectRead]:
    return [SubjectRead.model_validate(s) for s in await svc.list_subjects(semester_id)]


@router.get("/subjects/{subject_id}")
async def read_subject(subject_id: uuid.UUID, svc: Service) -> SubjectRead:
    return SubjectRead.model_validate(await svc.get_subject(subject_id))


@router.post("/subjects", status_code=status.HTTP_201_CREATED)
async def create_subject(data: SubjectCreate, svc: Service) -> SubjectRead:
    return SubjectRead.model_validate(await svc.create_subject(data))


@router.patch("/subjects/{subject_id}")
async def update_subject(subject_id: uuid.UUID, patch: SubjectUpdate, svc: Service) -> SubjectRead:
    return SubjectRead.model_validate(await svc.update_subject(subject_id, patch))


@router.delete("/subjects/{subject_id}", status_code=NO_CONTENT)
async def delete_subject(subject_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_subject(subject_id)


# ---------- правила пар ----------


@router.get("/class-rules")
async def list_class_rules(
    svc: Service, semester_id: uuid.UUID | None = None
) -> list[ClassRuleRead]:
    return [ClassRuleRead.model_validate(r) for r in await svc.list_rules(semester_id)]


@router.post("/class-rules", status_code=status.HTTP_201_CREATED)
async def create_class_rule(data: ClassRuleCreate, svc: Service) -> ClassRuleRead:
    return ClassRuleRead.model_validate(await svc.create_rule(data))


@router.patch("/class-rules/{rule_id}")
async def update_class_rule(
    rule_id: uuid.UUID, patch: ClassRuleUpdate, svc: Service
) -> ClassRuleRead:
    return ClassRuleRead.model_validate(await svc.update_rule(rule_id, patch))


@router.delete("/class-rules/{rule_id}", status_code=NO_CONTENT)
async def delete_class_rule(rule_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_rule(rule_id)
