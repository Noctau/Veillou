"""Миграции M16 «до/после» на фикстуре студентки (tests/fixtures/student.sql).

Отдельная БД: схема до ревизии фикстуры → строки фикстуры (+ предмет без контроля
с «грязным» контактом преподавателя) → `upgrade head` → проверки сфер →
`downgrade` до ревизии фикстуры → предметы и ссылки на них на месте.
"""

import json
from collections.abc import Iterator

import asyncpg
import pytest
from alembic import command

from app.core.config import settings
from scripts.migrate_check import (
    FIXTURE,
    _alembic,
    _run,
    fixture_revision,
    load_fixture,
    recreate,
)

from .test_migration_m15 import STUDENT, query, value

EXTRA = "0b9e1f3c-6c43-4d2a-9d0e-6a3f1c2b7e01"
REFERRERS = ("events", "tasks", "notes", "sources", "exams", "class_rules")


@pytest.fixture(scope="module")
def db() -> Iterator[str]:
    name = f"{settings.POSTGRES_DB}_m16"
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
    teachers = [
        {"name": "Петров", "role": "", "contact": "+7 900 123-45-67, ауд. 1801; https://t.me/p"}
    ]
    await conn.execute(
        "INSERT INTO subjects (id, user_id, name, color, control_form, teachers, links, "
        "synonyms, notes) VALUES ($1, $2, 'Физкультура', '#000000', 'none', $3::jsonb, "
        "'[]'::jsonb, '[]'::jsonb, '')",
        EXTRA,
        STUDENT,
        json.dumps(teachers, ensure_ascii=False),
    )


def references(db: str, column: str) -> dict[str, int]:
    return {
        t: int(str(value(db, f"SELECT count({column}) FROM {t}")))  # noqa: S608
        for t in REFERRERS
    }


def test_upgrade_then_downgrade(db: str):
    before = references(db, "subject_id")
    assert all(before[t] for t in ("tasks", "class_rules", "events"))
    clim_id = value(db, "SELECT id FROM subjects WHERE name = 'Климатология'")

    cfg = _alembic()
    command.upgrade(cfg, "head")

    # ---------- типы сфер ----------
    types = query(
        db, "SELECT id, user_id, key, name, name_plural, fields, sections FROM area_types"
    )
    assert len(types) == int(str(value(db, "SELECT count(*) FROM users")))
    subject = next(t for t in types if str(t["user_id"]) == STUDENT)
    assert (subject["key"], subject["name"], subject["name_plural"]) == (
        "subject",
        "Предмет",
        "Предметы",
    )
    fields = json.loads(subject["fields"])
    assert [(f["id"], f["type"], f["multiple"]) for f in fields] == [
        ("teachers", "contact", True),
        ("control_form", "select", False),
        ("links", "link", True),
    ]
    assert fields[1]["options"] == ["Экзамен", "Зачёт", "Дифзачёт", "Курсовая"]
    assert json.loads(subject["sections"]) == ["schedule", "tasks", "notes", "materials", "prep"]

    # ---------- сферы ----------
    assert value(db, "SELECT to_regclass('subjects')") is None
    areas = {
        r["name"]: r
        for r in query(
            db, "SELECT id, name, area_type_id, period_id, fields, archived_at FROM areas"
        )
    }
    assert len(areas) == 7
    assert all(a["area_type_id"] == subject["id"] for a in areas.values())
    assert all(a["archived_at"] is None for a in areas.values())
    clim = areas["Климатология"]
    assert clim["id"] == clim_id
    assert clim["period_id"] is not None
    assert json.loads(clim["fields"]) == {
        "teachers": [
            {"name": "Иванов Пётр Сергеевич", "role": "лектор", "email": "ivanov@example.com"},
            {"name": "Смирнова Анна", "role": "семинарист"},
        ],
        "control_form": "Экзамен",
        "links": [{"title": "Курс на сайте кафедры", "url": "https://example.com/clim"}],
    }
    assert json.loads(areas["Математический анализ"]["fields"]) == {"control_form": "Дифзачёт"}
    assert json.loads(areas["Физкультура"]["fields"]) == {
        "teachers": [
            {
                "name": "Петров",
                "phone": "+7 900 123-45-67",
                "link": "https://t.me/p",
                "note": "ауд. 1801",
            }
        ]
    }
    columns = {
        r["column_name"]
        for r in query(
            db,
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'areas'",
        )
    }
    assert not columns & {"teachers", "control_form", "links", "semester_id"}

    # ---------- ссылки ----------
    assert references(db, "area_id") == before
    assert value(db, "SELECT count(area_id) FROM projects") == 0
    rule_areas = value(
        db,
        "SELECT count(*) FROM class_rules r JOIN areas a ON a.id = r.area_id "
        "WHERE a.name = 'Климатология'",
    )
    assert rule_areas

    # ---------- downgrade: старое на месте ----------
    command.downgrade(cfg, fixture_revision(FIXTURE))
    assert value(db, "SELECT to_regclass('areas')") is None
    assert value(db, "SELECT to_regclass('area_types')") is None
    assert references(db, "subject_id") == before
    old = {
        r["name"]: r
        for r in query(db, "SELECT name, semester_id, control_form, teachers, links FROM subjects")
    }
    assert old["Климатология"]["control_form"] == "exam"
    assert old["Математический анализ"]["control_form"] == "graded_credit"
    assert old["Физкультура"]["control_form"] == "none"
    assert old["Климатология"]["semester_id"] is not None
    assert json.loads(old["Климатология"]["teachers"]) == [
        {"name": "Иванов Пётр Сергеевич", "role": "лектор", "contact": "ivanov@example.com"},
        {"name": "Смирнова Анна", "role": "семинарист", "contact": ""},
    ]
    assert json.loads(old["Климатология"]["links"]) == [
        {"title": "Курс на сайте кафедры", "url": "https://example.com/clim"}
    ]
    # Части контакта собираются обратно (порядок — email, телефон, ссылка, остальное)
    assert json.loads(old["Физкультура"]["teachers"]) == [
        {"name": "Петров", "role": "", "contact": "+7 900 123-45-67, https://t.me/p, ауд. 1801"}
    ]
