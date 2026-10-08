import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.domain.enums import PlanReason
from app.schemas.plan import (
    CalibrationRead,
    PlanState,
    PlanUndoResult,
    StudyDayLimitPut,
    StudyDayLimitRead,
)
from app.services import calibration
from app.services.replan import ReplanService, plan_state, revision_read
from app.services.study_limits import StudyLimitService


def get_service(db: SessionDep, user: CurrentUser) -> ReplanService:
    return ReplanService(db, user)


Service = Annotated[ReplanService, Depends(get_service)]

router = APIRouter(prefix="/plan", tags=["plan"])
calibration_router = APIRouter(prefix="/calibration", tags=["plan"])


@router.get("")
async def read_plan_state(svc: Service) -> PlanState:
    """Ожидающее превью (после триггеров его считает воркер) и что можно откатить."""
    return await plan_state(svc)


@router.post("/preview")
async def preview_plan(svc: Service, reason: PlanReason = PlanReason.manual) -> PlanState:
    """Перепланировать сейчас. Ничего не меняет — только превью; пустое, если
    менять нечего. Показывает и превью, которое раньше отклонили."""
    await svc.preview([reason], force=True)
    return await plan_state(svc)


@router.post("/revisions/{revision_id}/apply")
async def apply_plan(revision_id: uuid.UUID, svc: Service) -> PlanState:
    """Применить превью. 409 plan_stale — план успел измениться: новое превью уже
    посчитано (GET /plan)."""
    await svc.apply(revision_id)
    return await plan_state(svc)


@router.post("/revisions/{revision_id}/dismiss")
async def dismiss_plan(revision_id: uuid.UUID, svc: Service) -> PlanState:
    """«Отменить» в шторке: превью отклонено, план не меняется."""
    await svc.dismiss(revision_id)
    return await plan_state(svc)


@router.post("/undo")
async def undo_plan(svc: Service) -> PlanUndoResult:
    """Откатить последнее применение (за сутки). Блоки, которые после него
    правили руками, остаются как есть."""
    rev, restored, skipped = await svc.undo()
    read = revision_read(rev)
    assert read is not None
    return PlanUndoResult(revision=read, restored=restored, skipped=skipped)


# ---------- разовый лимит учёбы ----------


@router.get("/day-limits")
async def list_day_limits(db: SessionDep, user: CurrentUser) -> list[StudyDayLimitRead]:
    """Разовые лимиты учёбы на сегодня и дальше."""
    items = await StudyLimitService(db, user).list()
    return [StudyDayLimitRead.model_validate(i) for i in items]


@router.put("/day-limits/{day}")
async def put_day_limit(
    day: date, data: StudyDayLimitPut, db: SessionDep, user: CurrentUser
) -> StudyDayLimitRead:
    """«Расширить часы в этот день»: лимит учёбы на дату вместо общего."""
    item = await StudyLimitService(db, user).put(day, data.minutes)
    return StudyDayLimitRead.model_validate(item)


@router.delete("/day-limits/{day}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_day_limit(day: date, db: SessionDep, user: CurrentUser) -> None:
    await StudyLimitService(db, user).delete(day)


# ---------- калибровка ----------


@calibration_router.get("")
async def list_calibration(db: SessionDep, user: CurrentUser) -> list[CalibrationRead]:
    """Коэффициенты оценок по (тип задания, тип действия) — только где есть отметки."""
    rows = await calibration.list_calibrations(db, user.id)
    return [CalibrationRead.model_validate(r) for r in rows]


@calibration_router.post("/reset")
async def reset_calibration(db: SessionDep, user: CurrentUser) -> list[CalibrationRead]:
    """Все коэффициенты → 1; прошлые отметки больше не учитываются."""
    await calibration.reset(db, user.id)
    return []
