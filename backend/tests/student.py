"""Фикстура «студентка» (M14.1): типичный пользователь Part 1 со всеми кирпичами.

Данные создаются через публичный API (как их создала бы сама студентка),
«сейчас» заморожено (`Clock`). Из этой же фикстуры собран SQL-дамп для
`make migrate-check` (M14.2, tests/fixtures/student.sql).

Состав:
- типы занятости, как их создаёт миграция M17.1: «Пара» (дорога 40 мин со склейкой,
  напоминание за 20 мин, поля «Вид занятия» и «Преподаватель»), «Личное», «Отдых»,
  «Экзамен»;
- период с циклом 2 недели и паузами «Перерыв» / «Сессия» (бывший семестр с
  чётностью и сессией), сетка «Звонки» с общими слотами и своими на субботу,
  праздник и каникулы;
- 6 предметов и 10 правил «Пары» (в т. ч. неделя цикла 1 / 2, «своё время»,
  правило с `valid_from`), отменённая и перенесённая пара, пара с заметкой;
- личный повтор (бассейн) и отдых, разовое личное событие;
- типы задач, как их создала миграция M15.1 (с ключами сида и синонимами), в т. ч.
  «Задание с работы» (срок + 14 дней, проект «Работа в лаборатории»);
- задания с шагами разных типов действий, зависимостями, закреплённым шагом и
  калибровкой; задание без шагов; «задание с работы»; регулярное задание;
- ящик: дела с чипом «в дни пар» и «в часы учреждений», взятые на неделю, и старое;
- экзамен (событие типа «Экзамен») с планом подготовки по билетам;
- проект с недельной нормой (ВКР) и проект для заданий с работы;
- лимит «Учёба» (5 ч) с разовым лимитом дня (M15.3); режимы дня «Будни» и
  «Выходные» с поздним сном (M18).
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import session_factory
from app.core.time import get_tz, wall_to_utc

API = "/api/v1"
TZ = get_tz("Europe/Moscow")
EMAIL = "student@example.com"

# Типы задач студентки — как их создаёт миграция M15.1 из enum TaskType Part 1
TASK_TYPES: list[tuple[str, str, str, list[str]]] = [
    ("homework", "ДЗ", "pencil", ["дз", "домашка", "домашнее задание", "упражнение"]),
    ("report", "Доклад", "presentation", ["доклад", "презентация", "выступление"]),
    ("essay", "Реферат", "file-text", ["реферат", "эссе"]),
    ("lab", "Лабораторная", "flask-conical", ["лаба", "лабораторная", "практикум"]),
    ("coursework", "Курсовая", "graduation-cap", ["курсовая", "курсач"]),
    ("reading", "Чтение", "book-open", ["прочитать", "дочитать", "чтение", "глава"]),
    (
        "exam_prep",
        "Подготовка к экзамену",
        "clipboard-check",
        ["экзамен", "зачёт", "коллоквиум", "контрольная"],
    ),
]

# Поля «Пары» — как их создаёт миграция M17.1 (id полей сида, а не f1, f2)
CLASS_FIELDS = [
    {
        "id": "class_type",
        "label": "Вид занятия",
        "type": "select",
        "options": ["лекция", "семинар", "лаба"],
        "multiple": False,
        "show_in_reminder": True,
        "required": False,
        "deleted": False,
    },
    {
        "id": "teacher",
        "label": "Преподаватель",
        "type": "text",
        "options": [],
        "multiple": False,
        "show_in_reminder": True,
        "required": False,
        "deleted": False,
    },
]
CLASS_TYPES = {"lecture": "лекция", "seminar": "семинар", "lab": "лаба"}

# «Сейчас» фикстуры — понедельник 30.11.2026, 07:00 МСК (до утренней сводки)
TODAY = date(2026, 11, 30)
NOW = wall_to_utc(TODAY, time(7, 0), TZ)


def at(d: date, h: int, m: int = 0) -> str:
    return wall_to_utc(d, time(h, m), TZ).isoformat()


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


class Clock:
    """Подменяет `now_utc` во всех загруженных модулях `app.*`.

    Модули импортируют функцию по имени (`from app.core.time import now_utc`),
    поэтому патчится и источник, и каждая копия ссылки.
    """

    def __init__(self, monkeypatch: Any, now: datetime) -> None:
        import app.core.time as core_time

        self.now = now
        original = core_time.now_utc
        for name, module in list(sys.modules.items()):
            if (name == "app" or name.startswith("app.")) and getattr(
                module, "now_utc", None
            ) is original:
                monkeypatch.setattr(module, "now_utc", self)

    def __call__(self) -> datetime:
        return self.now

    def set(self, now: datetime) -> None:
        self.now = now.astimezone(UTC)


@dataclass
class Student:
    """id созданных сущностей по понятным именам (для проверок и меток снимков)."""

    ids: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, name: str) -> str:
        return self.ids[name]


async def _ok(resp: Any, *codes: int) -> Any:
    assert resp.status_code in (codes or (200, 201)), resp.text
    return resp.json() if resp.content else None


async def build_student(client: AsyncClient) -> Student:
    """Заполняет аккаунт залогиненного клиента. Вызывать при замороженных часах (NOW)."""
    st = Student()
    c = client

    async def post(url: str, body: dict[str, Any], key: str | None = None) -> Any:
        data = await _ok(await c.post(API + url, json=body))
        if key:
            st.ids[key] = data["id"]
        return data

    async def patch(url: str, body: dict[str, Any]) -> Any:
        return await _ok(await c.patch(API + url, json=body))

    async def put(url: str, body: dict[str, Any] | None = None) -> Any:
        return await _ok(await c.put(API + url, json=body))

    # ---------- настройки ----------
    # Сон 00:00–08:00 и будни 9–22 — как их перенесла миграция M18 в «Будни» и
    # «Выходные» (тихие часы — из настроек); сводка в 08:00 = подъём, разбор в 21:30
    await patch(
        "/me/settings",
        {
            "schedule": {
                "morning_digest_after_wake_min": 0,
                "evening_review_before_sleep_min": 150,
            },
            "onboarding_done": True,
        },
    )
    for profile in await _ok(await c.get(f"{API}/day-profiles")):
        body: dict[str, Any] = {"wake": "08:00", "sleep": "00:00", "quiet_follows_sleep": False}
        if profile["key"] == "weekdays":
            body["work_windows"] = [{"start": "09:00", "end": "22:00"}]
        await patch(f"/day-profiles/{profile['id']}", body)
    types = {t["key"]: t["id"] for t in await _ok(await c.get(f"{API}/action-types"))}
    cats = {x["key"]: x["id"] for x in await _ok(await c.get(f"{API}/categories")) if x["key"]}
    # Лимит «Учёба» — бывший study_limit_min_per_day: 300
    budget = await post(
        "/load-budgets",
        {"name": "Учёба", "minutes_per_day": 300, "action_type_ids": [types["study"]]},
        "budget",
    )

    # ---------- типы задач (как после миграции M15.1) ----------
    task_types: dict[str, str] = {}
    for key, name, icon, synonyms in TASK_TYPES:
        data = await post(
            "/task-types", {"name": name, "icon": icon, "synonyms": synonyms}, f"tt_{key}"
        )
        task_types[key] = data["id"]

    # ---------- типы занятости (как после миграции M17.1) ----------
    event_types = {}
    for key, body in (
        (
            "class",
            {
                "name": "Пара",
                "name_plural": "Пары",
                "icon": "graduation-cap",
                "color": "#3b82f6",
                "buffer_before_min": 40,
                "buffer_after_min": 40,
                "merge_buffers": True,
                "remind_before_min": 20,
                "show_now_next": True,
                "location_label": "ауд.",
            },
        ),
        ("personal", {"name": "Личное", "icon": "user", "color": "#64748b"}),
        ("rest", {"name": "Отдых", "icon": "coffee", "color": "#22c55e", "is_rest": True}),
        (
            "exam",
            {
                "name": "Экзамен",
                "name_plural": "Экзамены",
                "icon": "clipboard-check",
                "color": "#ef4444",
                "show_now_next": True,
                "supports_prep": True,
                "location_label": "ауд.",
            },
        ),
    ):
        event_types[key] = (await post("/event-types", body, f"et_{key}"))["id"]
    # Ключи сида и id полей «Пары» — как после миграции (через API их не задать)
    async with session_factory() as db:
        for key in event_types:
            await db.execute(
                text("UPDATE event_types SET key = :key WHERE id = :id"),
                {"key": key, "id": event_types[key]},
            )
        await db.execute(
            text("UPDATE event_types SET fields = CAST(:fields AS jsonb) WHERE id = :id"),
            {"fields": json.dumps(CLASS_FIELDS, ensure_ascii=False), "id": event_types["class"]},
        )
        await db.commit()

    # ---------- период, звонки, исключения ----------
    sem = await post(
        "/periods",
        {
            "name": "Осень 2026",
            "start_date": "2026-09-01",
            "end_date": "2027-01-25",
            "cycle_weeks": 2,
            "first_cycle_week": 1,
            "pauses": [
                {"from": "2026-12-28", "to": "2027-01-08", "title": "Перерыв"},
                {"from": "2027-01-09", "to": "2027-01-25", "title": "Сессия"},
            ],
        },
        "semester",
    )
    grid = await put(
        "/slot-grids",
        {
            "period_id": sem["id"],
            "name": "Звонки",
            "schedules": [
                {
                    "weekday": None,
                    "slots": [
                        {"number": 1, "start": "09:00", "end": "10:35"},
                        {"number": 2, "start": "10:45", "end": "12:20"},
                        {"number": 3, "start": "13:00", "end": "14:35"},
                        {"number": 4, "start": "14:45", "end": "16:20"},
                        {"number": 5, "start": "16:30", "end": "18:05"},
                    ],
                },
                {
                    "weekday": 6,
                    "slots": [
                        {"number": 1, "start": "10:00", "end": "11:30"},
                        {"number": 2, "start": "11:40", "end": "13:10"},
                    ],
                },
            ],
        },
    )
    grid_id = next(g["id"] for g in grid if g["weekday"] is None)
    await post(
        "/days-off",
        {"date_from": "2026-12-10", "date_to": "2026-12-10", "title": "День факультета"},
        "day_off",
    )
    await post(
        "/days-off",
        {"date_from": "2026-12-31", "date_to": "2027-01-08", "title": "Новогодние каникулы"},
        "holidays",
    )

    # ---------- сферы: тип «Предмет» (как его создаёт миграция M16) ----------
    subject_type = await post(
        "/area-types",
        {
            "name": "Предмет",
            "name_plural": "Предметы",
            "icon": "graduation-cap",
            "fields": [
                {"label": "Преподаватели", "type": "contact", "multiple": True},
                {
                    "label": "Форма контроля",
                    "type": "select",
                    "options": ["Экзамен", "Зачёт", "Дифзачёт", "Курсовая"],
                },
                {"label": "Ссылки", "type": "link", "multiple": True},
            ],
            "sections": ["schedule", "tasks", "notes", "materials", "prep"],
        },
        "subject_type",
    )
    # id полей выдаёт сервер — по порядку
    teachers_f, control_f, links_f = (f["id"] for f in subject_type["fields"])

    async def subject(key: str, control: str = "Экзамен", **body: Any) -> str:
        fields = {control_f: control, **body.pop("fields", {})}
        data = await post(
            "/areas",
            {"area_type_id": subject_type["id"], "period_id": sem["id"], "fields": fields, **body},
            key,
        )
        return str(data["id"])

    clim = await subject(
        "clim",
        name="Климатология",
        short_name="клим",
        synonyms=["климат"],
        color="#10b981",
        fields={
            teachers_f: [
                {"name": "Иванов Пётр Сергеевич", "role": "лектор", "email": "ivanov@example.com"},
                {"name": "Смирнова Анна", "role": "семинарист"},
            ],
            links_f: [{"title": "Курс на сайте кафедры", "url": "https://example.com/clim"}],
        },
    )
    fiz = await subject("fiz", name="Физика атмосферы", short_name="физат", color="#3b82f6")
    dyn = await subject(
        "dyn", name="Динамическая метеорология", short_name="динмет", color="#8b5cf6"
    )
    eng = await subject("eng", "Зачёт", name="Английский язык", short_name="англ", color="#f59e0b")
    matan = await subject(
        "matan",
        "Дифзачёт",
        name="Математический анализ",
        short_name="матан",
        color="#ef4444",
    )
    sat = await subject(
        "sat",
        "Зачёт",
        name="Спутниковая метеорология",
        short_name="спутмет",
        color="#14b8a6",
        notes="Спецкурс, по выбору",
    )

    # ---------- 10 правил «Пары» (как после миграции M17.4) ----------
    rules: list[tuple[str, dict[str, Any]]] = [
        (
            "r_clim_mon",
            {
                "area_id": clim,
                "weekday": 1,
                "pair_number": 1,
                "class_type": "lecture",
                "location": "1801",
                "teacher": "Иванов П. С.",
            },
        ),
        (
            "r_fiz_mon_odd",
            {
                "area_id": fiz,
                "weekday": 1,
                "pair_number": 2,
                "parity": "odd",
                "class_type": "seminar",
                "location": "1805",
            },
        ),
        (
            "r_dyn_mon_even",
            {
                "area_id": dyn,
                "weekday": 1,
                "pair_number": 2,
                "parity": "even",
                "class_type": "seminar",
                "location": "1805",
            },
        ),
        (
            "r_dyn_tue",
            {
                "area_id": dyn,
                "weekday": 2,
                "pair_number": 3,
                "class_type": "lecture",
                "location": "1801",
            },
        ),
        (
            "r_eng_tue",
            {
                "area_id": eng,
                "weekday": 2,
                "pair_number": 4,
                "class_type": "seminar",
                "location": "516",
                "teacher": "Brown J.",
            },
        ),
        (
            "r_matan_wed",
            {
                "area_id": matan,
                "weekday": 3,
                "pair_number": 2,
                "class_type": "lecture",
                "location": "02",
            },
        ),
        (
            "r_fiz_thu_even",
            {
                "area_id": fiz,
                "weekday": 4,
                "pair_number": 1,
                "parity": "even",
                "class_type": "lab",
                "location": "1810",
            },
        ),
        (
            "r_clim_thu",
            {
                "area_id": clim,
                "weekday": 4,
                "pair_number": 3,
                "class_type": "seminar",
                "location": "1805",
                "valid_from": "2026-09-15",
            },
        ),
        (
            "r_sat_fri",
            {
                "area_id": sat,
                "weekday": 5,
                "start_time": "18:30",
                "end_time": "20:00",
                "class_type": "other",
                "location": "ИКИ, к. 200",
            },
        ),
        (
            "r_eng_sat",
            {
                "area_id": eng,
                "weekday": 6,
                "pair_number": 1,
                "class_type": "seminar",
                "location": "516",
            },
        ),
    ]
    for key, body in rules:
        mask = {"odd": [1], "even": [2]}.get(body.pop("parity", "all"))
        fields = {}
        if (kind := body.pop("class_type")) in CLASS_TYPES:
            fields["class_type"] = CLASS_TYPES[kind]
        if teacher := body.pop("teacher", None):
            fields["teacher"] = teacher
        slot = body.pop("pair_number", None)
        rule = {
            "event_type_id": event_types["class"],
            "period_id": sem["id"],
            "pattern": {"kind": "weekly", "weekdays": [body.pop("weekday")], "cycle_weeks": mask},
            "fields": fields,
            **body,
        }
        if slot:
            rule |= {"slot_from": slot, "slot_grid_id": grid_id}
        await post("/schedule-rules", rule, key)

    # ---------- личное и отдых ----------
    await post(
        "/schedule-rules",
        {
            "event_type_id": event_types["personal"],
            "title": "Бассейн",
            "pattern": {"kind": "weekly", "weekdays": [2, 4]},
            "valid_from": "2026-09-01",
            "start_time": "19:00",
            "end_time": "20:30",
            "location": "СК МГУ",
        },
        "pool",
    )
    await post(
        "/schedule-rules",
        {
            "event_type_id": event_types["rest"],
            "title": "Прогулка",
            "pattern": {"kind": "weekly", "weekdays": [7]},
            "valid_from": "2026-09-06",
            "start_time": "15:00",
            "end_time": "18:00",
        },
        "walk",
    )
    await post(
        "/events",
        {
            "event_type_id": event_types["personal"],
            "title": "Врач",
            "start": at(day(2), 17),
            "end": at(day(2), 18),
            "location": "Поликлиника №202",
        },
        "doctor",
    )

    # Ручные правки вхождений: отмена, перенос с другой аудиторией, заметка к паре
    cal = await _ok(
        await c.get(f"{API}/calendar", params={"from": at(TODAY, 0), "to": at(day(14), 0)})
    )

    def occurrence(title: str, d: date, h: int, m: int = 0) -> str:
        start = datetime.fromisoformat(at(d, h, m))
        found = [
            e["id"]
            for e in cal["events"]
            if e["title"] == title and datetime.fromisoformat(e["start"]) == start
        ]
        assert len(found) == 1, (title, d, found)
        return str(found[0])

    st.ids["cancelled_class"] = occurrence("Климатология", day(7), 9)
    await _ok(await c.delete(f"{API}/events/{st['cancelled_class']}"), 204)
    st.ids["moved_class"] = occurrence("Математический анализ", day(2), 10, 45)
    await patch(
        f"/events/{st['moved_class']}",
        {"start": at(day(2), 13), "end": at(day(2), 14, 35), "location": "П-13"},
    )
    st.ids["noted_class"] = occurrence("Английский язык", day(1), 14, 45)
    await patch(f"/events/{st['noted_class']}", {"note": "Эссе распечатать\nСловарь"})

    # ---------- задания ----------
    essay = await post(
        "/tasks",
        {
            "title": "Реферат по климатологии",
            "task_type_id": task_types["essay"],
            "area_id": clim,
            "deadline": at(day(11), 23, 59),
            "priority": "high",
        },
        "essay",
    )

    async def step(task: dict[str, Any], key: str, **body: Any) -> str:
        data = await post(f"/tasks/{task['id']}/subtasks", body, key)
        return str(data["id"])

    topic = await step(essay, "essay_topic", title="Выбрать тему", estimate_min=30)
    lit = await step(
        essay,
        "essay_lit",
        title="Подобрать литературу в библиотеке",
        estimate_min=60,
        action_type_id=types["institutions"],
    )
    draft = await step(
        essay, "essay_draft", title="Написать черновик", estimate_min=180, depends_on=[lit]
    )
    await step(
        essay,
        "essay_agree",
        title="Согласовать план с преподавателем",
        estimate_min=15,
        action_type_id=types["people"],
    )
    await step(essay, "essay_final", title="Оформить и сдать", estimate_min=60, depends_on=[draft])
    # Сделано дольше, чем думала → калибровка (essay, study)
    await patch(f"/subtasks/{topic}", {"status": "done", "actual_feel": "slower"})

    await post(
        "/tasks",
        {
            "title": "ДЗ по матану: ряды",
            "task_type_id": task_types["homework"],
            "area_id": matan,
            "deadline": at(day(2), 23, 59),
            "estimate_min": 90,
        },
        "homework",
    )

    lab = await post(
        "/tasks",
        {
            "title": "Лабораторная №3",
            "task_type_id": task_types["lab"],
            "area_id": fiz,
            "deadline": at(day(17), 18),
            "description": "Обработка радиозондовых данных",
        },
        "lab",
    )
    await step(lab, "lab_data", title="Обработать данные", estimate_min=90)
    lab_report = await step(lab, "lab_report", title="Написать отчёт", estimate_min=60)
    # Шаг поставлен руками → закреплённый блок
    await _ok(
        await c.post(
            f"{API}/subtasks/{lab_report}/schedule",
            json={"start": at(day(1), 16, 30), "end": at(day(1), 18)},
        )
    )

    reading = await post(
        "/tasks",
        {
            "title": "Прочитать главу 4 «Климат и циркуляция»",
            "task_type_id": task_types["reading"],
            "area_id": clim,
            "deadline": at(day(6), 23, 59),
            "estimate_min": 60,
        },
        "reading",
    )
    await patch(f"/tasks/{reading['id']}", {"deadline_buffer_days": 0})

    # ---------- проекты ----------
    vkr = await post(
        "/projects",
        {
            "title": "ВКР: блокинги над Европой",
            "deadline": "2027-05-31",
            "weekly_norm_min": 240,
            "contacts": [{"name": "Петрова Е. В.", "role": "научный руководитель"}],
        },
        "vkr",
    )
    await post(
        f"/projects/{vkr['id']}/milestones",
        {"title": "Обзор литературы", "date": "2026-12-20"},
        "ms_review",
    )
    await post(
        "/tasks",
        {
            "title": "Глава 1: обзор",
            "project_id": vkr["id"],
            "deadline": at(day(20), 23, 59),
            "subtasks": [
                {"title": "Собрать статьи", "estimate_min": 120},
                {"title": "Написать раздел 1.1", "estimate_min": 180},
            ],
        },
        "chapter",
    )
    labwork = await post(
        "/projects",
        {"title": "Работа в лаборатории", "category_id": cats["work"]},
        "labwork",
    )
    work = await post(
        "/task-types",
        {
            "name": "Задание с работы",
            "icon": "briefcase",
            "deadline_rule": {"kind": "days", "days": 14},
            "default_project_id": labwork["id"],
            "default_category_id": cats["work"],
        },
        "tt_work",
    )
    await post(
        "/tasks",
        {
            "title": "Обработать данные за ноябрь",
            "task_type_id": work["id"],
            "issued_at": "2026-11-25",
        },
        "work_task",
    )
    await post(
        "/tasks",
        {
            "title": "Встреча с научруком",
            "action_type_id": types["people"],
            "recurrence": "FREQ=WEEKLY;BYDAY=TH",
            "recurrence_start": "2026-11-26",
            "estimate_min": 60,
            "project_id": vkr["id"],
        },
        "meeting",
    )

    # ---------- долгий ящик ----------
    books = await post(
        "/backlog",
        {
            "title": "Сдать книги в библиотеку",
            "estimate_min": 30,
            "days_event_type_id": event_types["class"],
        },
        "books",
    )
    mfc = await post(
        "/backlog",
        {
            "title": "Продлить студенческий",
            "action_type_id": types["institutions"],
            "estimate_min": 60,
            "conditions": ["weekday_daytime"],
            "hours_action_type_id": types["institutions"],
            "desired_by": "2026-12-15",
        },
        "mfc",
    )
    await post("/backlog", {"title": "Разобрать шкаф", "estimate_min": 120}, "closet")
    for item in (books, mfc):
        await put(f"/backlog/{item['id']}/week")

    # ---------- экзамен ----------
    # Экзамен — событие типа «Экзамен» и план подготовки к нему (M20)
    exam = await post(
        "/prep-plans",
        {
            "area_id": clim,
            "event": {"start": at(date(2027, 1, 12), 10), "duration_min": 180, "location": "1801"},
            "start_days_before": 7,
        },
        "exam",
    )
    questions = "\n".join(
        f"{i}. {q}"
        for i, q in enumerate(
            [
                "Климатическая система и её компоненты",
                "Радиационный баланс Земли",
                "Общая циркуляция атмосферы",
                "Муссоны",
                "Классификация климатов Кёппена",
                "Климат России",
                "Парниковый эффект",
                "Модели климата",
            ],
            1,
        )
    )
    await _ok(await c.post(f"{API}/prep-plans/{exam['id']}/items/import", json={"text": questions}))
    await _ok(await c.post(f"{API}/prep-plans/{exam['id']}/enable"))

    # ---------- разовый лимит дня ----------
    await put(f"/load-budgets/{budget['id']}/overrides/{day(3).isoformat()}", {"minutes": 480})

    # ---------- конспект и литература (для счётчиков migrate-check) ----------
    await post(
        "/notes",
        {
            "title": "Лекция 12: муссоны",
            "area_id": clim,
            "body_md": "Муссон: $\\Delta T$ суша/океан",
        },
        "note",
    )
    await post(
        "/sources",
        {"title": "Метеорология и климатология", "author": "Хромов С. П.", "area_id": clim},
        "source",
    )

    # created_at ставит БД (now()) — фиксируем, иначе возраст дел в ящике плывёт.
    # Ключи сида у типов задач — как после миграции M15.1 (по ним словарь быстрого
    # ввода находит тип до M21.1); через API ключ не задаётся.
    async with session_factory() as db:
        for key in (*(t[0] for t in TASK_TYPES), "work"):
            await db.execute(
                text("UPDATE task_types SET key = :key WHERE id = :id"),
                {"key": key, "id": st[f"tt_{key}"]},
            )
        for key, created in (
            ("closet", date(2026, 9, 10)),
            ("books", date(2026, 10, 20)),
            ("mfc", date(2026, 11, 16)),
        ):
            await db.execute(
                text("UPDATE backlog_items SET created_at = :at WHERE id = :id"),
                {"at": wall_to_utc(created, time(12), TZ), "id": st[key]},
            )
        await db.commit()
    return st
