"""Разбивка задания на шаги (M10.2–M10.4).

«Разбить на шаги» ставит джобу `ai.breakdown`; воркер собирает контекст
(описание, предмет, дедлайн, свободные минуты до дедлайна, калибровка, уже
сделанное), зовёт ИИ и кладёт черновик в `jobs.result`. Задание при этом не
меняется. Экран проверки правит черновик у себя и шлёт «Запланировать»:
несделанные шаги задания заменяются присланными (их блоки в календаре
убираются, закреплённые тоже), и сразу считается превью плана — применяет
его, как всегда, только пользователь.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import BreakdownContext, PrevStep, breakdown_messages
from app.ai.schemas import AIBreakdown
from app.core.config import settings
from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc
from app.domain.breakdown import RawStep, normalize_steps, time_warning
from app.domain.enums import (
    AIOrigin,
    AIPurpose,
    EventStatus,
    JobKind,
    JobStatus,
    PlanReason,
    SourceType,
    SubtaskStatus,
)
from app.domain.planner import free_minutes
from app.models import (
    ActionType,
    Area,
    AreaType,
    BreakdownTemplate,
    Category,
    Event,
    Job,
    Project,
    Subtask,
    Task,
    User,
)
from app.schemas.ai import (
    BreakdownApply,
    BreakdownDraft,
    BreakdownRequest,
    BreakdownStep,
    TemplateCreate,
    TemplateRead,
    TemplateUpdate,
)
from app.services import jobs
from app.services.ai import call_llm, enqueue_ai
from app.services.ai_profile import AIContext, load_ai_context
from app.services.base import UserScopedRepository
from app.services.budgets import budget_index
from app.services.calibration import coefficients
from app.services.catalog import ensure_defaults, load_task_types
from app.services.replan import ReplanService, windows_from_json
from app.services.tasks import TaskRepo


@dataclass
class Catalog:
    """Типы действий пользователя: проверка ссылок шагов и шаблонов."""

    actions: dict[uuid.UUID, ActionType]


async def load_catalog(db: AsyncSession, user_id: uuid.UUID) -> Catalog:
    if await ensure_defaults(db, user_id):
        await db.flush()
    actions = await db.scalars(
        select(ActionType).where(ActionType.user_id == user_id, ActionType.deleted_at.is_(None))
    )
    return Catalog({a.id: a for a in actions})


class _TemplateRepo(UserScopedRepository[BreakdownTemplate]):
    model = BreakdownTemplate
    not_found_message = "Шаблон не найден"


class BreakdownService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.tasks = TaskRepo(db, user.id)
        self.templates = _TemplateRepo(db, user.id)

    # ---------- джоба ----------

    async def start(
        self,
        task_id: uuid.UUID,
        data: BreakdownRequest,
        *,
        origin: AIOrigin = AIOrigin.app,
        chat_id: int | None = None,
    ) -> uuid.UUID:
        task = await self.tasks.get_or_404(task_id)
        if task.recurrence:
            raise InvalidDataError("Регулярное задание не разбивается на шаги")
        payload: dict[str, Any] = {
            "task_id": str(task.id),
            "comment": data.comment,
            "previous": [s.model_dump(mode="json") for s in data.previous],
            "origin": origin,
        }
        if chat_id is not None:
            payload["chat_id"] = chat_id
        job_id = await enqueue_ai(
            self.db, JobKind.ai_breakdown, user_id=self.user_id, payload=payload
        )
        await self.db.commit()
        return job_id

    async def _free_minutes(self, task: Task, catalog: Catalog) -> int | None:
        if task.deadline is None:
            return None
        snap = await ReplanService(self.db, self.user).snapshot()
        at = catalog.actions.get(task.action_type_id) if task.action_type_id else None
        windows = windows_from_json(task.time_window or (at.windows if at else None))
        budgets = await budget_index(self.db, self.user_id, local_date(snap.inp.now, self.tz))
        return free_minutes(
            snap.inp,
            deadline=task.deadline,
            windows=windows,
            budgets=budgets.of(at.id if at else None),
            exclude_group=str(task.id),
        )

    async def context(
        self, task: Task, request: BreakdownRequest, ai: AIContext
    ) -> tuple[BreakdownContext, int | None, float]:
        """Контекст промпта, свободные минуты (в темпе пользователя) и коэффициент калибровки."""
        catalog = await load_catalog(self.db, self.user_id)
        coefs = await coefficients(self.db, self.user_id)
        coef = coefs.get((task.task_type_id, task.action_type_id), 1.0)
        free = await self._free_minutes(task, catalog)

        area = await self.db.get(Area, task.area_id) if task.area_id else None
        area_type = await self.db.get(AreaType, area.area_type_id) if area else None
        project = await self.db.get(Project, task.project_id) if task.project_id else None
        done = await self.db.scalars(
            select(Subtask.title)
            .where(
                Subtask.task_id == task.id,
                Subtask.user_id == self.user_id,
                Subtask.deleted_at.is_(None),
                Subtask.status == SubtaskStatus.done,
            )
            .order_by(Subtask.position)
        )
        now = now_utc().astimezone(self.tz)
        ctx = BreakdownContext(
            title=task.title,
            today=now.date(),
            task_type=ai.task_types.name_of(task.task_type_id),
            description=task.description,
            area=(f"{area.name} ({area_type.name})" if area_type else area.name) if area else None,
            project=project.title if project else None,
            deadline=task.deadline.astimezone(self.tz) if task.deadline else None,
            # ИИ оценивает «чистое» время; в темпе пользователя свободного как бы меньше
            free_minutes=round(free / coef) if free is not None else None,
            done_steps=list(done),
            previous=[PrevStep(s.title, s.estimate_min) for s in request.previous],
            comment=request.comment,
            profile=ai.profile,
        )
        return ctx, free, coef

    async def run(self, job: Job) -> BreakdownDraft:
        """Обработчик джобы: черновик в `job.result`."""
        payload = job.payload
        task = await self.tasks.get(uuid.UUID(payload["task_id"]))
        if task is None:
            raise jobs.JobFailedError("Задание удалено")
        request = BreakdownRequest(
            comment=payload.get("comment"),
            previous=[BreakdownStep.model_validate(s) for s in payload.get("previous") or []],
        )
        ai = await load_ai_context(self.db, self.user, local_date(now_utc(), self.tz))
        ctx, free, coef = await self.context(task, request, ai)
        answer = await call_llm(
            self.db,
            self.user_id,
            AIPurpose.breakdown,
            breakdown_messages(ctx),
            ai.schema(AIBreakdown),
            job_id=job.id,
        )
        draft = await self.to_draft(task, answer, free, coef, ai)
        job.result = draft.model_dump(mode="json")
        return draft

    async def to_draft(
        self,
        task: Task,
        answer: AIBreakdown,
        free: int | None,
        coef: float,
        ai: AIContext | None = None,
    ) -> BreakdownDraft:
        normalized = normalize_steps(
            [
                RawStep(
                    s.order, s.title, s.estimate_min, s.action_type, tuple(s.depends_on), s.note
                )
                for s in answer.subtasks
            ]
        )
        # Тип задачи ИИ уточняет, только если его не задали руками
        if ai is None:
            ai = await load_ai_context(self.db, self.user, local_date(now_utc(), self.tz))
        task_type_id = task.task_type_id or ai.task_types.id_of(answer.task_type)
        return BreakdownDraft(
            task_id=task.id,
            task_type_id=task_type_id,
            category_id=task.category_id or ai.category_id(answer.category),
            steps=[
                BreakdownStep(
                    title=s.title[:300],
                    estimate_min=s.estimate_min,
                    action_type_id=ai.action_id(s.action_type),
                    depends_on=list(s.depends_on),
                    note=s.note,
                )
                for s in normalized.steps
            ],
            total_estimate_min=normalized.total_estimate_min,
            warning=answer.warning,
            time_warning=time_warning(normalized.total_estimate_min, free, coef),
            free_minutes=free,
            coef=round(coef, 2),
        )

    # ---------- «Запланировать» ----------

    async def apply(self, task_id: uuid.UUID, data: BreakdownApply) -> Task:
        """Несделанные шаги → присланные. Блоки старых шагов убираются. Коммитит.

        Задание блокируется: параллельное «Запланировать» ждёт и заменяет уже
        записанные шаги, а не добавляет второй комплект."""
        task = await self.tasks.get_or_404(task_id, for_update=True)
        if task.recurrence:
            raise InvalidDataError("Регулярное задание не разбивается на шаги")
        catalog = await load_catalog(self.db, self.user_id)
        for s in data.steps:
            if s.action_type_id and s.action_type_id not in catalog.actions:
                raise InvalidDataError("Тип действия не найден")
        if data.task_type_id is not None:
            await self._check_task_type(data.task_type_id)
        if data.category_id is not None:
            category = await self.db.get(Category, data.category_id)
            if category is None or category.user_id != self.user_id or category.deleted_at:
                raise InvalidDataError("Категория не найдена")

        existing = list(
            await self.db.scalars(
                select(Subtask)
                .where(
                    Subtask.task_id == task.id,
                    Subtask.user_id == self.user_id,
                    Subtask.deleted_at.is_(None),
                )
                .order_by(Subtask.position, Subtask.created_at)
            )
        )
        done = [s for s in existing if s.status == SubtaskStatus.done]
        todo = [s for s in existing if s.status != SubtaskStatus.done]
        now = now_utc()
        if todo:
            events = await self.db.scalars(
                select(Event).where(
                    Event.user_id == self.user_id,
                    Event.deleted_at.is_(None),
                    Event.source_type == SourceType.subtask,
                    Event.source_id.in_([s.id for s in todo]),
                    Event.status == EventStatus.planned,
                )
            )
            for e in events:
                e.deleted_at = now
            for old in todo:
                old.deleted_at = now
        # Задание шло одним блоком (без шагов) — теперь блоки будут у шагов
        task_events = await self.db.scalars(
            select(Event).where(
                Event.user_id == self.user_id,
                Event.deleted_at.is_(None),
                Event.source_type == SourceType.task,
                Event.source_id == task.id,
                Event.status == EventStatus.planned,
            )
        )
        for e in task_events:
            e.deleted_at = now

        for position, kept in enumerate(done):
            kept.position = position
        ids = [uuid.uuid4() for _ in data.steps]
        for i, step in enumerate(data.steps):
            self.db.add(
                Subtask(
                    id=ids[i],
                    user_id=self.user_id,
                    task_id=task.id,
                    title=step.title,
                    estimate_min=step.estimate_min,
                    position=len(done) + i,
                    depends_on=[str(ids[d]) for d in step.depends_on],
                    status=SubtaskStatus.todo,
                    action_type_id=step.action_type_id,
                    note=step.note,
                )
            )
        if data.task_type_id is not None:
            task.task_type_id = data.task_type_id
        if data.category_id is not None:
            task.category_id = data.category_id
        if data.job_id is not None:
            await self.mark_applied(data.job_id)
        await self.db.commit()
        return task

    async def mark_applied(self, job_id: uuid.UUID) -> None:
        job = await self.db.scalar(select(Job).where(Job.id == job_id, Job.user_id == self.user_id))
        if job is not None and job.result is not None:
            job.result = {**job.result, "applied": True}

    async def latest_job(self, task_id: uuid.UUID) -> Job | None:
        """Последняя разбивка задания, которую ещё не применили: ждёт ИИ, считается
        или готова. Пользователь мог уйти со страницы — задание напомнит о ней."""
        await self.tasks.get_or_404(task_id)
        since = now_utc() - timedelta(hours=settings.LLM_QUEUE_MAX_HOURS)
        job = await self.db.scalar(
            select(Job)
            .where(
                Job.user_id == self.user_id,
                Job.kind == JobKind.ai_breakdown,
                Job.payload["task_id"].astext == str(task_id),
                Job.created_at >= since,
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        if job is None or job.status == JobStatus.failed:
            return None
        if job.status == JobStatus.done and (job.result or {}).get("applied"):
            return None
        return job

    async def apply_and_preview(self, task_id: uuid.UUID, data: BreakdownApply) -> bool:
        """`apply` + превью плана. True — превью посчитано."""
        await self.apply(task_id, data)
        if not data.plan:
            return False
        await ReplanService(self.db, self.user).preview([PlanReason.changes], force=True)
        return True

    # ---------- шаблоны ----------

    async def _check_task_type(self, task_type_id: uuid.UUID) -> None:
        if (await load_task_types(self.db, self.user_id)).name_of(task_type_id) is None:
            raise InvalidDataError("Тип задачи не найден")

    def _template_read(self, t: BreakdownTemplate, catalog: Catalog) -> TemplateRead:
        steps = []
        for s in t.steps:
            raw = s.get("action_type_id")
            type_id = uuid.UUID(raw) if raw else None
            steps.append(
                BreakdownStep(
                    title=s["title"],
                    estimate_min=s["estimate_min"],
                    # Удалённый тип действия — как «без типа»
                    action_type_id=type_id if type_id in catalog.actions else None,
                    depends_on=s.get("depends_on", []),
                    note=s.get("note", ""),
                )
            )
        return TemplateRead(
            id=t.id,
            name=t.name,
            task_type_id=t.task_type_id,
            steps=steps,
            total_estimate_min=sum(s.estimate_min for s in steps),
            created_at=t.created_at,
        )

    async def list_templates(self) -> list[TemplateRead]:
        catalog = await load_catalog(self.db, self.user_id)
        items = await self.templates.find_all(
            order_by=[func.lower(BreakdownTemplate.name), BreakdownTemplate.created_at]
        )
        return [self._template_read(t, catalog) for t in items]

    async def create_template(self, data: TemplateCreate) -> TemplateRead:
        catalog = await load_catalog(self.db, self.user_id)
        if data.task_type_id is not None:
            await self._check_task_type(data.task_type_id)
        steps = []
        for s in data.steps:
            if s.action_type_id and s.action_type_id not in catalog.actions:
                raise InvalidDataError("Тип действия не найден")
            steps.append(
                {
                    "title": s.title,
                    "estimate_min": s.estimate_min,
                    "action_type_id": str(s.action_type_id) if s.action_type_id else None,
                    "depends_on": s.depends_on,
                    "note": s.note,
                }
            )
        t = BreakdownTemplate(
            user_id=self.user_id, name=data.name, task_type_id=data.task_type_id, steps=steps
        )
        self.db.add(t)
        await self.db.commit()
        await self.db.refresh(t)
        return self._template_read(t, catalog)

    async def update_template(self, id: uuid.UUID, data: TemplateUpdate) -> TemplateRead:
        t = await self.templates.get_or_404(id)
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes and changes["name"] is None:
            raise InvalidDataError("name: не может быть пустым")
        if changes.get("task_type_id") is not None:
            await self._check_task_type(changes["task_type_id"])
        for name, value in changes.items():
            setattr(t, name, value)
        await self.db.commit()
        await self.db.refresh(t)
        return self._template_read(t, await load_catalog(self.db, self.user_id))

    async def delete_template(self, id: uuid.UUID) -> None:
        t = await self.templates.get_or_404(id)
        self.templates.soft_delete(t)
        await self.db.commit()
