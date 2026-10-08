"""Разовые лимиты учёбы на день — вариант «расширить часы» при угрозе дедлайну."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import get_tz, local_date, now_utc
from app.models import StudyDayLimit, User
from app.services.base import UserScopedRepository


class StudyDayLimitRepo(UserScopedRepository[StudyDayLimit]):
    model = StudyDayLimit
    not_found_message = "Лимита на этот день нет"


class StudyLimitService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.repo = StudyDayLimitRepo(db, user.id)
        self.tz = get_tz(user.timezone)

    async def list(self) -> list[StudyDayLimit]:
        today = local_date(now_utc(), self.tz)
        return await self.repo.find_all(StudyDayLimit.date >= today, order_by=[StudyDayLimit.date])

    async def put(self, day: date, minutes: int) -> StudyDayLimit:
        item = await self.db.scalar(self.repo.select().where(StudyDayLimit.date == day))
        if item is None:
            item = self.repo.add(StudyDayLimit(date=day, minutes=minutes))
        item.minutes = minutes
        await self.db.commit()
        return item

    async def delete(self, day: date) -> None:
        item = await self.db.scalar(self.repo.select().where(StudyDayLimit.date == day))
        if item is not None:
            self.repo.soft_delete(item)
            await self.db.commit()
