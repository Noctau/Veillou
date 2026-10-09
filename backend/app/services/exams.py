"""Экзамены: билеты, статусы, план подготовки (M12).

Экзамен сам — жёсткое событие `events.kind=exam` (планировщик туда ничего не
ставит). План подготовки включается кнопкой и дальше пересобирается сам —
после правки вопросов, статусов, даты экзамена, отметок на блоках и ночью:
`domain/srs.py` считает дни, `sync_sessions` сверяет их с `exam_sessions`
(правит на месте по ключу «день + вид», лишние убирает). Блоки этих дней ставит
в календарь планировщик (services/replan.py) — через обычное превью.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc
from app.domain import srs
from app.domain.enums import (
    EventKind,
    EventStatus,
    ExamQuestionStatus,
    ExamSessionKind,
    ExamSessionStatus,
    PlanReason,
    SourceType,
)
from app.domain.exams import exam_title, parse_questions, session_title
from app.models import Event, Exam, ExamQuestion, ExamSession, Subject, User
from app.schemas.exam import (
    ExamCreate,
    ExamDetail,
    ExamQuestionCreate,
    ExamQuestionRead,
    ExamQuestionUpdate,
    ExamRead,
    ExamSessionRead,
    ExamUpdate,
)
from app.services.base import UserScopedRepository, validate_patch


class ExamRepo(UserScopedRepository[Exam]):
    model = Exam
    not_found_message = "Экзамен не найден"


class QuestionRepo(UserScopedRepository[ExamQuestion]):
    model = ExamQuestion
    not_found_message = "Вопрос не найден"


class SessionRepo(UserScopedRepository[ExamSession]):
    model = ExamSession
    not_found_message = "День подготовки не найден"


class _SubjectRepo(UserScopedRepository[Subject]):
    model = Subject
    not_found_message = "Предмет не найден"


class _EventRepo(UserScopedRepository[Event]):
    model = Event


MAX_QUESTIONS = 300


def params_of(exam: Exam) -> srs.Params:
    return srs.Params(
        learn_min=exam.learn_min,
        review_min=exam.review_min,
        run_min=exam.run_min,
        prep_days=exam.prep_days,
    )


class ExamService:
    def __init__(self, db: AsyncSession, user: User, now: datetime | None = None) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.now = now or now_utc()
        self.today = local_date(self.now, self.tz)
        self.exams = ExamRepo(db, user.id)
        self.questions = QuestionRepo(db, user.id)
        self.sessions = SessionRepo(db, user.id)
        self.subjects = _SubjectRepo(db, user.id)
        self.events = _EventRepo(db, user.id)

    # ---------- чтение ----------

    async def _subject_names(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, Subject]:
        if not ids:
            return {}
        return {s.id: s for s in await self.subjects.find_all(Subject.id.in_(ids))}

    async def _counts(self, exam_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        if not exam_ids:
            return {}
        rows = await self.db.execute(
            select(
                ExamQuestion.exam_id,
                func.count(),
                func.count().filter(ExamQuestion.status != ExamQuestionStatus.not_started),
            )
            .where(
                ExamQuestion.user_id == self.user_id,
                ExamQuestion.deleted_at.is_(None),
                ExamQuestion.exam_id.in_(exam_ids),
            )
            .group_by(ExamQuestion.exam_id)
        )
        return {exam_id: (total, learned) for exam_id, total, learned in rows}

    def _read(self, exam: Exam, subject: Subject | None, counts: tuple[int, int]) -> ExamRead:
        read = ExamRead.model_validate(exam)
        read.title = exam_title(exam.title, subject.name if subject else None)
        read.questions_total, read.questions_learned = counts
        return read

    async def list_exams(self, subject_id: uuid.UUID | None = None) -> list[ExamRead]:
        where = [Exam.subject_id == subject_id] if subject_id else []
        exams = await self.exams.find_all(*where, order_by=[Exam.starts_at])
        subjects = await self._subject_names({e.subject_id for e in exams})
        counts = await self._counts([e.id for e in exams])
        return [self._read(e, subjects.get(e.subject_id), counts.get(e.id, (0, 0))) for e in exams]

    async def _questions(self, exam_id: uuid.UUID) -> list[ExamQuestion]:
        return await self.questions.find_all(
            ExamQuestion.exam_id == exam_id, order_by=[ExamQuestion.number, ExamQuestion.created_at]
        )

    async def get_detail(self, id: uuid.UUID) -> ExamDetail:
        exam = await self.exams.get_or_404(id)
        subject = await self.subjects.get(exam.subject_id)
        questions = await self._questions(exam.id)
        learned = sum(q.status != ExamQuestionStatus.not_started for q in questions)
        sessions = await self.sessions.find_all(
            ExamSession.exam_id == exam.id,
            ExamSession.date >= self.today,
            order_by=[ExamSession.date, ExamSession.kind],
        )
        placed: dict[uuid.UUID, list[Event]] = defaultdict(list)
        if sessions:
            for e in await self.events.find_all(
                Event.source_type == SourceType.exam_session,
                Event.source_id.in_([x.id for x in sessions]),
                Event.status.in_([EventStatus.planned, EventStatus.done]),
                order_by=[Event.start],
            ):
                if e.source_id is not None:
                    placed[e.source_id].append(e)
        numbers = {str(q.id): q.number for q in questions}
        name = (subject.short_name or subject.name) if subject else "Экзамен"
        session_reads = []
        for x in sessions:
            nums = sorted(numbers[q] for q in x.question_ids if q in numbers)
            events = placed.get(x.id, [])
            session_reads.append(
                ExamSessionRead(
                    id=x.id,
                    date=x.date,
                    kind=ExamSessionKind(x.kind),
                    title=session_title(ExamSessionKind(x.kind), name, nums),
                    numbers=nums,
                    minutes=x.minutes,
                    status=ExamSessionStatus(x.status),
                    start=events[0].start if events else None,
                    end=events[-1].end if events else None,
                )
            )
        base = self._read(exam, subject, (len(questions), learned))
        return ExamDetail(
            **base.model_dump(),
            questions=[ExamQuestionRead.model_validate(q) for q in questions],
            sessions=session_reads,
        )

    # ---------- экзамен ----------

    async def create(self, data: ExamCreate) -> ExamDetail:
        await self.subjects.get_or_404(data.subject_id)
        exam = Exam(**data.model_dump())
        self.exams.add(exam)
        await self.db.flush()
        await self._sync_event(exam)
        await self.db.commit()
        return await self.get_detail(exam.id)

    async def update(self, id: uuid.UUID, patch: ExamUpdate) -> ExamDetail:
        exam = await self.exams.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name in ("starts_at", "duration_min", "prep_days", "learn_min", "review_min"):
            if name in changes and changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        data = validate_patch(exam, patch, ExamCreate)
        for name in changes:
            setattr(exam, name, getattr(data, name))
        await self._sync_event(exam)
        await self.sync_sessions(exam)
        await self.db.commit()
        return await self.get_detail(exam.id)

    async def delete(self, id: uuid.UUID) -> None:
        exam = await self.exams.get_or_404(id)
        self.exams.soft_delete(exam)
        for q in await self._questions(exam.id):
            self.questions.soft_delete(q)
        for x in await self.sessions.find_all(ExamSession.exam_id == exam.id):
            self.sessions.soft_delete(x)
        await self._sync_event(exam)
        await self.db.commit()

    async def _sync_event(self, exam: Exam) -> None:
        """Сам экзамен — жёсткое событие в календаре."""
        event = await self.db.scalar(
            self.events.select().where(
                Event.source_type == SourceType.exam, Event.source_id == exam.id
            )
        )
        if exam.deleted_at is not None:
            if event is not None:
                self.events.soft_delete(event)
            return
        subject = await self.subjects.get(exam.subject_id)
        fields = {
            "title": exam_title(exam.title, subject.name if subject else None),
            "start": exam.starts_at,
            "end": exam.starts_at + timedelta(minutes=exam.duration_min),
            "location": exam.location,
            "subject_id": exam.subject_id,
            "note": exam.note,
        }
        if event is None:
            event = Event(
                kind=EventKind.exam,
                is_fixed=True,
                is_pinned=False,
                status=EventStatus.planned,
                source_type=SourceType.exam,
                source_id=exam.id,
                **fields,
            )
            self.events.add(event)
            return
        for name, value in fields.items():
            if getattr(event, name) != value:
                setattr(event, name, value)

    # ---------- вопросы ----------

    async def import_questions(self, id: uuid.UUID, text: str) -> ExamDetail:
        exam = await self.exams.get_or_404(id)
        existing = await self._questions(exam.id)
        start = max((q.number for q in existing), default=0) + 1
        parsed = parse_questions(text, start_number=start)
        if not parsed:
            raise InvalidDataError("Не нашла вопросов в тексте")
        if len(existing) + len(parsed) > MAX_QUESTIONS:
            raise InvalidDataError(f"Слишком много вопросов (максимум {MAX_QUESTIONS})")
        for p in parsed:
            self.questions.add(
                ExamQuestion(
                    exam_id=exam.id,
                    number=p.number,
                    text=p.text,
                    status=ExamQuestionStatus.not_started,
                    reviews_done=0,
                )
            )
        await self.db.flush()
        await self.sync_sessions(exam)
        await self.db.commit()
        return await self.get_detail(exam.id)

    async def add_question(self, id: uuid.UUID, data: ExamQuestionCreate) -> ExamDetail:
        exam = await self.exams.get_or_404(id)
        existing = await self._questions(exam.id)
        if len(existing) >= MAX_QUESTIONS:
            raise InvalidDataError(f"Слишком много вопросов (максимум {MAX_QUESTIONS})")
        number = data.number or max((q.number for q in existing), default=0) + 1
        self.questions.add(
            ExamQuestion(
                exam_id=exam.id,
                number=number,
                text=data.text,
                status=ExamQuestionStatus.not_started,
                reviews_done=0,
            )
        )
        await self.db.flush()
        await self.sync_sessions(exam)
        await self.db.commit()
        return await self.get_detail(exam.id)

    def _set_status(self, q: ExamQuestion, status: ExamQuestionStatus) -> None:
        if status == q.status:
            return
        if status == ExamQuestionStatus.not_started:
            q.learned_on, q.reviews_done = None, 0
        elif status == ExamQuestionStatus.review:
            # «Повторить»: цикл повторений заново, от сегодняшнего дня
            q.learned_on, q.reviews_done = self.today, 0
        elif q.status == ExamQuestionStatus.not_started or q.learned_on is None:
            q.learned_on, q.reviews_done = self.today, 0
        q.status = status

    async def update_question(self, qid: uuid.UUID, patch: ExamQuestionUpdate) -> ExamQuestionRead:
        q = await self.questions.get_or_404(qid)
        changes = patch.model_dump(exclude_unset=True)
        for name in ("number", "text", "status"):
            if name in changes and changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if "number" in changes:
            q.number = changes["number"]
        if "text" in changes:
            q.text = changes["text"]
        if "status" in changes:
            self._set_status(q, ExamQuestionStatus(changes["status"]))
        await self.db.flush()
        exam = await self.exams.get_or_404(q.exam_id)
        await self.sync_sessions(exam)
        await self.db.commit()
        return ExamQuestionRead.model_validate(q)

    async def delete_question(self, qid: uuid.UUID) -> None:
        q = await self.questions.get_or_404(qid)
        self.questions.soft_delete(q)
        await self.db.flush()
        exam = await self.exams.get_or_404(q.exam_id)
        await self.sync_sessions(exam)
        await self.db.commit()

    # ---------- план подготовки ----------

    async def enable_plan(self, id: uuid.UUID) -> ExamDetail:
        """«Построить план»: дни подготовки + превью плана (применяет пользователь)."""
        from app.services.replan import ReplanService

        exam = await self.exams.get_or_404(id)
        if not await self._questions(exam.id):
            raise InvalidDataError("Сначала добавьте вопросы")
        if exam.starts_at <= self.now:
            raise InvalidDataError("Экзамен уже прошёл")
        exam.plan_enabled = True
        await self.sync_sessions(exam)
        await self.db.commit()
        await ReplanService(self.db, self.user, self.now).preview([PlanReason.exam], force=True)
        return await self.get_detail(exam.id)

    async def disable_plan(self, id: uuid.UUID) -> ExamDetail:
        """Убрать план: будущие дни подготовки удаляются, их блоки уберёт превью."""
        exam = await self.exams.get_or_404(id)
        exam.plan_enabled = False
        await self.sync_sessions(exam)
        await self.db.commit()
        return await self.get_detail(exam.id)

    async def sync_sessions(self, exam: Exam) -> bool:
        """Сверяет дни подготовки с расчётом SRS. Не коммитит. True — что-то изменилось."""
        sessions = await self.sessions.find_all(ExamSession.exam_id == exam.id)
        changed = False
        for x in sessions:
            if x.status == ExamSessionStatus.planned and x.date < self.today:
                x.status = ExamSessionStatus.missed
                changed = True
        closed = frozenset(
            (x.date, ExamSessionKind(x.kind))
            for x in sessions
            if x.date >= self.today and x.status != ExamSessionStatus.planned
        )
        desired: list[srs.DayPlan] = []
        if exam.plan_enabled and exam.deleted_at is None and exam.starts_at > self.now:
            questions = [
                srs.Question(
                    str(q.id),
                    q.number,
                    ExamQuestionStatus(q.status),
                    learned_on=q.learned_on,
                    reviews_done=q.reviews_done,
                )
                for q in await self._questions(exam.id)
            ]
            desired = srs.build(
                questions,
                self.today,
                local_date(exam.starts_at, self.tz),
                params_of(exam),
                closed,
            )

        current = {
            (x.date, x.kind): x
            for x in sessions
            if x.status == ExamSessionStatus.planned and x.date >= self.today
        }
        renamed: list[ExamSession] = []
        for plan in desired:
            ids = list(plan.question_ids)
            existing = current.pop((plan.date, str(plan.kind)), None)
            if existing is None:
                self.sessions.add(
                    ExamSession(
                        exam_id=exam.id,
                        date=plan.date,
                        kind=plan.kind,
                        question_ids=ids,
                        minutes=plan.minutes,
                        status=ExamSessionStatus.planned,
                    )
                )
                changed = True
            elif existing.question_ids != ids or existing.minutes != plan.minutes:
                if existing.question_ids != ids:
                    renamed.append(existing)
                existing.question_ids, existing.minutes = ids, plan.minutes
                changed = True
        for x in current.values():
            self.sessions.soft_delete(x)
            changed = True
        if renamed:
            await self._rename_events(exam, renamed)
        return changed

    async def _rename_events(self, exam: Exam, sessions: list[ExamSession]) -> None:
        """Название блока следует за вопросами дня."""
        subject = await self.subjects.get(exam.subject_id)
        name = (subject.short_name or subject.name) if subject else "Экзамен"
        numbers = {str(q.id): q.number for q in await self._questions(exam.id)}
        by_id = {x.id: x for x in sessions}
        for e in await self.events.find_all(
            Event.source_type == SourceType.exam_session,
            Event.source_id.in_(by_id),
            Event.status == EventStatus.planned,
        ):
            if e.source_id is None:
                continue
            x = by_id[e.source_id]
            nums = [numbers[q] for q in x.question_ids if q in numbers]
            e.title = session_title(ExamSessionKind(x.kind), name, nums)

    # ---------- отметки на блоках ----------

    async def on_session_status(self, session_id: uuid.UUID, status: str) -> None:
        """Блок дня подготовки отметили: сделано → вопросы выучены / повторены;
        снятие отметки → назад; «не сделано» → день пропущен, вопросы уходят дальше.
        Не коммитит."""
        x = await self.sessions.get(session_id)
        if x is None:
            return
        questions = {
            str(q.id): q
            for q in await self.questions.find_all(
                ExamQuestion.id.in_([uuid.UUID(i) for i in x.question_ids])
            )
        }
        kind = ExamSessionKind(x.kind)
        if status == EventStatus.done and x.status != ExamSessionStatus.done:
            x.status, x.done_at = ExamSessionStatus.done, self.now
            for q in questions.values():
                if kind == ExamSessionKind.learn and q.status == ExamQuestionStatus.not_started:
                    q.status, q.learned_on, q.reviews_done = ExamQuestionStatus.learned, x.date, 0
                elif kind == ExamSessionKind.review and q.learned_on is not None:
                    q.reviews_done += 1
                    if q.status == ExamQuestionStatus.review:
                        q.status = ExamQuestionStatus.learned
        elif status == EventStatus.planned and x.status == ExamSessionStatus.done:
            x.status, x.done_at = ExamSessionStatus.planned, None
            for q in questions.values():
                if kind == ExamSessionKind.learn and q.learned_on == x.date and not q.reviews_done:
                    q.status, q.learned_on = ExamQuestionStatus.not_started, None
                elif kind == ExamSessionKind.review and q.reviews_done > 0:
                    q.reviews_done -= 1
        elif status == EventStatus.missed and x.status == ExamSessionStatus.planned:
            x.status = ExamSessionStatus.missed
        else:
            return
        await self.db.flush()
        exam = await self.exams.get(x.exam_id)
        if exam is not None:
            await self.sync_sessions(exam)


async def sync_all(db: AsyncSession, user: User, now: datetime | None = None) -> int:
    """Ночью: пропущенные дни → missed, план подготовки пересобран. Коммитит."""
    svc = ExamService(db, user, now)
    exams = await svc.exams.find_all(Exam.plan_enabled.is_(True))
    changed = 0
    for exam in exams:
        changed += await svc.sync_sessions(exam)
    await db.commit()
    return changed


async def upcoming_exams(
    db: AsyncSession, user: User, start: datetime, end: datetime
) -> list[tuple[Exam, str]]:
    """Экзамены в [start, end) с готовым названием — для сводок."""
    exams = list(
        await db.scalars(
            select(Exam)
            .where(
                Exam.user_id == user.id,
                Exam.deleted_at.is_(None),
                Exam.starts_at >= start,
                Exam.starts_at < end,
            )
            .order_by(Exam.starts_at)
        )
    )
    subjects = {
        s.id: s
        for s in await db.scalars(
            select(Subject).where(Subject.id.in_({e.subject_id for e in exams}))
        )
    }
    return [
        (e, exam_title(e.title, subjects[e.subject_id].name if e.subject_id in subjects else None))
        for e in exams
    ]


def days_until(exam: Exam, today: date, tz: ZoneInfo) -> int:
    return (local_date(exam.starts_at, tz) - today).days
