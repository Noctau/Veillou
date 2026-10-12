"""M19.1: автозадачи от событий — материализация, перенос, отмена, идемпотентность,
срок «к следующему уроку» (сценарий репетитора и школьника)."""

from datetime import date, datetime, time, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from app.core.db import session_factory
from app.core.time import get_tz, now_utc, wall_to_utc
from app.domain.enums import TaskStatus
from app.domain.event_tasks import LOOKAHEAD
from app.models import Event, Task, User
from app.services.event_tasks import sync_user

from .test_schedule_api import make_rule

API = "/api/v1"
TZ = get_tz("Europe/Moscow")
TODAY = now_utc().astimezone(TZ).date()


def at(d: date, h: int, m: int = 0) -> datetime:
    return wall_to_utc(d, time(h, m), TZ)


async def _ok(resp, *codes: int) -> Any:
    assert resp.status_code in (codes or (200, 201)), resp.text
    return resp.json() if resp.status_code != 204 else None


async def tutor(c: AsyncClient, **rule_over: Any) -> dict[str, Any]:
    """Тип сферы «Ученик», ученица Маша, тип «Урок» и уроки по Вт и Чт 16:00–17:00."""
    student_type = await _ok(
        await c.post(
            f"{API}/area-types",
            json={
                "name": "Ученик",
                "name_plural": "Ученики",
                "fields": [{"label": "Класс", "type": "text"}],
                "sections": ["schedule", "tasks"],
            },
        )
    )
    masha = await _ok(
        await c.post(
            f"{API}/areas",
            json={
                "area_type_id": student_type["id"],
                "name": "Маша",
                "fields": {student_type["fields"][0]["id"]: "7"},
            },
        )
    )
    lesson = await _ok(
        await c.post(
            f"{API}/event-types",
            json={
                "name": "Урок",
                "name_plural": "Уроки",
                "fields": [{"label": "Тема", "type": "text"}],
            },
        )
    )
    rule = await make_rule(
        c,
        event_type_id=lesson["id"],
        area_id=masha["id"],
        pattern={"kind": "weekly", "weekdays": [2, 4]},
        start_time="16:00",
        end_time="17:00",
        **rule_over,
    )
    return {"area_type": student_type, "area": masha, "type": lesson, "rule": rule}


async def add_auto(c: AsyncClient, **body: Any) -> dict:
    return await _ok(await c.post(f"{API}/event-rules", json=body))


async def lessons(user: User) -> list[Event]:
    async with session_factory() as db:
        rows = await db.scalars(
            select(Event)
            .where(Event.user_id == user.id, Event.deleted_at.is_(None), Event.start > now_utc())
            .order_by(Event.start)
        )
        return list(rows)


async def tasks_of(user: User, rule_id: str | None = None) -> dict[Any, Task]:
    """Живые автозадачи по вхождению."""
    async with session_factory() as db:
        where = [
            Task.user_id == user.id,
            Task.deleted_at.is_(None),
            Task.origin_rule_id.is_not(None),
        ]
        if rule_id:
            where.append(Task.origin_rule_id == rule_id)
        return {t.origin_event_id: t for t in await db.scalars(select(Task).where(*where))}


async def run_sync(user: User, now: datetime | None = None):
    async with session_factory() as db:
        u = await db.get(User, user.id)
        assert u is not None
        stats = await sync_user(db, u, now)
        await db.commit()
        return stats


async def test_tutor_tasks_before_and_after(auth_client, user):
    """Сценарий 3: «Подготовить урок — {area}» за 30 мин до начала и «Проверить ДЗ —
    {area}» не позже чем через 2 дня после урока."""
    t = await tutor(auth_client)
    prep = await add_auto(
        auth_client,
        event_type_id=t["type"]["id"],
        when="before",
        title_template="Подготовить урок — {area} ({field:Класс} кл.)",
        estimate_min=45,
        offset_min=30,
    )
    check = await add_auto(
        auth_client,
        event_type_id=t["type"]["id"],
        when="after",
        title_template="Проверить ДЗ — {area}",
        estimate_min=20,
        within_days=2,
    )
    occ = await lessons(user)
    assert len(occ) > 10
    preps, checks = await tasks_of(user, prep["id"]), await tasks_of(user, check["id"])
    assert set(preps) == set(checks) == {e.id for e in occ}

    first, second = occ[0], occ[1]
    p, c = preps[second.id], checks[first.id]
    assert p.title == "Подготовить урок — Маша (7 кл.)"
    assert p.deadline == second.start - timedelta(minutes=30)
    assert p.earliest == max(first.end, second.start - LOOKAHEAD)
    assert (p.estimate_min, p.status, p.deadline_buffer_days) == (45, TaskStatus.active, 0)
    assert c.title == "Проверить ДЗ — Маша"
    assert (c.earliest, c.deadline) == (first.end, first.end + timedelta(days=2))
    assert c.area_id == first.area_id

    # Идемпотентно: повторная сверка ничего не создаёт
    stats = await run_sync(user)
    assert stats.created == 0
    assert len(await tasks_of(user, prep["id"])) + len(
        await tasks_of(user, check["id"])
    ) == 2 * len(occ)

    # Задача видна со ссылкой на событие
    detail = await _ok(await auth_client.get(f"{API}/tasks/{c.id}"))
    assert detail["origin_event"]["id"] == str(first.id)


async def test_moved_lesson_moves_window(auth_client, user):
    """Урок перенесли (вхождение отрывается от серии) — «проверить ДЗ» сдвинулось."""
    t = await tutor(auth_client)
    check = await add_auto(
        auth_client,
        event_type_id=t["type"]["id"],
        when="after",
        title_template="Проверить ДЗ — {area}",
        within_days=2,
    )
    lesson = (await lessons(user))[0]
    shift = timedelta(days=1, hours=2)
    await _ok(
        await auth_client.patch(
            f"{API}/events/{lesson.id}",
            json={
                "start": (lesson.start + shift).isoformat(),
                "end": (lesson.end + shift).isoformat(),
            },
        )
    )
    await run_sync(user)
    task = (await tasks_of(user, check["id"]))[lesson.id]
    assert task.earliest == lesson.end + shift
    assert task.deadline == lesson.end + shift + timedelta(days=2)
    async with session_factory() as db:
        moved = await db.get(Event, lesson.id)
        assert moved is not None
        assert moved.detached


async def test_cancelled_lesson_cancels_task_but_keeps_done(auth_client, user):
    t = await tutor(auth_client)
    prep = await add_auto(
        auth_client,
        event_type_id=t["type"]["id"],
        when="before",
        title_template="Подготовить урок",
        offset_min=30,
    )
    first, second = (await lessons(user))[:2]
    tasks = await tasks_of(user, prep["id"])
    await _ok(await auth_client.patch(f"{API}/tasks/{tasks[first.id].id}", json={"status": "done"}))
    for e in (first, second):
        await _ok(await auth_client.patch(f"{API}/events/{e.id}", json={"status": "cancelled"}))
    await run_sync(user)
    tasks = await tasks_of(user, prep["id"])
    assert tasks[first.id].status == TaskStatus.done
    assert tasks[second.id].status == TaskStatus.cancelled
    # Отменённое не возвращается
    await run_sync(user)
    assert (await tasks_of(user, prep["id"]))[second.id].status == TaskStatus.cancelled


async def test_until_next_and_schedule_rule_binding(auth_client, user):
    """Правило у конкретного правила расписания: «после» — до начала следующего урока."""
    t = await tutor(auth_client)
    rule = await add_auto(
        auth_client,
        schedule_rule_id=t["rule"]["id"],
        when="after",
        title_template="{event}: ДЗ",
        until_next=True,
    )
    occ = await lessons(user)
    tasks = await tasks_of(user, rule["id"])
    assert tasks[occ[0].id].deadline == occ[1].start
    assert tasks[occ[0].id].title == "Маша: ДЗ"  # название вхождения — сфера


async def test_delete_rule_removes_future_tasks(auth_client, user):
    t = await tutor(auth_client)
    rule = await add_auto(
        auth_client, event_type_id=t["type"]["id"], title_template="Подготовить", offset_min=0
    )
    assert await tasks_of(user, rule["id"])
    await _ok(await auth_client.delete(f"{API}/event-rules/{rule['id']}"), 204)
    assert await tasks_of(user, rule["id"]) == {}


async def test_confirm_rule_proposes_only_soon(auth_client, user):
    """С подтверждением — предложения только на сегодня и завтра, в списках задач их нет,
    вечерний разбор их показывает."""
    t = await tutor(auth_client)
    rule = await add_auto(
        auth_client,
        event_type_id=t["type"]["id"],
        title_template="Подготовить",
        confirm=True,
    )
    soon = wall_to_utc(TODAY + timedelta(days=2), time(0), TZ)
    occ = await lessons(user)
    tasks = await tasks_of(user, rule["id"])
    assert set(tasks) == {e.id for e in occ if e.start < soon}
    assert all(x.status == TaskStatus.proposed for x in tasks.values())
    listed = await _ok(await auth_client.get(f"{API}/tasks"))
    assert not any(x["status"] == "proposed" for x in listed)
    review = await _ok(await auth_client.get(f"{API}/review/evening"))
    assert {p["id"] for p in review["proposals"]} == {str(x.id) for x in tasks.values()}


async def test_rule_validation(auth_client):
    t = await tutor(auth_client)
    for body in (
        {"title_template": "x"},
        {
            "title_template": "x",
            "event_type_id": t["type"]["id"],
            "schedule_rule_id": t["rule"]["id"],
        },
        {"title_template": "", "event_type_id": t["type"]["id"]},
        {"title_template": "x", "event_type_id": t["type"]["id"], "within_days": 99},
    ):
        resp = await auth_client.post(f"{API}/event-rules", json=body)
        assert resp.status_code == 422, body


# ---------- срок «к следующему уроку» ----------


async def test_next_occurrence_deadline_after_pause(auth_client, user):
    """Школьник: «алгебра №245» — срок к следующему уроку сферы; на каникулах уроков
    нет — срок на первый урок после паузы; урок отменили — следующий."""
    start = TODAY - timedelta(days=7)
    pause_from, pause_to = TODAY, TODAY + timedelta(days=9)
    period = await _ok(
        await auth_client.post(
            f"{API}/periods",
            json={
                "name": "Четверть",
                "start_date": str(start),
                "end_date": str(TODAY + timedelta(days=60)),
                "pauses": [{"from": str(pause_from), "to": str(pause_to), "title": "Каникулы"}],
            },
        )
    )
    t = await tutor(auth_client, period_id=period["id"])
    hw = await _ok(
        await auth_client.post(
            f"{API}/task-types",
            json={"name": "ДЗ", "icon": "pencil", "deadline_rule": {"kind": "next_occurrence"}},
        )
    )
    task = await _ok(
        await auth_client.post(
            f"{API}/tasks",
            json={"title": "№245", "task_type_id": hw["id"], "area_id": t["area"]["id"]},
        )
    )
    occ = await lessons(user)
    assert occ[0].start.astimezone(TZ).date() > pause_to
    assert task["deadline_auto"] is True
    assert datetime.fromisoformat(task["deadline"]) == occ[0].start

    await _ok(await auth_client.patch(f"{API}/events/{occ[0].id}", json={"status": "cancelled"}))
    await run_sync(user)
    detail = await _ok(await auth_client.get(f"{API}/tasks/{task['id']}"))
    assert datetime.fromisoformat(detail["deadline"]) == occ[1].start

    # Поправили срок руками — больше не следует за расписанием
    manual = at(TODAY + timedelta(days=20), 12)
    await _ok(
        await auth_client.patch(f"{API}/tasks/{task['id']}", json={"deadline": manual.isoformat()})
    )
    await run_sync(user)
    detail = await _ok(await auth_client.get(f"{API}/tasks/{task['id']}"))
    assert (datetime.fromisoformat(detail["deadline"]), detail["deadline_auto"]) == (manual, False)


async def test_next_occurrence_without_area_has_no_deadline(auth_client):
    hw = await _ok(
        await auth_client.post(
            f"{API}/task-types",
            json={"name": "ДЗ", "icon": "pencil", "deadline_rule": {"kind": "next_occurrence"}},
        )
    )
    task = await _ok(
        await auth_client.post(f"{API}/tasks", json={"title": "x", "task_type_id": hw["id"]})
    )
    assert (task["deadline"], task["deadline_auto"]) == (None, False)


async def test_auto_task_planned_inside_window(auth_client, user):
    """Планировщик ставит «проверить ДЗ» не раньше конца урока и до срока."""
    from app.services.replan import ReplanService

    t = await tutor(auth_client)
    rule = await add_auto(
        auth_client,
        event_type_id=t["type"]["id"],
        when="after",
        title_template="Проверить ДЗ",
        within_days=2,
        estimate_min=30,
    )
    tasks = await tasks_of(user, rule["id"])
    async with session_factory() as db:
        u = await db.get(User, user.id)
        assert u is not None
        snap = await ReplanService(db, u).snapshot()
    blocks = {b.id: b for b in snap.inp.blocks}
    for event_id, task in tasks.items():
        block = blocks.get(f"task:{task.id}")
        if block is None:  # окно за горизонтом плана
            assert task.earliest is not None
            assert task.earliest >= now_utc() + timedelta(days=59)
            continue
        assert (block.earliest, block.deadline) == (task.earliest, task.deadline), event_id
