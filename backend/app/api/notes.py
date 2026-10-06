import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.domain.enums import NoteKind
from app.schemas.note import NoteCreate, NoteListItem, NoteRead, NoteUpdate
from app.services.notes import NoteService


def get_service(db: SessionDep, user: CurrentUser) -> NoteService:
    return NoteService(db, user)


Service = Annotated[NoteService, Depends(get_service)]

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("")
async def list_notes(
    svc: Service,
    subject_id: uuid.UUID | None = None,
    event_id: Annotated[list[uuid.UUID], Query(max_length=200)] = [],  # noqa: B006
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[NoteListItem]:
    """Свежие пары первыми. `event_id` можно повторять — конспекты этих пар."""
    return await svc.list(subject_id=subject_id, event_ids=event_id, limit=limit)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_note(data: NoteCreate, svc: Service) -> NoteRead:
    """С `event_id` предмет и дата берутся из пары, если не указаны."""
    return await svc.create(data)


@router.post("/for-event/{event_id}")
async def note_for_event(
    event_id: uuid.UUID, svc: Service, response: Response, kind: NoteKind = NoteKind.text
) -> NoteRead:
    """«Конспект к этой паре»: открывает уже начатый конспект пары (200) или
    создаёт новый с предметом, датой и названием из пары (201)."""
    note, created = await svc.for_event(event_id, kind)
    if created:
        response.status_code = status.HTTP_201_CREATED
    return note


@router.get("/{note_id}")
async def read_note(note_id: uuid.UUID, svc: Service) -> NoteRead:
    return await svc.get(note_id)


@router.patch("/{note_id}")
async def update_note(note_id: uuid.UUID, patch: NoteUpdate, svc: Service) -> NoteRead:
    return await svc.update(note_id, patch)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: uuid.UUID, svc: Service) -> None:
    """Вместе со страницами и файлами."""
    await svc.delete(note_id)
