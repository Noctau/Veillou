"""M10: ИИ-джобы — разбивка, «Запланировать», шаблоны, разбор текста, фото, ai_log."""

import json
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.ai import set_provider
from app.ai.fake import FakeProvider
from app.core.config import settings
from app.core.db import session_factory
from app.core.time import get_tz, now_utc, wall_to_utc
from app.domain.enums import AI_JOB_KINDS, EventKind, EventStatus, JobStatus, SourceType
from app.domain.quickparse import KindHint, ParseResult, needs_ai
from app.models import AILog, Event, Job
from app.services import jobs
from app.services.replan import ReplanService
from app.worker.__main__ import build_handlers

from .test_attachments import upload
from .test_schedule_api import API, other_client
from .test_tasks import add_subtask, get_task, make_task

TZ = get_tz("Europe/Moscow")


@pytest.fixture
def fake():
    provider = FakeProvider()
    set_provider(provider)
    yield provider
    set_provider(None)


@pytest.fixture(autouse=True)
def _fast_solver(monkeypatch):
    monkeypatch.setattr(ReplanService, "time_limit_s", 0.4)


@pytest.fixture(autouse=True)
def storage(tmp_path: Path, monkeypatch):
    # И API, и «воркер» берут файлы из одного места
    monkeypatch.setattr(settings, "STORAGE_DIR", tmp_path)
    return tmp_path


async def run_jobs(bot=None) -> int:
    return await jobs.run_ready(session_factory, build_handlers(bot))


async def run_ai_jobs(bot=None) -> int:
    """Только ИИ-джобы: отложенные на секунды пересборки (reminders.sync, plan.preview)
    под нагрузкой тоже успевают стать готовыми — счёт по всем джобам нестабилен."""
    return await jobs.run_ready(session_factory, build_handlers(bot), kinds=AI_JOB_KINDS)


async def job_result(client: AsyncClient, job_id: str) -> dict:
    resp = await client.get(f"{API}/jobs/{job_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def breakdown_answer(**over) -> str:
    data = {
        "task_type": "essay",
        "category": "study",
        "subtasks": [
            {"order": 2, "title": "Написать текст", "estimate_min": 90, "action_type": "study",
             "depends_on": [1], "note": ""},
            {"order": 1, "title": "Найти 3 источника", "estimate_min": 40,
             "action_type": "study", "depends_on": [], "note": "в библиотеке кафедры"},
            {"order": 3, "title": "Согласовать тему с преподавателем", "estimate_min": 15,
             "action_type": "people", "depends_on": [], "note": ""},
        ],
        "total_estimate_min": 145,
        "warning": None,
    }  # fmt: skip
    data.update(over)
    return json.dumps(data, ensure_ascii=False)


def parsed_answer(**over) -> str:
    data = {
        "kind": "task",
        "title": "Задание",
        "task_type": "other",
        "subject": "",
        "deadline_date": "",
        "deadline_time": "",
        "action_type": "study",
        "description": "",
    }
    return json.dumps({**data, **over}, ensure_ascii=False)


def photo_answer(**over) -> str:
    data = {
        "text": "",
        "title": "Задание",
        "task_type": "other",
        "subject": "",
        "deadline_date": "",
        "deadline_time": "",
    }
    return json.dumps({**data, **over}, ensure_ascii=False)


async def ai_logs() -> list[AILog]:
    async with session_factory() as db:
        return list(await db.scalars(select(AILog).order_by(AILog.created_at)))


# ---------- разбивка ----------


async def test_breakdown_draft(auth_client, fake):
    deadline = (now_utc() + timedelta(days=5)).isoformat()
    task = await make_task(
        auth_client, title="Реферат о муссонах", description="10 страниц, 5 источников",
        deadline=deadline,
    )  # fmt: skip
    resp = await auth_client.post(f"{API}/tasks/{task['id']}/breakdown", json={})
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    assert (await job_result(auth_client, job_id))["status"] == "pending"

    fake.push(breakdown_answer())
    assert await run_ai_jobs() == 1
    job = await job_result(auth_client, job_id)
    assert job["status"] == "done"
    assert job["error"] is None
    draft = job["result"]
    assert draft["type"] == "breakdown"
    assert draft["task_id"] == task["id"]
    titles = [s["title"] for s in draft["steps"]]
    assert titles == ["Найти 3 источника", "Написать текст", "Согласовать тему с преподавателем"]
    assert draft["steps"][1]["depends_on"] == [0]
    assert draft["total_estimate_min"] == 145
    assert draft["free_minutes"] > 0
    assert draft["coef"] == 1.0
    types = {a["key"]: a["id"] for a in (await auth_client.get(f"{API}/action-types")).json()}
    assert draft["steps"][2]["action_type_id"] == types["people"]
    assert draft["category_id"] is not None

    # Задание не изменилось
    assert (await get_task(auth_client, task["id"]))["subtasks"] == []

    # В промпте — описание, дедлайн и свободное время
    prompt = fake.calls[0][0][1].content
    assert "10 страниц" in prompt
    assert "Дедлайн:" in prompt
    assert "Свободного времени" in prompt

    logs = await ai_logs()
    assert len(logs) == 1
    assert logs[0].ok
    assert logs[0].purpose == "breakdown"
    assert str(logs[0].job_id) == job_id
    assert logs[0].prompt_tokens == 10


async def test_regenerate_with_comment(auth_client, fake):
    task = await make_task(auth_client)
    body = {
        "comment": "слишком мелко",
        "previous": [
            {"title": "Шаг А", "estimate_min": 15},
            {"title": "Шаг Б", "estimate_min": 20},
        ],
    }
    job_id = (await auth_client.post(f"{API}/tasks/{task['id']}/breakdown", json=body)).json()[
        "job_id"
    ]
    fake.push(breakdown_answer())
    await run_jobs()
    messages = fake.calls[0][0]
    assert "Шаг А — 15 мин" in messages[-1].content
    assert "слишком мелко" in messages[-1].content
    assert (await job_result(auth_client, job_id))["status"] == "done"


async def test_invalid_answer_twice_fails_without_retry(auth_client, fake):
    task = await make_task(auth_client)
    job_id = (await auth_client.post(f"{API}/tasks/{task['id']}/breakdown", json={})).json()[
        "job_id"
    ]
    fake.push("не json", breakdown_answer(subtasks=[]))
    await run_jobs()
    job = await job_result(auth_client, job_id)
    assert job["status"] == "failed"
    assert job["result"] is None
    assert "ИИ ответил непонятно" in job["error"]
    assert [log.ok for log in await ai_logs()] == [False, False]
    # Без повторов: очередь пуста
    assert await run_jobs() == 0


async def run_ai_later(minutes: int = 10, bot=None) -> list:
    """Как очередь ИИ воркера, но «через N минут» (отложенные джобы уже созрели).
    ИИ снова недоступен — останавливаемся: воркер в этот момент делает паузу."""
    later = now_utc() + timedelta(minutes=minutes)
    outcomes = []
    while outcome := await jobs.run_one(
        session_factory, build_handlers(bot), now=later, kinds=AI_JOB_KINDS, fifo=True
    ):
        outcomes.append(outcome)
        if outcome == jobs.JobOutcome.deferred:
            break
    return outcomes


async def test_unavailable_provider_queues_until_back(auth_client, fake):
    import httpx

    task = await make_task(auth_client)
    url = f"{API}/tasks/{task['id']}/breakdown"
    first = (await auth_client.post(url, json={})).json()["job_id"]
    second = (await auth_client.post(url, json={"comment": "ещё"})).json()["job_id"]

    # ИИ выключен: запросы не падают, а ждут
    fake.push(httpx.ConnectError("нет"), httpx.ConnectError("нет"))
    await run_jobs()
    for job_id in (first, second):
        job = await job_result(auth_client, job_id)
        assert job["status"] == "pending"
        assert job["error"] is None
        assert "в очереди" in job["waiting"]
    async with session_factory() as db:
        row = await db.get(Job, uuid.UUID(first))
        assert row is not None
        assert row.attempts == 0

    # Ещё не появился — проверяем первой джобой в очереди, остальные ждут, без лимита попыток
    fake.push(httpx.ConnectError("нет"))
    assert await run_ai_later(2) == [jobs.JobOutcome.deferred]

    # Появился — всё выполняется по очереди, в порядке постановки
    fake.push(breakdown_answer(), breakdown_answer())
    assert await run_ai_later(10) == [jobs.JobOutcome.done] * 2
    assert "ещё" not in fake.calls[-2][0][-1].content
    assert "ещё" in fake.calls[-1][0][-1].content
    for job_id in (first, second):
        job = await job_result(auth_client, job_id)
        assert job["status"] == "done"
        assert job["waiting"] is None
        assert job["result"]["type"] == "breakdown"


async def test_queue_gives_up_after_max_wait(auth_client, fake, monkeypatch):
    import httpx

    monkeypatch.setattr(settings, "LLM_QUEUE_MAX_HOURS", 1)
    task = await make_task(auth_client)
    job_id = (await auth_client.post(f"{API}/tasks/{task['id']}/breakdown", json={})).json()[
        "job_id"
    ]
    async with session_factory() as db:
        row = await db.get(Job, uuid.UUID(job_id))
        assert row is not None
        row.created_at = now_utc() - timedelta(hours=2)
        await db.commit()
    fake.push(httpx.ConnectError("нет"))
    await run_jobs()
    job = await job_result(auth_client, job_id)
    assert job["status"] == "failed"
    assert "так и не стал доступен" in job["error"]


async def test_latest_breakdown_on_task(auth_client, fake):
    task = await make_task(auth_client)
    latest = f"{API}/tasks/{task['id']}/breakdown/latest"
    assert (await auth_client.get(latest)).json() is None
    job_id = (await auth_client.post(f"{API}/tasks/{task['id']}/breakdown", json={})).json()[
        "job_id"
    ]
    assert (await auth_client.get(latest)).json()["status"] == "pending"
    fake.push(breakdown_answer())
    await run_jobs()
    ready = (await auth_client.get(latest)).json()
    assert ready["id"] == job_id
    assert ready["result"]["type"] == "breakdown"

    body = {"steps": ready["result"]["steps"], "plan": False, "job_id": job_id}
    resp = await auth_client.post(f"{API}/tasks/{task['id']}/breakdown/apply", json=body)
    assert resp.status_code == 200, resp.text
    # Применили — задание больше не напоминает о черновике
    assert (await auth_client.get(latest)).json() is None


async def test_jobs_are_private(auth_client, session):
    task = await make_task(auth_client)
    job_id = (await auth_client.post(f"{API}/tasks/{task['id']}/breakdown", json={})).json()[
        "job_id"
    ]
    async with other_client(auth_client, session) as other:
        assert (await other.get(f"{API}/jobs/{job_id}")).status_code == 404
        resp = await other.post(f"{API}/tasks/{task['id']}/breakdown", json={})
        assert resp.status_code == 404


async def test_recurring_task_not_broken_down(auth_client):
    task = await make_task(auth_client, recurrence="FREQ=WEEKLY;BYDAY=TH")
    resp = await auth_client.post(f"{API}/tasks/{task['id']}/breakdown", json={})
    assert resp.status_code == 400


# ---------- «Запланировать» ----------


async def test_apply_replaces_open_steps_and_previews_plan(auth_client):
    deadline = (now_utc() + timedelta(days=7)).isoformat()
    task = await make_task(auth_client, deadline=deadline, estimate_min=120)
    done = await add_subtask(auth_client, task["id"], title="Уже сделано")
    await auth_client.patch(f"{API}/subtasks/{done['id']}", json={"status": "done"})
    old = await add_subtask(auth_client, task["id"], title="Старый шаг")
    start = (now_utc() + timedelta(days=1)).replace(microsecond=0)
    resp = await auth_client.post(
        f"{API}/subtasks/{old['id']}/schedule", json={"start": start.isoformat()}
    )
    assert resp.status_code == 200

    types = {a["key"]: a["id"] for a in (await auth_client.get(f"{API}/action-types")).json()}
    body = {
        "task_type": "report",
        "steps": [
            {"title": "Найти источники", "estimate_min": 45, "action_type_id": types["study"]},
            {"title": "Написать доклад", "estimate_min": 90, "depends_on": [0]},
            {"title": "Отправить преподавателю", "estimate_min": 15,
             "action_type_id": types["people"], "depends_on": [1], "note": "на почту"},
        ],
    }  # fmt: skip
    resp = await auth_client.post(f"{API}/tasks/{task['id']}/breakdown/apply", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    detail = data["task"]
    assert detail["task_type"] == "report"
    assert [s["title"] for s in detail["subtasks"]] == [
        "Уже сделано",
        "Найти источники",
        "Написать доклад",
        "Отправить преподавателю",
    ]
    by_title = {s["title"]: s for s in detail["subtasks"]}
    assert by_title["Написать доклад"]["depends_on"] == [by_title["Найти источники"]["id"]]
    assert by_title["Отправить преподавателю"]["note"] == "на почту"

    # Блок старого шага (даже закреплённый) убран
    async with session_factory() as db:
        live = await db.scalar(
            select(func.count()).where(
                Event.source_type == SourceType.subtask,
                Event.source_id == old["id"],
                Event.deleted_at.is_(None),
            )
        )
    assert live == 0

    # Превью плана посчитано сразу, но ничего не применено
    proposal = data["plan"]["proposal"]
    assert proposal is not None
    assert proposal["added"] >= 3
    async with session_factory() as db:
        planned = await db.scalar(
            select(func.count()).where(
                Event.kind == EventKind.subtask,
                Event.deleted_at.is_(None),
                Event.status == EventStatus.planned,
            )
        )
    assert planned == 0


async def test_apply_without_plan_and_validation(auth_client):
    task = await make_task(auth_client)
    url = f"{API}/tasks/{task['id']}/breakdown/apply"
    cycle = {
        "steps": [
            {"title": "А", "estimate_min": 30, "depends_on": [1]},
            {"title": "Б", "estimate_min": 30, "depends_on": [0]},
        ]
    }
    assert (await auth_client.post(url, json=cycle)).status_code == 422
    bad_ref = {"steps": [{"title": "А", "estimate_min": 30, "depends_on": [3]}]}
    assert (await auth_client.post(url, json=bad_ref)).status_code == 422
    resp = await auth_client.post(
        url, json={"steps": [{"title": "А", "estimate_min": 30}], "plan": False}
    )
    assert resp.status_code == 200
    assert resp.json()["plan"] is None


# ---------- шаблоны ----------


async def test_templates(auth_client, session):
    types = {a["key"]: a["id"] for a in (await auth_client.get(f"{API}/action-types")).json()}
    body = {
        "name": "Реферат",
        "task_type": "essay",
        "steps": [
            {"title": "Найти источники", "estimate_min": 60, "action_type_id": types["study"]},
            {"title": "Написать", "estimate_min": 120, "depends_on": [0]},
        ],
    }
    resp = await auth_client.post(f"{API}/breakdown-templates", json=body)
    assert resp.status_code == 201, resp.text
    tpl = resp.json()
    assert tpl["total_estimate_min"] == 180
    assert tpl["steps"][0]["action_type_id"] == types["study"]
    assert tpl["steps"][1]["depends_on"] == [0]

    resp = await auth_client.patch(
        f"{API}/breakdown-templates/{tpl['id']}", json={"name": "Реферат (большой)"}
    )
    assert resp.json()["name"] == "Реферат (большой)"
    assert len((await auth_client.get(f"{API}/breakdown-templates")).json()) == 1
    async with other_client(auth_client, session) as other:
        assert (await other.get(f"{API}/breakdown-templates")).json() == []
        resp = await other.delete(f"{API}/breakdown-templates/{tpl['id']}")
        assert resp.status_code == 404

    assert (await auth_client.delete(f"{API}/breakdown-templates/{tpl['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/breakdown-templates")).json() == []


# ---------- разбор текста ----------


@pytest.mark.parametrize(
    ("text", "result", "expected"),
    [
        ("купить продукты", ParseResult("купить продукты"), False),
        ("реферат клим до пт", ParseResult("реферат", kind_hint=KindHint.task), True),
        (
            "реферат клим до пт",
            ParseResult("реферат", kind_hint=KindHint.task, subject_id=1, date=now_utc().date()),
            False,
        ),
        ("x" * 81, ParseResult("x"), True),
        ("строка 1\nстрока 2", ParseResult("строка"), True),
        ("кино в пт в 19", ParseResult("кино", kind_hint=KindHint.event), False),
    ],
)
def test_needs_ai(text, result, expected):
    assert needs_ai(text, result) is expected


async def make_subject(client: AsyncClient, name: str, short: str) -> dict:
    resp = await client.post(
        f"{API}/subjects", json={"name": name, "short_name": short, "color": "#3b82f6"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_ai_parse_card(auth_client, fake):
    subject = await make_subject(auth_client, "Климатология", "клим")
    text = "Нужно подготовить доклад про Эль-Ниньо на 10 минут, со слайдами, к семинару Петрова"
    job_id = (await auth_client.post(f"{API}/quick-add/ai-parse", json={"text": text})).json()[
        "job_id"
    ]
    fake.push(
        parsed_answer(
            title="Доклад про Эль-Ниньо",
            task_type="report",
            subject="Климатология",
            deadline_date="2030-01-09",
            # Такого времени в тексте нет — выдуманное время отбрасывается
            deadline_time="15:00",
            description="10 минут, со слайдами",
        )
    )
    await run_jobs()
    draft = (await job_result(auth_client, job_id))["result"]
    assert draft["type"] == "parse"
    assert draft["kind"] == "task"
    assert draft["title"] == "Доклад про Эль-Ниньо"
    assert draft["task_type"] == "report"
    assert draft["subject_id"] == subject["id"]
    deadline = datetime.fromisoformat(draft["deadline"])
    assert deadline == wall_to_utc(date(2030, 1, 9), time(23, 59), TZ)
    assert draft["text"] == text
    # Предметы ушли в схему ответа списком
    assert "Климатология" in fake.calls[0][0][1].content


async def test_ai_parse_prefers_explicit_date_from_quickparse(auth_client, fake):
    text = "реферат по истории науки до 15.11 объём 15 страниц, шрифт 14, интервал полуторный"
    job_id = (await auth_client.post(f"{API}/quick-add/ai-parse", json={"text": text})).json()[
        "job_id"
    ]
    fake.push(parsed_answer(kind="event", title="Реферат", deadline_date="2031-01-01"))
    await run_jobs()
    draft = (await job_result(auth_client, job_id))["result"]
    # Событие без времени — не событие; дата — из явного «до 15.11»
    assert draft["kind"] == "task"
    local = datetime.fromisoformat(draft["deadline"]).astimezone(TZ)
    assert (local.month, local.day) == (11, 15)


# ---------- фото ----------


async def test_recognize_photo_fills_task(auth_client, fake):
    task = await make_task(auth_client, title="Задание с фото", task_type="other")
    assert (await upload(auth_client, task["id"])).status_code == 201
    resp = await auth_client.post(f"{API}/tasks/{task['id']}/recognize")
    assert resp.status_code == 202, resp.text
    fake.push(
        photo_answer(
            title="Задачи 3.1–3.5",
            text="Решить задачи 3.1–3.5 из задачника",
            task_type="homework",
            deadline_date="2030-02-01",
            deadline_time="09:00",
        )
    )
    await run_jobs()
    draft = (await job_result(auth_client, resp.json()["job_id"]))["result"]
    assert draft["type"] == "photo"
    assert set(draft["updated"]) == {"description", "title", "deadline", "task_type"}
    detail = await get_task(auth_client, task["id"])
    assert detail["title"] == "Задачи 3.1–3.5"
    assert "3.1–3.5 из задачника" in detail["description"]
    assert detail["task_type"] == "homework"
    _, model = fake.calls[0]
    assert model == "fake-vision"
    assert fake.calls[0][0][-1].images


async def test_recognize_needs_images(auth_client):
    task = await make_task(auth_client)
    assert (await auth_client.post(f"{API}/tasks/{task['id']}/recognize")).status_code == 400


async def test_failed_job_reports_error(auth_client, fake):
    task = await make_task(auth_client)
    job_id = (await auth_client.post(f"{API}/tasks/{task['id']}/breakdown", json={})).json()[
        "job_id"
    ]
    await auth_client.delete(f"{API}/tasks/{task['id']}")
    await run_jobs()
    job = await job_result(auth_client, job_id)
    assert job["status"] == JobStatus.failed
    assert job["error"] == "Задание удалено"
    async with session_factory() as db:
        row = await db.get(Job, uuid.UUID(job_id))
        assert row is not None
        assert row.attempts == 1


@pytest.mark.parametrize(
    ("text", "cue"),
    [
        ("прочитать главу учебника по гидрологии", False),
        ("написать научруку про структуру главы", False),
        ("реферат к пятнице", True),
        ("доклад через неделю", True),
        ("сдать 15.11", True),
    ],
)
def test_date_cue(text, cue):
    from app.domain.quickparse import has_date_cue

    assert has_date_cue(text) is cue


async def test_ai_parse_drops_invented_deadline_and_prefers_keyword_rules(auth_client, fake):
    text = "написать научному руководителю про структуру первой главы и попросить список литературы"
    job_id = (await auth_client.post(f"{API}/quick-add/ai-parse", json={"text": text})).json()[
        "job_id"
    ]
    fake.push(
        parsed_answer(title="Письмо научруку", deadline_date="2030-01-01", action_type="study")
    )
    await run_jobs()
    draft = (await job_result(auth_client, job_id))["result"]
    assert draft["deadline"] is None
    types = {a["key"]: a["id"] for a in (await auth_client.get(f"{API}/action-types")).json()}
    assert draft["action_type_id"] == types["people"]
