"""M11.1–M11.3: вечерний разбор (сценарий 3), ящик в плане и недельный разбор (сценарий 6)."""

from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.core.db import session_factory
from app.core.exceptions import InvalidDataError
from app.core.time import now_utc
from app.domain.enums import (
    BacklogCondition,
    BacklogStatus,
    EventKind,
    EventStatus,
    PlanReason,
    SourceType,
)
from app.models import BacklogItem, Event, PlanRevision, User
from app.services.replan import ReplanService
from app.services.review import ReviewService

from .test_replan import (
    API,
    FRI,
    MON,
    NOW,
    TZ,
    add_event,
    at,
    call,
    ops_of,
    snapshot,
    task_with_steps,
)

SUN = MON + timedelta(days=6)
NEXT_MON = MON + timedelta(days=7)
WED = MON + timedelta(days=2)


@pytest.fixture(autouse=True)
def _fast_solver(monkeypatch):
    monkeypatch.setattr(ReplanService, "time_limit_s", 0.4)


async def review(user, fn: str, *args, now: datetime, **kw):
    async with session_factory() as db:
        u = await db.get(User, user.id)
        return await getattr(ReviewService(db, u, now), fn)(*args, **kw)


async def apply_preview(user, now: datetime = NOW) -> PlanRevision:
    rev = await call(user, "preview", now=now)
    assert rev is not None
    return await call(user, "apply", rev.id, now=now)


async def events_of(user, kind: EventKind | None = None) -> list[Event]:
    async with session_factory() as db:
        stmt = select(Event).where(Event.user_id == user.id, Event.deleted_at.is_(None))
        if kind:
            stmt = stmt.where(Event.kind == kind)
        return list(await db.scalars(stmt.order_by(Event.start)))


async def add_item(user, title: str, *, created: datetime | None = None, **kw) -> BacklogItem:
    kw.setdefault("conditions", [])
    async with session_factory() as db:
        item = BacklogItem(user_id=user.id, title=title, status=BacklogStatus.active, **kw)
        db.add(item)
        await db.flush()
        # По умолчанию — «только что» относительно тестового времени
        item.created_at = created or NOW
        await db.commit()
        return item


# ---------- вечерний разбор (сценарий 3) ----------


async def test_evening_items_are_started_unmarked_blocks(auth_client, user):
    await task_with_steps(auth_client, 60, 90)
    await apply_preview(user)
    blocks = await events_of(user, EventKind.subtask)
    assert all(e.start.astimezone(TZ).date() == MON for e in blocks)

    evening = at(MON, 21, 30)
    items, done = await review(user, "evening_items", now=evening)
    assert {e.id for e in items} == {e.id for e in blocks}
    assert done == 0

    # До начала блока — ещё не разбираем
    items, _ = await review(user, "evening_items", now=blocks[0].start - timedelta(minutes=1))
    assert items == []


async def test_reschedule_all_moves_to_preview(auth_client, user):
    _, steps = await task_with_steps(auth_client, 60, 90)
    await apply_preview(user)
    evening = at(MON, 21, 30)
    moved, rev = await review(user, "reschedule", now=evening)
    assert moved == 2
    assert rev is not None and PlanReason.missed in rev.reasons
    # Старые блоки — «не сделано», новые предложены на завтра и дальше
    statuses = {e.status for e in await events_of(user, EventKind.subtask)}
    assert statuses == {EventStatus.missed}
    adds = ops_of(rev, "add")
    assert {o["source_id"] for o in adds} == {s["id"] for s in steps}
    # «Не сделано сегодня» — не раньше завтрашнего дня
    tomorrow = at(MON + timedelta(days=1), 0)
    assert all(datetime.fromisoformat(o["after"]["start"]) >= tomorrow for o in adds)
    applied = await call(user, "apply", rev.id, now=evening)
    assert applied.status == "applied"


async def test_reschedule_one_by_one(auth_client, user):
    await task_with_steps(auth_client, 60, 90)
    await apply_preview(user)
    first, second = await events_of(user, EventKind.subtask)
    resp = await auth_client.patch(f"{API}/events/{first.id}", json={"status": "done"})
    assert resp.status_code == 200
    moved, rev = await review(user, "reschedule", [second.id], now=at(MON, 21, 30))
    assert moved == 1
    assert rev is not None
    assert [o["source_id"] for o in ops_of(rev, "add")] == [str(second.source_id)]


async def test_reschedule_warns_about_deadline(auth_client, user):
    await task_with_steps(auth_client, 120, 120, deadline=at(MON + timedelta(days=1), 12))
    await apply_preview(user)
    _, rev = await review(user, "reschedule", now=at(MON, 21, 30))
    assert rev is not None and rev.at_risk
    assert rev.at_risk[0]["group_kind"] == "task"


async def test_reschedule_nothing(auth_client, user):
    moved, _ = await review(user, "reschedule", now=at(MON, 21, 30))
    assert moved == 0


async def test_evening_api(auth_client, user):
    task = (
        await auth_client.post(f"{API}/tasks", json={"title": "Чтение", "estimate_min": 60})
    ).json()
    now = now_utc()
    await add_event(
        user,
        kind=EventKind.subtask,
        title="Чтение",
        start=now - timedelta(minutes=1),
        end=now + timedelta(minutes=59),
        is_fixed=False,
        source_type=SourceType.task,
        source_id=task["id"],
    )
    resp = await auth_client.get(f"{API}/review/evening")
    assert resp.status_code == 200
    assert [e["title"] for e in resp.json()["items"]] == ["Чтение"]
    resp = await auth_client.post(f"{API}/review/evening/reschedule", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["moved"] == 1
    assert resp.json()["plan"]["proposal"] is not None


# ---------- ящик в плане (M11.2) ----------


async def test_only_items_taken_for_week_are_planned(auth_client, user):
    taken = await add_item(user, "Стоматолог", planned_week=MON, estimate_min=60)
    await add_item(user, "Когда-нибудь", estimate_min=60)
    await add_item(user, "На прошлой неделе", planned_week=MON - timedelta(days=7))
    snap = await snapshot(user)
    blocks = {b.id: b for b in snap.inp.blocks}
    assert set(blocks) == {f"backlog_item:{taken.id}"}
    block = blocks[f"backlog_item:{taken.id}"]
    assert block.filler and not block.splittable and block.group_id is None
    assert block.deadline == at(NEXT_MON, 0)


async def test_backlog_goes_after_study_and_into_its_week(auth_client, user):
    await task_with_steps(auth_client, 60)
    item = await add_item(user, "Аптека", planned_week=MON, estimate_min=30)
    rev = await call(user, "preview")
    adds = {o["source_type"]: o for o in ops_of(rev, "add")}
    assert adds["backlog_item"]["kind"] == "backlog"
    start = datetime.fromisoformat(adds["backlog_item"]["after"]["start"])
    assert start.astimezone(TZ).date() < NEXT_MON
    await call(user, "apply", rev.id)
    [box] = await events_of(user, EventKind.backlog)
    assert box.source_id == item.id and not box.is_fixed


async def test_on_class_days_condition(auth_client, user):
    await add_event(
        user,
        kind=EventKind.class_,
        title="Климатология",
        start=at(WED, 10, 45),
        end=at(WED, 12, 20),
        is_fixed=True,
    )
    item = await add_item(
        user,
        "Забрать посылку",
        planned_week=MON,
        estimate_min=30,
        conditions=[BacklogCondition.on_class_days],
    )
    rev = await call(user, "preview")
    [op] = [o for o in ops_of(rev, "add") if o["source_id"] == str(item.id)]
    assert datetime.fromisoformat(op["after"]["start"]).astimezone(TZ).date() == WED


async def test_backlog_block_done_closes_item(auth_client, user):
    item = await add_item(user, "Стоматолог", planned_week=MON, estimate_min=60)
    await apply_preview(user)
    [box] = await events_of(user, EventKind.backlog)
    resp = await auth_client.patch(f"{API}/events/{box.id}", json={"status": "done"})
    assert resp.status_code == 200
    resp = await auth_client.get(f"{API}/backlog", params={"status": "done"})
    assert [i["id"] for i in resp.json()] == [str(item.id)]
    # Сняли отметку — дело снова в ящике
    await auth_client.patch(f"{API}/events/{box.id}", json={"status": "planned"})
    resp = await auth_client.get(f"{API}/backlog")
    assert [i["id"] for i in resp.json()] == [str(item.id)]


async def test_dropped_item_block_is_removed(auth_client, user):
    item = await add_item(user, "Стоматолог", planned_week=MON, estimate_min=60)
    await apply_preview(user)
    async with session_factory() as db:
        row = await db.get(BacklogItem, item.id)
        row.planned_week = None
        await db.commit()
    rev = await call(user, "preview")
    assert [o["op"] for o in rev.ops] == ["remove"]


async def test_take_for_week_api_and_limit(auth_client, user):
    ids = []
    for title in ("a", "b", "c", "d"):
        resp = await auth_client.post(f"{API}/backlog", json={"title": title})
        ids.append(resp.json()["id"])
    for i in ids[:3]:
        resp = await auth_client.put(f"{API}/backlog/{i}/week")
        assert resp.status_code == 200, resp.text
        assert resp.json()["planned_week"] is not None
    resp = await auth_client.put(f"{API}/backlog/{ids[3]}/week")
    assert resp.status_code == 400
    resp = await auth_client.delete(f"{API}/backlog/{ids[0]}/week")
    assert resp.json()["planned_week"] is None
    resp = await auth_client.put(f"{API}/backlog/{ids[3]}/week")
    assert resp.status_code == 200


# ---------- недельный разбор (сценарий 6) ----------


async def test_weekly_suggests_for_next_week(auth_client, user):
    old = await add_item(user, "Записаться к стоматологу", created=at(MON, 9) - timedelta(days=60))
    desired = await add_item(user, "Продлить пропуск", desired_by=NEXT_MON + timedelta(days=2))
    await add_item(user, "Свежее")
    await add_item(user, "Ещё одно")
    week = await review(user, "weekly", now=at(SUN, 19))
    assert week.week_start == NEXT_MON
    assert week.per_week == 3
    assert [i.id for i in week.suggestions][:2] == [desired.id, old.id]
    assert len(week.suggestions) == 3


async def test_weekly_confirm_plans_items(auth_client, user):
    a = await add_item(user, "Стоматолог", estimate_min=60)
    b = await add_item(user, "Паспорт", estimate_min=60, conditions=["weekday_daytime"])
    sunday = at(SUN, 19)
    rev = await review(user, "confirm_week", [a.id, b.id], now=sunday)
    assert rev is not None and PlanReason.weekly in rev.reasons
    adds = [o for o in ops_of(rev, "add") if o["source_type"] == "backlog_item"]
    assert {o["source_id"] for o in adds} == {str(a.id), str(b.id)}
    for o in adds:
        local = datetime.fromisoformat(o["after"]["start"]).astimezone(TZ)
        assert NEXT_MON <= local.date() < NEXT_MON + timedelta(days=7)
        if o["source_id"] == str(b.id):
            assert local.isoweekday() <= 5 and time(9) <= local.time() < time(18)
    week = await review(user, "weekly", now=sunday)
    assert {i.id for i in week.planned} == {a.id, b.id}
    assert len(week.suggestions) <= 1


async def test_weekly_confirm_replaces_week_and_enforces_limit(auth_client, user):
    items = [await add_item(user, f"Дело {i}") for i in range(4)]
    sunday = at(SUN, 19)
    await review(user, "confirm_week", [i.id for i in items[:2]], now=sunday)
    await review(user, "confirm_week", [items[2].id], now=sunday)
    async with session_factory() as db:
        weeks = {i.id: (await db.get(BacklogItem, i.id)).planned_week for i in items}
    assert weeks == {items[0].id: None, items[1].id: None, items[2].id: NEXT_MON, items[3].id: None}
    with pytest.raises(InvalidDataError):
        await review(user, "confirm_week", [i.id for i in items], now=sunday)


async def test_weekly_stats(auth_client, user):
    await task_with_steps(auth_client, 60, 60, deadline=at(FRI, 23))
    await apply_preview(user)
    first, second = await events_of(user, EventKind.subtask)
    await auth_client.patch(f"{API}/events/{first.id}", json={"status": "done"})
    async with session_factory() as db:
        (await db.get(Event, second.id)).status = EventStatus.missed
        await db.commit()
    week = await review(user, "weekly", now=at(SUN, 19))
    assert week.stats.week_start == MON
    assert (week.stats.blocks_planned, week.stats.blocks_done, week.stats.blocks_missed) == (
        2,
        1,
        1,
    )
    assert week.stats.done_minutes == 60


async def test_weekly_api(auth_client, user):
    await auth_client.post(f"{API}/backlog", json={"title": "Стоматолог"})
    resp = await auth_client.get(f"{API}/review/week")
    assert resp.status_code == 200
    body = resp.json()
    assert [i["title"] for i in body["suggestions"]] == ["Стоматолог"]
    resp = await auth_client.post(
        f"{API}/review/week/confirm", json={"item_ids": [body["suggestions"][0]["id"]]}
    )
    assert resp.status_code == 200, resp.text
    resp = await auth_client.get(f"{API}/review/week")
    assert [i["title"] for i in resp.json()["planned"]] == ["Стоматолог"]


def test_dates():
    assert MON == date(2030, 1, 7) and SUN.isoweekday() == 7
