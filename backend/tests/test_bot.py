"""Бот: /today, /week, /add, свободный текст с «Изменить», кнопки напоминаний."""

from datetime import UTC, datetime, time, timedelta
from itertools import count

import pytest
from aiogram.methods import EditMessageReplyMarkup, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import cards
from app.core.time import get_tz, now_utc, wall_to_utc
from app.domain.enums import BacklogStatus, EventKind, EventStatus, ReminderKind, TaskStatus
from app.domain.quickparse import KindHint
from app.models import BacklogItem, Event, Reminder, Task, User
from app.notify.notifier import reminder_callback

from .test_reminders import add_reminder
from .test_telegram import TG_ID, BotHarness

TZ = get_tz("Europe/Moscow")
_ids = count(10_000)


@pytest.fixture
async def linked(session: AsyncSession, user: User) -> User:
    user.tg_user_id = TG_ID
    await session.commit()
    return user


@pytest.fixture
def tg() -> BotHarness:
    return BotHarness()


def tg_message(text: str, reply_to: Message | None = None) -> Message:
    return Message(
        message_id=next(_ids),
        date=datetime.now(UTC),
        chat=Chat(id=TG_ID, type="private"),
        from_user=TgUser(id=TG_ID, is_bot=False, first_name="Аня"),
        text=text,
        reply_to_message=reply_to,
    )


async def press(tg: BotHarness, data: str, message: Message) -> None:
    update = Update(
        update_id=next(_ids),
        callback_query=CallbackQuery(
            id=str(next(_ids)),
            from_user=TgUser(id=TG_ID, is_bot=False, first_name="Аня"),
            chat_instance="x",
            message=message,
            data=data,
        ),
    )
    await tg.dp.feed_update(tg.bot, update)


def last_markup(tg: BotHarness):
    return tg.session.sent[-1].reply_markup  # type: ignore[attr-defined]


def buttons(markup) -> list[tuple[str, str | None]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def active_tasks(session: AsyncSession) -> list[Task]:
    session.expire_all()
    return list(
        await session.scalars(
            select(Task).where(Task.deleted_at.is_(None), Task.status == TaskStatus.active)
        )
    )


async def active_backlog(session: AsyncSession) -> list[BacklogItem]:
    session.expire_all()
    return list(
        await session.scalars(
            select(BacklogItem).where(
                BacklogItem.deleted_at.is_(None), BacklogItem.status == BacklogStatus.active
            )
        )
    )


# ---------- ввод ----------


async def test_free_text_to_backlog(tg, session, linked):
    [reply] = await tg.send("записаться к стоматологу")
    assert "В ящике" in reply and "Записаться к стоматологу" in reply
    [item] = await active_backlog(session)
    assert item.title == "Записаться к стоматологу"
    assert ("Изменить", f"qa:edit:b:{item.id.hex}") in buttons(last_markup(tg))


async def test_add_task_with_deadline(tg, session, linked):
    """/add — всегда быстрый разбор, без ИИ (свободный текст без предмета ушёл бы в ИИ)."""
    [reply] = await tg.send("/add сдать реферат до 15 окт")
    assert "Задание" in reply and "до " in reply
    [task] = await active_tasks(session)
    assert task.deadline is not None
    assert task.task_type == "essay"


async def test_add_command(tg, session, linked):
    await tg.send("/add купить лампочки")
    assert [i.title for i in await active_backlog(session)] == ["Купить лампочки"]


async def test_add_without_text(tg, session, linked):
    [reply] = await tg.send("/add")
    assert "Что добавить" in reply
    assert await active_backlog(session) == []


async def test_free_text_event(tg, session, linked):
    [reply] = await tg.send("кино завтра в 19")
    assert "Событие" in reply
    event = await session.scalar(select(Event).where(Event.kind == EventKind.personal))
    assert event is not None
    local = event.start.astimezone(TZ)
    assert local.time() == time(19) and event.end - event.start == timedelta(hours=1)


async def test_edit_switch_backlog_to_task(tg, session, linked):
    original = tg_message("записаться к стоматологу")
    await tg.dp.feed_update(tg.bot, Update(update_id=next(_ids), message=original))
    [item] = await active_backlog(session)
    card = tg_message("✓ В ящике", reply_to=original)

    await press(tg, f"qa:edit:b:{item.id.hex}", card)
    assert isinstance(tg.session.sent[-1], EditMessageReplyMarkup)
    labels = [t for t, _ in buttons(last_markup(tg))]
    assert labels == ["→ Задание", "→ Событие", "Удалить", "← Назад"]

    await press(tg, f"qa:to:b:{item.id.hex}:t", card)
    assert await active_backlog(session) == []
    [task] = await active_tasks(session)
    assert task.title == "Записаться к стоматологу"
    edit = tg.session.sent[-1]
    assert isinstance(edit, EditMessageText) and "Задание" in edit.text


async def test_edit_to_event_without_time_is_refused(tg, session, linked):
    original = tg_message("записаться к стоматологу")
    await tg.dp.feed_update(tg.bot, Update(update_id=next(_ids), message=original))
    [item] = await active_backlog(session)
    await press(tg, f"qa:to:b:{item.id.hex}:e", tg_message("card", reply_to=original))
    assert [i.id for i in await active_backlog(session)] == [item.id]


async def test_delete_created(tg, session, linked):
    await tg.send("купить хлеб")
    [item] = await active_backlog(session)
    await press(tg, f"qa:del:b:{item.id.hex}", tg_message("card"))
    assert await active_backlog(session) == []
    assert tg.session.sent[-1].text == "Удалено."  # type: ignore[attr-defined]


# ---------- /today и /week ----------


async def add_class(session, user, start: datetime) -> Event:
    e = Event(
        user_id=user.id,
        kind=EventKind.class_,
        title="Климатология",
        start=start,
        end=start + timedelta(minutes=95),
        is_fixed=True,
        status=EventStatus.planned,
        location="1234",
        class_type="lecture",
    )
    session.add(e)
    await session.commit()
    return e


async def test_today(tg, session, linked):
    today = now_utc().astimezone(TZ).date()
    await add_class(session, linked, wall_to_utc(today, time(10, 45), TZ))
    session.add(
        Task(
            user_id=linked.id,
            title="Реферат",
            deadline=wall_to_utc(today + timedelta(days=2), time(23, 59), TZ),
            status=TaskStatus.active,
        )
    )
    session.add(BacklogItem(user_id=linked.id, title="записаться к стоматологу", status="active"))
    await session.commit()
    [reply] = await tg.send("/today")
    assert "10:45–12:20 Климатология (лекция) · ауд. 1234" in reply
    assert "Дедлайны недели" in reply and "Реферат" in reply
    assert "Из долгого ящика" in reply and "стоматологу" in reply


async def test_today_shows_overdue(tg, session, linked):
    today = now_utc().astimezone(TZ).date()
    for title, days in (("Эссе", -1), ("Лаба", 2)):
        session.add(
            Task(
                user_id=linked.id,
                title=title,
                deadline=wall_to_utc(today + timedelta(days=days), time(23, 59), TZ),
                status=TaskStatus.active,
            )
        )
    await session.commit()
    [reply] = await tg.send("/today")
    overdue, week = reply.split("Дедлайны недели")
    assert "Просрочено" in overdue and "Эссе" in overdue and "Лаба" not in overdue
    assert "Лаба" in week and "Эссе" not in week


async def test_today_empty(tg, linked):
    [reply] = await tg.send("/today")
    assert "Пар и дел в календаре нет" in reply


async def test_week(tg, session, linked):
    today = now_utc().astimezone(TZ).date()
    await add_class(session, linked, wall_to_utc(today + timedelta(days=2), time(9), TZ))
    [reply] = await tg.send("/week")
    assert reply.startswith("<b>Неделя")
    assert "Климатология" in reply


# ---------- кнопки напоминаний ----------


async def test_reminder_done_button(tg, session, linked):
    task = Task(
        user_id=linked.id,
        title="Реферат",
        deadline=now_utc() + timedelta(days=1),
        status=TaskStatus.active,
    )
    session.add(task)
    await session.commit()
    r = await add_reminder(
        session,
        linked,
        kind=ReminderKind.deadline,
        entity_type="task",
        entity_id=task.id,
        payload={"deadline": task.deadline.isoformat()},
    )
    await press(tg, reminder_callback("done", r.id), tg_message("Напоминание"))
    await session.refresh(task)
    assert task.status == TaskStatus.done
    assert any(
        isinstance(m, SendMessage) and m.text.startswith("✓ Готово") for m in tg.session.sent
    )


async def test_reminder_button_of_other_user_is_rejected(tg, session, linked):
    from app.services.users import create_user

    other = await create_user(session, email="o@example.com", password="x" * 12)
    r = await add_reminder(session, other, kind=ReminderKind.deadline)
    await press(tg, reminder_callback("done", r.id), tg_message("x"))
    assert (await session.get(Reminder, r.id)).action_used_at is None


# ---------- callback_data ----------


def test_callback_data_fits_telegram_limit():
    import uuid

    id = uuid.uuid4()
    data = cards._qa("to", KindHint.backlog, id, KindHint.event)
    assert len(data.encode()) <= 64
    assert cards.parse_quick_add(data) == cards.QuickAddData(
        "to", KindHint.backlog, id, KindHint.event
    )
    assert len(reminder_callback("tomorrow", id).encode()) <= 64
    assert cards.parse_reminder(reminder_callback("snooze", id)) == ("snooze", id)


@pytest.mark.parametrize("data", ["qa:", "qa:to:b:zz", "qa:to:b:" + "0" * 32, "qa:x:t:" + "0" * 32])
def test_bad_callback_data(data):
    assert cards.parse_quick_add(data) is None


async def test_create_bot_real_constructor() -> None:
    # Прод падал на старте бота и воркера: в dev токена нет, и create_bot не вызывался нигде
    from app.bot.app import create_bot

    bot = create_bot("123456:TEST-token")
    try:
        assert bot.default.link_preview_is_disabled is True
    finally:
        await bot.session.close()
