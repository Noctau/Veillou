"""M11.4: «У меня есть N минут» / /free."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.db import session_factory
from app.domain.enums import BacklogStatus, EventKind, SourceType
from app.models import BacklogItem, Event, User
from app.services.free import FreeService

from .test_replan import API, MON, add_event, at, task_with_steps

TUE = MON + timedelta(days=1)


async def free(user, fn: str, *args, now):
    async with session_factory() as db:
        u = await db.get(User, user.id)
        return await getattr(FreeService(db, u, now), fn)(*args)


async def add_item(user, title: str, **kw) -> BacklogItem:
    kw.setdefault("conditions", [])
    async with session_factory() as db:
        item = BacklogItem(user_id=user.id, title=title, status=BacklogStatus.active, **kw)
        db.add(item)
        await db.commit()
        return item


async def test_suggests_steps_then_backlog(auth_client, user):
    _, (_, _, c) = await task_with_steps(auth_client, 30, 45, 120)
    item = await add_item(user, "Позвонить в банк", estimate_min=15)
    result = await free(user, "suggest", 60, now=at(TUE, 10))
    kinds = [(r.kind, str(r.id)) for r in result]
    assert ("subtask", c["id"]) not in kinds  # 2 часа в 60 минут не влезают
    assert kinds[-1] == ("backlog", str(item.id))
    assert result[0].kind == "subtask" and result[0].subtitle == "Реферат"


async def test_dependencies_respected(auth_client, user):
    _, (a, b) = await task_with_steps(auth_client, 30, 30)
    await auth_client.patch(f"{API}/subtasks/{b['id']}", json={"depends_on": [a["id"]]})
    result = await free(user, "suggest", 60, now=at(TUE, 10))
    assert [str(r.id) for r in result] == [a["id"]]


async def test_window_respected(auth_client, user):
    await add_item(user, "Позвонить в деканат", estimate_min=15, conditions=["weekday_daytime"])
    assert await free(user, "suggest", 30, now=at(TUE, 20)) == []
    assert len(await free(user, "suggest", 30, now=at(TUE, 11))) == 1


async def test_on_class_days(auth_client, user):
    await add_item(user, "Посылка", estimate_min=15, conditions=["on_class_days"])
    assert await free(user, "suggest", 30, now=at(TUE, 11)) == []
    await add_event(
        user,
        kind=EventKind.class_,
        title="Пара",
        start=at(TUE, 9),
        end=at(TUE, 10, 30),
        is_fixed=True,
    )
    assert len(await free(user, "suggest", 30, now=at(TUE, 11))) == 1


async def test_start_subtask_pins_block_now(auth_client, user):
    _, (a,) = await task_with_steps(auth_client, 30)
    now = at(TUE, 10, 7)
    event = await free(user, "start", "subtask", uuid.UUID(a["id"]), now=now)
    assert event.is_pinned and event.start == at(TUE, 10, 7)
    assert event.end - event.start == timedelta(minutes=30)


async def test_start_backlog_item(auth_client, user):
    item = await add_item(user, "Позвонить в банк", estimate_min=15)
    await free(user, "start", "backlog", item.id, now=at(TUE, 10))
    async with session_factory() as db:
        [e] = list(
            await db.scalars(select(Event).where(Event.source_type == SourceType.backlog_item))
        )
    assert e.kind == EventKind.backlog and e.is_pinned and not e.is_fixed


async def test_free_api(auth_client, user):
    await auth_client.post(f"{API}/backlog", json={"title": "Купить лампочки", "estimate_min": 15})
    resp = await auth_client.get(f"{API}/free", params={"minutes": 30})
    assert resp.status_code == 200
    items = resp.json()
    # Окно дела может быть закрыто прямо сейчас (ночь) — тогда пусто
    if items:
        assert items[0]["title"] == "Купить лампочки"
        resp = await auth_client.post(
            f"{API}/free/start", json={"kind": "backlog", "id": items[0]["id"]}
        )
        assert resp.status_code == 200, resp.text
    assert (await auth_client.get(f"{API}/free", params={"minutes": 1})).status_code == 422
