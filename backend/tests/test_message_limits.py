"""M-08: сообщения не превышают лимиты Telegram (4096 символов) и Web Push (~4 КБ)."""

import json
import uuid
from datetime import date, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.ai import plan_text
from app.core.time import get_tz, wall_to_utc
from app.domain.enums import EventKind, EventStatus
from app.models import Event, User
from app.notify.message import (
    PUSH_PAYLOAD_LIMIT,
    TELEGRAM_TEXT_LIMIT,
    Message,
    Section,
)
from app.notify.notifier import push_payload
from app.schemas.plan import PlanRevisionRead, PlanRisk, PlanState
from app.services.digest import Digest

LINE = "Подготовить раздел ВКР про климатические аномалии <&>"  # с символами для экранирования


def big_message(lines: int = 300) -> Message:
    per_section = 30
    sections = tuple(
        Section(f"День {i}", tuple(f"{LINE} {i}.{j}" for j in range(per_section)))
        for i in range(lines // per_section)
    )
    return Message(title="Неделя", sections=sections)


def test_short_message_is_unchanged():
    msg = Message(title="Т", sections=(Section("Р", ("а", "б")),))
    assert msg.telegram_html() == "<b>Т</b>\n\n<b>Р</b>\nа\nб"
    assert msg.fit(lambda _: True) is msg


def test_telegram_html_fits_limit_and_says_how_many_left():
    html = big_message().telegram_html()
    assert len(html) <= TELEGRAM_TEXT_LIMIT
    assert html.count("<b>") == html.count("</b>")
    last = html.rsplit("\n", 1)[-1]
    assert last.startswith("…и ещё ")
    assert int(last.split()[-1]) > 0


def test_push_payload_fits_limit():
    payload = push_payload(big_message())
    assert len(payload.encode()) <= PUSH_PAYLOAD_LIMIT
    assert "…и ещё" in json.loads(payload)["body"]


def test_plan_text_lists_limited_number_of_titles():
    risks = [
        PlanRisk.model_construct(
            group_kind="task",
            group_id=uuid.uuid4(),
            group_title=f"Очень длинное название задания номер {i} " * 3,
        )
        for i in range(60)
    ]
    rev = PlanRevisionRead.model_construct(
        id=uuid.uuid4(), added=1, moved=0, removed=0, at_risk=risks
    )
    text = plan_text(PlanState(proposal=rev, undoable=None))
    assert len(text) <= TELEGRAM_TEXT_LIMIT
    assert "и ещё" in text


async def test_dense_week_fits_telegram(session: AsyncSession, user: User):
    tz = get_tz(user.timezone)
    monday = date(2030, 1, 7)
    for d in range(7):
        for h in range(9, 19):
            day = monday + timedelta(days=d)
            session.add(
                Event(
                    user_id=user.id,
                    kind=EventKind.subtask,
                    title="Подготовить раздел ВКР про климатические аномалии",
                    start=wall_to_utc(day, time(h), tz),
                    end=wall_to_utc(day, time(h, 45), tz),
                    is_fixed=False,
                    is_pinned=False,
                    status=EventStatus.planned,
                )
            )
    await session.commit()
    week = await Digest(session, user, wall_to_utc(monday, time(7), tz)).week(monday)
    assert len(week.telegram_html()) <= TELEGRAM_TEXT_LIMIT
