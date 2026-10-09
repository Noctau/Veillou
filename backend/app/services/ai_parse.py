"""ИИ-разбор свободного текста (M10.5) и фото задания (M10.6).

Текст: quickparse не уверен (`needs_ai`) → джоба `ai.parse` → черновик
карточки (что это, название, предмет, тип, дедлайн). Явные даты и предмет,
которые нашёл quickparse, важнее догадок ИИ. Ничего не создаётся — карточку
подтверждают «Создать и разбить» / «Изменить».

Фото: картинки-вложения задания → vision-модель → текст задания в описание,
дедлайн, предмет и тип, если их ещё нет. Это правка самого задания (не плана),
поэтому применяется сразу, а `PhotoDraft.updated` говорит, что поменялось.
"""

import re
import uuid
from datetime import time
from typing import Any

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import Image
from app.ai.prompts import ParseContext, parse_messages, photo_messages
from app.ai.schemas import AIParsed, AIPhoto, with_subjects
from app.core.exceptions import InvalidDataError
from app.core.storage import Storage, get_storage
from app.core.time import get_tz, now_utc, wall_to_utc
from app.domain.enums import AIOrigin, AIPurpose, AttachmentOwner, JobKind, TaskType
from app.domain.quickparse import AI_TEXT_LEN, END_OF_DAY, KindHint, SubjectRef, has_date_cue
from app.models import Attachment, Job, Subject, Task, User
from app.schemas.ai import ParseDraft, PhotoDraft
from app.schemas.backlog import BacklogCreate
from app.schemas.task import TaskCreate
from app.services import jobs
from app.services.ai import call_llm, enqueue_ai
from app.services.backlog import BacklogService
from app.services.breakdown import load_catalog
from app.services.quickadd import Created, create_from_text, parse_text, subject_refs
from app.services.tasks import TaskRepo, TaskService

# Название задания, созданного из фото без подписи: распознавание его заменит
PHOTO_TITLE = "Задание с фото"
MAX_IMAGES = 4
# Больше в vision-модель не шлём: файл целиком в памяти и ещё раз в base64
MAX_IMAGE_BYTES = 15 * 1024 * 1024


def _subject_names(refs: list[SubjectRef]) -> dict[str, uuid.UUID]:
    """Название предмета → id (первое имя в SubjectRef — полное название)."""
    result: dict[str, uuid.UUID] = {}
    for ref in refs:
        if ref.names and isinstance(ref.id, uuid.UUID):
            result.setdefault(ref.names[0], ref.id)
    return result


def _task_type(value: TaskType) -> TaskType | None:
    return None if value == TaskType.other else value


def _said(at: time | None, text: str) -> time | None:
    """Время от ИИ, только если час есть в тексте («в 15», «к 9:30») — иначе выдумано."""
    if at is None:
        return None
    return at if re.search(rf"(?<!\d)0?{at.hour}(?!\d)", text) else None


def _description(ai: str, text: str) -> str:
    """Описание от ИИ, если ему можно верить.

    Короткий ввод — это и есть название, требований в нём нет. Описание длиннее
    исходного текста — модель дописала от себя; тогда берём сам текст.
    """
    text, ai = text.strip(), ai.strip()
    if len(text) <= AI_TEXT_LEN and "\n" not in text:
        return ""
    return text if len(ai) > len(text) else ai


class AIParseService:
    def __init__(self, db: AsyncSession, user: User, storage: Storage | None = None) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.tasks = TaskRepo(db, user.id)
        self.storage = storage or get_storage()

    async def _enqueue(self, kind: JobKind, payload: dict[str, Any]) -> uuid.UUID:
        job_id = await enqueue_ai(self.db, kind, user_id=self.user_id, payload=payload)
        await self.db.commit()
        return job_id

    # ---------- текст ----------

    async def start_parse(
        self, text: str, *, origin: AIOrigin = AIOrigin.app, **extra: Any
    ) -> uuid.UUID:
        return await self._enqueue(
            JobKind.ai_parse, {"text": text.strip()[:6000], "origin": origin, **extra}
        )

    async def parse(self, text: str, job_id: uuid.UUID | None = None) -> ParseDraft:
        now = now_utc().astimezone(self.tz)
        refs = await subject_refs(self.db, self.user, now.date())
        names = _subject_names(refs)
        quick = await parse_text(self.db, self.user, text)
        answer = await call_llm(
            self.db,
            self.user_id,
            AIPurpose.parse,
            parse_messages(ParseContext(text, now.replace(tzinfo=None), list(names))),
            with_subjects(AIParsed, list(names)),
            job_id=job_id,
        )
        catalog = await load_catalog(self.db, self.user_id)

        deadline = None
        if quick.date is not None and quick.deadline is not None:
            deadline = quick.deadline
        elif (wall := answer.deadline_wall()) and has_date_cue(text):
            day, at = wall
            deadline = wall_to_utc(day, _said(at, text) or END_OF_DAY, self.tz)
        subject_id = quick.subject_id if isinstance(quick.subject_id, uuid.UUID) else None
        subject_id = subject_id or (names.get(answer.subject) if answer.subject else None)
        kind = KindHint(answer.kind)
        if kind == KindHint.event and (quick.date is None or quick.time is None):
            # Событию нужно точное время — без него это задание или дело
            kind = KindHint.task if deadline or answer.task_type else KindHint.backlog
        # Правила quickparse по ключевым словам надёжнее догадки ИИ
        action = quick.action_type or answer.action_type
        return ParseDraft(
            kind=kind,
            title=answer.title[:300],
            description=_description(answer.description, text),
            task_type=_task_type(answer.task_type) or quick.task_type,
            subject_id=subject_id,
            deadline=deadline,
            action_type_id=catalog.action_id(action),
            text=text,
        )

    async def run_parse(self, job: Job) -> ParseDraft:
        draft = await self.parse(job.payload["text"], job.id)
        job.result = draft.model_dump(mode="json")
        return draft

    # ---------- фото ----------

    async def _images(self, task_id: uuid.UUID) -> list[Image]:
        rows = await self.db.scalars(
            select(Attachment)
            .where(
                Attachment.user_id == self.user_id,
                Attachment.deleted_at.is_(None),
                Attachment.owner_type == AttachmentOwner.task,
                Attachment.owner_id == task_id,
                Attachment.mime.like("image/%"),
                Attachment.size <= MAX_IMAGE_BYTES,
            )
            .order_by(Attachment.position, Attachment.created_at)
            .limit(MAX_IMAGES)
        )
        images = []
        for a in rows:
            path = self.storage.path(a.storage_key)
            data = await anyio.Path(path).read_bytes()
            images.append(Image(data, a.mime))
        return images

    async def start_photo(
        self, task_id: uuid.UUID, *, origin: AIOrigin = AIOrigin.app, **extra: Any
    ) -> uuid.UUID:
        await self.tasks.get_or_404(task_id)
        if not await self._has_images(task_id):
            raise InvalidDataError("У задания нет фото (или все больше 15 МБ)")
        return await self._enqueue(
            JobKind.ai_photo, {"task_id": str(task_id), "origin": origin, **extra}
        )

    async def _has_images(self, task_id: uuid.UUID) -> bool:
        found = await self.db.scalar(
            select(Attachment.id)
            .where(
                Attachment.user_id == self.user_id,
                Attachment.deleted_at.is_(None),
                Attachment.owner_type == AttachmentOwner.task,
                Attachment.owner_id == task_id,
                Attachment.mime.like("image/%"),
                Attachment.size <= MAX_IMAGE_BYTES,
            )
            .limit(1)
        )
        return found is not None

    async def recognize(self, task: Task, job_id: uuid.UUID | None = None) -> PhotoDraft:
        images = await self._images(task.id)
        if not images:
            raise jobs.JobFailedError("У задания нет фото")
        now = now_utc().astimezone(self.tz)
        names = _subject_names(await subject_refs(self.db, self.user, now.date()))
        caption = "" if task.title == PHOTO_TITLE else task.title
        answer = await call_llm(
            self.db,
            self.user_id,
            AIPurpose.photo,
            photo_messages(ParseContext(caption, now.replace(tzinfo=None), list(names))),
            with_subjects(AIPhoto, list(names)),
            images=images,
            job_id=job_id,
        )
        deadline = None
        if wall := answer.deadline_wall():
            day, at = wall
            deadline = wall_to_utc(day, at or END_OF_DAY, self.tz)
        subject_id = names.get(answer.subject) if answer.subject else None

        updated: list[str] = []
        text = answer.text.strip()
        if text and text not in task.description:
            task.description = f"{task.description.rstrip()}\n\n{text}".strip()[:20_000]
            updated.append("description")
        if task.title == PHOTO_TITLE and answer.title:
            task.title = answer.title[:300]
            updated.append("title")
        if task.deadline is None and deadline is not None:
            task.deadline = deadline
            updated.append("deadline")
        if task.subject_id is None and subject_id is not None:
            task.subject_id = subject_id
            updated.append("subject_id")
        if task.task_type == TaskType.other and _task_type(answer.task_type):
            task.task_type = answer.task_type
            updated.append("task_type")
        return PhotoDraft(
            task_id=task.id,
            title=task.title,
            text=text,
            task_type=_task_type(answer.task_type),
            subject_id=subject_id,
            deadline=deadline,
            updated=updated,
        )

    async def run_photo(self, job: Job) -> PhotoDraft:
        task = await self.tasks.get(uuid.UUID(job.payload["task_id"]))
        if task is None:
            raise jobs.JobFailedError("Задание удалено")
        draft = await self.recognize(task, job.id)
        job.result = draft.model_dump(mode="json")
        return draft


async def create_from_draft(
    db: AsyncSession, user: User, draft: ParseDraft, kind: KindHint | None = None
) -> Created:
    """Создаёт по карточке ИИ задание или дело в ящике. Событие — разбором
    исходного текста (точное время даёт только quickparse)."""
    kind = kind or draft.kind
    if kind == KindHint.event:
        return await create_from_text(db, user, draft.text, kind=KindHint.event)
    subject = await db.get(Subject, draft.subject_id) if draft.subject_id else None
    if kind == KindHint.backlog:
        tz = get_tz(user.timezone)
        desired = draft.deadline.astimezone(tz).date() if draft.deadline else None
        note = draft.description[:2000]
        item = await BacklogService(db, user).create(
            BacklogCreate(
                title=draft.title,
                note=note,
                desired_by=desired,
                action_type_id=draft.action_type_id,
            )
        )
        return Created(kind, item.id, draft.title, desired_by=desired)
    task = await TaskService(db, user).create(
        TaskCreate(
            title=draft.title,
            task_type=draft.task_type or TaskType.other,
            description=draft.description,
            subject_id=draft.subject_id,
            action_type_id=draft.action_type_id,
            deadline=draft.deadline,
        )
    )
    return Created(
        KindHint.task,
        task.id,
        draft.title,
        deadline=draft.deadline,
        subject=subject.name if subject else None,
    )
