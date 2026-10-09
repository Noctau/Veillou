"""Разовые лимиты учёбы на день — вариант «расширить часы» при угрозе дедлайну."""

import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
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
        """Upsert одним запросом: параллельные PUT на тот же день не падают на
        уникальном индексе (раньше select → insert давал 500)."""
        stmt = (
            insert(StudyDayLimit)
            .values(id=uuid.uuid4(), user_id=self.repo.user_id, date=day, minutes=minutes)
            .on_conflict_do_update(
                index_elements=["user_id", "date"],
                index_where=StudyDayLimit.deleted_at.is_(None),
                set_={"minutes": minutes, "updated_at": func.now()},
            )
            .returning(StudyDayLimit.id)
        )
        item_id = await self.db.scalar(stmt)
        await self.db.commit()
        if item_id is None:  # RETURNING есть и у вставки, и у обновления
            raise RuntimeError("Лимит не сохранён")
        return await self.repo.get_or_404(item_id)

    async def delete(self, day: date) -> None:
        item = await self.db.scalar(self.repo.select().where(StudyDayLimit.date == day))
        if item is not None:
            self.repo.soft_delete(item)
            await self.db.commit()
