"""M13.2: ИИ предлагает этапы проекта — черновик, перегенерация, «Сохранить»."""

import json
from datetime import date, timedelta

from app.ai.prompts import ExistingMilestone, MilestonesContext, milestones_messages
from app.core.time import get_tz, local_date, now_utc
from app.domain.projects import MilestoneDates, RawMilestone, behind_days, normalize_milestones

from .test_ai import ai_logs, fake, job_result, run_jobs  # noqa: F401
from .test_projects import add_milestone, make_project
from .test_schedule_api import API, other_client
from .test_tasks import make_task

TODAY = local_date(now_utc(), get_tz("Europe/Moscow"))


def answer(*items: tuple[str, str], warning: str = "") -> str:
    return json.dumps(
        {
            "milestones": [{"title": t, "date": d, "note": "что входит"} for t, d in items],
            "warning": warning,
        },
        ensure_ascii=False,
    )


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


# ---------- чистые функции ----------


def test_normalize_milestones():
    today, deadline = date(2026, 10, 8), date(2027, 6, 15)
    raw = [
        RawMilestone("Защита", date(2027, 7, 1)),
        RawMilestone("  Обзор   литературы ", date(2026, 12, 1), "  статьи  и книги "),
        RawMilestone("обзор литературы.", date(2026, 12, 5)),  # повтор
        RawMilestone("Тема согласована", date(2026, 9, 1)),  # уже прошло — без даты
        RawMilestone("Данные собраны", date(2027, 2, 1)),
        RawMilestone("Глава 1", None),
        RawMilestone("   ", date(2027, 1, 1)),
    ]
    result = normalize_milestones(raw, today=today, deadline=deadline, existing=["Глава 1"])
    assert [(m.title, m.date) for m in result] == [
        ("Обзор литературы", date(2026, 12, 1)),
        ("Данные собраны", date(2027, 2, 1)),
        ("Защита", deadline),
        ("Тема согласована", None),
    ]
    assert result[0].note == "статьи и книги"


def test_normalize_with_past_deadline_does_not_clamp_into_past():
    today = date(2026, 10, 8)
    result = normalize_milestones(
        [RawMilestone("Этап", date(2026, 11, 1))], today=today, deadline=date(2026, 9, 1)
    )
    assert result[0].date == date(2026, 11, 1)


def test_behind_days():
    today = date(2026, 10, 8)
    ms = [
        MilestoneDates(date(2026, 10, 1), done=False),
        MilestoneDates(date(2026, 9, 20), done=True),
        MilestoneDates(date(2026, 10, 5), done=False),
        MilestoneDates(None, done=False),
        MilestoneDates(date(2026, 11, 1), done=False),
    ]
    assert behind_days(ms, today) == 7
    assert behind_days([MilestoneDates(date(2026, 10, 8), done=False)], today) == 0


def test_prompt_has_context():
    ctx = MilestonesContext(
        title="ВКР",
        today=date(2026, 10, 8),
        description="Тема: муссоны",
        deadline=date(2027, 6, 15),
        weekly_norm_min=360,
        existing=[ExistingMilestone("Тема согласована", date(2026, 10, 20), True)],
        tasks=["Найти статьи"],
        previous=["Обзор — 2026-12-01"],
        comment="поменьше этапов",
    )
    system, user, redo = milestones_messages(ctx)
    assert "этапы" in system.content
    assert "15 июня 2027" in user.content and "через 250 дн." in user.content
    assert "Тема согласована — 2026-10-20 (выполнен)" in user.content
    assert "Найти статьи" in user.content and "6 ч" in user.content
    assert "поменьше этапов" in redo.content and "Обзор — 2026-12-01" in redo.content


# ---------- джоба и экран проверки ----------


async def test_suggest_and_save(auth_client, fake):  # noqa: F811
    project = await make_project(
        auth_client, description="ВКР про муссоны", deadline=d(240), weekly_norm_min=360
    )
    await add_milestone(auth_client, project["id"], title="Тема согласована", date=d(10))
    await make_task(auth_client, title="Найти статьи", project_id=project["id"])
    latest = f"{API}/projects/{project['id']}/milestones/suggest/latest"
    assert (await auth_client.get(latest)).json() is None

    resp = await auth_client.post(f"{API}/projects/{project['id']}/milestones/suggest", json={})
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    assert (await auth_client.get(latest)).json()["status"] == "pending"

    fake.push(
        answer(
            ("Защита", d(300)),
            ("Тема согласована", d(10)),  # уже есть
            ("Обзор литературы готов", d(60)),
            warning="Уточните требования кафедры",
        )
    )
    assert await run_jobs() == 1
    job = await job_result(auth_client, job_id)
    assert job["status"] == "done", job
    draft = job["result"]
    assert draft["type"] == "milestones" and draft["project_id"] == project["id"]
    assert [(m["title"], m["date"]) for m in draft["milestones"]] == [
        ("Обзор литературы готов", d(60)),
        ("Защита", d(240)),  # прижато к итоговому сроку
    ]
    assert draft["warning"] == "Уточните требования кафедры"
    prompt = fake.calls[0][0][1].content
    assert "ВКР про муссоны" in prompt and "Тема согласована" in prompt and "Найти статьи" in prompt
    assert (await ai_logs())[0].purpose == "milestones"

    # Проект не изменился, пока не сохранили
    detail = (await auth_client.get(f"{API}/projects/{project['id']}")).json()
    assert len(detail["milestones"]) == 1

    body = {"milestones": draft["milestones"], "job_id": job_id}
    resp = await auth_client.post(f"{API}/projects/{project['id']}/milestones/bulk", json=body)
    assert resp.status_code == 200, resp.text
    titles = [(m["title"], m["note"]) for m in resp.json()["milestones"]]
    assert titles == [
        ("Тема согласована", ""),
        ("Обзор литературы готов", "что входит"),
        ("Защита", "что входит"),
    ]
    assert (await auth_client.get(latest)).json() is None


async def test_regenerate_with_comment(auth_client, fake):  # noqa: F811
    project = await make_project(auth_client, deadline=d(200))
    body = {"comment": "без предзащиты", "previous": [{"title": "Предзащита", "date": d(150)}]}
    await auth_client.post(f"{API}/projects/{project['id']}/milestones/suggest", json=body)
    fake.push(answer(("Защита", d(200))))
    await run_jobs()
    messages = fake.calls[0][0]
    assert "без предзащиты" in messages[-1].content and "Предзащита" in messages[-1].content


async def test_nothing_new_fails_with_message(auth_client, fake):  # noqa: F811
    project = await make_project(auth_client)
    await add_milestone(auth_client, project["id"], title="Защита")
    job_id = (
        await auth_client.post(f"{API}/projects/{project['id']}/milestones/suggest", json={})
    ).json()["job_id"]
    fake.push(answer(("Защита", d(30))))
    await run_jobs()
    job = await job_result(auth_client, job_id)
    assert job["status"] == "failed" and "новых этапов" in job["error"]


async def test_dismiss_hides_draft(auth_client, fake):  # noqa: F811
    project = await make_project(auth_client)
    base = f"{API}/projects/{project['id']}/milestones/suggest"
    job_id = (await auth_client.post(base, json={})).json()["job_id"]
    fake.push(answer(("Обзор", d(30))))
    await run_jobs()
    resp = await auth_client.post(f"{base}/{job_id}/dismiss")
    assert resp.status_code == 204
    assert (await auth_client.get(f"{base}/latest")).json() is None


async def test_bulk_validation_and_privacy(auth_client, session):
    project = await make_project(auth_client)
    url = f"{API}/projects/{project['id']}/milestones/bulk"
    assert (await auth_client.post(url, json={"milestones": []})).status_code == 422
    async with other_client(auth_client, session) as other:
        assert (await other.post(url, json={"milestones": [{"title": "x"}]})).status_code == 404
        suggest = f"{API}/projects/{project['id']}/milestones/suggest"
        assert (await other.post(suggest, json={})).status_code == 404
