"""M9.1–M9.2, M9.4: перепланирование из БД — превью, применение, откат, триггеры."""

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import func, select

from app.core.db import session_factory
from app.core.time import get_tz, now_utc, wall_to_utc
from app.domain.enums import (
    EventKind,
    EventStatus,
    JobKind,
    JobStatus,
    PlanReason,
    PlanRevisionStatus,
    SourceType,
)
from app.models import Calibration, Event, Job, PlanRevision, User
from app.services import jobs
from app.services.replan import (
    SKIP_REPLAN,
    PlanStaleError,
    ReplanService,
    Snapshot,
    handle_preview_job,
    nightly_replan,
)

from .test_schedule_api import other_client
from .test_tasks import add_subtask, make_task

API = "/api/v1"
TZ = get_tz("Europe/Moscow")
MON = date(2030, 1, 7)  # понедельник
FRI = MON + timedelta(days=4)
NOW = wall_to_utc(MON, time(8), TZ)


def at(d: date, h: int, m: int = 0) -> datetime:
    return wall_to_utc(d, time(h, m), TZ)


@pytest.fixture(autouse=True)
def _fast_solver(monkeypatch):
    monkeypatch.setattr(ReplanService, "time_limit_s", 0.4)


# Каждый вызов — в своей сессии: тестовая сессия и API не делят identity map
async def call(user, fn: str, *args, now: datetime | None = NOW, **kw):
    async with session_factory() as db:
        u = await db.get(User, user.id)
        return await getattr(ReplanService(db, u, now), fn)(*args, **kw)


async def snapshot(user, now: datetime = NOW) -> Snapshot:
    return await call(user, "snapshot", now=now)


async def flexible_events(user) -> list[Event]:
    async with session_factory() as db:
        rows = await db.scalars(
            select(Event)
            .where(
                Event.user_id == user.id,
                Event.deleted_at.is_(None),
                Event.kind == EventKind.subtask,
            )
            .order_by(Event.start)
        )
        return list(rows)


async def add_event(user, **kw) -> Event:
    async with session_factory() as db:
        e = Event(user_id=user.id, **kw)
        db.add(e)
        await db.commit()
        return e


async def task_with_steps(client, *estimates: int, deadline: datetime | None = None, **kw):
    task = await make_task(client, deadline=(deadline or at(FRI, 23, 59)).isoformat(), **kw)
    steps = [await add_subtask(client, task["id"], estimate_min=m) for m in estimates]
    return task, steps


def ops_of(rev: PlanRevision, op: str) -> list[dict]:
    return [o for o in rev.ops if o["op"] == op]


# ---------- сбор входа ----------


async def test_snapshot_blocks(auth_client, user):
    task, (a, b) = await task_with_steps(auth_client, 60, 90, priority="high")
    await auth_client.patch(f"{API}/subtasks/{b['id']}", json={"depends_on": [a["id"]]})
    done = await add_subtask(auth_client, task["id"], estimate_min=30)
    await auth_client.patch(f"{API}/subtasks/{done['id']}", json={"status": "done"})
    whole = await make_task(auth_client, title="Без шагов", estimate_min=120)
    await make_task(auth_client, title="Без оценки")
    cancelled = await make_task(auth_client, title="Отменено", estimate_min=60)
    await auth_client.patch(f"{API}/tasks/{cancelled['id']}", json={"status": "cancelled"})

    snap = await snapshot(user)
    blocks = {b.id: b for b in snap.inp.blocks}
    assert set(blocks) == {
        f"subtask:{a['id']}",
        f"subtask:{b['id']}",
        f"task:{whole['id']}",
    }
    first = blocks[f"subtask:{a['id']}"]
    assert first.duration_min == 60
    assert first.priority == 3
    assert first.group_id == task["id"]
    assert first.counts_as_study and first.splittable
    assert first.windows  # окно «самостоятельной учёбы»
    assert blocks[f"subtask:{b['id']}"].depends_on == (f"subtask:{a['id']}",)
    assert blocks[f"task:{whole['id']}"].duration_min == 120


async def test_snapshot_people_prefers_morning_and_own_buffer(auth_client, user):
    types = (await auth_client.get(f"{API}/action-types")).json()
    people = next(t for t in types if t["key"] == "people")
    task, _ = await task_with_steps(auth_client, 30, action_type_id=people["id"])
    await auth_client.patch(f"{API}/tasks/{task['id']}", json={"deadline_buffer_days": 0})
    (block,) = (await snapshot(user)).inp.blocks
    assert block.prefer_morning and not block.counts_as_study
    assert block.buffer_days == 0
    assert block.windows[0].end == time(19)


async def test_snapshot_day_limit(auth_client, user):
    resp = await auth_client.put(f"{API}/plan/day-limits/2030-01-08", json={"minutes": 480})
    assert resp.status_code == 200
    assert (await snapshot(user)).inp.study_limits == ((MON + timedelta(days=1), 480),)
    await auth_client.delete(f"{API}/plan/day-limits/2030-01-08")
    assert (await snapshot(user)).inp.study_limits == ()


async def test_pinned_and_started_blocks_are_fixed(auth_client, user):
    task, (pinned, started, free) = await task_with_steps(auth_client, 60, 60, 60)
    await auth_client.post(
        f"{API}/subtasks/{pinned['id']}/schedule", json={"start": at(MON, 15).isoformat()}
    )
    await add_event(
        user,
        kind=EventKind.subtask,
        title="идёт",
        start=at(MON, 7, 45),
        end=at(MON, 8, 15),
        is_fixed=False,
        source_type=SourceType.subtask,
        source_id=started["id"],
    )
    snap = await snapshot(user)
    blocks = {b.id: b for b in snap.inp.blocks}
    # Закреплённое — не блок; начавшееся — остаток после него
    assert f"subtask:{pinned['id']}" not in blocks
    assert f"subtask:{free['id']}" in blocks
    assert blocks[f"subtask:{started['id']}"].duration_min == 30
    assert len(snap.inp.fixed) == 2
    assert all(f.group_id == task["id"] for f in snap.inp.fixed)


async def test_pinned_part_keeps_rest_of_estimate(auth_client, user):
    _, (step,) = await task_with_steps(auth_client, 180)
    resp = await auth_client.post(
        f"{API}/subtasks/{step['id']}/schedule",
        json={"start": at(MON, 15).isoformat(), "end": at(MON, 16).isoformat()},
    )
    assert resp.status_code == 200
    (block,) = (await snapshot(user)).inp.blocks
    assert block.duration_min == 120


async def test_dependency_on_pinned_subtask_uses_fixed_block(auth_client, user):
    _, (a, b) = await task_with_steps(auth_client, 60, 60)
    await auth_client.patch(f"{API}/subtasks/{b['id']}", json={"depends_on": [a["id"]]})
    await auth_client.post(
        f"{API}/subtasks/{a['id']}/schedule", json={"start": at(MON, 15).isoformat()}
    )
    (block,) = (await snapshot(user)).inp.blocks
    (fixed,) = (await snapshot(user)).inp.fixed
    assert block.depends_on == (fixed.id,)


async def test_calibration_scales_estimates(auth_client, user):
    _, steps = await task_with_steps(auth_client, 60, 60, 60, 60)
    for st in steps[:3]:
        await auth_client.patch(
            f"{API}/subtasks/{st['id']}", json={"status": "done", "actual_feel": "slower"}
        )
    (block,) = (await snapshot(user)).inp.blocks
    assert block.duration_min == round(60 * 1.075**3)

    rows = (await auth_client.get(f"{API}/calibration")).json()
    assert rows == [
        {
            "task_type": "essay",
            "action_type": "study",
            "coef": pytest.approx(1.075**3),
            "samples": 3,
        }
    ]
    # Сняли отметку «сделано» — её отметка больше не в счёт
    await auth_client.patch(f"{API}/subtasks/{steps[0]['id']}", json={"status": "todo"})
    rows = (await auth_client.get(f"{API}/calibration")).json()
    assert rows[0]["samples"] == 2

    assert (await auth_client.post(f"{API}/calibration/reset")).json() == []
    assert (await auth_client.get(f"{API}/calibration")).json() == []
    blocks = (await snapshot(user)).inp.blocks
    assert {b.duration_min for b in blocks} == {60}


async def test_calibration_after_reset_counts_new_feels(auth_client, user, session):
    _, (a, b) = await task_with_steps(auth_client, 60, 60)
    await auth_client.patch(
        f"{API}/subtasks/{a['id']}", json={"status": "done", "actual_feel": "faster"}
    )
    await auth_client.post(f"{API}/calibration/reset")
    await auth_client.patch(
        f"{API}/subtasks/{b['id']}", json={"status": "done", "actual_feel": "slower"}
    )
    row = await session.scalar(select(Calibration).where(Calibration.user_id == user.id))
    assert row is not None and row.samples == 1 and row.coef == pytest.approx(1.075)


# ---------- превью → применить → откатить ----------


async def test_preview_apply_undo(auth_client, user):
    _, (a, b) = await task_with_steps(auth_client, 60, 90)
    await auth_client.patch(f"{API}/subtasks/{b['id']}", json={"depends_on": [a["id"]]})

    rev = await call(user, "preview")
    assert rev is not None and rev.status == PlanRevisionStatus.proposed
    assert len(ops_of(rev, "add")) == 2
    assert rev.at_risk == []

    applied = await call(user, "apply", rev.id)
    assert applied.status == PlanRevisionStatus.applied
    events = await flexible_events(user)
    assert [str(e.source_id) for e in events] == [a["id"], b["id"]]
    assert all(not e.is_fixed and not e.is_pinned for e in events)
    assert events[0].start >= NOW and events[0].end <= events[1].start
    # Блоки видны и у подзадачи
    detail = (await auth_client.get(f"{API}/subtasks/{a['id']}")).json()
    assert len(detail["events"]) == 1

    # План стабилен: повторный пересчёт ничего не предлагает
    assert await call(user, "preview", [PlanReason.changes]) is None

    rev2, restored, skipped = await call(user, "undo")
    assert rev2.status == PlanRevisionStatus.undone
    assert (restored, skipped) == (2, 0)
    assert await flexible_events(user) == []
    with pytest.raises(Exception, match="Нечего отменять"):
        await call(user, "undo")


async def test_preview_moves_blocks_after_new_urgent_task(auth_client, user):
    await task_with_steps(auth_client, 120, 120, deadline=at(MON + timedelta(days=20), 12))
    await call(user, "apply", (await call(user, "preview")).id)
    before = {e.id: (e.start, e.end) for e in await flexible_events(user)}

    # Срочное задание на сегодня вытесняет старые блоки (они переезжают или режутся)
    urgent, _ = await task_with_steps(auth_client, 120, 120, deadline=at(MON, 23), priority="high")
    rev = await call(user, "preview")
    assert rev is not None
    # Позже внутреннего срока (дедлайн − 1 день), но до дедлайна
    assert {r["reason"] for r in rev.at_risk} == {"late"}
    added = [o for o in ops_of(rev, "add") if o["task_id"] == urgent["id"]]
    minutes = sum(
        (datetime.fromisoformat(o["after"]["end"]) - datetime.fromisoformat(o["after"]["start"]))
        // timedelta(minutes=1)
        for o in added
    )
    assert minutes == 240
    assert all(datetime.fromisoformat(o["after"]["end"]) <= at(MON, 23) for o in added)
    moves = ops_of(rev, "move")
    assert moves
    for op in moves:
        assert (op["before"]["start"], op["before"]["end"]) == tuple(
            t.isoformat() for t in before[uuid.UUID(op["event_id"])]
        )

    await call(user, "apply", rev.id)
    assert len(await flexible_events(user)) == 2 + len(ops_of(rev, "add"))


async def test_undo_skips_blocks_changed_by_hand(auth_client, user):
    await task_with_steps(auth_client, 60, 60)
    await call(user, "apply", (await call(user, "preview")).id)
    first, _ = await flexible_events(user)
    moved = (first.start + timedelta(days=2)).isoformat()
    end = (first.end + timedelta(days=2)).isoformat()
    resp = await auth_client.patch(f"{API}/events/{first.id}", json={"start": moved, "end": end})
    assert resp.status_code == 200

    _, restored, skipped = await call(user, "undo")
    assert (restored, skipped) == (1, 1)
    (left,) = await flexible_events(user)
    assert left.id == first.id and left.is_pinned


async def test_apply_stale_preview_recomputes(auth_client, user):
    await task_with_steps(auth_client, 60)
    rev = await call(user, "preview")
    await task_with_steps(auth_client, 60)  # вход изменился после превью

    with pytest.raises(PlanStaleError):
        await call(user, "apply", rev.id)
    fresh = await call(user, "proposal")
    assert fresh is not None and fresh.id != rev.id
    assert len(ops_of(fresh, "add")) == 2
    assert await flexible_events(user) == []
    with pytest.raises(PlanStaleError):
        await call(user, "apply", rev.id)


async def test_apply_after_time_passed_is_stale(auth_client, user):
    await task_with_steps(auth_client, 60)
    rev = await call(user, "preview")
    with pytest.raises(PlanStaleError):
        await call(user, "apply", rev.id, now=NOW + timedelta(hours=3))


async def test_same_preview_is_reused_and_dismissed_not_repeated(auth_client, user):
    await task_with_steps(auth_client, 60)
    rev = await call(user, "preview", [PlanReason.changes])
    again = await call(user, "preview", [PlanReason.missed])
    assert again.id == rev.id
    assert again.reasons == ["changes", "missed"]

    await call(user, "dismiss", rev.id)
    assert await call(user, "preview", [PlanReason.changes]) is None
    # Кнопка «Перепланировать» показывает и отклонённое
    forced = await call(user, "preview", force=True)
    assert forced is not None and forced.id != rev.id


async def test_new_preview_supersedes_old(auth_client, user):
    await task_with_steps(auth_client, 60)
    old = await call(user, "preview")
    await task_with_steps(auth_client, 60)
    new = await call(user, "preview")
    assert new.id != old.id
    async with session_factory() as db:
        statuses = dict((await db.execute(select(PlanRevision.id, PlanRevision.status))).all())
    assert statuses == {old.id: "superseded", new.id: "proposed"}


async def test_at_risk_in_preview(auth_client, user):
    task, _ = await task_with_steps(auth_client, 600, 600, deadline=at(MON, 20))
    rev = await call(user, "preview")
    assert rev is not None
    assert {r["reason"] for r in rev.at_risk} <= {"no_time", "no_slots"}
    assert rev.at_risk and rev.at_risk[0]["task_id"] == task["id"]
    assert rev.at_risk[0]["task_title"] == "Реферат"


async def test_stale_and_orphan_blocks(auth_client, user):
    _, (old,) = await task_with_steps(auth_client, 60)
    done_task, (step,) = await task_with_steps(auth_client, 60)
    stale = await add_event(
        user,
        kind=EventKind.subtask,
        title="вчера",
        start=at(MON - timedelta(days=1), 10),
        end=at(MON - timedelta(days=1), 11),
        is_fixed=False,
        source_type=SourceType.subtask,
        source_id=old["id"],
    )
    orphan = await add_event(
        user,
        kind=EventKind.subtask,
        title="лишний",
        start=at(MON, 16),
        end=at(MON, 17),
        is_fixed=False,
        source_type=SourceType.subtask,
        source_id=step["id"],
    )
    await auth_client.patch(f"{API}/tasks/{done_task['id']}", json={"status": "done"})

    rev = await call(user, "preview")
    assert [o["event_id"] for o in ops_of(rev, "miss")] == [str(stale.id)]
    assert [o["event_id"] for o in ops_of(rev, "remove")] == [str(orphan.id)]
    assert [o["source_id"] for o in ops_of(rev, "add")] == [old["id"]]

    await call(user, "apply", rev.id)
    async with session_factory() as db:
        assert (await db.get(Event, stale.id)).status == EventStatus.missed
        assert (await db.get(Event, orphan.id)).deleted_at is not None
    _, restored, _ = await call(user, "undo")
    assert restored == 3
    async with session_factory() as db:
        assert (await db.get(Event, stale.id)).status == EventStatus.planned
        assert (await db.get(Event, orphan.id)).deleted_at is None


async def test_missed_block_is_replanned(auth_client, user):
    _, (step,) = await task_with_steps(auth_client, 60)
    await call(user, "apply", (await call(user, "preview")).id)
    (event,) = await flexible_events(user)
    await auth_client.patch(f"{API}/events/{event.id}", json={"status": "missed"})

    rev = await call(user, "preview", [PlanReason.missed])
    assert [o["source_id"] for o in ops_of(rev, "add")] == [step["id"]]


async def test_recurring_occurrence_stays_in_its_day(auth_client, user):
    today = now_utc().astimezone(TZ).date()
    resp = await auth_client.post(
        f"{API}/tasks",
        json={"title": "Встреча", "recurrence": "FREQ=WEEKLY", "estimate_min": 60},
    )
    assert resp.status_code == 201
    snap = await snapshot(user, now=now_utc())
    occ = [b for b in snap.inp.blocks if b.earliest is not None]
    assert occ
    first = min(occ, key=lambda b: b.earliest)
    assert first.earliest == wall_to_utc(today, time(0), TZ)
    assert first.deadline == wall_to_utc(today + timedelta(days=1), time(0), TZ)
    assert first.buffer_days == 0 and not first.splittable


# ---------- триггеры и фон ----------


async def plan_jobs(session, user) -> list[Job]:
    rows = await session.scalars(
        select(Job).where(
            Job.user_id == user.id,
            Job.kind == JobKind.plan_preview,
            Job.status == JobStatus.pending,
        )
    )
    return list(rows)


async def drop_jobs(session) -> None:
    await session.execute(Job.__table__.delete())
    await session.commit()


async def test_triggers(auth_client, session, user):
    task, (step,) = await task_with_steps(auth_client, 60)
    (job,) = await plan_jobs(session, user)
    assert job.payload == {"reasons": ["changes"]}

    await drop_jobs(session)
    # «Сделано» и заметки план не трогают
    await auth_client.patch(f"{API}/subtasks/{step['id']}", json={"status": "done", "note": "x"})
    await auth_client.patch(f"{API}/tasks/{task['id']}", json={"description": "y"})
    assert await plan_jobs(session, user) == []

    # Сняли «сделано» — снова есть что планировать
    await auth_client.patch(f"{API}/subtasks/{step['id']}", json={"status": "todo"})
    assert len(await plan_jobs(session, user)) == 1

    await drop_jobs(session)
    await auth_client.patch(f"{API}/tasks/{task['id']}", json={"deadline": at(FRI, 12).isoformat()})
    assert len(await plan_jobs(session, user)) == 1


async def test_missed_triggers_with_reason(auth_client, session, user):
    resp = await auth_client.post(
        f"{API}/events",
        json={"title": "Спорт", "start": at(MON, 19).isoformat(), "end": at(MON, 20).isoformat()},
    )
    event_id = resp.json()["id"]
    await drop_jobs(session)
    await auth_client.patch(f"{API}/events/{event_id}", json={"status": "done"})
    assert await plan_jobs(session, user) == []
    await auth_client.patch(f"{API}/events/{event_id}", json={"status": "missed"})
    (job,) = await plan_jobs(session, user)
    assert job.payload == {"reasons": ["missed"]}


async def test_apply_and_undo_do_not_trigger(auth_client, session, user):
    await task_with_steps(auth_client, 60)
    rev = await call(user, "preview")
    await drop_jobs(session)
    await call(user, "apply", rev.id)
    await call(user, "undo")
    assert await plan_jobs(session, user) == []
    # Напоминания при этом пересчитываются
    count = await session.scalar(
        select(func.count()).select_from(Job).where(Job.kind == JobKind.reminders_sync)
    )
    assert count == 1


async def test_settings_change_triggers(auth_client, session, user):
    await drop_jobs(session)
    await auth_client.patch(f"{API}/me/settings", json={"study_limit_min_per_day": 300})
    assert len(await plan_jobs(session, user)) == 1


async def test_preview_job_through_queue(auth_client, session, user):
    await make_task(auth_client, title="Срочно", estimate_min=60)
    handlers = {JobKind.plan_preview: handle_preview_job}
    later = now_utc() + timedelta(seconds=10)
    while await jobs.run_one(session_factory, handlers, now=later):
        pass
    rev = await call(user, "proposal", now=None)
    assert rev is not None and rev.reasons == ["changes"]


async def test_nightly_marks_yesterday_missed_and_previews(auth_client, user):
    _, (step,) = await task_with_steps(auth_client, 60)
    yesterday = await add_event(
        user,
        kind=EventKind.subtask,
        title="вчера",
        start=at(MON - timedelta(days=1), 10),
        end=at(MON - timedelta(days=1), 11),
        is_fixed=False,
        source_type=SourceType.subtask,
        source_id=step["id"],
    )
    today = await add_event(
        user,
        kind=EventKind.subtask,
        title="сегодня ночью",
        start=at(MON, 0, 30),
        end=at(MON, 1),
        is_fixed=False,
        source_type=SourceType.subtask,
        source_id=step["id"],
    )
    async with session_factory() as db:
        assert await nightly_replan(db, wall_to_utc(MON, time(3), TZ)) == 1
        assert not db.info.get(SKIP_REPLAN)
    async with session_factory() as db:
        assert (await db.get(Event, yesterday.id)).status == EventStatus.missed
        assert (await db.get(Event, today.id)).status == EventStatus.planned
    rev = await call(user, "proposal")
    assert rev is not None and rev.reasons == ["nightly"]


# ---------- API ----------


async def test_api_flow(auth_client, user):
    resp = await auth_client.get(f"{API}/plan")
    assert resp.json() == {"proposal": None, "undoable": None}

    deadline = now_utc() + timedelta(days=5)
    await make_task(auth_client, title="Доклад", estimate_min=90, deadline=deadline.isoformat())
    resp = await auth_client.post(f"{API}/plan/preview")
    assert resp.status_code == 200, resp.text
    proposal = resp.json()["proposal"]
    assert proposal["added"] == 1 and proposal["moved"] == 0
    assert proposal["reasons"] == ["manual"]
    (change,) = proposal["changes"]
    assert change["op"] == "add" and change["title"] == "Доклад"

    resp = await auth_client.post(f"{API}/plan/revisions/{proposal['id']}/apply")
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert state["proposal"] is None
    assert state["undoable"]["id"] == proposal["id"]

    resp = await auth_client.post(f"{API}/plan/undo")
    assert resp.status_code == 200
    assert resp.json()["restored"] == 1
    assert (await auth_client.post(f"{API}/plan/undo")).status_code == 404


async def test_api_stale_and_dismiss(auth_client, user):
    deadline = (now_utc() + timedelta(days=5)).isoformat()
    await make_task(auth_client, title="A", estimate_min=60, deadline=deadline)
    proposal = (await auth_client.post(f"{API}/plan/preview")).json()["proposal"]
    await make_task(auth_client, title="B", estimate_min=60, deadline=deadline)

    resp = await auth_client.post(f"{API}/plan/revisions/{proposal['id']}/apply")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "plan_stale"
    fresh = (await auth_client.get(f"{API}/plan")).json()["proposal"]
    assert fresh["added"] == 2

    resp = await auth_client.post(f"{API}/plan/revisions/{fresh['id']}/dismiss")
    assert resp.json()["proposal"] is None


async def test_api_per_user(auth_client, session):
    await make_task(auth_client, title="A", estimate_min=60)
    proposal = (await auth_client.post(f"{API}/plan/preview")).json()["proposal"]
    async with other_client(auth_client, session) as other:
        resp = await other.post(f"{API}/plan/revisions/{proposal['id']}/apply")
        assert resp.status_code == 404
        assert (await other.get(f"{API}/plan")).json()["proposal"] is None
