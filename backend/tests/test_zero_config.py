"""Нулевая настройка (M22.1): «Пропустить всё» в онбординге — и приложение работает.

Новый пользователь без сфер, занятости, лимитов и типов задач: создаёт задачу,
планирует её (превью → «Применить»), утром получает сводку с блоком задачи.
"""

from datetime import datetime, time, timedelta

from httpx import AsyncClient

from app.core.db import session_factory
from app.core.time import wall_to_utc
from app.models import User
from app.services.digest import Digest
from app.services.replan import ReplanService

from .student import API, NOW, TODAY, TZ, Clock


async def _ok(resp, code: int = 200):
    assert resp.status_code == code, resp.text
    return resp.json()


async def test_zero_config_task_plan_digest(clock: Clock, auth_client: AsyncClient, user):
    # «Пропустить всё»
    await _ok(await auth_client.patch(f"{API}/me/settings", json={"onboarding_done": True}))
    exported = await _ok(await auth_client.get(f"{API}/config/export"))
    for section in ("areas", "event_types", "schedule_rules", "budgets", "task_types"):
        assert exported[section] == [], section
    # Что есть сразу: режимы «Будни» / «Выходные» и типы действий
    assert [p["name"] for p in exported["day_profiles"]] == ["Будни", "Выходные"]
    assert exported["settings"]["default_action_type"] == "Сосредоточенная работа"

    # Задача быстрым вводом: без сферы ИИ не нужен
    parsed = await _ok(
        await auth_client.post(f"{API}/quick-add/parse", json={"text": "отчёт к пятнице"})
    )
    assert (parsed["kind_hint"], parsed["needs_ai"]) == ("task", False)
    task = await _ok(
        await auth_client.post(
            f"{API}/tasks",
            json={
                "title": parsed["title"],
                "deadline": parsed["deadline"],
                "action_type_id": parsed["action_type_id"],
                "estimate_min": 90,
            },
        ),
        201,
    )

    # План: превью → применить; блок задачи до срока
    async with session_factory() as db:
        svc = ReplanService(db, await db.get(User, user.id), NOW)
        rev = await svc.preview(force=True)
        assert rev is not None
        await svc.apply(rev.id)
    cal = await _ok(
        await auth_client.get(
            f"{API}/calendar",
            params={
                "from": wall_to_utc(TODAY, time(0), TZ).isoformat(),
                "to": wall_to_utc(TODAY + timedelta(days=7), time(0), TZ).isoformat(),
            },
        )
    )
    blocks = [e for e in cal["events"] if e["source_id"] == task["id"]]
    assert blocks
    first = min(blocks, key=lambda e: e["start"])

    # Сводка в день блока — с задачей
    block_day = datetime.fromisoformat(first["start"]).astimezone(TZ).date()
    assert block_day >= TODAY
    morning = wall_to_utc(block_day, time(8), TZ)
    clock.set(morning)
    async with session_factory() as db:
        digest = await Digest(db, await db.get(User, user.id), morning).day(block_day, morning=True)
    assert digest is not None
    assert parsed["title"] in digest.plain_body()
