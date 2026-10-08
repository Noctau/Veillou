import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.exam import (
    ExamCreate,
    ExamDetail,
    ExamQuestionCreate,
    ExamQuestionRead,
    ExamQuestionsImport,
    ExamQuestionUpdate,
    ExamRead,
    ExamUpdate,
)
from app.services.exams import ExamService


def get_service(db: SessionDep, user: CurrentUser) -> ExamService:
    return ExamService(db, user)


Service = Annotated[ExamService, Depends(get_service)]

router = APIRouter(prefix="/exams", tags=["exams"])
questions_router = APIRouter(prefix="/exam-questions", tags=["exams"])


@router.get("")
async def list_exams(svc: Service, subject_id: uuid.UUID | None = None) -> list[ExamRead]:
    """Экзамены (ближайшие первыми); с subject_id — только по предмету."""
    return await svc.list_exams(subject_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_exam(data: ExamCreate, svc: Service) -> ExamDetail:
    """Экзамен сразу появляется в календаре жёстким событием."""
    return await svc.create(data)


@router.get("/{exam_id}")
async def read_exam(exam_id: uuid.UUID, svc: Service) -> ExamDetail:
    """Вопросы со статусами и план подготовки по дням (с сегодняшнего)."""
    return await svc.get_detail(exam_id)


@router.patch("/{exam_id}")
async def update_exam(exam_id: uuid.UUID, patch: ExamUpdate, svc: Service) -> ExamDetail:
    return await svc.update(exam_id, patch)


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(exam_id: uuid.UUID, svc: Service) -> None:
    await svc.delete(exam_id)


@router.post("/{exam_id}/questions/import")
async def import_questions(
    exam_id: uuid.UUID, data: ExamQuestionsImport, svc: Service
) -> ExamDetail:
    """Вставка списком: «1. …», «1) …» или по одному в строке — добавляются в конец."""
    return await svc.import_questions(exam_id, data.text)


@router.post("/{exam_id}/questions", status_code=status.HTTP_201_CREATED)
async def add_question(exam_id: uuid.UUID, data: ExamQuestionCreate, svc: Service) -> ExamDetail:
    return await svc.add_question(exam_id, data)


@router.post("/{exam_id}/plan")
async def enable_exam_plan(exam_id: uuid.UUID, svc: Service) -> ExamDetail:
    """«Построить план подготовки»: дни по билетам + превью плана (GET /plan)."""
    return await svc.enable_plan(exam_id)


@router.delete("/{exam_id}/plan")
async def disable_exam_plan(exam_id: uuid.UUID, svc: Service) -> ExamDetail:
    """Убрать план подготовки: будущие дни удаляются, их блоки уберёт превью."""
    return await svc.disable_plan(exam_id)


@questions_router.patch("/{question_id}")
async def update_question(
    question_id: uuid.UUID, patch: ExamQuestionUpdate, svc: Service
) -> ExamQuestionRead:
    """Статус «повторить» возвращает вопрос в цикл повторений; план пересобирается."""
    return await svc.update_question(question_id, patch)


@questions_router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(question_id: uuid.UUID, svc: Service) -> None:
    await svc.delete_question(question_id)
