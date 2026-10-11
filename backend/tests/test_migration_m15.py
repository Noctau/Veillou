"""Миграции M15 «до/после» на фикстуре студентки (tests/fixtures/student.sql).

Отдельная БД: схема до ревизии фикстуры → строки фикстуры (+ шаблон разбивки и
удалённый разовый лимит — их в фикстуре нет) → `upgrade head` → проверки данных →
`downgrade` до ревизии фикстуры → старые колонки и значения на месте.
"""

import json
from collections.abc import Iterator

import asyncpg
import pytest
from alembic import command

from app.core.config import settings
from app.models import User
from app.services.settings import effective_settings
from scripts.migrate_check import (
    FIXTURE,
    _alembic,
    _run,
    fixture_revision,
    load_fixture,
    recreate,
)

STUDENT = "fe2b1e58-b524-4f2a-9148-ad6a2cae10e7"
NAMES = [
    "ДЗ",
    "Доклад",
    "Реферат",
    "Лабораторная",
    "Курсовая",
    "Чтение",
    "Подготовка к экзамену",
    "Задание с работы",
]


@pytest.fixture(scope="module")
def db() -> Iterator[str]:
    name = f"{settings.POSTGRES_DB}_m15"
    original = settings.POSTGRES_DB
    recreate(name)
    settings.POSTGRES_DB = name  # env.py миграций берёт адрес из настроек
    try:
        command.upgrade(_alembic(), fixture_revision(FIXTURE))
        load_fixture(name, FIXTURE)
        _run(_extra_rows, name)
        yield name
    finally:
        settings.POSTGRES_DB = original
        recreate(name)


async def _extra_rows(conn: asyncpg.Connection) -> None:
    steps = [
        {"title": "Найти", "estimate_min": 60, "action_type": "people", "depends_on": []},
        {"title": "Написать", "estimate_min": 90, "action_type": None, "depends_on": [0]},
    ]
    await conn.execute(
        "INSERT INTO breakdown_templates (id, user_id, name, task_type, steps) "
        "VALUES (gen_random_uuid(), $1, 'Реферат', 'essay', $2::jsonb)",
        STUDENT,
        json.dumps(steps),
    )
    await conn.execute(
        "INSERT INTO study_day_limits (id, user_id, date, minutes, deleted_at) "
        "VALUES (gen_random_uuid(), $1, '2026-12-05', 600, now())",
        STUDENT,
    )


def query(db: str, sql: str, *args: object) -> list[asyncpg.Record]:
    async def go(conn: asyncpg.Connection) -> list[asyncpg.Record]:
        return list(await conn.fetch(sql, *args))

    return _run(go, db)


def value(db: str, sql: str, *args: object) -> object:
    rows = query(db, sql, *args)
    return rows[0][0] if rows else None


def test_upgrade_then_downgrade(db: str):
    cfg = _alembic()
    command.upgrade(cfg, "head")

    # ---------- M15.1: типы задач ----------
    types = query(
        db,
        "SELECT id, key, name, synonyms, deadline_rule, default_project_id, default_category_id "
        "FROM task_types WHERE user_id = $1 ORDER BY position",
        STUDENT,
    )
    assert [t["name"] for t in types] == NAMES
    by_key = {t["key"]: t for t in types}
    assert json.loads(by_key["essay"]["synonyms"]) == ["реферат", "эссе"]
    work = by_key["work"]
    assert json.loads(work["deadline_rule"]) == {"kind": "days", "days": 14}
    assert work["default_project_id"] == value(
        db, "SELECT id FROM projects WHERE title = 'Работа в лаборатории'"
    )
    assert work["default_category_id"] == value(
        db, "SELECT id FROM categories WHERE user_id = $1 AND key = 'work'", STUDENT
    )
    tasks = {
        r["title"]: r["key"]
        for r in query(
            db,
            "SELECT t.title, tt.key FROM tasks t LEFT JOIN task_types tt "
            "ON tt.id = t.task_type_id WHERE t.user_id = $1",
            STUDENT,
        )
    }
    assert tasks["Реферат по климатологии"] == "essay"
    assert tasks["Лабораторная №3"] == "lab"
    assert tasks["Обработать данные за ноябрь"] == "work"  # бывшее «задание с работы»
    assert tasks["Глава 1: обзор"] is None  # other → без типа
    calibration = query(
        db,
        "SELECT tt.key AS task_type, a.key AS action_type FROM calibrations c "
        "JOIN task_types tt ON tt.id = c.task_type_id "
        "JOIN action_types a ON a.id = c.action_type_id",
    )
    assert [(r["task_type"], r["action_type"]) for r in calibration] == [("essay", "study")]
    template = query(db, "SELECT task_type_id, steps FROM breakdown_templates")[0]
    assert template["task_type_id"] == by_key["essay"]["id"]
    people = str(value(db, "SELECT id FROM action_types WHERE key = 'people'"))
    steps = json.loads(template["steps"])
    assert [s["action_type_id"] for s in steps] == [people, None]
    assert all("action_type" not in s for s in steps)

    # ---------- M15.2: типы действий ----------
    morning = query(db, "SELECT key FROM action_types WHERE prefer_morning")
    assert [r["key"] for r in morning] == ["people"]
    raw = value(db, "SELECT settings FROM users WHERE id = $1", STUDENT)
    user_settings = json.loads(str(raw))
    study = str(value(db, "SELECT id FROM action_types WHERE key = 'study'"))
    assert user_settings["default_action_type_id"] == study
    assert "study_limit_min_per_day" not in user_settings
    assert effective_settings(User(settings=user_settings)).default_action_type_id
    mfc = query(
        db,
        "SELECT b.conditions, a.key FROM backlog_items b "
        "JOIN action_types a ON a.id = b.hours_action_type_id",
    )
    assert len(mfc) == 1
    assert json.loads(mfc[0]["conditions"]) == ["weekday_daytime"]
    assert mfc[0]["key"] == "institutions"

    # ---------- M15.3: лимиты ----------
    budgets = query(db, "SELECT id, name, minutes_per_day FROM load_budgets")
    assert [(b["name"], b["minutes_per_day"]) for b in budgets] == [("Учёба", 300)]
    members = query(
        db,
        "SELECT a.key FROM load_budget_members m JOIN action_types a ON a.id = m.action_type_id",
    )
    assert [m["key"] for m in members] == ["study"]
    overrides = query(db, "SELECT date::text, minutes FROM budget_day_overrides ORDER BY date")
    assert [(o["date"], o["minutes"]) for o in overrides] == [("2026-12-03", 480)]
    assert value(db, "SELECT to_regclass('study_day_limits')") is None

    # ---------- downgrade: старое на месте ----------
    command.downgrade(cfg, fixture_revision(FIXTURE))
    old = {
        r["title"]: r["task_type"]
        for r in query(db, "SELECT title, task_type FROM tasks WHERE user_id = $1", STUDENT)
    }
    assert old["Реферат по климатологии"] == "essay"
    assert old["Глава 1: обзор"] == "other"
    assert old["Обработать данные за ноябрь"] == "other"
    work_default = query(db, "SELECT title FROM projects WHERE is_work_default")
    assert [r["title"] for r in work_default] == ["Работа в лаборатории"]
    limits = query(db, "SELECT date::text, minutes FROM study_day_limits")
    assert [(r["date"], r["minutes"]) for r in limits] == [("2026-12-03", 480)]
    raw = value(db, "SELECT settings FROM users WHERE id = $1", STUDENT)
    old_settings = json.loads(str(raw))
    assert old_settings["study_limit_min_per_day"] == 300
    assert "default_action_type_id" not in old_settings
    conditions = value(db, "SELECT conditions FROM backlog_items WHERE title LIKE 'Продлить%'")
    assert set(json.loads(str(conditions))) == {"weekday_daytime", "institution_hours"}
    calibration = query(db, "SELECT task_type, action_type FROM calibrations")
    assert [(r["task_type"], r["action_type"]) for r in calibration] == [("essay", "study")]
    steps = json.loads(str(value(db, "SELECT steps FROM breakdown_templates")))
    assert [s["action_type"] for s in steps] == ["people", None]
    assert value(db, "SELECT task_type FROM breakdown_templates") == "essay"
