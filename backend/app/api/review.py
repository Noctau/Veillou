from datetime import date

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.event import EventRead
from app.schemas.review import (
    EveningReview,
    RescheduleRequest,
    RescheduleResult,
    WeekConfirm,
    WeeklyReview,
)
from app.services.replan import ReplanService, plan_state
from app.services.review import ReviewService

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/evening")
async def read_evening_review(
    db: SessionDep, user: CurrentUser, day: date | None = None
) -> EveningReview:
    """Вечерний разбор: начатые и прошедшие блоки дня без отметки."""
    svc = ReviewService(db, user)
    items, done = await svc.evening_items(day)
    return EveningReview(
        date=day or svc.today, items=[EventRead.model_validate(e) for e in items], done=done
    )


@router.post("/evening/reschedule")
async def reschedule_evening(
    data: RescheduleRequest, db: SessionDep, user: CurrentUser, day: date | None = None
) -> RescheduleResult:
    """«Перенести всё» (или выбранное): блоки → «не сделано», превью плана.
    Применяет пользователь (POST /plan/revisions/{id}/apply)."""
    moved, _ = await ReviewService(db, user).reschedule(data.event_ids, day)
    return RescheduleResult(moved=moved, plan=await plan_state(ReplanService(db, user)))


@router.get("/week")
async def read_weekly_review(db: SessionDep, user: CurrentUser) -> WeeklyReview:
    """Итоги недели и 1–N дел из ящика на неделю (в Сб/Вс — на следующую)."""
    return await ReviewService(db, user).weekly()


@router.post("/week/confirm")
async def confirm_week(data: WeekConfirm, db: SessionDep, user: CurrentUser) -> RescheduleResult:
    """Дела на неделю (список целиком) + превью: они встают в свободные окна."""
    await ReviewService(db, user).confirm_week(data.item_ids)
    return RescheduleResult(moved=0, plan=await plan_state(ReplanService(db, user)))
