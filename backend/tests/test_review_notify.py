"""M11.1, M11.3, M11.6: разборы в push и боте, утренняя сводка v2 (сценарий 1)."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from aiogram.methods import EditMessageReplyMarkup
from sqlalchemy import select

from app.core.db import session_factory
from app.core.time import get_tz, local_date, now_utc
from app.domain.enums import (
    BacklogStatus,
    EventKind,
    EventStatus,
    ReminderAction,
    ReminderKind,
    SourceType,
)
from app.models import BacklogItem, Event, Reminder, User
from app.notify.notifier import push_payload, reminder_callback
from app.services import reminder_actions
from app.services.digest import Digest
from app.services.notify_render import render
from app.services.reminders import sync_user_reminders
from app.services.replan import ReplanService

from .test_bot import buttons, linked, press, tg, tg_message  # noqa: F401
from .test_reminders import add_reminder
from .test_replan import MON, add_event, at, call, task_with_steps

API = "/api/v1"
TZ = get_tz("Europe/Moscow")
SUN = MON + timedelta(days=6)


@pytest.fixture(autouse=True)
def _fast_solver(monkeypatch):
    monkeypatch.setattr(ReplanService, "time_limit_s", 0.4)


async def fresh(user) -> tuple:
    db = session_factory()
    return db, await db.get(User, user.id)


async def plan_monday(client, user, *estimates: int):
    task, steps = await task_with_steps(client, *estimates)
    rev = await call(user, "preview")
    await call(user, "apply", rev.id)
    return task, steps


def evening_reminder(user, d) -> Reminder:
    return Reminder(
        user_id=user.id,
        kind=ReminderKind.evening_review,
        fire_at=at(d, 21, 30),
        due_at=at(d, 21, 30),
        channels=["push", "telegram"],
        payload={"date": d.isoformat()},
        dedupe_key=f"evening_review:{d}",
        is_auto=True,
        status="pending",
        sent_channels=[],
        attempts=0,
    )


# ---------- напоминания ----------


async def test_sync_creates_review_reminders(session, user):
    await sync_user_reminders(session, user.id)
    rows = list(await session.scalars(select(Reminder)))
    evenings = [r for r in rows if r.kind == ReminderKind.evening_review]
    weeklies = [r for r in rows if r.kind == ReminderKind.weekly_review]
    assert len(evenings) >= 7
    assert all(r.fire_at.astimezone(TZ).strftime("%H:%M") == "21:30" for r in evenings)
    assert weeklies and all(r.fire_at.astimezone(TZ).isoweekday() == 7 for r in weeklies)
    assert all(r.fire_at.astimezone(TZ).strftime("%H:%M") == "19:00" for r in weeklies)


async def test_evening_message_skipped_when_nothing_to_review(session, user):
    msg = await render(session, user, evening_reminder(user, MON), at(MON, 21, 30))
    assert msg is None


async def test_evening_message_lists_blocks_with_actions(auth_client, user):
    await plan_monday(auth_client, user, 60, 90)
    db, u = await fresh(user)
    async with db:
        msg = await render(db, u, evening_reminder(user, MON), at(MON, 21, 30))
    assert msg is not None
    assert msg.title == "Вечерний разбор: не отмечено 2"
    assert msg.actions == (ReminderAction.reschedule, ReminderAction.pick)
    assert msg.url == "/review"
    # В пуше «По одному» не показываем
    payload = json.loads(push_payload(replace(msg, action_token="x")))
    assert [a["action"] for a in payload["actions"]] == ["reschedule"]


async def test_evening_action_reschedules_and_returns_proposal(auth_client, user):
    await plan_monday(auth_client, user, 60)
    db, u = await fresh(user)
    async with db:
        r = evening_reminder(user, MON)
        db.add(r)
        await db.commit()
        result = await reminder_actions.perform(
            db, u, r, ReminderAction.reschedule, now=at(MON, 21, 30)
        )
    assert result.proposal_id is not None
    assert "Перенесла: 1 блок" in result.message


async def test_weekly_message_and_accept(auth_client, user):
    async with session_factory() as db:
        for title in ("Стоматолог", "Паспорт"):
            db.add(
                BacklogItem(
                    user_id=user.id, title=title, status=BacklogStatus.active, conditions=[]
                )
            )
        await db.commit()
    r = Reminder(
        user_id=user.id,
        kind=ReminderKind.weekly_review,
        fire_at=at(SUN, 19),
        due_at=at(SUN, 19),
        channels=["telegram"],
        payload={"date": SUN.isoformat()},
        dedupe_key="weekly_review:x",
        is_auto=True,
        status="pending",
        sent_channels=[],
        attempts=0,
    )
    db, u = await fresh(user)
    async with db:
        db.add(r)
        await db.commit()
        msg = await render(db, u, r, at(SUN, 19))
        assert msg is not None and msg.title == "Разбор недели"
        assert msg.actions == (ReminderAction.accept,)
        assert any("Стоматолог" in line for s in msg.sections for line in s.lines)
        result = await reminder_actions.perform(db, u, r, ReminderAction.accept, now=at(SUN, 19))
        assert result.proposal_id is not None
        items = list(await db.scalars(select(BacklogItem)))
        assert all(i.planned_week == MON + timedelta(days=7) for i in items)


# ---------- утренняя сводка v2 (сценарий 1) ----------


async def test_morning_digest_has_plan_and_backlog(auth_client, user):
    await add_event(
        user,
        kind=EventKind.class_,
        title="Климатология",
        start=at(MON, 10, 45),
        end=at(MON, 12, 20),
        is_fixed=True,
        location="1801",
    )
    await task_with_steps(auth_client, 60, 60)
    async with session_factory() as db:
        db.add(
            BacklogItem(
                user_id=user.id,
                title="Стоматолог",
                status=BacklogStatus.active,
                conditions=[],
                planned_week=MON,
                estimate_min=30,
            )
        )
        await db.commit()
    rev = await call(user, "preview")
    await call(user, "apply", rev.id)

    db, u = await fresh(user)
    async with db:
        msg = await Digest(db, u, at(MON, 8)).day(MON, morning=True)
    sections = {s.heading: s.lines for s in msg.sections}
    assert any("ауд. 1801" in line for line in sections["Пары"])
    plan = sections["План на день"]
    assert len(plan) == 2 and all("Шаг — Реферат" in line for line in plan)
    assert any("Стоматолог" in line for line in sections["Из долгого ящика"])


async def test_morning_digest_mentions_pending_plan_and_exams(auth_client, user):
    await task_with_steps(auth_client, 60)
    await call(user, "preview")  # превью не применено
    db, u = await fresh(user)
    async with db:
        msg = await Digest(db, u, at(MON, 8)).day(MON, morning=True)
    assert "План ждёт подтверждения" in msg.sections[0].lines[0]


async def test_today_digest_shows_upcoming_exam(auth_client, user):
    from .test_exams import make_exam, subject

    subj = await subject(auth_client)
    await make_exam(auth_client, subj["id"], days=3, location="1801")
    db, u = await fresh(user)
    async with db:
        digest = Digest(db, u)
        msg = await digest.day(digest.today)
    exams = next(s for s in msg.sections if s.heading == "Экзамены")
    assert "Экзамен: Климатология" in exams.lines[0] and "через 3 дня" in exams.lines[0]


# ---------- бот ----------


async def test_bot_pick_and_mark_done(tg, session, linked, auth_client):  # noqa: F811
    task = (
        await auth_client.post(f"{API}/tasks", json={"title": "Чтение", "estimate_min": 60})
    ).json()
    now = now_utc()
    event = await add_event(
        linked,
        kind=EventKind.subtask,
        title="Чтение",
        start=now - timedelta(minutes=1),
        end=now + timedelta(minutes=59),
        is_fixed=False,
        source_type=SourceType.task,
        source_id=task["id"],
    )
    r = await add_reminder(
        session,
        linked,
        kind=ReminderKind.evening_review,
        payload={"date": local_date(now, TZ).isoformat()},
    )
    msg = tg_message("Вечерний разбор")
    await press(tg, reminder_callback(ReminderAction.pick, r.id), msg)
    edit = tg.session.sent[-1]
    assert isinstance(edit, EditMessageReplyMarkup)
    data = buttons(edit.reply_markup)
    assert (f"✓ {event.start.astimezone(TZ):%H:%M} Чтение", f"rv:d:{event.id.hex}") in data
    assert data[-1][1] == reminder_callback(ReminderAction.reschedule, r.id)

    await press(
        tg, f"rv:d:{event.id.hex}", msg.model_copy(update={"reply_markup": edit.reply_markup})
    )
    session.expire_all()
    done = await session.get(Event, event.id)
    assert done.status == EventStatus.done


async def test_bot_free_command(tg, session, linked):  # noqa: F811
    session.add(
        BacklogItem(
            user_id=linked.id,
            title="Купить лампочки",
            status=BacklogStatus.active,
            conditions=[],
            estimate_min=15,
        )
    )
    await session.commit()
    [reply] = await tg.send("/free")
    assert reply == "Сколько есть времени?"
    assert ("30 мин", "fr:m:30") in buttons(tg.session.sent[-1].reply_markup)  # type: ignore[attr-defined]
    [reply] = await tg.send("/free 30")
    assert "Есть 30 мин" in reply or "подходящего сейчас нет" in reply
