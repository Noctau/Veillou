"""Разборы: вечерний (M11.1) и недельный (M11.3).

Вечерний: что из сегодняшнего начато или прошло, но не отмечено. «Перенести
всё» (или выбранное) — блоки становятся «не сделано», считается превью плана,
применяет пользователь (в шторке или кнопкой в боте). Угрозы дедлайнам — в превью.

Недельный: итоги недели и 1–N дел из ящика на неделю. Подтверждённые дела
получают `planned_week`, считается превью — дела встают в свободные окна.
"""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc, wall_to_utc
from app.domain import backlog as box
from app.domain.enums import (
    FIXED_KINDS,
    BacklogStatus,
    EventStatus,
    PlanReason,
    TaskStatus,
)
from app.models import BacklogItem, Event, PlanRevision, Task, User
from app.schemas.backlog import BacklogRead
from app.schemas.review import WeeklyReview, WeekStats
from app.services.replan import PLANNED_SOURCES, ReplanService
from app.services.settings import effective_settings


class ReviewService:
    def __init__(self, db: AsyncSession, user: User, now: datetime | None = None) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.tz = get_tz(user.timezone)
        self.now = now or now_utc()
        self.today = local_date(self.now, self.tz)

    def _day(self, d: date) -> tuple[datetime, datetime]:
        return wall_to_utc(d, time(0), self.tz), wall_to_utc(
            d + timedelta(days=1), time(0), self.tz
        )

    def _flexible(self, start: datetime, end: datetime) -> Select[Event]:
        return select(Event).where(
            Event.user_id == self.user_id,
            Event.deleted_at.is_(None),
            Event.kind.not_in(FIXED_KINDS),
            Event.source_type.in_(PLANNED_SOURCES),
            Event.start >= start,
            Event.start < end,
        )

    # ---------- вечер ----------

    async def evening_items(self, day: date | None = None) -> tuple[list[Event], int]:
        """(начатые/прошедшие блоки дня без отметки, сколько отмечено «сделано»)."""
        start, end = self._day(day or self.today)
        rows = list(await self.db.scalars(self._flexible(start, end).order_by(Event.start)))
        items = [e for e in rows if e.status == EventStatus.planned and e.start < self.now]
        return items, sum(e.status == EventStatus.done for e in rows)

    async def reschedule(
        self, event_ids: list[uuid.UUID] | None = None, day: date | None = None
    ) -> tuple[int, PlanRevision | None]:
        """Неотмеченное → «не сделано», превью плана. Коммитит."""
        from app.services.events import on_event_status

        items, _ = await self.evening_items(day)
        if event_ids is not None:
            wanted = set(event_ids)
            items = [e for e in items if e.id in wanted]
        for e in items:
            e.status = EventStatus.missed
            await on_event_status(self.db, self.user, e)
        await self.db.commit()
        rev = await ReplanService(self.db, self.user, self.now).preview(
            [PlanReason.missed], force=True
        )
        return len(items), rev

    # ---------- неделя ----------

    def target_week(self) -> date:
        return box.review_week(self.today)

    async def week_stats(self, week: date) -> WeekStats:
        start, _ = self._day(week)
        _, end = self._day(week + timedelta(days=6))
        events = list(await self.db.scalars(self._flexible(start, end)))
        done = [e for e in events if e.status == EventStatus.done]
        tasks_done = await self.db.scalar(
            select(func.count()).where(
                Task.user_id == self.user_id,
                Task.deleted_at.is_(None),
                Task.status == TaskStatus.done,
                Task.done_at >= start,
                Task.done_at < end,
            )
        )
        backlog_done = await self.db.scalar(
            select(func.count()).where(
                BacklogItem.user_id == self.user_id,
                BacklogItem.deleted_at.is_(None),
                BacklogItem.status == BacklogStatus.done,
                BacklogItem.done_at >= start,
                BacklogItem.done_at < end,
            )
        )
        return WeekStats(
            week_start=week,
            blocks_planned=sum(e.status != EventStatus.cancelled for e in events),
            blocks_done=len(done),
            blocks_missed=sum(e.status == EventStatus.missed for e in events),
            done_minutes=sum(round((e.end - e.start).total_seconds() / 60) for e in done),
            tasks_done=tasks_done or 0,
            backlog_done=backlog_done or 0,
        )

    async def _active(self) -> list[BacklogItem]:
        return list(
            await self.db.scalars(
                select(BacklogItem)
                .where(
                    BacklogItem.user_id == self.user_id,
                    BacklogItem.deleted_at.is_(None),
                    BacklogItem.status == BacklogStatus.active,
                )
                .order_by(BacklogItem.created_at)
            )
        )

    async def weekly(self) -> WeeklyReview:
        week = self.target_week()
        per_week = effective_settings(self.user).backlog_per_week
        items = await self._active()
        planned = [i for i in items if i.planned_week == week]
        candidates = [
            box.Candidate(i.id, local_date(i.created_at, self.tz), i.desired_by, i.planned_week)
            for i in items
        ]
        by_id = {i.id: i for i in items}
        picked = box.suggest(candidates, week, max(per_week - len(planned), 0))
        # Итоги — последней законченной (или заканчивающейся в Сб/Вс) недели
        stats_week = box.week_start(self.today)
        if self.today.isoweekday() < 6:
            stats_week -= timedelta(days=7)
        return WeeklyReview(
            week_start=week,
            per_week=per_week,
            stats=await self.week_stats(stats_week),
            planned=[BacklogRead.model_validate(i) for i in planned],
            suggestions=[BacklogRead.model_validate(by_id[c.id]) for c in picked],
        )

    async def confirm_week(self, item_ids: list[uuid.UUID]) -> PlanRevision | None:
        """Дела на неделю целиком (снятые — убираются с неё) + превью. Коммитит."""
        week = self.target_week()
        per_week = effective_settings(self.user).backlog_per_week
        wanted = list(dict.fromkeys(item_ids))
        if len(wanted) > per_week:
            raise InvalidDataError(
                f"На неделю — не больше {per_week} дел (можно поменять в Настройках)"
            )
        items = {i.id: i for i in await self._active()}
        missing = [i for i in wanted if i not in items]
        if missing:
            raise InvalidDataError("Некоторых дел уже нет в ящике")
        for item in items.values():
            if item.id in wanted:
                item.planned_week = week
            elif item.planned_week == week:
                item.planned_week = None
        await self.db.commit()
        return await ReplanService(self.db, self.user, self.now).preview(
            [PlanReason.weekly], force=True
        )


async def take_for_week(db: AsyncSession, user: User, item: BacklogItem, take: bool) -> None:
    """Кнопка на деле: «Взять на неделю» / «Снять с недели». Не коммитит."""
    tz = get_tz(user.timezone)
    week = box.review_week(local_date(now_utc(), tz))
    if not take:
        item.planned_week = None
        return
    if item.status != BacklogStatus.active:
        raise InvalidDataError("Дело уже закрыто")
    per_week = effective_settings(user).backlog_per_week
    taken = await db.scalar(
        select(func.count()).where(
            BacklogItem.user_id == user.id,
            BacklogItem.deleted_at.is_(None),
            BacklogItem.status == BacklogStatus.active,
            BacklogItem.planned_week == week,
            BacklogItem.id != item.id,
        )
    )
    if (taken or 0) >= per_week:
        raise InvalidDataError(
            f"На неделю уже {per_week} — снимите одно или увеличьте лимит в Настройках"
        )
    item.planned_week = week
