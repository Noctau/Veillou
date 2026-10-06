"""Литература: CRUD по предмету и задание чтения из источника."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.domain.enums import AttachmentOwner, SourceStatus, TaskType
from app.domain.sources import reading_description, reading_title
from app.models import Attachment, Source, Subject, User
from app.schemas.source import ReadingTaskCreate, SourceCreate, SourceRead, SourceUpdate
from app.schemas.task import TaskCreate, TaskDetail
from app.services.attachments import delete_for_owners
from app.services.base import UserScopedRepository
from app.services.tasks import TaskService


class SourceRepo(UserScopedRepository[Source]):
    model = Source
    not_found_message = "Источник не найден"


class _SubjectRepo(UserScopedRepository[Subject]):
    model = Subject
    not_found_message = "Предмет не найден"


_REQUIRED = {"subject_id", "title", "author", "kind", "required", "status", "note"}
# Обязательное и непрочитанное — выше
_STATUS_ORDER = {SourceStatus.reading: 0, SourceStatus.to_read: 1, SourceStatus.done: 2}


class SourceService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.sources = SourceRepo(db, user.id)
        self.subjects = _SubjectRepo(db, user.id)

    async def _files_count(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not ids:
            return {}
        rows = await self.db.execute(
            select(Attachment.owner_id, func.count())
            .where(
                Attachment.user_id == self.user_id,
                Attachment.deleted_at.is_(None),
                Attachment.owner_type == AttachmentOwner.source,
                Attachment.owner_id.in_(ids),
            )
            .group_by(Attachment.owner_id)
        )
        return {owner_id: count for owner_id, count in rows.all()}

    async def _read(self, source: Source) -> SourceRead:
        read = SourceRead.model_validate(source)
        read.files_count = (await self._files_count([source.id])).get(source.id, 0)
        return read

    async def list(self, subject_id: uuid.UUID | None = None) -> list[SourceRead]:
        where = [Source.subject_id == subject_id] if subject_id else []
        sources = await self.sources.find_all(*where, order_by=[Source.created_at])
        sources.sort(key=lambda s: (not s.required, _STATUS_ORDER.get(s.status, 9)))
        counts = await self._files_count([s.id for s in sources])
        reads = [SourceRead.model_validate(s) for s in sources]
        for read in reads:
            read.files_count = counts.get(read.id, 0)
        return reads

    async def get(self, id: uuid.UUID) -> SourceRead:
        return await self._read(await self.sources.get_or_404(id))

    async def create(self, data: SourceCreate) -> SourceRead:
        await self.subjects.get_or_404(data.subject_id)
        source = Source(**data.model_dump(exclude={"url"}), url=str(data.url) if data.url else None)
        self.sources.add(source)
        await self.db.commit()
        return await self._read(source)

    async def update(self, id: uuid.UUID, patch: SourceUpdate) -> SourceRead:
        source = await self.sources.get_or_404(id)
        changes: dict[str, Any] = patch.model_dump(exclude_unset=True)
        for name in _REQUIRED & changes.keys():
            if changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if "url" in changes:
            changes["url"] = str(patch.url) if patch.url else None
        if changes.get("subject_id"):
            await self.subjects.get_or_404(changes["subject_id"])
        for name, value in changes.items():
            setattr(source, name, value)
        await self.db.commit()
        return await self._read(source)

    async def delete(self, id: uuid.UUID) -> None:
        source = await self.sources.get_or_404(id)
        await delete_for_owners(self.db, self.user_id, AttachmentOwner.source, [id])
        self.sources.soft_delete(source)
        await self.db.commit()

    async def create_reading_task(self, id: uuid.UUID, data: ReadingTaskCreate) -> TaskDetail:
        """«Прочитать главы 3–5»: задание типа «чтение» по предмету источника."""
        source = await self.sources.get_or_404(id)
        task = TaskCreate(
            title=reading_title(source.title, data.chapters),
            task_type=TaskType.reading,
            description=reading_description(source.title, source.author, source.url),
            subject_id=source.subject_id,
            deadline=data.deadline,
            estimate_min=data.estimate_min,
        )
        return await TaskService(self.db, self.user).create(task)
