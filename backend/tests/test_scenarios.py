"""Сценарии приёмки Part 2 (TZ §3), которые замыкает M22.3.

5. Офис 5/2: режим 9–18 с обедом, стендап по будням и планирование по средам,
   лимит «Фокус-работа» 5 ч, задачи со сроками и проект с нормой, звонки клиентам —
   только в рабочее время. Конфигурация — сборкой (M21.3).
6. Плавающий график: без регулярной занятости — задачи, дело в ящике, окна типов
   действий и лимит; разовое жёсткое событие — быстрым вводом.
"""

from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Any

from httpx import AsyncClient

from app.core.db import session_factory
from app.core.time import wall_to_utc
from app.models import User
from app.services.replan import ReplanService

from .student import API, NOW, TODAY, TZ, Clock

WEEKDAYS = [1, 2, 3, 4, 5]
FLEXIBLE = {"subtask", "backlog", "project", "prep"}

OFFICE: dict[str, Any] = {
    "action_types": [
        {
            "ref": "Фокус-работа",
            "name": "Фокус-работа",
            "windows": [{"weekdays": WEEKDAYS, "start": "09:00", "end": "18:00"}],
        },
        {
            "ref": "Связь с людьми",
            "name": "Связь с людьми",
            "windows": [{"weekdays": WEEKDAYS, "start": "09:00", "end": "18:00"}],
            "prefer_morning": True,
            "synonyms": ["позвонить", "созвон", "клиент"],
        },
    ],
    "task_types": [{"ref": "Отчёт", "name": "Отчёт", "action_type": "Фокус-работа"}],
    "event_types": [
        {
            "ref": "Встреча",
            "name": "Встреча",
            "name_plural": "Встречи",
            "remind_before_min": 10,
            "show_now_next": True,
            "synonyms": ["стендап", "планирование"],
        }
    ],
    "schedule_rules": [
        {
            "ref": "Стендап",
            "event_type": "Встреча",
            "title": "Стендап",
            "pattern": {"kind": "weekly", "weekdays": WEEKDAYS},
            "start_time": "10:00",
            "end_time": "10:15",
        },
        {
            "ref": "Планирование",
            "event_type": "Встреча",
            "title": "Планирование",
            "pattern": {"kind": "weekly", "weekdays": [3]},
            "start_time": "14:00",
            "end_time": "15:00",
        },
    ],
    "day_profiles": [
        {
            "ref": "Будни",
            "name": "Будни",
            "wake": "07:30",
            "sleep": "23:30",
            "lunch": {"start": "13:00", "end": "14:00"},
            "work_windows": [{"start": "09:00", "end": "18:00"}],
        }
    ],
    "budgets": [
        {
            "ref": "Фокус",
            "name": "Фокус-работа",
            "minutes_per_day": 300,
            "action_types": ["Фокус-работа"],
        }
    ],
    "settings": {"default_action_type": "Фокус-работа"},
}


async def _ok(resp: Any, code: int = 200) -> Any:
    assert resp.status_code == code, resp.text
    return resp.json()


async def plan_and_read(client: AsyncClient, user, days: int = 7) -> list[dict[str, Any]]:
    async with session_factory() as db:
        svc = ReplanService(db, await db.get(User, user.id), NOW)
        rev = await svc.preview(force=True)
        assert rev is not None
        await svc.apply(rev.id)
    cal = await _ok(
        await client.get(
            f"{API}/calendar",
            params={
                "from": wall_to_utc(TODAY, time(0), TZ).isoformat(),
                "to": wall_to_utc(TODAY + timedelta(days=days), time(0), TZ).isoformat(),
            },
        )
    )
    return cal["events"]


def local(e: dict[str, Any]) -> tuple[datetime, datetime]:
    return (
        datetime.fromisoformat(e["start"]).astimezone(TZ),
        datetime.fromisoformat(e["end"]).astimezone(TZ),
    )


def overlaps(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


async def test_scenario_5_office(clock: Clock, auth_client: AsyncClient, user):
    await _ok(await auth_client.patch(f"{API}/me/settings", json={"onboarding_done": True}))
    await _ok(
        await auth_client.post(f"{API}/config/import", params={"dry_run": False}, json=OFFICE)
    )
    types = {t["name"]: t["id"] for t in await _ok(await auth_client.get(f"{API}/action-types"))}
    task_types = {t["name"]: t["id"] for t in await _ok(await auth_client.get(f"{API}/task-types"))}

    deadline = wall_to_utc(TODAY + timedelta(days=4), time(18), TZ).isoformat()
    report = await _ok(
        await auth_client.post(
            f"{API}/tasks",
            json={
                "title": "Квартальный отчёт",
                "task_type_id": task_types["Отчёт"],
                "deadline": deadline,
                "estimate_min": 600,
            },
        ),
        201,
    )
    assert report["action_type_id"] == types["Фокус-работа"]
    # Звонок клиенту — быстрым вводом: тип действия по словам
    parsed = await _ok(
        await auth_client.post(
            f"{API}/quick-add/parse", json={"text": "позвонить клиенту по договору до среды"}
        )
    )
    assert parsed["action_type_id"] == types["Связь с людьми"]
    call = await _ok(
        await auth_client.post(
            f"{API}/tasks",
            json={
                "title": parsed["title"],
                "deadline": parsed["deadline"],
                "action_type_id": parsed["action_type_id"],
                "estimate_min": 30,
            },
        ),
        201,
    )
    await _ok(
        await auth_client.post(
            f"{API}/projects",
            json={"title": "Внедрение CRM", "weekly_norm_min": 240},
        ),
        201,
    )

    events = await plan_and_read(auth_client, user)
    busy = [local(e) for e in events if e["kind"] == "busy"]
    assert len([b for b in busy if b[0].time() == time(10)]) >= 4  # стендапы
    flexible = [e for e in events if e["kind"] in FLEXIBLE and e["status"] != "cancelled"]
    assert flexible
    focus_by_day: dict[Any, int] = defaultdict(int)
    for e in flexible:
        start, end = local(e)
        assert start.isoweekday() in WEEKDAYS, e["title"]
        assert start.time() >= time(9), e["title"]
        assert end.time() <= time(18), e["title"]
        lunch = (start.replace(hour=13, minute=0), start.replace(hour=14, minute=0))
        assert not overlaps((start, end), lunch), e["title"]
        assert not any(overlaps((start, end), b) for b in busy), e["title"]
        if e["source_id"] != call["id"]:
            focus_by_day[start.date()] += int((end - start).total_seconds() // 60)
    assert max(focus_by_day.values()) <= 300
    assert any(e["source_id"] == call["id"] for e in flexible)
    assert sum(1 for e in flexible if e["kind"] == "project") >= 1


async def test_scenario_6_floating(clock: Clock, auth_client: AsyncClient, user):
    """Регулярной занятости нет: задачи, ящик, окна типов действий, лимит; разовое
    событие быстрым вводом — план его обходит."""
    await _ok(await auth_client.patch(f"{API}/me/settings", json={"onboarding_done": True}))
    exported = await _ok(await auth_client.get(f"{API}/config/export"))
    assert exported["schedule_rules"] == []
    focus = next(
        t["id"]
        for t in await _ok(await auth_client.get(f"{API}/action-types"))
        if t["name"] == exported["settings"]["default_action_type"]
    )
    await _ok(
        await auth_client.post(
            f"{API}/load-budgets",
            json={"name": "Работа", "minutes_per_day": 180, "action_type_ids": [focus]},
        ),
        201,
    )

    # Разовое жёсткое событие — быстрым вводом (без типа занятости — «просто занято»)
    from app.services.quickadd import create_from_text

    async with session_factory() as db:
        u = await db.get(User, user.id)
        assert u is not None
        created = await create_from_text(db, u, "завтра с 10 до 13 собеседование")
    assert created.kind == "event"

    await _ok(
        await auth_client.post(
            f"{API}/tasks",
            json={
                "title": "Лендинг для заказчика",
                "deadline": wall_to_utc(TODAY + timedelta(days=3), time(23, 59), TZ).isoformat(),
                "subtasks": [
                    {"title": "Макет", "estimate_min": 120},
                    {"title": "Вёрстка", "estimate_min": 180},
                    {"title": "Тексты", "estimate_min": 90},
                ],
            },
        ),
        201,
    )
    await _ok(
        await auth_client.post(f"{API}/backlog", json={"title": "Записаться к стоматологу"}),
        201,
    )

    events = await plan_and_read(auth_client, user, days=4)
    interview = next(e for e in events if e["id"] == str(created.id))
    flexible = [e for e in events if e["kind"] in FLEXIBLE]
    assert flexible
    per_day: dict[Any, int] = defaultdict(int)
    for e in flexible:
        assert not overlaps(local(e), local(interview)), e["title"]
        if e["kind"] == "subtask":
            start, end = local(e)
            per_day[start.date()] += int((end - start).total_seconds() // 60)
    assert sum(per_day.values()) == 390
    assert max(per_day.values()) <= 180
