"""Конспекты: CRUD, привязка к предмету и паре, сводка по вложениям для списка."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc
from app.domain.enums import AttachmentOwner, NoteKind
from app.domain.notes import default_title, excerpt
from app.models import Attachment, Event, Note, Subject, User
from app.schemas.note import NoteCreate, NoteEvent, NoteListItem, NoteRead, NoteUpdate
from app.services.attachments import delete_for_owners, is_inline_image, signed_url
from app.services.base import UserScopedRepository


class NoteRepo(UserScopedRepository[Note]):
    model = Note
    not_found_message = "Конспект не найден"


class _EventRepo(UserScopedRepository[Event]):
    model = Event
    not_found_message = "Пара не найдена"


class _SubjectRepo(UserScopedRepository[Subject]):
    model = Subject
    not_found_message = "Предмет не найден"


_REQUIRED = {"title", "kind", "body_md"}
# Сначала конспекты свежих пар, без даты — в конце
NOTE_ORDER = [Note.class_date.desc().nulls_last(), Note.created_at.desc()]


class NoteService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.notes = NoteRepo(db, user.id)
        self.events = _EventRepo(db, user.id)
        self.subjects = _SubjectRepo(db, user.id)

    # ---------- чтение ----------

    async def _attachments(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[Attachment]]:
        result: dict[uuid.UUID, list[Attachment]] = {}
        if not ids:
            return result
        rows = await self.db.scalars(
            select(Attachment)
            .where(
                Attachment.user_id == self.user_id,
                Attachment.deleted_at.is_(None),
                Attachment.owner_type == AttachmentOwner.note,
                Attachment.owner_id.in_(list(ids)),
            )
            .order_by(Attachment.position, Attachment.created_at)
        )
        for a in rows:
            result.setdefault(a.owner_id, []).append(a)
        return result

    @staticmethod
    def _fill[R: NoteListItem](read: R, note: Note, attachments: list[Attachment]) -> R:
        read.excerpt = excerpt(note.body_md)
        read.attachments_count = len(attachments)
        cover = next((a for a in attachments if is_inline_image(a.mime)), None)
        read.cover_url = signed_url(cover.id) if cover else None
        return read

    async def list_items(self, notes: Sequence[Note]) -> list[NoteListItem]:
        attachments = await self._attachments([n.id for n in notes])
        return [
            self._fill(NoteListItem.model_validate(n), n, attachments.get(n.id, [])) for n in notes
        ]

    async def list(
        self,
        *,
        subject_id: uuid.UUID | None = None,
        event_ids: Sequence[uuid.UUID] = (),
        limit: int = 100,
    ) -> list[NoteListItem]:
        where = []
        if subject_id:
            where.append(Note.subject_id == subject_id)
        if event_ids:
            where.append(Note.event_id.in_(list(event_ids)))
        notes = await self.notes.find_all(*where, order_by=NOTE_ORDER, limit=limit)
        return await self.list_items(notes)

    async def get(self, id: uuid.UUID) -> NoteRead:
        note = await self.notes.get_or_404(id)
        read = NoteRead.model_validate(note)
        if note.event_id and (event := await self.events.get(note.event_id)):
            read.event = NoteEvent.model_validate(event)
        attachments = await self._attachments([id])
        return self._fill(read, note, attachments.get(id, []))

    # ---------- запись ----------

    async def _subject_name(self, subject_id: uuid.UUID | None) -> str | None:
        if subject_id is None:
            return None
        return (await self.subjects.get_or_404(subject_id)).name

    async def create(self, data: NoteCreate) -> NoteRead:
        subject_id = data.subject_id
        class_date = data.class_date
        if data.event_id:
            event = await self.events.get_or_404(data.event_id)
            subject_id = subject_id or event.subject_id
            class_date = class_date or local_date(event.start, self.tz)
        class_date = class_date or local_date(now_utc(), self.tz)
        subject_name = await self._subject_name(subject_id)
        note = Note(
            title=data.title or default_title(class_date, subject_name),
            kind=data.kind,
            subject_id=subject_id,
            event_id=data.event_id,
            class_date=class_date,
            body_md=data.body_md,
            url=str(data.url) if data.url else None,
        )
        self.notes.add(note)
        await self.db.commit()
        return await self.get(note.id)

    async def for_event(self, event_id: uuid.UUID, kind: NoteKind) -> tuple[NoteRead, bool]:
        """«Конспект к этой паре»: уже начатый конспект пары или новый. (конспект, создан?)"""
        await self.events.get_or_404(event_id)
        existing = await self.notes.find_all(
            Note.event_id == event_id, order_by=[Note.created_at], limit=1
        )
        if existing:
            return await self.get(existing[0].id), False
        return await self.create(NoteCreate(event_id=event_id, kind=kind)), True

    async def update(self, id: uuid.UUID, patch: NoteUpdate) -> NoteRead:
        note = await self.notes.get_or_404(id)
        changes: dict[str, Any] = patch.model_dump(exclude_unset=True)
        for name in _REQUIRED & changes.keys():
            if changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if "url" in changes:
            changes["url"] = str(patch.url) if patch.url else None
        if changes.get("event_id") and changes["event_id"] != note.event_id:
            # Новая пара задаёт предмет и дату, если их не прислали явно
            event = await self.events.get_or_404(changes["event_id"])
            changes.setdefault("subject_id", event.subject_id or note.subject_id)
            changes.setdefault("class_date", local_date(event.start, self.tz))
        if changes.get("subject_id"):
            await self.subjects.get_or_404(changes["subject_id"])
        for name, value in changes.items():
            setattr(note, name, value)
        await self.db.commit()
        return await self.get(id)

    async def delete(self, id: uuid.UUID) -> None:
        """Конспект удаляется вместе со страницами и файлами (мягко)."""
        note = await self.notes.get_or_404(id)
        await delete_for_owners(self.db, self.user_id, AttachmentOwner.note, [id])
        self.notes.soft_delete(note)
        await self.db.commit()
