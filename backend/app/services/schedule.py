"""CRUD шаблонов расписания: семестры, звонки, выходные, правила пар."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import get_tz
from app.models import Area, BellSchedule, ClassRule, DayOff, Semester, User
from app.schemas.schedule import (
    BellsReplace,
    ClassRuleCreate,
    ClassRuleUpdate,
    DayOffCreate,
    DayOffUpdate,
    SemesterCreate,
    SemesterUpdate,
)
from app.services.base import UserScopedRepository, apply_fields, validate_patch
from app.services.schedule_sync import SeriesSync


class SemesterRepo(UserScopedRepository[Semester]):
    model = Semester
    not_found_message = "Семестр не найден"


class BellRepo(UserScopedRepository[BellSchedule]):
    model = BellSchedule


class DayOffRepo(UserScopedRepository[DayOff]):
    model = DayOff
    not_found_message = "Выходной не найден"


class AreaRepo(UserScopedRepository[Area]):
    model = Area
    not_found_message = "Сфера не найдена"


class ClassRuleRepo(UserScopedRepository[ClassRule]):
    model = ClassRule
    not_found_message = "Пара не найдена"


class ScheduleService:
    """CRUD шаблонов; каждое изменение пересинхронизирует затронутые серии пар."""

    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user_id = user.id
        self.sync = SeriesSync(db, user_id, get_tz(user.timezone))
        self.semesters = SemesterRepo(db, user_id)
        self.bells = BellRepo(db, user_id)
        self.days_off = DayOffRepo(db, user_id)
        self.areas = AreaRepo(db, user_id)
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
        await self.db.flush()
        await self.sync.sync_semester(id)
        await self.db.commit()
        return semester

    async def delete_semester(self, id: uuid.UUID) -> None:
        """Удаляет семестр с его звонками и парами. Сферы остаются «без периода»."""
        semester = await self.semesters.get_or_404(id)
        for rule in await self.rules.find_all(ClassRule.semester_id == id):
            self.rules.soft_delete(rule)
            await self.sync.remove_series(rule)
        for bell in await self.bells.find_all(BellSchedule.semester_id == id):
            self.bells.soft_delete(bell)
        for area in await self.areas.find_all(Area.period_id == id):
            area.period_id = None
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
        await self.db.flush()
        await self.sync.sync_semester(semester_id)
        await self.db.commit()
        return await self.list_bells(semester_id)

    # ---------- выходные ----------

    async def list_days_off(self) -> list[DayOff]:
        return await self.days_off.find_all(order_by=[DayOff.date_from])

    async def create_day_off(self, data: DayOffCreate) -> DayOff:
        day_off = DayOff()
        apply_fields(day_off, data)
        self.days_off.add(day_off)
        await self._days_off_changed()
        return day_off

    async def update_day_off(self, id: uuid.UUID, patch: DayOffUpdate) -> DayOff:
        day_off = await self.days_off.get_or_404(id)
        apply_fields(day_off, validate_patch(day_off, patch, DayOffCreate))
        await self._days_off_changed()
        return day_off

    async def delete_day_off(self, id: uuid.UUID) -> None:
        self.days_off.soft_delete(await self.days_off.get_or_404(id))
        await self._days_off_changed()

    async def _days_off_changed(self) -> None:
        await self.db.flush()
        await self.sync.sync_all_class_rules()
        await self.db.commit()

    # ---------- правила пар ----------

    async def list_rules(self, semester_id: uuid.UUID | None = None) -> list[ClassRule]:
        where = [ClassRule.semester_id == semester_id] if semester_id else []
        return await self.rules.find_all(
            *where, order_by=[ClassRule.weekday, ClassRule.pair_number, ClassRule.start_time]
        )

    async def create_rule(self, data: ClassRuleCreate) -> ClassRule:
        await self.semesters.get_or_404(data.semester_id)
        await self.areas.get_or_404(data.area_id)
        rule = ClassRule()
        apply_fields(rule, data)
        self.rules.add(rule)
        await self.db.flush()
        await self.sync.sync_class_rules([rule])
        await self.db.commit()
        return rule

    async def update_rule(self, id: uuid.UUID, patch: ClassRuleUpdate) -> ClassRule:
        rule = await self.rules.get_or_404(id)
        data = validate_patch(rule, patch, ClassRuleCreate)
        if data.area_id != rule.area_id:
            await self.areas.get_or_404(data.area_id)
        apply_fields(rule, data)
        await self.db.flush()
        await self.sync.sync_class_rules([rule])
        await self.db.commit()
        return rule

    async def delete_rule(self, id: uuid.UUID) -> None:
        rule = await self.rules.get_or_404(id)
        self.rules.soft_delete(rule)
        await self.sync.remove_series(rule)
        await self.db.commit()
