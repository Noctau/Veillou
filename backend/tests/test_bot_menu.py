"""Бот: управление кнопками — меню, задания, шаги, календарь, ящик, проекты,
заметки, поиск, план, разбор, настройки и ввод текстом."""

from datetime import datetime, time, timedelta

import pytest
from aiogram.methods import EditMessageText, SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import kit
from app.core.time import get_tz, local_date, now_utc, wall_to_utc
from app.domain.enums import (
    BacklogStatus,
    EventStatus,
    MilestoneStatus,
    Priority,
    SubtaskStatus,
    TaskStatus,
)
from app.models import BacklogItem, Event, Milestone, Note, Project, Subtask, Task, User
from app.schemas.backlog import BacklogCreate
from app.schemas.event import EventCreate
from app.schemas.note import NoteCreate
from app.schemas.project import MilestoneCreate
from app.schemas.task import TaskCreate
from app.services.backlog import BacklogService
from app.services.events import EventService
from app.services.notes import NoteService
from app.services.projects import ProjectService
from app.services.settings import effective_settings
from app.services.tasks import TaskService

from .test_bot import buttons, press, tg_message
from .test_telegram import TG_ID, BotHarness

TZ = get_tz("Europe/Moscow")


@pytest.fixture
async def linked(session: AsyncSession, user: User) -> User:
    user.tg_user_id = TG_ID
    await session.commit()
    return user


@pytest.fixture
def tg() -> BotHarness:
    return BotHarness()


def screen(tg: BotHarness) -> tuple[str, list[tuple[str, str | None]]]:
    """Последний показанный экран: текст и кнопки (новое сообщение или правка)."""
    for method in reversed(tg.session.sent):
        if isinstance(method, SendMessage | EditMessageText):
            markup = method.reply_markup
            return method.text, buttons(markup) if markup else []
    raise AssertionError("Экранов не было")


def data_of(tg: BotHarness, text_part: str) -> str:
    """callback_data кнопки, в подписи которой есть `text_part`."""
    _, btns = screen(tg)
    for text, data in btns:
        if text_part in text and data:
            return data
    raise AssertionError(f"Нет кнопки «{text_part}» среди {btns}")


async def click(tg: BotHarness, text_part: str) -> str:
    """Нажимает кнопку последнего экрана; возвращает текст нового экрана."""
    await press(tg, data_of(tg, text_part), tg_message("экран"))
    return screen(tg)[0]


async def fresh[M](session: AsyncSession, model: type[M], id) -> M:
    session.expire_all()
    obj = await session.get(model, id)
    assert obj is not None
    return obj


async def make_task(user: User, **kw) -> Task:
    from app.core.db import session_factory

    async with session_factory() as db:
        detail = await TaskService(db, user).create(
            TaskCreate(title=kw.pop("title", "Реферат"), **kw)
        )
    return detail  # type: ignore[return-value]


# ---------- разбор ввода ----------


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("90", 90),
        ("1.5 ч", 90),
        ("1,5 часа", 90),
        ("1 ч 30 мин", 90),
        ("2ч", 120),
        ("45 мин", 45),
        ("на 20 минут", 20),
        ("полчаса", None),
        ("", None),
    ],
)
def test_parse_minutes(text: str, minutes: int | None):
    assert kit.parse_minutes(text) == minutes


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Найти источники, 40 мин", ("Найти источники", 40)),
        ("Написать введение — 1.5 ч", ("Написать введение", 90)),
        ("Прочитать главу 3", ("Прочитать главу", 3)),
        ("Сдать", ("Сдать", None)),
        ("Созвон на 30 мин", ("Созвон", 30)),
    ],
)
def test_split_step(text: str, expected: tuple[str, int | None]):
    assert kit.split_step(text) == expected


def test_callback_data_fits_telegram_limit():
    import uuid

    data = kit.cb("ask", "dsc", uuid.uuid4())
    assert len(data.encode()) <= 64
    assert kit.parse(data) == ("ask", ["dsc", data.split(":")[-1]])
    assert kit.parse("qa:edit") is None


# ---------- меню и команды ----------


async def test_menu_lists_sections(tg, linked):
    [reply] = await tg.send("/menu")
    assert "Меню" in reply
    labels = [t for t, _ in screen(tg)[1]]
    for label in ("Сегодня", "Задания", "Ящик", "Проекты", "Заметки", "Поиск", "План", "Настройки"):
        assert any(label in t for t in labels), label


async def test_help_mentions_new_commands(tg, linked):
    [reply] = await tg.send("/help")
    for cmd in ("/menu", "/tasks", "/day", "/inbox", "/notes", "/search", "/plan", "/settings"):
        assert cmd in reply


async def test_stranger_cannot_use_menu(tg, user):
    assert await tg.send("/menu") == []


# ---------- задания ----------


async def test_task_card_done_and_back(tg, session, linked):
    task = await make_task(linked, title="Эссе", estimate_min=60)
    await tg.send("/tasks")
    text = await click(tg, "Эссе")
    assert "<b>Эссе</b>" in text
    assert "⏱ 1 ч" in text
    await click(tg, "Готово")
    assert (await fresh(session, Task, task.id)).status == TaskStatus.done
    await click(tg, "Вернуть")
    assert (await fresh(session, Task, task.id)).status == TaskStatus.active


async def test_task_priority_toggle(tg, session, linked):
    task = await make_task(linked)
    await tg.send("/tasks")
    await click(tg, "Реферат")
    await click(tg, "Важное")
    assert (await fresh(session, Task, task.id)).priority == Priority.high


async def test_task_without_estimate_warns(tg, linked):
    await make_task(linked)
    await tg.send("/tasks")
    text = await click(tg, "Реферат")
    assert "время не указано" in text


async def test_set_estimate_by_text(tg, session, linked):
    task = await make_task(linked)
    await tg.send("/tasks")
    await click(tg, "Реферат")
    await press(tg, data_of(tg, "Время"), tg_message("экран"))
    assert "Сколько займёт" in tg.session.texts[-1]
    replies = await tg.send("1 ч 30 мин")
    assert "1 ч 30 мин" in replies[-1]
    assert (await fresh(session, Task, task.id)).estimate_min == 90


async def test_bad_input_keeps_waiting_then_cancel(tg, session, linked):
    task = await make_task(linked)
    await tg.send("/tasks")
    await click(tg, "Реферат")
    await press(tg, data_of(tg, "Время"), tg_message("экран"))
    [reply] = await tg.send("сколько-то")
    assert "Не понял время" in reply
    # Всё ещё ждём время
    await tg.send("45")
    assert (await fresh(session, Task, task.id)).estimate_min == 45
    # После ответа текст снова идёт в быстрый ввод
    await tg.send("записаться к стоматологу")
    items = list(await session.scalars(select(BacklogItem)))
    assert [i.title for i in items] == ["Записаться к стоматологу"]


async def test_cancel_and_command_drop_pending_input(tg, session, linked):
    task = await make_task(linked)
    await tg.send("/tasks")
    await click(tg, "Реферат")
    await press(tg, data_of(tg, "Название"), tg_message("экран"))
    [reply] = await tg.send("/cancel")
    assert reply == "Отменил."
    await tg.send("купить хлеб")
    assert (await fresh(session, Task, task.id)).title == "Реферат"

    await tg.send("/tasks")
    await click(tg, "Реферат")
    await press(tg, data_of(tg, "Название"), tg_message("экран"))
    await tg.send("/today")  # любая команда отменяет ввод
    await tg.send("купить молоко")
    assert (await fresh(session, Task, task.id)).title == "Реферат"


async def test_set_deadline_title_description(tg, session, linked):
    task = await make_task(linked)
    await tg.send("/tasks")
    await click(tg, "Реферат")
    await press(tg, data_of(tg, "Срок"), tg_message("экран"))
    await tg.send("завтра в 18:00")
    t = await fresh(session, Task, task.id)
    assert t.deadline is not None
    tomorrow = local_date(now_utc(), TZ) + timedelta(days=1)
    assert t.deadline == wall_to_utc(tomorrow, time(18), TZ)

    await press(tg, data_of(tg, "Срок"), tg_message("экран"))
    await tg.send("нет")
    assert (await fresh(session, Task, task.id)).deadline is None

    await press(tg, data_of(tg, "Название"), tg_message("экран"))
    await tg.send("Реферат по истории")
    await press(tg, data_of(tg, "Описание"), tg_message("экран"))
    await tg.send("10 страниц, шрифт 14")
    t = await fresh(session, Task, task.id)
    assert (t.title, t.description) == ("Реферат по истории", "10 страниц, шрифт 14")


async def test_steps_add_toggle_delete(tg, session, linked):
    task = await make_task(linked, estimate_min=120)
    await tg.send("/tasks")
    await click(tg, "Реферат")
    await press(tg, data_of(tg, "Шаг"), tg_message("экран"))
    reply = (await tg.send("Найти источники, 40 мин"))[-1]
    assert "Найти источники — 40 мин" in reply
    # С шагами время задания — их сумма, своё поле времени скрыто
    assert "40 мин (сумма шагов)" in reply
    assert not any("Время" in t for t, _ in screen(tg)[1])

    [step] = list(await session.scalars(select(Subtask).where(Subtask.task_id == task.id)))
    assert step.estimate_min == 40
    await click(tg, "Отметить шаги")
    await click(tg, "Найти источники")
    assert (await fresh(session, Subtask, step.id)).status == SubtaskStatus.done
    await click(tg, "🗑")
    assert (await fresh(session, Subtask, step.id)).deleted_at is not None


async def test_delete_task_asks_first(tg, session, linked):
    task = await make_task(linked)
    await tg.send("/tasks")
    await click(tg, "Реферат")
    text = await click(tg, "Удалить")
    assert "Удалить задание" in text
    assert (await fresh(session, Task, task.id)).deleted_at is None
    await click(tg, "Да, удалить")
    assert (await fresh(session, Task, task.id)).deleted_at is not None


async def test_new_task_from_list(tg, session, linked):
    await tg.send("/tasks")
    await press(tg, data_of(tg, "Новое"), tg_message("экран"))
    # Похоже на дело в ящик, но просили задание
    reply = (await tg.send("купить лампочки"))[-1]
    assert "<b>Купить лампочки</b>" in reply
    [task] = list(await session.scalars(select(Task)))
    assert task.title == "Купить лампочки"


async def test_done_tasks_list(tg, session, linked):
    task = await make_task(linked, title="Старое")
    from app.core.db import session_factory
    from app.schemas.task import TaskUpdate

    async with session_factory() as db:
        await TaskService(db, linked).update(task.id, TaskUpdate(status=TaskStatus.done))
    await tg.send("/tasks")
    assert not any("Старое" in t for t, _ in screen(tg)[1])
    await click(tg, "Сделанные")
    assert any("Старое" in t for t, _ in screen(tg)[1])


async def test_foreign_task_button_is_not_found(tg, session, linked):
    from app.services.users import create_user

    other = await create_user(session, email="other@example.com", password="x" * 12)
    task = await make_task(other, title="Чужое")
    await press(tg, kit.cb("t", task.id), tg_message("экран"))
    answer = tg.session.sent[-1]
    assert "не найдено" in answer.text.lower()  # type: ignore[attr-defined]


async def test_broken_callback_is_ignored(tg, linked):
    await press(tg, "m:t:zzz", tg_message("экран"))
    await press(tg, "m:unknown", tg_message("экран"))
    assert not tg.session.texts


# ---------- календарь ----------


async def add_event(user: User, title: str, start: datetime, minutes: int = 90) -> Event:
    from app.core.db import session_factory

    async with session_factory() as db:
        return await EventService(db, user).create(
            EventCreate(title=title, start=start, end=start + timedelta(minutes=minutes))
        )


async def test_day_view_and_event_actions(tg, session, linked):
    today = local_date(now_utc(), TZ)
    event = await add_event(linked, "Созвон", wall_to_utc(today, time(23, 0), TZ), 30)
    [reply] = await tg.send("/day")
    assert "сегодня" in reply
    assert "23:00–23:30" in reply
    text = await click(tg, "Созвон")
    assert "<b>Созвон</b>" in text
    await click(tg, "Сделано")
    assert (await fresh(session, Event, event.id)).status == EventStatus.done
    await click(tg, "Вернуть")
    await click(tg, "Отменить")
    assert (await fresh(session, Event, event.id)).status == EventStatus.cancelled


async def test_day_navigation_and_command_date(tg, linked):
    today = local_date(now_utc(), TZ)
    tomorrow = today + timedelta(days=1)
    await add_event(linked, "Кино", wall_to_utc(tomorrow, time(19), TZ))
    await tg.send("/day")
    text = await click(tg, "▶")
    assert "Кино" in text
    [reply] = await tg.send("/day завтра")
    assert "Кино" in reply


async def test_move_event(tg, session, linked):
    today = local_date(now_utc(), TZ)
    event = await add_event(linked, "Созвон", wall_to_utc(today, time(23), TZ), 30)
    await tg.send("/day")
    await click(tg, "Созвон")
    await press(tg, data_of(tg, "Перенести"), tg_message("экран"))
    [reply] = await tg.send("так")
    assert "Нужно время" in reply
    await tg.send("завтра в 15")
    e = await fresh(session, Event, event.id)
    tomorrow = today + timedelta(days=1)
    assert e.start == wall_to_utc(tomorrow, time(15), TZ)
    assert e.end - e.start == timedelta(minutes=30)


async def test_delete_event_and_new_event(tg, session, linked):
    today = local_date(now_utc(), TZ)
    event = await add_event(linked, "Лишнее", wall_to_utc(today, time(23), TZ))
    await tg.send("/day")
    await click(tg, "Лишнее")
    await click(tg, "Удалить")
    await click(tg, "Да")
    assert (await fresh(session, Event, event.id)).deleted_at is not None

    await click(tg, "▶")  # завтра
    await press(tg, data_of(tg, "Событие"), tg_message("экран"))
    reply = (await tg.send("стоматолог в 10"))[-1]
    assert "<b>Стоматолог</b>" in reply
    created = await session.scalar(select(Event).where(Event.title == "Стоматолог"))
    assert created is not None
    assert local_date(created.start, TZ) == today + timedelta(days=1)


# ---------- ящик ----------


async def test_inbox_flow(tg, session, linked):
    await tg.send("/inbox")
    await press(tg, data_of(tg, "Новое дело"), tg_message("экран"))
    await tg.send("записаться к врачу")
    item = await session.scalar(select(BacklogItem))
    assert item is not None
    assert item.title == "Записаться к врачу"

    await click(tg, "На неделю")
    assert (await fresh(session, BacklogItem, item.id)).planned_week is not None
    await click(tg, "Снять с недели")
    assert (await fresh(session, BacklogItem, item.id)).planned_week is None

    await press(tg, data_of(tg, "Время"), tg_message("экран"))
    await tg.send("45")
    assert (await fresh(session, BacklogItem, item.id)).estimate_min == 45

    await click(tg, "Сделано")
    assert (await fresh(session, BacklogItem, item.id)).status == BacklogStatus.done


async def test_inbox_item_to_task(tg, session, linked):
    from app.core.db import session_factory

    async with session_factory() as db:
        item = await BacklogService(db, linked).create(
            BacklogCreate(title="Почитать про CP-SAT", estimate_min=60)
        )
    await tg.send("/inbox")
    await click(tg, "Почитать")
    text = await click(tg, "В задание")
    assert "<b>Почитать про CP-SAT</b>" in text
    [task] = list(await session.scalars(select(Task)))
    assert task.estimate_min == 60
    assert (await fresh(session, BacklogItem, item.id)).deleted_at is not None


# ---------- проекты ----------


async def test_projects_flow(tg, session, linked):
    await tg.send("/projects")
    await press(tg, data_of(tg, "Новый проект"), tg_message("экран"))
    await tg.send("Курсовая")
    project = await session.scalar(select(Project))
    assert project is not None
    assert project.title == "Курсовая"
    project_id = project.id

    from app.core.db import session_factory

    async with session_factory() as db:
        m = await ProjectService(db, linked).add_milestone(
            project_id, MilestoneCreate(title="Глава 1")
        )
    await tg.send("/projects")
    await click(tg, "Курсовая")
    await click(tg, "Глава 1")
    assert (await fresh(session, Milestone, m.id)).status == MilestoneStatus.done

    await press(tg, data_of(tg, "➕ Задание"), tg_message("экран"))
    reply = (await tg.send("введение до 1 дек на 2 часа"))[-1]
    assert "<b>Введение</b>" in reply
    task = await session.scalar(select(Task).where(Task.project_id == project_id))
    assert task is not None
    assert task.estimate_min == 120

    await tg.send("/projects")
    await click(tg, "Курсовая")
    text = await click(tg, "Задания")
    assert "Курсовая" in text
    assert any("Введение" in t for t, _ in screen(tg)[1])
    await click(tg, "Проект")
    await click(tg, "Завершить")
    assert (await fresh(session, Project, project_id)).status == "done"


# ---------- заметки и поиск ----------


async def test_note_command_and_append(tg, session, linked):
    [reply] = await tg.send("/note Список литературы\nЛотман, Бахтин")
    assert "<b>Список литературы</b>" in reply
    note = await session.scalar(select(Note))
    assert note is not None
    assert note.body_md == "Лотман, Бахтин"
    note_id = note.id
    await press(tg, data_of(tg, "Дописать"), tg_message("экран"))
    await tg.send("Аверинцев")
    assert (await fresh(session, Note, note_id)).body_md == "Лотман, Бахтин\n\nАверинцев"


async def test_note_without_text(tg, linked):
    [reply] = await tg.send("/note")
    assert "Напишите текст заметки" in reply


async def test_search_finds_notes_and_tasks(tg, linked):
    from app.core.db import session_factory

    async with session_factory() as db:
        await NoteService(db, linked).create(
            NoteCreate(title="Лекция", body_md="Теорема Ферма и её доказательство")
        )
    await make_task(linked, title="Доклад про Ферма")
    [reply] = await tg.send("/search Ферма")
    assert "найдено 2" in reply
    labels = [t for t, _ in screen(tg)[1]]
    assert any("Доклад про Ферма" in t for t in labels)
    assert any("Лекция" in t for t in labels)


async def test_notes_list_and_delete(tg, session, linked):
    await tg.send("/note Купить билеты")
    await tg.send("/notes")
    await click(tg, "Купить билеты")
    await click(tg, "Удалить")
    await click(tg, "Да")
    note = await session.scalar(select(Note))
    assert note is not None
    assert note.deleted_at is not None


# ---------- план, разбор, настройки ----------


async def test_plan_preview_and_apply(tg, session, linked):
    await make_task(
        linked,
        title="Отчёт",
        estimate_min=60,
        deadline=now_utc() + timedelta(days=3),
    )
    await tg.send("/plan")
    await click(tg, "Пересчитать")
    text, _ = screen(tg)
    assert "Превью плана" in text
    await click(tg, "Применить")
    blocks = list(
        await session.scalars(
            select(Event).where(Event.title == "Отчёт", Event.deleted_at.is_(None))
        )
    )
    assert blocks, "задание без шагов, но со временем — в плане"
    assert sum((b.end - b.start).total_seconds() for b in blocks) == 3600
    await click(tg, "Отменить последнее")
    session.expire_all()
    left = list(
        await session.scalars(
            select(Event).where(Event.title == "Отчёт", Event.deleted_at.is_(None))
        )
    )
    assert not left


async def test_review_marks_and_reschedules(tg, session, linked):
    task = await make_task(linked, title="Конспект", estimate_min=60)
    start = now_utc() - timedelta(hours=1)
    session.add(
        Event(
            user_id=linked.id,
            kind="subtask",
            title="Конспект",
            start=start,
            end=start + timedelta(minutes=30),
            is_fixed=False,
            status=EventStatus.planned,
            source_type="task",
            source_id=task.id,
        )
    )
    await session.commit()
    if local_date(start, TZ) != local_date(now_utc(), TZ):
        pytest.skip("около полуночи блок «прошедший» попадает во вчера")
    [reply] = await tg.send("/review")
    assert "Не отмечено: 1" in reply
    await click(tg, "Конспект")
    assert "Всё отмечено" in screen(tg)[0]


async def test_settings_toggle_reminder_and_buffer(tg, session, linked):
    user_id = linked.id
    [reply] = await tg.send("/settings")
    assert "Часовой пояс: Europe/Moscow" in reply
    await click(tg, "Утренняя сводка")
    session.expire_all()
    user = await session.get(User, user_id)
    assert user is not None
    assert not effective_settings(user).reminders.morning_digest.enabled
    before = effective_settings(user).deadline_buffer_days
    await click(tg, "+ день")
    session.expire_all()
    user = await session.get(User, user_id)
    assert user is not None
    assert effective_settings(user).deadline_buffer_days == before + 1


async def test_screen_edits_message_in_place(tg, linked):
    await tg.send("/menu")
    await press(tg, data_of(tg, "Задания"), tg_message("экран"))
    assert isinstance(tg.session.sent[-2], EditMessageText)
