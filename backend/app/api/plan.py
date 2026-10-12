import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, SessionDep
from app.domain.enums import PlanReason
from app.schemas.plan import CalibrationRead, PlanState, PlanUndoResult
from app.services import calibration
from app.services.replan import ReplanService, plan_state, revision_read


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
    return PlanUndoResult(revision=revision_read(rev), restored=restored, skipped=skipped)


# ---------- калибровка ----------


@calibration_router.get("")
async def list_calibration(db: SessionDep, user: CurrentUser) -> list[CalibrationRead]:
    """Коэффициенты оценок по (тип задачи, тип действия) — только где есть отметки."""
    rows = await calibration.list_calibrations(db, user.id)
    return [CalibrationRead.model_validate(r) for r in rows]


@calibration_router.post("/reset")
async def reset_calibration(db: SessionDep, user: CurrentUser) -> list[CalibrationRead]:
    """Все коэффициенты → 1; прошлые отметки больше не учитываются."""
    await calibration.reset(db, user.id)
    return []
