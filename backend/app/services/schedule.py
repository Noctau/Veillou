"""CRUD шаблонов расписания: семестры, звонки, выходные, предметы, правила пар."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BellSchedule, ClassRule, DayOff, Semester, Subject
from app.schemas.schedule import (
    BellsReplace,
    ClassRuleCreate,
    ClassRuleUpdate,
    DayOffCreate,
    DayOffUpdate,
    SemesterCreate,
    SemesterUpdate,
    SubjectCreate,
    SubjectUpdate,
)
from app.services.base import UserScopedRepository, apply_fields, validate_patch


class SemesterRepo(UserScopedRepository[Semester]):
    model = Semester
    not_found_message = "Семестр не найден"


class BellRepo(UserScopedRepository[BellSchedule]):
    model = BellSchedule


class DayOffRepo(UserScopedRepository[DayOff]):
    model = DayOff
    not_found_message = "Выходной не найден"


class SubjectRepo(UserScopedRepository[Subject]):
    model = Subject
    not_found_message = "Предмет не найден"


class ClassRuleRepo(UserScopedRepository[ClassRule]):
    model = ClassRule
    not_found_message = "Пара не найдена"


class ScheduleService:
    def __init__(self, db: AsyncSession, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id
        self.semesters = SemesterRepo(db, user_id)
        self.bells = BellRepo(db, user_id)
        self.days_off = DayOffRepo(db, user_id)
        self.subjects = SubjectRepo(db, user_id)
        self.rules = ClassRuleRepo(db, user_id)

    # ---------- семестры ----------

    async def list_semesters(self) -> list[Semester]:
        return await self.semesters.find_all(order_by=[Semester.start_date.desc()])

    async def create_semester(self, data: SemesterCreate) -> Semester:
        semester = Semester()
        apply_fields(semester, data)
        self.semesters.add(semester)
        await self.db.commit()
        return semester

    async def update_semester(self, id: uuid.UUID, patch: SemesterUpdate) -> Semester:
        semester = await self.semesters.get_or_404(id)
        apply_fields(semester, validate_patch(semester, patch, SemesterCreate))
        await self.db.commit()
        return semester

    async def delete_semester(self, id: uuid.UUID) -> None:
        """Удаляет семестр с его звонками и парами. Предметы остаются «без семестра»."""
        semester = await self.semesters.get_or_404(id)
        for rule in await self.rules.find_all(ClassRule.semester_id == id):
            self.rules.soft_delete(rule)
        for bell in await self.bells.find_all(BellSchedule.semester_id == id):
            self.bells.soft_delete(bell)
        for subject in await self.subjects.find_all(Subject.semester_id == id):
            subject.semester_id = None
        self.semesters.soft_delete(semester)
        await self.db.commit()

    # ---------- звонки ----------

    async def list_bells(self, semester_id: uuid.UUID) -> list[BellSchedule]:
        await self.semesters.get_or_404(semester_id)
        rows = await self.bells.find_all(BellSchedule.semester_id == semester_id)
        return sorted(rows, key=lambda b: b.weekday or 0)

    async def replace_bells(self, semester_id: uuid.UUID, data: BellsReplace) -> list[BellSchedule]:
        await self.semesters.get_or_404(semester_id)
        for old in await self.bells.find_all(BellSchedule.semester_id == semester_id):
            self.bells.soft_delete(old)
        await self.db.flush()  # частичный уникальный индекс: сначала гасим старые
        for item in data.schedules:
            self.bells.add(
                BellSchedule(
                    semester_id=semester_id,
                    weekday=item.weekday,
                    slots=[s.model_dump(mode="json") for s in item.slots],
                )
            )
        await self.db.commit()
        return await self.list_bells(semester_id)

    # ---------- выходные ----------

    async def list_days_off(self) -> list[DayOff]:
        return await self.days_off.find_all(order_by=[DayOff.date_from])

    async def create_day_off(self, data: DayOffCreate) -> DayOff:
        day_off = DayOff()
        apply_fields(day_off, data)
        self.days_off.add(day_off)
        await self.db.commit()
        return day_off

    async def update_day_off(self, id: uuid.UUID, patch: DayOffUpdate) -> DayOff:
        day_off = await self.days_off.get_or_404(id)
        apply_fields(day_off, validate_patch(day_off, patch, DayOffCreate))
        await self.db.commit()
        return day_off

    async def delete_day_off(self, id: uuid.UUID) -> None:
        self.days_off.soft_delete(await self.days_off.get_or_404(id))
        await self.db.commit()

    # ---------- предметы ----------

    async def list_subjects(self, semester_id: uuid.UUID | None = None) -> list[Subject]:
        where = [Subject.semester_id == semester_id] if semester_id else []
        return await self.subjects.find_all(*where, order_by=[Subject.name])

    async def get_subject(self, id: uuid.UUID) -> Subject:
        return await self.subjects.get_or_404(id)

    async def create_subject(self, data: SubjectCreate) -> Subject:
        if data.semester_id:
            await self.semesters.get_or_404(data.semester_id)
        subject = Subject()
        apply_fields(subject, data)
        self.subjects.add(subject)
        await self.db.commit()
        return subject

    async def update_subject(self, id: uuid.UUID, patch: SubjectUpdate) -> Subject:
        subject = await self.subjects.get_or_404(id)
        data = validate_patch(subject, patch, SubjectCreate)
        if data.semester_id and data.semester_id != subject.semester_id:
            await self.semesters.get_or_404(data.semester_id)
        apply_fields(subject, data)
        await self.db.commit()
        return subject

    async def delete_subject(self, id: uuid.UUID) -> None:
        subject = await self.subjects.get_or_404(id)
        for rule in await self.rules.find_all(ClassRule.subject_id == id):
            self.rules.soft_delete(rule)
        self.subjects.soft_delete(subject)
        await self.db.commit()

    # ---------- правила пар ----------

    async def list_rules(self, semester_id: uuid.UUID | None = None) -> list[ClassRule]:
        where = [ClassRule.semester_id == semester_id] if semester_id else []
        return await self.rules.find_all(
            *where, order_by=[ClassRule.weekday, ClassRule.pair_number, ClassRule.start_time]
        )

    async def create_rule(self, data: ClassRuleCreate) -> ClassRule:
        await self.semesters.get_or_404(data.semester_id)
        await self.subjects.get_or_404(data.subject_id)
        rule = ClassRule()
        apply_fields(rule, data)
        self.rules.add(rule)
        await self.db.commit()
        return rule

    async def update_rule(self, id: uuid.UUID, patch: ClassRuleUpdate) -> ClassRule:
        rule = await self.rules.get_or_404(id)
        data = validate_patch(rule, patch, ClassRuleCreate)
        if data.subject_id != rule.subject_id:
            await self.subjects.get_or_404(data.subject_id)
        apply_fields(rule, data)
        await self.db.commit()
        return rule

    async def delete_rule(self, id: uuid.UUID) -> None:
        self.rules.soft_delete(await self.rules.get_or_404(id))
        await self.db.commit()
