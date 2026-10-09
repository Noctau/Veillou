"""M10.5–M10.6 в боте: неуверенный текст → ИИ-карточка, фото → задание, разбивка."""

from datetime import UTC, datetime
from itertools import count
from pathlib import Path

import pytest
from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import Chat, Message, PhotoSize, Update
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import set_provider
from app.ai.fake import FakeProvider
from app.bot import handlers
from app.core.config import settings
from app.core.db import session_factory
from app.domain.enums import SubtaskStatus
from app.models import Attachment, BacklogItem, PlanRevision, Subtask, Task, User
from app.services.replan import ReplanService

from .test_ai import breakdown_answer, parsed_answer, photo_answer, run_jobs
from .test_bot import buttons, linked, press, tg, tg_message
from .test_telegram import TG_ID, BotHarness

__all__ = ["linked", "tg"]
_ids = count(50_000)

LONG = (
    "Реферат по климатологии: тема — муссоны Южной Азии. Объём 10–12 страниц, "
    "не меньше 5 источников, оформление по ГОСТу"
)


@pytest.fixture
def fake():
    provider = FakeProvider()
    set_provider(provider)
    yield provider
    set_provider(None)


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(settings, "APP_URL", "https://veillou.test")
    monkeypatch.setattr(ReplanService, "time_limit_s", 0.4)


def sent(tg: BotHarness, kind: type) -> list:
    return [m for m in tg.session.sent if isinstance(m, kind)]


def as_message(method) -> Message:
    """Сообщение бота (для нажатия кнопки на нём)."""
    return Message(
        message_id=next(_ids),
        date=datetime.now(UTC),
        chat=Chat(id=TG_ID, type="private"),
        text=method.text,
        reply_markup=method.reply_markup,
    )


async def tasks(session: AsyncSession) -> list[Task]:
    session.expire_all()
    return list(await session.scalars(select(Task).where(Task.deleted_at.is_(None))))


def parse_answer(**over) -> str:
    data = {
        "title": "Реферат о муссонах",
        "task_type": "essay",
        "deadline_date": "2030-03-01",
        "description": "10–12 страниц, 5 источников, ГОСТ",
    }
    return parsed_answer(**{**data, **over})


async def test_short_clear_text_skips_ai(tg, linked, session, fake):
    await tg.dp.feed_update(tg.bot, Update(update_id=next(_ids), message=tg_message("купить хлеб")))
    assert fake.calls == []
    assert len(list(await session.scalars(select(BacklogItem)))) == 1


async def test_long_text_goes_to_ai_and_create_and_break_down(tg, linked, session, fake):
    await tg.dp.feed_update(tg.bot, Update(update_id=next(_ids), message=tg_message(LONG)))
    assert sent(tg, SendMessage)[-1].text == "🤖 Разбираю…"
    assert await tasks(session) == []  # пока только черновик

    fake.push(parse_answer())
    await run_jobs(tg.bot)
    card = sent(tg, EditMessageText)[-1]
    assert "Реферат о муссонах" in card.text
    assert "Реферат" in card.text
    labels = [t for t, _ in buttons(card.reply_markup)]
    assert labels == ["Создать и разбить", "Создать", "Изменить"]

    mk = buttons(card.reply_markup)[0][1]
    await press(tg, mk, as_message(card))
    [task] = await tasks(session)
    task_id = task.id
    assert task.title == "Реферат о муссонах"
    assert task.task_type == "essay"
    assert "ГОСТ" in task.description
    assert task.deadline is not None
    assert "Разбиваю на шаги" in sent(tg, EditMessageText)[-1].text

    # Повторное нажатие не создаёт второе задание
    await press(tg, mk, as_message(card))
    assert len(await tasks(session)) == 1

    fake.push(breakdown_answer())
    await run_jobs(tg.bot)
    steps = sent(tg, SendMessage)[-1]
    assert "Шаги для «Реферат о муссонах»" in steps.text
    assert "1. Найти 3 источника" in steps.text
    assert "(после 1)" in steps.text
    kb = buttons(steps.reply_markup)
    assert kb[0][0] == "Запланировать"
    assert any("Поправить" in t for t, _ in kb)

    await press(tg, kb[0][1], as_message(steps))
    session.expire_all()
    subtasks = list(await session.scalars(select(Subtask).where(Subtask.task_id == task_id)))
    assert len(subtasks) == 3
    assert all(s.status == SubtaskStatus.todo for s in subtasks)
    plan_msg = sent(tg, SendMessage)[-1]
    assert plan_msg.text.startswith("Превью плана")
    apply = next(cb for t, cb in buttons(plan_msg.reply_markup) if t == "Применить план")

    await press(tg, apply, as_message(plan_msg))
    rev = await session.scalar(select(PlanRevision).order_by(PlanRevision.created_at.desc()))
    assert rev is not None
    assert rev.status == "applied"


async def test_edit_to_backlog_and_raw(tg, linked, session, fake):
    await tg.dp.feed_update(tg.bot, Update(update_id=next(_ids), message=tg_message(LONG)))
    fake.push(parse_answer())
    await run_jobs(tg.bot)
    card = sent(tg, EditMessageText)[-1]
    edit = dict(buttons(card.reply_markup))["Изменить"]
    await press(tg, edit, as_message(card))
    markup = tg.session.sent[-1].reply_markup  # type: ignore[attr-defined]
    labels = dict(buttons(markup))
    assert "→ В ящик" in labels
    assert "Как написано, без ИИ" in labels

    await press(tg, labels["→ В ящик"], as_message(card))
    items = list(await session.scalars(select(BacklogItem)))
    assert [i.title for i in items] == ["Реферат о муссонах"]
    assert await tasks(session) == []


async def test_ai_unavailable_waits_in_queue_then_answers(tg, linked, fake):
    import httpx

    from .test_ai import run_ai_later

    await tg.dp.feed_update(tg.bot, Update(update_id=next(_ids), message=tg_message(LONG)))
    fake.push(httpx.ConnectError("нет"))
    await run_jobs(tg.bot)
    edits = sent(tg, EditMessageText)
    assert len(edits) == 1
    assert "в очереди" in edits[0].text

    # Снова недоступен — второй раз не пишем
    fake.push(httpx.ConnectError("нет"))
    await run_ai_later(2, tg.bot)
    assert len(sent(tg, EditMessageText)) == 1

    # Появился — то же сообщение становится карточкой
    fake.push(parse_answer())
    await run_ai_later(10, tg.bot)
    card = sent(tg, EditMessageText)[-1]
    assert "Реферат о муссонах" in card.text
    assert card.message_id == edits[0].message_id


async def test_ai_error_reported_in_chat(tg, linked, fake):
    await tg.dp.feed_update(tg.bot, Update(update_id=next(_ids), message=tg_message(LONG)))
    fake.push("мусор", "опять мусор")
    await run_jobs(tg.bot)
    assert "ИИ ответил непонятно" in sent(tg, EditMessageText)[-1].text


async def test_photo_creates_task_and_recognizes(tg, linked, session, fake, monkeypatch):
    async def download(bot, file_id: str) -> bytes:
        return b"\xff\xd8jpeg"

    monkeypatch.setattr(handlers, "download", download)
    message = Message(
        message_id=next(_ids),
        date=datetime.now(UTC),
        chat=Chat(id=TG_ID, type="private"),
        from_user=TgUser(id=TG_ID, is_bot=False, first_name="Аня"),
        photo=[
            PhotoSize(file_id="small", file_unique_id="s", width=90, height=90),
            PhotoSize(file_id="big", file_unique_id="b", width=1280, height=960),
        ],
    )
    await tg.dp.feed_update(tg.bot, Update(update_id=next(_ids), message=message))
    [task] = await tasks(session)
    assert task.title == "Задание с фото"
    [att] = list(await session.scalars(select(Attachment)))
    assert att.owner_id == task.id
    assert att.mime == "image/jpeg"
    assert sent(tg, SendMessage)[-1].text == "📷 Распознаю фото…"

    fake.push(photo_answer(title="Задачи 1–5", text="Решить задачи 1–5", task_type="homework"))
    await run_jobs(tg.bot)
    card = sent(tg, EditMessageText)[-1]
    assert "Задачи 1–5" in card.text
    assert "Решить задачи 1–5" in card.text
    assert [t for t, _ in buttons(card.reply_markup)] == ["Разбить на шаги", "Открыть", "Удалить"]
    async with session_factory() as db:
        fresh = await db.get(Task, task.id)
        assert fresh is not None
        assert fresh.task_type == "homework"
        assert (await db.get(User, fresh.user_id)) is not None
