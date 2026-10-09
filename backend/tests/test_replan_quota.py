"""M13.1: недельная норма проекта в перепланировании (резерв, засчёт шагов, угрозы)."""

from datetime import timedelta

from sqlalchemy import select

from app.core.db import session_factory
from app.domain.enums import EventKind, EventStatus, JobKind, SourceType
from app.domain.projects import reserve_chunks, week_target
from app.models import Event, Job

from .test_projects import add_milestone, make_project
from .test_replan import API, MON, NOW, add_event, at, call, snapshot, task_with_steps

NEXT_MON = MON + timedelta(days=7)
WED = MON + timedelta(days=2)


async def project_events(user) -> list[Event]:
    async with session_factory() as db:
        rows = await db.scalars(
            select(Event)
            .where(
                Event.user_id == user.id,
                Event.deleted_at.is_(None),
                Event.kind == EventKind.project,
            )
            .order_by(Event.start)
        )
        return list(rows)


# ---------- чистые функции ----------


def test_reserve_chunks():
    assert reserve_chunks(0) == []
    assert reserve_chunks(20) == []
    assert reserve_chunks(30) == [30]
    assert reserve_chunks(90) == [90]
    assert reserve_chunks(100) == [60, 60]
    assert reserve_chunks(360) == [90] * 4
    assert reserve_chunks(300) == [75] * 4


def test_week_target():
    assert week_target(360, 0, 7) == 360  # понедельник
    assert week_target(360, 300, 5) == 60  # почти всё уже сделано
    assert week_target(420, 0, 3) == 180  # пропущенное в начале недели не набиваем
    assert week_target(360, 400, 2) == 0


# ---------- сбор входа ----------


async def test_snapshot_quotas_and_reserve(auth_client, user):
    project = await make_project(auth_client, weekly_norm_min=360)
    await make_project(auth_client, title="Без нормы")
    snap = await snapshot(user)
    tag = f"project:{project['id']}"
    assert [(q.start, q.end, q.minutes) for q in snap.inp.quotas] == [
        (MON, NEXT_MON, 360),
        (NEXT_MON, NEXT_MON + timedelta(days=7), 360),
    ]
    reserve = [b for b in snap.inp.blocks if b.reserve]
    assert len(reserve) == 8
    assert {b.duration_min for b in reserve} == {90}
    assert all(b.quota == tag and b.group_id == tag and b.counts_as_study for b in reserve)
    assert reserve[0].earliest == at(MON, 0)
    assert reserve[0].deadline == at(NEXT_MON, 0)


async def test_project_steps_count_toward_norm(auth_client, user):
    project = await make_project(auth_client, weekly_norm_min=180)
    _, (step,) = await task_with_steps(auth_client, 60, project_id=project["id"])
    _, (free,) = await task_with_steps(auth_client, 60)
    blocks = {b.id: b for b in (await snapshot(user)).inp.blocks}
    assert blocks[f"subtask:{step['id']}"].quota == f"project:{project['id']}"
    assert blocks[f"subtask:{free['id']}"].quota is None


async def test_project_deadline_limits_weeks(auth_client, user):
    await make_project(
        auth_client, weekly_norm_min=180, deadline=(MON + timedelta(days=3)).isoformat()
    )
    snap = await snapshot(user)
    (quota,) = snap.inp.quotas
    assert quota.end == MON + timedelta(days=4)
    assert all(b.deadline == at(MON + timedelta(days=4), 0) for b in snap.inp.blocks if b.reserve)


async def test_done_earlier_this_week_reduces_target(auth_client, user):
    project = await make_project(auth_client, weekly_norm_min=360)
    await add_event(
        user,
        kind=EventKind.project,
        title="ВКР — работа над проектом",
        start=at(MON, 10),
        end=at(MON, 13),
        is_fixed=False,
        status=EventStatus.done,
        source_type=SourceType.project,
        source_id=project["id"],
    )
    snap = await snapshot(user, now=at(WED, 8))
    this_week = snap.inp.quotas[0]
    # Сделано 3 ч из 6, а до конца недели 5 дней из 7 — ставим оставшиеся 3 ч
    assert this_week.minutes == 180
    assert len([b for b in snap.inp.blocks if b.reserve and b.earliest == at(MON, 0)]) == 2


# ---------- превью и применение ----------


async def test_preview_apply_reserve_blocks(auth_client, user):
    project = await make_project(auth_client, weekly_norm_min=180)
    rev = await call(user, "preview")
    assert rev is not None
    assert rev.at_risk == []
    adds = [o for o in rev.ops if o["op"] == "add"]
    assert len(adds) == 4
    assert all(o["kind"] == EventKind.project for o in adds)
    await call(user, "apply", rev.id)

    events = await project_events(user)
    assert len(events) == 4
    assert all(e.source_type == SourceType.project for e in events)
    assert events[0].title == "ВКР — работа над проектом"
    # Повторный пересчёт ничего не двигает
    assert await call(user, "preview") is None

    # Шаг задания проекта на 2 часа — резерв этой недели больше не нужен целиком
    await task_with_steps(
        auth_client, 120, project_id=project["id"], deadline=at(MON + timedelta(days=4), 23)
    )
    rev = await call(user, "preview")
    assert rev is not None
    removed = [o for o in rev.ops if o["op"] == "remove" and o["kind"] == EventKind.project]
    assert len(removed) >= 1

    detail = (await auth_client.get(f"{API}/projects/{project['id']}")).json()
    assert detail["week_done_min"] == 0


async def test_norm_removed_drops_reserve(auth_client, user):
    project = await make_project(auth_client, weekly_norm_min=90)
    await call(user, "apply", (await call(user, "preview")).id)
    assert len(await project_events(user)) == 2
    await auth_client.patch(f"{API}/projects/{project['id']}", json={"weekly_norm_min": 0})
    rev = await call(user, "preview")
    assert {o["op"] for o in rev.ops} == {"remove"}
    await call(user, "apply", rev.id)
    assert await project_events(user) == []


async def test_impossible_norm_is_a_project_risk(auth_client, user):
    project = await make_project(auth_client, weekly_norm_min=60 * 60)
    rev = await call(user, "preview")
    risks = [r for r in rev.at_risk if r["reason"] == "quota"]
    assert risks
    assert all(r["group_kind"] == "project" for r in risks)
    assert risks[0]["group_id"] == project["id"]
    assert risks[0]["group_title"] == "ВКР"
    # Неразмещённые резервные блоки сами угрозой не считаются
    assert {r["reason"] for r in rev.at_risk} == {"quota"}


async def test_delete_project_removes_planned_reserve(auth_client, user):
    project = await make_project(auth_client, weekly_norm_min=90)
    await call(user, "apply", (await call(user, "preview")).id)
    assert await project_events(user)
    await auth_client.delete(f"{API}/projects/{project['id']}")
    assert await project_events(user) == []


async def test_norm_change_triggers_replan(auth_client, session, user):
    project = await make_project(auth_client)
    await auth_client.patch(f"{API}/projects/{project['id']}", json={"weekly_norm_min": 240})
    jobs = await session.scalars(
        select(Job).where(Job.user_id == user.id, Job.kind == JobKind.plan_preview)
    )
    assert list(jobs)


# ---------- карточка ----------


async def test_project_week_minutes_and_behind(auth_client, user, monkeypatch):
    monkeypatch.setattr("app.services.projects.now_utc", lambda: NOW)
    project = await make_project(auth_client, weekly_norm_min=240)
    await add_milestone(
        auth_client, project["id"], title="Обзор", date=(MON - timedelta(days=5)).isoformat()
    )
    await add_milestone(
        auth_client, project["id"], title="Главы", date=(MON + timedelta(days=30)).isoformat()
    )
    _, (step,) = await task_with_steps(auth_client, 60, project_id=project["id"])
    for start, status, sid, kind in (
        (at(MON, 10), EventStatus.done, project["id"], SourceType.project),
        (at(MON, 14), EventStatus.planned, step["id"], SourceType.subtask),
        (at(MON, 16), EventStatus.missed, project["id"], SourceType.project),
        (at(NEXT_MON, 10), EventStatus.planned, project["id"], SourceType.project),
    ):
        await add_event(
            user,
            kind=EventKind.project,
            title="x",
            start=start,
            end=start + timedelta(minutes=90),
            is_fixed=False,
            status=status,
            source_type=kind,
            source_id=sid,
        )
    detail = (await auth_client.get(f"{API}/projects/{project['id']}")).json()
    assert detail["week_done_min"] == 90
    assert detail["week_planned_min"] == 180
    assert detail["behind_days"] == 5
    listed = (await auth_client.get(f"{API}/projects")).json()
    assert listed[0]["week_planned_min"] == 180
