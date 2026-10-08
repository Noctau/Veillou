"""Перепланирование (M9.1): БД → `PlanInput` → solve → превью → apply → undo.

Что планируется:
- подзадачи `todo` активных заданий (оценка × коэффициент калибровки);
- задание без подзадач, но с оценкой — одним блоком (`source_type=task`);
- вхождение регулярного задания — только в свой день, без разрезания;
- дела из ящика, взятые на неделю (M11.2): только в оставшееся после учёбы
  время своей недели, в окна по условиям (`domain/backlog.py`);
- дни подготовки к экзамену (M12.2): каждый — в свой день, до начала экзамена;
- недельная норма проекта (M13.1) на текущую и следующую неделю: шаги заданий
  проекта засчитываются в норму, на недостающее — резервные блоки «работа над
  проектом» (ставятся, только если без них норма не набирается).

Что не трогаем: жёсткие события, закреплённые блоки, уже начавшиеся и
сделанные сегодня (они занимают время, считаются в дневные лимиты и уменьшают
остаток оценки: перетащили одну часть разрезанного блока — вторая остаётся).
Незакреплённые будущие блоки — это «прошлый план»: планировщик старается
их не двигать. Неотмеченные блоки прошлых дней в превью становятся `missed`.

Порядок: превью (ревизия `proposed`) → «Применить» → `applied` (+ данные для
отката) → «Отменить» → `undone`. Перед применением вход планировщика
собирается заново; если он изменился (новое задание, сдвинулось расписание,
блок начался), превью устарело — считаем новое и отвечаем 409.
"""

import asyncio
import hashlib
import json
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.core.time import get_tz, local_date, now_utc, wall_to_utc
from app.domain import backlog as box
from app.domain import projects as proj
from app.domain.calibration import calibrated
from app.domain.enums import (
    FIXED_KINDS,
    ActionTypeKey,
    BacklogCondition,
    BacklogStatus,
    EventKind,
    EventStatus,
    ExamSessionKind,
    ExamSessionStatus,
    PlanReason,
    PlanRevisionStatus,
    Priority,
    ProjectStatus,
    SourceType,
    SubtaskStatus,
    TaskStatus,
)
from app.domain.exams import exam_title, session_title
from app.domain.planner import (
    Block,
    Busy,
    FixedBlock,
    Placement,
    PlanInput,
    PlanResult,
    PlanSettings,
    Quota,
    TimeRange,
    Window,
    solve,
)
from app.models import (
    ActionType,
    BacklogItem,
    Category,
    Event,
    Exam,
    ExamQuestion,
    ExamSession,
    Job,
    PlanRevision,
    Project,
    StudyDayLimit,
    Subject,
    Subtask,
    Task,
    User,
)
from app.schemas.plan import PlanRevisionRead, PlanState
from app.schemas.settings import UserSettings
from app.services import exams
from app.services.calibration import DEFAULT_ACTION, coefficients
from app.services.settings import effective_settings

# Флаг сессии: правки делает сам планировщик — не запускать пересчёт по триггеру
SKIP_REPLAN = "skip_replan"

PRIORITY_WEIGHT = {Priority.normal: 1, Priority.high: 3}
PLANNED_SOURCES = (
    SourceType.subtask,
    SourceType.task,
    SourceType.backlog_item,
    SourceType.exam_session,
    SourceType.project,
)
# Подготовка к экзамену: день не сдвинуть — важнее обычных шагов
EXAM_PRIORITY = 3
SESSION_ORDER = {ExamSessionKind.learn: 0, ExamSessionKind.review: 1, ExamSessionKind.run: 2}
MAX_HORIZON_DAYS = 60
# Остаток короче — блок не нужен
MIN_BLOCK_MIN = 15
# Откатить можно только недавнее применение
UNDO_TTL = timedelta(hours=24)


class PlanStaleError(AppError):
    status_code = 409
    code = "plan_stale"
    message = "План успел измениться — пересчитали превью"


def plan_settings(s: UserSettings) -> PlanSettings:
    return PlanSettings(
        work_weekdays=TimeRange(s.work_hours.weekdays.start, s.work_hours.weekdays.end),
        work_weekends=TimeRange(s.work_hours.weekends.start, s.work_hours.weekends.end),
        sleep=TimeRange(s.sleep.start, s.sleep.end),
        lunch=TimeRange(s.lunch.start, s.lunch.end),
        travel_buffer_min=s.travel_buffer_min,
        study_limit_min_per_day=s.study_limit_min_per_day,
        deadline_buffer_days=s.deadline_buffer_days,
        free_evenings_per_week=s.rest.free_evenings_per_week,
        weekend_half_days=s.rest.weekend_half_days,
    )


def windows_from_json(raw: Iterable[dict[str, Any]] | None) -> tuple[Window, ...]:
    return tuple(
        Window(
            frozenset(w["weekdays"]), time.fromisoformat(w["start"]), time.fromisoformat(w["end"])
        )
        for w in raw or ()
    )


def _slot(start: datetime, end: datetime) -> dict[str, str]:
    return {"start": start.isoformat(), "end": end.isoformat()}


def _moment(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def _hash(data: Any) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def block_id(source_type: SourceType, source_id: uuid.UUID) -> str:
    return f"{source_type}:{source_id}"


def fixed_id(event_id: uuid.UUID) -> str:
    return f"event:{event_id}"


def project_tag(project_id: uuid.UUID) -> str:
    """Метка нормы проекта и группа его резервных блоков (≤ N в день)."""
    return f"project:{project_id}"


def quota_id(project_id: uuid.UUID, week: date) -> str:
    return f"quota:{project_id}:{week.isoformat()}"


def reserve_id(project_id: uuid.UUID, week: date, k: int) -> str:
    return f"{project_tag(project_id)}:{week.isoformat()}:{k}"


@dataclass
class Source:
    """Что стоит за блоком планировщика."""

    source_type: SourceType
    source_id: uuid.UUID
    kind: EventKind  # каким событием встаёт в календарь
    title: str
    color: str | None
    # К чему относится: задание / дело из ящика / экзамен — для угроз и шторки
    group_kind: str
    group_id: uuid.UUID
    group_title: str
    deadline: datetime | None = None
    subject_id: uuid.UUID | None = None
    # Незакреплённые будущие блоки этого источника — «прошлый план»
    events: list[Event] = field(default_factory=list)

    @property
    def task_id(self) -> uuid.UUID | None:
        return self.group_id if self.group_kind == "task" else None


@dataclass
class Snapshot:
    inp: PlanInput
    sources: dict[str, Source]
    # Будущие незакреплённые блоки, которым больше нечего планировать (сделано, удалено)
    orphans: list[Event]
    # Неотмеченные блоки прошлых дней → missed
    stale: list[Event]
    fingerprint: str


class _Builder:
    """Собирает вход планировщика из БД."""

    def __init__(self, db: AsyncSession, user: User, now: datetime) -> None:
        self.db = db
        self.user_id = user.id
        self.now = now
        self.tz = get_tz(user.timezone)
        self.settings = effective_settings(user)
        self.today = local_date(now, self.tz)
        self.day_start = wall_to_utc(self.today, time(0), self.tz)
        self.horizon_end = now + timedelta(days=MAX_HORIZON_DAYS)

    async def _scalars[M](
        self, model: type[M], *where: Any, order_by: Sequence[Any] = ()
    ) -> list[M]:
        stmt = (
            select(model)
            .where(model.user_id == self.user_id, model.deleted_at.is_(None), *where)  # type: ignore[attr-defined]
            .order_by(*order_by)
        )
        return list(await self.db.scalars(stmt))

    async def build(self) -> Snapshot:
        s = self.settings
        action_types = {a.id: a for a in await self._scalars(ActionType)}
        types_by_key = {a.key: a for a in action_types.values() if a.key}
        colors = {c.id: c.color for c in await self._scalars(Category)}
        coefs = await coefficients(self.db, self.user_id)
        limits = await self._scalars(StudyDayLimit, StudyDayLimit.date >= self.today)

        hard = await self._scalars(
            Event,
            Event.kind.in_(FIXED_KINDS),
            Event.status != EventStatus.cancelled,
            Event.end > self.day_start,
            Event.start < self.horizon_end,
            order_by=[Event.start, Event.id],
        )
        busy = tuple(Busy(e.start, e.end, is_class=e.kind == EventKind.class_) for e in hard)
        class_days = frozenset(
            local_date(e.start, self.tz) for e in hard if e.kind == EventKind.class_
        )

        flexible = await self._scalars(
            Event,
            Event.kind.not_in(FIXED_KINDS),
            Event.status.in_([EventStatus.planned, EventStatus.done]),
            or_(Event.status == EventStatus.planned, Event.start >= self.day_start),
            Event.start < self.horizon_end,
            order_by=[Event.start, Event.id],
        )
        tasks = await self._scalars(
            Task, Task.status == TaskStatus.active, order_by=[Task.created_at, Task.id]
        )
        task_by_id = {t.id: t for t in tasks}
        subtasks = await self._scalars(
            Subtask,
            Subtask.task_id.in_(task_by_id),
            order_by=[Subtask.position, Subtask.occurrence_date, Subtask.created_at, Subtask.id],
        )
        subs_by_task: dict[uuid.UUID, list[Subtask]] = defaultdict(list)
        for st in subtasks:
            subs_by_task[st.task_id].append(st)
        subtask_by_id = {st.id: st for st in subtasks}
        this_week = box.week_start(self.today)
        items = await self._scalars(
            BacklogItem,
            BacklogItem.status == BacklogStatus.active,
            BacklogItem.planned_week >= this_week,
            order_by=[BacklogItem.created_at, BacklogItem.id],
        )
        item_by_id = {i.id: i for i in items}
        exams = await self._scalars(
            Exam, Exam.plan_enabled.is_(True), Exam.starts_at > self.now, order_by=[Exam.starts_at]
        )
        exam_by_id = {e.id: e for e in exams}
        sessions = await self._scalars(
            ExamSession,
            ExamSession.exam_id.in_(exam_by_id),
            ExamSession.status == ExamSessionStatus.planned,
            ExamSession.date >= self.today,
            order_by=[ExamSession.date, ExamSession.kind, ExamSession.id],
        )
        session_by_id = {x.id: x for x in sessions}
        numbers = {
            str(q.id): q.number
            for q in await self._scalars(ExamQuestion, ExamQuestion.exam_id.in_(exam_by_id))
        }
        subjects = {
            x.id: x for x in await self._scalars(Subject) if x.id in {e.subject_id for e in exams}
        }
        # Проекты с недельной нормой (итоговый срок ещё не прошёл)
        projects = {
            p.id: p
            for p in await self._scalars(
                Project,
                Project.status == ProjectStatus.active,
                Project.weekly_norm_min > 0,
                order_by=[Project.created_at, Project.id],
            )
            if p.deadline is None or p.deadline >= self.today
        }

        def task_quota(task: Task) -> str | None:
            return project_tag(task.project_id) if task.project_id in projects else None

        def type_key(type_id: uuid.UUID | None) -> str:
            at = action_types.get(type_id) if type_id else None
            return at.key if at else DEFAULT_ACTION

        def action_key(task: Task, st: Subtask | None) -> str:
            return type_key((st.action_type_id if st else None) or task.action_type_id)

        def type_windows(key: str) -> tuple[Window, ...]:
            at = types_by_key.get(key)
            return windows_from_json(at.windows) if at else ()

        def windows(task: Task, st: Subtask | None) -> tuple[Window, ...]:
            if st is not None and st.time_window:
                return windows_from_json(st.time_window)
            if task.time_window:
                return windows_from_json(task.time_window)
            type_id = (st.action_type_id if st else None) or task.action_type_id
            at = action_types.get(type_id) if type_id else None
            return windows_from_json(at.windows) if at else ()

        def owner_of(e: Event) -> tuple[str | None, bool, str | None]:
            """(группа для «≤ N в день», считается ли учёбой, метка нормы) — для
            занятого времени."""
            if e.source_type == SourceType.subtask:
                st = subtask_by_id.get(e.source_id)  # type: ignore[arg-type]
                task = task_by_id.get(st.task_id) if st else None
            elif e.source_type == SourceType.task:
                task, st = task_by_id.get(e.source_id), None  # type: ignore[arg-type]
            elif e.source_type == SourceType.exam_session:
                sess = session_by_id.get(e.source_id)  # type: ignore[arg-type]
                return (f"exam:{sess.exam_id}" if sess else None), True, None
            elif e.source_type == SourceType.backlog_item:
                item = item_by_id.get(e.source_id)  # type: ignore[arg-type]
                return None, item is not None and type_key(item.action_type_id) == "study", None
            elif e.source_type == SourceType.project and e.source_id is not None:
                tag = project_tag(e.source_id)
                return tag, True, (tag if e.source_id in projects else None)
            else:
                return None, False, None
            if task is None:
                return None, False, None
            return str(task.id), action_key(task, st) == ActionTypeKey.study, task_quota(task)

        # ---------- гибкие события: что занято, что можно двигать ----------
        fixed: list[FixedBlock] = []
        fixed_by_source: dict[str, list[str]] = defaultdict(list)
        # (метка нормы, неделя) → минут закреплено/сделано с сегодняшнего дня
        fixed_quota: dict[tuple[str, date], int] = defaultdict(int)
        # Минут уже стоит намертво (закреплено, идёт, сделано) — блок планируем на остаток
        consumed: dict[str, int] = defaultdict(int)
        movable: dict[str, list[Event]] = defaultdict(list)
        stale: list[Event] = []
        for e in flexible:
            ours = e.source_type in PLANNED_SOURCES and e.source_id is not None
            key = block_id(SourceType(e.source_type), e.source_id) if ours else None  # type: ignore[arg-type]
            if e.status == EventStatus.planned and e.end <= self.day_start:
                if ours:
                    stale.append(e)
                continue
            minutes = round((e.end - e.start).total_seconds() / 60)
            is_fixed = not ours or e.status == EventStatus.done or e.is_pinned or e.start < self.now
            if is_fixed:
                group, study, quota = owner_of(e)
                fixed.append(
                    FixedBlock(
                        fixed_id(e.id),
                        e.start,
                        e.end,
                        group_id=group,
                        counts_as_study=study,
                        quota=quota,
                    )
                )
                if quota is not None:
                    week = box.week_start(local_date(e.start, self.tz))
                    fixed_quota[(quota, week)] += minutes
                if key:
                    fixed_by_source[key].append(fixed_id(e.id))
                    consumed[key] += minutes
            else:
                movable[key].append(e)  # type: ignore[index]

        # «Не сделано» сегодня (вечерний разбор) — переносим не раньше завтра
        missed_today = set(
            await self.db.scalars(
                select(Event.source_id).where(
                    Event.user_id == self.user_id,
                    Event.deleted_at.is_(None),
                    Event.status == EventStatus.missed,
                    Event.source_type.in_(PLANNED_SOURCES),
                    Event.start >= self.day_start,
                )
            )
        )
        tomorrow = wall_to_utc(self.today + timedelta(days=1), time(0), self.tz)

        # Задание без подзадач: сделанные блоки прошлых дней тоже уменьшают остаток
        done_rows = await self.db.execute(
            select(Event.source_id, Event.start, Event.end).where(
                Event.user_id == self.user_id,
                Event.deleted_at.is_(None),
                Event.source_type == SourceType.task,
                Event.status == EventStatus.done,
                Event.start < self.day_start,
            )
        )
        for source_id, start, end in done_rows.all():
            consumed[block_id(SourceType.task, source_id)] += round(
                (end - start).total_seconds() / 60
            )

        # ---------- блоки ----------
        blocks: list[Block] = []
        sources: dict[str, Source] = {}

        def add(block: Block, source: Source) -> None:
            # …если срок позволяет: сдать сегодня — пусть лучше сегодня же вечером
            if source.source_id in missed_today and (
                block.deadline is None or block.deadline > tomorrow
            ):
                block = replace(block, earliest=max(block.earliest or tomorrow, tomorrow))
            blocks.append(block)
            source.events = movable.pop(str(block.id), [])
            sources[str(block.id)] = source

        for task in tasks:
            subs = subs_by_task.get(task.id, [])
            todo: list[tuple[SourceType, uuid.UUID, Subtask | None, int]] = []
            if subs:
                for st in subs:
                    if st.status == SubtaskStatus.todo:
                        todo.append((SourceType.subtask, st.id, st, st.estimate_min))
            elif task.estimate_min:
                todo.append((SourceType.task, task.id, None, task.estimate_min))

            for source_type, source_id, st, estimate in todo:
                key = block_id(source_type, source_id)
                occurrence = st.occurrence_date if st else None
                if occurrence is not None and occurrence < self.today:
                    continue
                act = action_key(task, st)
                coef = coefs.get((task.task_type, act), 1.0)
                remaining = calibrated(estimate, coef) - consumed.get(key, 0)
                if remaining < MIN_BLOCK_MIN:
                    continue
                deadline, earliest, buffer = task.deadline, None, task.deadline_buffer_days
                if occurrence is not None:
                    earliest = wall_to_utc(occurrence, time(0), self.tz)
                    day_end = wall_to_utc(occurrence + timedelta(days=1), time(0), self.tz)
                    deadline = min(deadline, day_end) if deadline else day_end
                    buffer = 0
                deps: list[str] = []
                for dep in st.depends_on if st else ():
                    dep_key = block_id(SourceType.subtask, uuid.UUID(dep))
                    dep_st = subtask_by_id.get(uuid.UUID(dep))
                    if dep_st is None or dep_st.status == SubtaskStatus.done:
                        continue
                    # После всех её блоков: и закреплённых, и того, что ещё поставим
                    deps.append(dep_key)
                    deps.extend(fixed_by_source.get(dep_key, []))
                category_id = (st.category_id if st else None) or task.category_id
                add(
                    Block(
                        id=key,
                        duration_min=remaining,
                        group_id=str(task.id),
                        deadline=deadline,
                        priority=PRIORITY_WEIGHT.get(Priority(task.priority), 1),
                        windows=windows(task, st),
                        depends_on=tuple(deps),
                        splittable=occurrence is None,
                        counts_as_study=act == ActionTypeKey.study,
                        prefer_morning=act == ActionTypeKey.people,
                        earliest=earliest,
                        buffer_days=buffer,
                        sequence=st.position if st else None,
                        quota=task_quota(task),
                    ),
                    Source(
                        source_type,
                        source_id,
                        EventKind.subtask,
                        st.title if st else task.title,
                        colors.get(category_id) if category_id else None,
                        "task",
                        task.id,
                        task.title,
                        deadline=task.deadline,
                        subject_id=task.subject_id,
                    ),
                )

        # Дела из ящика, взятые на неделю: только в своей неделе, после учёбы
        work = (
            Window(
                frozenset({1, 2, 3, 4, 5}), s.work_hours.weekdays.start, s.work_hours.weekdays.end
            ),
            Window(frozenset({6, 7}), s.work_hours.weekends.start, s.work_hours.weekends.end),
        )
        for item in items:
            key = block_id(SourceType.backlog_item, item.id)
            remaining = (item.estimate_min or box.DEFAULT_ESTIMATE_MIN) - consumed.get(key, 0)
            if remaining < MIN_BLOCK_MIN:
                continue
            act = type_key(item.action_type_id)
            base = (
                windows_from_json(item.time_window)
                if item.time_window
                else (type_windows(act) if item.action_type_id else ()) or work
            )
            week = item.planned_week
            assert week is not None
            add(
                Block(
                    id=key,
                    duration_min=remaining,
                    deadline=wall_to_utc(week + timedelta(days=7), time(0), self.tz),
                    earliest=wall_to_utc(week, time(0), self.tz),
                    buffer_days=0,
                    priority=box.priority(
                        local_date(item.created_at, self.tz), item.desired_by, self.today
                    ),
                    windows=box.condition_windows(
                        base, item.conditions, type_windows(ActionTypeKey.institutions)
                    ),
                    days=class_days if BacklogCondition.on_class_days in item.conditions else None,
                    counts_as_study=act == ActionTypeKey.study,
                    prefer_morning=act == ActionTypeKey.people,
                    filler=True,
                ),
                Source(
                    SourceType.backlog_item,
                    item.id,
                    EventKind.backlog,
                    item.title,
                    colors.get(item.category_id) if item.category_id else None,
                    "backlog",
                    item.id,
                    item.title,
                ),
            )

        # Подготовка к экзаменам: каждый день плана — в свой день, до экзамена
        study_windows = type_windows(ActionTypeKey.study)
        for sess in sessions:
            exam = exam_by_id[sess.exam_id]
            key = block_id(SourceType.exam_session, sess.id)
            remaining = sess.minutes - consumed.get(key, 0)
            if remaining < MIN_BLOCK_MIN:
                continue
            subject = subjects.get(exam.subject_id)
            name = subject.short_name or subject.name if subject else "экзамен"
            day_end = wall_to_utc(sess.date + timedelta(days=1), time(0), self.tz)
            add(
                Block(
                    id=key,
                    duration_min=remaining,
                    group_id=f"exam:{exam.id}",
                    deadline=min(day_end, exam.starts_at),
                    earliest=wall_to_utc(sess.date, time(0), self.tz),
                    buffer_days=0,
                    priority=EXAM_PRIORITY,
                    windows=study_windows,
                    splittable=True,
                    # Сквозной порядок по дням: в день — сначала выучить, потом повторить
                    sequence=sess.date.toordinal() * 3
                    + SESSION_ORDER.get(ExamSessionKind(sess.kind), 0),
                ),
                Source(
                    SourceType.exam_session,
                    sess.id,
                    EventKind.exam_prep,
                    session_title(
                        ExamSessionKind(sess.kind),
                        name,
                        [numbers[q] for q in sess.question_ids if q in numbers],
                    ),
                    None,  # цвет слоя «Экзамены», чтобы не путать с парами
                    "exam",
                    exam.id,
                    exam_title(exam.title, subject.name if subject else None),
                    deadline=exam.starts_at,
                    subject_id=exam.subject_id,
                ),
            )

        # Недельная норма проекта: текущая и следующая неделя
        quotas: list[Quota] = []
        done_before = await self._project_done_before_today(projects, this_week)
        for project in projects.values():
            tag = project_tag(project.id)
            norm = project.weekly_norm_min or 0
            # Резервные блоки проекта — по неделям, по порядку: k-й блок недели ↔ k-е событие
            by_week: dict[date, list[Event]] = defaultdict(list)
            for e in movable.pop(block_id(SourceType.project, project.id), []):
                by_week[box.week_start(local_date(e.start, self.tz))].append(e)
            last = project.deadline + timedelta(days=1) if project.deadline else None
            for i in range(proj.QUOTA_WEEKS):
                week = this_week + timedelta(weeks=i)
                end = min(week + timedelta(days=7), last or date.max)
                if end <= max(week, self.today):
                    break
                target = (
                    proj.week_target(norm, done_before.get(project.id, 0), 7 - self.today.weekday())
                    if i == 0
                    else norm
                )
                events = sorted(by_week.pop(week, []), key=lambda e: (e.start, e.id))
                if target <= 0:
                    by_week[week] = events
                    continue
                qid = quota_id(project.id, week)
                quotas.append(Quota(qid, tag, week, end, target))
                week_end = wall_to_utc(end, time(0), self.tz)
                color = colors.get(project.category_id) if project.category_id else None
                sources[qid] = Source(
                    SourceType.project,
                    project.id,
                    EventKind.project,
                    f"неделя с {week:%d.%m}",
                    color,
                    "project",
                    project.id,
                    project.title,
                    deadline=week_end,
                )
                chunks = proj.reserve_chunks(target - fixed_quota[(tag, week)])
                for k, minutes in enumerate(chunks):
                    key = reserve_id(project.id, week, k)
                    if k < len(events):
                        movable[key] = [events[k]]
                    add(
                        Block(
                            id=key,
                            duration_min=minutes,
                            group_id=tag,
                            deadline=week_end,
                            earliest=wall_to_utc(week, time(0), self.tz),
                            buffer_days=0,
                            windows=study_windows,
                            quota=tag,
                            reserve=True,
                        ),
                        Source(
                            SourceType.project,
                            project.id,
                            EventKind.project,
                            proj.reserve_title(project.title),
                            color,
                            "project",
                            project.id,
                            project.title,
                        ),
                    )
                by_week[week] = events[len(chunks) :]
            # Лишние резервные блоки (норму уменьшили, неделя вне горизонта) — убрать
            for week, events in by_week.items():
                if events:
                    movable[f"{tag}:{week.isoformat()}:rest"] = events

        # Зависимость от подзадачи, у которой нет блока (уже идёт / вне плана), — не держим
        known = set(sources) | {f.id for f in fixed}
        blocks = [
            replace(b, depends_on=tuple(d for d in b.depends_on if d in known)) for b in blocks
        ]
        orphans = [e for events in movable.values() for e in events]
        previous = tuple(
            Placement(key, k, e.start, e.end)
            for key, src in sources.items()
            for k, e in enumerate(src.events[:2])
        )
        inp = PlanInput(
            now=self.now,
            tz=self.tz,
            blocks=tuple(blocks),
            busy=busy,
            fixed=tuple(fixed),
            previous=previous,
            settings=plan_settings(s),
            study_limits=tuple((lim.date, lim.minutes) for lim in limits),
            quotas=tuple(quotas),
            max_horizon_days=MAX_HORIZON_DAYS,
        )
        fingerprint = _hash(
            [
                repr(inp.blocks),
                repr(inp.busy),
                repr(inp.fixed),
                repr(inp.previous),
                repr(inp.settings),
                repr(inp.study_limits),
                repr(inp.quotas),
                sorted(str(e.id) for e in orphans),
                sorted(str(e.id) for e in stale),
                sorted(f"{k}:{src.title}" for k, src in sources.items()),
                self.tz.key,
            ]
        )
        return Snapshot(inp, sources, orphans, stale, fingerprint)

    async def _project_done_before_today(
        self, projects: dict[uuid.UUID, Project], week: date
    ) -> dict[uuid.UUID, int]:
        """Минуты, отмеченные «сделано» в проекте с начала недели до сегодня."""
        if not projects:
            return {}
        rows = (
            await self.db.execute(
                select(Event.source_type, Event.source_id, Event.start, Event.end).where(
                    Event.user_id == self.user_id,
                    Event.deleted_at.is_(None),
                    Event.status == EventStatus.done,
                    Event.source_type.in_(
                        [SourceType.project, SourceType.subtask, SourceType.task]
                    ),
                    Event.start >= wall_to_utc(week, time(0), self.tz),
                    Event.start < self.day_start,
                )
            )
        ).all()
        sub_ids = {sid for kind, sid, *_ in rows if kind == SourceType.subtask}
        sub_task = (
            dict(
                (
                    await self.db.execute(
                        select(Subtask.id, Subtask.task_id).where(Subtask.id.in_(sub_ids))
                    )
                ).all()
            )
            if sub_ids
            else {}
        )
        task_ids = {sid for kind, sid, *_ in rows if kind == SourceType.task} | set(
            sub_task.values()
        )
        task_project = (
            dict(
                (
                    await self.db.execute(
                        select(Task.id, Task.project_id).where(
                            Task.user_id == self.user_id, Task.id.in_(task_ids)
                        )
                    )
                ).all()
            )
            if task_ids
            else {}
        )
        result: dict[uuid.UUID, int] = defaultdict(int)
        for kind, sid, start, end in rows:
            if kind == SourceType.project:
                pid = sid
            elif kind == SourceType.subtask:
                pid = task_project.get(sub_task.get(sid))
            else:
                pid = task_project.get(sid)
            if pid in projects:
                result[pid] += round((end - start).total_seconds() / 60)
        return result


# ---------- превью ----------


def _risk_dicts(result: PlanResult, sources: dict[str, Source]) -> list[dict[str, Any]]:
    risks = []
    for r in result.at_risk:
        src = sources.get(str(r.block_id))
        if src is None:
            continue
        risks.append(
            {
                "block_id": str(r.block_id),
                "group_kind": src.group_kind,
                "group_id": str(src.group_id),
                "group_title": src.group_title,
                "task_id": str(src.task_id) if src.task_id else None,
                "source_type": str(src.source_type),
                "source_id": str(src.source_id),
                "title": src.title,
                "reason": str(r.reason),
                "deadline": src.deadline.isoformat() if src.deadline else None,
            }
        )
    return risks


def _ops(snap: Snapshot, result: PlanResult) -> list[dict[str, Any]]:
    by_block: dict[str, list[Placement]] = defaultdict(list)
    for p in result.placements:
        by_block[str(p.block_id)].append(p)
    ops: list[dict[str, Any]] = []
    for key, src in snap.sources.items():
        base = {
            "task_id": str(src.task_id) if src.task_id else None,
            "kind": str(src.kind),
            "title": src.title,
            "source_type": str(src.source_type),
            "source_id": str(src.source_id),
        }
        placements = sorted(by_block.get(key, []), key=lambda p: p.part)
        for k, p in enumerate(placements):
            if k < len(src.events):
                e = src.events[k]
                if (e.start, e.end) != (p.start, p.end):
                    ops.append(
                        {
                            "op": "move",
                            "event_id": str(e.id),
                            **base,
                            "before": _slot(e.start, e.end),
                            "after": _slot(p.start, p.end),
                        }
                    )
            else:
                ops.append(
                    {
                        "op": "add",
                        "event_id": None,
                        **base,
                        "before": None,
                        "after": _slot(p.start, p.end),
                        "subject_id": str(src.subject_id) if src.subject_id else None,
                        "color": src.color,
                    }
                )
        for e in src.events[len(placements) :]:
            ops.append(
                {
                    "op": "remove",
                    "event_id": str(e.id),
                    **base,
                    "before": _slot(e.start, e.end),
                    "after": None,
                }
            )
    for op, events in (("remove", snap.orphans), ("miss", snap.stale)):
        for e in events:
            ops.append(
                {
                    "op": op,
                    "event_id": str(e.id),
                    "task_id": None,
                    "kind": e.kind,
                    "title": e.title,
                    "source_type": e.source_type,
                    "source_id": str(e.source_id) if e.source_id else None,
                    "before": _slot(e.start, e.end),
                    "after": None,
                }
            )
    return ops


def _stats(result: PlanResult) -> dict[str, Any]:
    st = result.stats
    return {
        "engine": st.engine,
        "status": st.status,
        "blocks": st.blocks,
        "placed": st.placed,
        "elapsed_ms": st.elapsed_ms,
    }


class ReplanService:
    # Бюджет солвера; тесты уменьшают
    time_limit_s: float = 2.0

    def __init__(self, db: AsyncSession, user: User, now: datetime | None = None) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self._now = now

    def now(self) -> datetime:
        return self._now or now_utc()

    async def snapshot(self) -> Snapshot:
        return await _Builder(self.db, self.user, self.now()).build()

    async def _solve(self, snap: Snapshot) -> PlanResult:
        inp = replace(snap.inp, time_limit_s=self.time_limit_s)
        return await asyncio.to_thread(solve, inp)

    # ---------- чтение ----------

    async def proposal(self) -> PlanRevision | None:
        return await self.db.scalar(
            select(PlanRevision).where(
                PlanRevision.user_id == self.user_id,
                PlanRevision.deleted_at.is_(None),
                PlanRevision.status == PlanRevisionStatus.proposed,
            )
        )

    async def undoable(self) -> PlanRevision | None:
        return await self.db.scalar(
            select(PlanRevision)
            .where(
                PlanRevision.user_id == self.user_id,
                PlanRevision.deleted_at.is_(None),
                PlanRevision.status == PlanRevisionStatus.applied,
                PlanRevision.applied_at > self.now() - UNDO_TTL,
            )
            .order_by(PlanRevision.applied_at.desc())
            .limit(1)
        )

    async def _last_closed(self, status: PlanRevisionStatus) -> PlanRevision | None:
        return await self.db.scalar(
            select(PlanRevision)
            .where(
                PlanRevision.user_id == self.user_id,
                PlanRevision.deleted_at.is_(None),
                PlanRevision.status == status,
            )
            .order_by(PlanRevision.updated_at.desc())
            .limit(1)
        )

    async def _get(self, id: uuid.UUID) -> PlanRevision:
        rev = await self.db.scalar(
            select(PlanRevision).where(
                PlanRevision.id == id,
                PlanRevision.user_id == self.user_id,
                PlanRevision.deleted_at.is_(None),
            )
        )
        if rev is None:
            raise NotFoundError("Превью не найдено")
        return rev

    # ---------- превью ----------

    async def preview(
        self, reasons: Sequence[PlanReason] = (PlanReason.manual,), *, force: bool = False
    ) -> PlanRevision | None:
        """Считает план и сохраняет его как ожидающее превью. Коммитит.

        None — менять нечего (и угроз нет). Превью, совпадающее с уже
        отклонённым, не показываем снова, если только не `force` (кнопка).
        """
        snap = await self.snapshot()
        result = await self._solve(snap)
        ops = _ops(snap, result)
        at_risk = _risk_dicts(result, snap.sources)
        content = _hash([ops, sorted(r["block_id"] + r["reason"] for r in at_risk)])
        current = await self.proposal()

        if current is not None and current.content_hash == content:
            current.fingerprint = snap.fingerprint
            current.reasons = sorted({*current.reasons, *map(str, reasons)})
            current.stats = _stats(result)
            await self.db.commit()
            return current

        quiet = not ops and not at_risk
        if not quiet and not ops and not force:
            # Только угрозы — и те же, что уже видели при последнем применении
            applied = await self._last_closed(PlanRevisionStatus.applied)
            if applied is not None and _risk_keys(applied.at_risk) == _risk_keys(at_risk):
                quiet = True
        if not quiet and not force:
            dismissed = await self._last_closed(PlanRevisionStatus.dismissed)
            if dismissed is not None and dismissed.content_hash == content:
                quiet = True

        if current is not None:
            current.status = PlanRevisionStatus.superseded
            await self.db.flush()
        if quiet:
            await self.db.commit()
            return None
        rev = PlanRevision(
            user_id=self.user_id,
            status=PlanRevisionStatus.proposed,
            reasons=sorted(map(str, reasons)),
            fingerprint=snap.fingerprint,
            content_hash=content,
            ops=ops,
            at_risk=at_risk,
            stats=_stats(result),
            undo=[],
        )
        self.db.add(rev)
        try:
            await self.db.commit()
        except IntegrityError:
            # Параллельно (джоба и кнопка) уже сохранили своё превью — берём его
            await self.db.rollback()
            return await self.proposal()
        return rev

    async def dismiss(self, id: uuid.UUID) -> None:
        rev = await self._get(id)
        if rev.status == PlanRevisionStatus.proposed:
            rev.status = PlanRevisionStatus.dismissed
            await self.db.commit()

    # ---------- применение ----------

    async def apply(self, id: uuid.UUID) -> PlanRevision:
        rev = await self._get(id)
        if rev.status != PlanRevisionStatus.proposed:
            raise PlanStaleError("Это превью уже неактуально")
        now = self.now()
        snap = await self.snapshot()
        fresh = snap.fingerprint == rev.fingerprint and all(
            _moment(op["after"]["start"]) >= now for op in rev.ops if op["after"]
        )
        self.db.info[SKIP_REPLAN] = True
        try:
            undo = await self._execute(rev.ops) if fresh else None
            if undo is not None:
                rev.status = PlanRevisionStatus.applied
                rev.applied_at = now
                rev.undo = undo
                await self.db.commit()
                return rev
            await self.db.rollback()
            await self.db.refresh(self.user)
        finally:
            self.db.info.pop(SKIP_REPLAN, None)
        await self._restale(id)
        raise PlanStaleError()

    async def _restale(self, id: uuid.UUID) -> None:
        rev = await self._get(id)
        reasons = [PlanReason(r) for r in rev.reasons]
        rev.status = PlanRevisionStatus.superseded
        await self.db.flush()
        await self.preview(reasons, force=True)

    async def _event(self, raw_id: str | None) -> Event | None:
        if raw_id is None:
            return None
        return await self.db.scalar(
            select(Event).where(
                Event.id == uuid.UUID(raw_id),
                Event.user_id == self.user_id,
                Event.deleted_at.is_(None),
            )
        )

    async def _execute(self, ops: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """Выполняет операции превью. None — событие успели изменить (превью устарело)."""
        undo: list[dict[str, Any]] = []
        for op in ops:
            if op["op"] == "add":
                after = op["after"]
                event = Event(
                    user_id=self.user_id,
                    kind=op.get("kind", EventKind.subtask),
                    title=op["title"],
                    start=_moment(after["start"]),
                    end=_moment(after["end"]),
                    is_fixed=False,
                    is_pinned=False,
                    status=EventStatus.planned,
                    source_type=op["source_type"],
                    source_id=uuid.UUID(op["source_id"]),
                    subject_id=uuid.UUID(op["subject_id"]) if op.get("subject_id") else None,
                    color=op.get("color"),
                )
                self.db.add(event)
                await self.db.flush()
                undo.append({"event_id": str(event.id), "created": True, "after": _state(event)})
                continue

            event = await self._event(op["event_id"])
            before = op["before"]
            if (
                event is None
                or event.status != EventStatus.planned
                or (event.is_pinned and op["op"] != "miss")
                or (event.start, event.end) != (_moment(before["start"]), _moment(before["end"]))
            ):
                return None
            was = _state(event)
            if op["op"] == "move":
                event.start = _moment(op["after"]["start"])
                event.end = _moment(op["after"]["end"])
            elif op["op"] == "remove":
                event.deleted_at = now_utc()
            elif op["op"] == "miss":
                event.status = EventStatus.missed
            undo.append(
                {"event_id": str(event.id), "created": False, "before": was, "after": _state(event)}
            )
        return undo

    # ---------- откат ----------

    async def undo(self) -> tuple[PlanRevision, int, int]:
        """Откатывает последнее применение. Блоки, которые после него правили
        руками, не трогаем. Возвращает (ревизия, откачено, пропущено)."""
        rev = await self.undoable()
        if rev is None:
            raise NotFoundError("Нечего отменять")
        self.db.info[SKIP_REPLAN] = True
        try:
            restored, skipped = await self._revert(rev)
            rev.status = PlanRevisionStatus.undone
            rev.undone_at = self.now()
            if (current := await self.proposal()) is not None:
                current.status = PlanRevisionStatus.superseded
            await self.db.commit()
        finally:
            self.db.info.pop(SKIP_REPLAN, None)
        return rev, restored, skipped

    async def _revert(self, rev: PlanRevision) -> tuple[int, int]:
        restored = skipped = 0
        for item in reversed(rev.undo):
            event = await self.db.scalar(
                select(Event).where(
                    Event.id == uuid.UUID(item["event_id"]), Event.user_id == self.user_id
                )
            )
            if event is None or _state(event) != item["after"]:
                skipped += 1
                continue
            if item["created"]:
                event.deleted_at = now_utc()
            else:
                before = item["before"]
                event.start = _moment(before["start"])
                event.end = _moment(before["end"])
                event.status = before["status"]
                event.deleted_at = None
            restored += 1
        return restored, skipped


def _state(e: Event) -> dict[str, Any]:
    return {
        "start": e.start.isoformat(),
        "end": e.end.isoformat(),
        "status": str(e.status),
        "deleted": e.deleted_at is not None,
    }


def _risk_keys(risks: Iterable[dict[str, Any]]) -> set[str]:
    return {r["block_id"] + r["reason"] for r in risks}


# ---------- фон ----------


async def mark_missed(db: AsyncSession, user_id: uuid.UUID, before: datetime) -> int:
    """Прошедшие неотмеченные гибкие блоки → missed. Не коммитит."""
    events = list(
        await db.scalars(
            select(Event).where(
                Event.user_id == user_id,
                Event.deleted_at.is_(None),
                Event.kind.not_in(FIXED_KINDS),
                Event.source_type.in_(PLANNED_SOURCES),
                Event.status == EventStatus.planned,
                Event.end <= before,
            )
        )
    )
    for e in events:
        e.status = EventStatus.missed
    return len(events)


async def handle_preview_job(db: AsyncSession, job: Job) -> None:
    if job.user_id is None:
        return
    user = await db.get(User, job.user_id)
    if user is None or user.deleted_at is not None:
        return
    reasons = [PlanReason(r) for r in job.payload.get("reasons", [PlanReason.changes])]
    await ReplanService(db, user).preview(reasons)


async def nightly_replan(db: AsyncSession, now: datetime | None = None) -> int:
    """3:00: неотмеченное за прошлые дни → missed, план подготовки к экзаменам
    пересобран, превью плана готово к утру.

    Сегодняшнее не трогаем: его отмечают на вечернем разборе (и воркер, перезапущенный
    днём, не должен записать утренний блок в «не сделано»).
    """
    now = now or now_utc()
    users = list(await db.scalars(select(User).where(User.deleted_at.is_(None))))
    for user in users:
        tz = get_tz(user.timezone)
        db.info[SKIP_REPLAN] = True
        try:
            await mark_missed(db, user.id, wall_to_utc(local_date(now, tz), time(0), tz))
            await exams.sync_all(db, user, now)
            await ReplanService(db, user, now).preview([PlanReason.nightly])
        finally:
            db.info.pop(SKIP_REPLAN, None)
    return len(users)


# ---------- ответ API ----------


def revision_read(rev: PlanRevision | None) -> PlanRevisionRead | None:
    if rev is None:
        return None
    read = PlanRevisionRead.model_validate(rev)
    for change in read.changes:
        if change.op == "move":
            read.moved += 1
        elif change.op == "add":
            read.added += 1
        elif change.op == "remove":
            read.removed += 1
        else:
            read.missed += 1
    return read


async def plan_state(svc: ReplanService) -> PlanState:
    return PlanState(
        proposal=revision_read(await svc.proposal()),
        undoable=revision_read(await svc.undoable()),
    )
