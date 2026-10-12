"""Миграции M17 «до/после» на фикстуре студентки (tests/fixtures/student.sql).

Отдельная БД: схема до ревизии фикстуры → строки фикстуры (+ семестр без сессии
только с субботними звонками, его пара и удалённый ежемесячный повтор) → `upgrade
head` → проверки типов занятости, периодов, сеток, правил и событий → `downgrade` до
ревизии фикстуры → данные Part 1 те же, что были (строка в строку).
"""

import json
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import asyncpg
import pytest
from alembic import command

from app.core.config import settings
from app.domain.recurrence import DateRange, PeriodSpec, cycle_week
from scripts.migrate_check import (
    FIXTURE,
    _alembic,
    _run,
    fixture_revision,
    load_fixture,
    recreate,
)

from .test_migration_m15 import STUDENT, query, value

SPRING = "7d1c3a2b-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
SPRING_RULE = "8e2d4b3c-5f6a-4b7c-9d8e-0f1a2b3c4d5e"
MONTHLY = "9f3e5c4d-6a7b-4c8d-0e9f-1a2b3c4d5e6f"

# Что сравнивается до upgrade и после downgrade (без created_at / updated_at)
SNAPSHOT = {
    "semesters": "SELECT id, name, start_date, classes_end, session_start, session_end, "
    "first_week_parity, deleted_at FROM semesters",
    "bell_schedules": "SELECT id, semester_id, weekday, slots, deleted_at FROM bell_schedules",
    "class_rules": "SELECT id, semester_id, subject_id, weekday, pair_number, start_time, "
    "end_time, parity, class_type, location, teacher, valid_from, valid_to, deleted_at "
    "FROM class_rules",
    "recurring_events": "SELECT id, kind, title, rrule, start_date, until, start_time, "
    "end_time, location, color, note, deleted_at FROM recurring_events",
    "events": "SELECT id, kind, class_type, teacher, pair_number, template_type, template_id, "
    'occurrence_date, start, "end", location FROM events',
    "days_off": "SELECT id, date_from, date_to, title FROM days_off",
    # Порядок чипов меняет откат M15 («часы учреждений» дописываются в конец)
    "backlog_items": "SELECT id, (SELECT jsonb_agg(c ORDER BY c) FROM "
    "jsonb_array_elements_text(conditions) c) AS conditions FROM backlog_items",
    "reminders": "SELECT id, kind, dedupe_key FROM reminders",
    "users": "SELECT id, settings FROM users",
}


@pytest.fixture(scope="module")
def db() -> Iterator[str]:
    name = f"{settings.POSTGRES_DB}_m17"
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
    await conn.execute(
        "INSERT INTO semesters (id, user_id, name, start_date, classes_end, first_week_parity) "
        "VALUES ($1, $2, 'Весна 2027', '2027-02-08', '2027-05-30', 'even')",
        SPRING,
        STUDENT,
    )
    await conn.execute(
        "INSERT INTO bell_schedules (id, user_id, semester_id, weekday, slots) "
        "VALUES (gen_random_uuid(), $1, $2, 6, $3::jsonb)",
        STUDENT,
        SPRING,
        json.dumps([{"number": 1, "start": "10:00", "end": "11:30"}]),
    )
    subject = await conn.fetchval("SELECT id FROM subjects WHERE name = 'Английский язык'")
    await conn.execute(
        "INSERT INTO class_rules (id, user_id, semester_id, subject_id, weekday, pair_number, "
        "parity, class_type, location) VALUES ($1, $2, $3, $4, 6, 1, 'odd', 'lab', '516')",
        SPRING_RULE,
        STUDENT,
        SPRING,
        subject,
    )
    await conn.execute(
        "INSERT INTO recurring_events (id, user_id, kind, title, rrule, start_date, start_time, "
        "end_time, note, deleted_at) VALUES ($1, $2, 'personal', 'Клуб', "
        "'FREQ=MONTHLY;BYDAY=2TU', '2026-09-01', '19:00', '21:00', 'взять книгу', now())",
        MONTHLY,
        STUDENT,
    )


def snapshot(db: str) -> dict[str, list[dict[str, Any]]]:
    return {
        table: [dict(r) for r in query(db, f"{sql} ORDER BY id")] for table, sql in SNAPSHOT.items()
    }


def old_parity(d: date, start: date, first: str) -> str:
    """`week_parity` Part 1: неделя начала — first, дальше чередуется."""
    weeks = ((d - timedelta(days=d.weekday())) - (start - timedelta(days=start.weekday()))).days
    if (weeks // 7) % 2 == 0:
        return first
    return "even" if first == "odd" else "odd"


def test_upgrade_then_downgrade(db: str):
    before = snapshot(db)
    old_rules = {str(r["id"]): r for r in before["class_rules"]}
    old_kinds: dict[str, int] = {}
    for e in before["events"]:
        old_kinds[e["kind"]] = old_kinds.get(e["kind"], 0) + 1
    assert all(old_kinds.get(k) for k in ("class", "rest", "exam"))

    cfg = _alembic()
    command.upgrade(cfg, "head")

    # ---------- M17.1: типы занятости ----------
    types = query(
        db,
        "SELECT id, key, name, name_plural, buffer_before_min, buffer_after_min, merge_buffers, "
        "remind_before_min, remind_channels, show_now_next, is_rest, supports_prep, "
        "location_label, fields FROM event_types WHERE user_id = $1 ORDER BY position",
        STUDENT,
    )
    assert [(t["key"], t["name"], t["name_plural"]) for t in types] == [
        ("class", "Пара", "Пары"),
        ("personal", "Личное", "Личное"),
        ("rest", "Отдых", "Отдых"),
        ("exam", "Экзамен", "Экзамены"),
    ]
    by_key = {t["key"]: t for t in types}
    cls = by_key["class"]
    # Переопределения студентки: дорога 40 мин, напоминание за 20 мин
    assert (cls["buffer_before_min"], cls["buffer_after_min"], cls["merge_buffers"]) == (
        40,
        40,
        True,
    )
    assert cls["remind_before_min"] == 20
    assert json.loads(cls["remind_channels"]) == ["push", "telegram"]
    assert (cls["show_now_next"], cls["location_label"]) == (True, "ауд.")
    assert [(f["id"], f["type"], f["show_in_reminder"]) for f in json.loads(cls["fields"])] == [
        ("class_type", "select", True),
        ("teacher", "text", True),
    ]
    assert by_key["rest"]["is_rest"]
    assert not by_key["personal"]["is_rest"]
    assert by_key["exam"]["supports_prep"]
    assert by_key["exam"]["show_now_next"]
    assert by_key["personal"]["remind_before_min"] is None
    users = int(str(value(db, "SELECT count(*) FROM users")))
    assert value(db, "SELECT count(*) FROM event_types") == 4 * users

    # ---------- события ----------
    events = {str(r["id"]): r for r in query(db, "SELECT * FROM events")}
    kinds: dict[str, int] = {}
    for e in events.values():
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    hard = sum(old_kinds.get(k, 0) for k in ("class", "personal", "rest", "exam"))
    assert kinds["busy"] == hard
    assert kinds["prep"] == old_kinds["exam_prep"]
    assert not kinds.keys() & {"class", "exam_prep"}
    type_key = {t["id"]: t["key"] for t in types}
    for old in before["events"]:
        new = events[str(old["id"])]
        if old["kind"] in ("class", "personal", "rest", "exam"):
            assert type_key[new["event_type_id"]] == old["kind"]
        assert new["slot"] == old["pair_number"]
    clim = next(
        e for e in events.values() if e["title"] == "Климатология" and e["location"] == "1801"
    )
    assert json.loads(clim["fields"]) == {"class_type": "лекция", "teacher": "Иванов П. С."}
    sat = next(e for e in events.values() if e["title"] == "Спутниковая метеорология")
    assert json.loads(sat["fields"]) == {}  # class_type other — без значения
    columns = {
        r["column_name"]
        for r in query(
            db, "SELECT column_name FROM information_schema.columns WHERE table_name = 'events'"
        )
    }
    assert not columns & {"class_type", "teacher", "pair_number"}

    # ---------- ящик и напоминания ----------
    [books] = query(
        db,
        "SELECT conditions, days_event_type_id FROM backlog_items "
        "WHERE title = 'Сдать книги в библиотеку'",
    )
    assert json.loads(books["conditions"]) == []
    assert books["days_event_type_id"] == cls["id"]
    assert value(db, "SELECT count(*) FROM reminders WHERE kind = 'before_class'") == 0
    keys = [
        r["dedupe_key"]
        for r in query(db, "SELECT dedupe_key FROM reminders WHERE kind = 'before_event'")
    ]
    assert keys
    assert all(k.startswith("before_event:") for k in keys)

    # ---------- настройки ----------
    stored = json.loads(str(value(db, "SELECT settings FROM users WHERE id = $1", STUDENT)))
    assert "travel_buffer_min" not in stored
    assert "before_class" not in stored.get("reminders", {})

    # ---------- M17.2: периоды и сетки ----------
    periods = {
        str(r["id"]): r
        for r in query(
            db,
            "SELECT id, name, start_date, end_date, cycle_weeks, first_cycle_week, pauses "
            "FROM periods",
        )
    }
    fall_old = next(s for s in before["semesters"] if s["name"] == "Осень 2026")
    fall = periods[str(fall_old["id"])]
    assert (fall["end_date"], fall["cycle_weeks"], fall["first_cycle_week"]) == (
        date(2027, 1, 25),
        2,
        1,
    )
    assert json.loads(fall["pauses"]) == [
        {"from": "2026-12-28", "to": "2027-01-08", "title": "Перерыв"},
        {"from": "2027-01-09", "to": "2027-01-25", "title": "Сессия"},
    ]
    spring = periods[SPRING]
    assert (spring["end_date"], spring["first_cycle_week"], json.loads(spring["pauses"])) == (
        date(2027, 5, 30),
        2,
        [],
    )
    # DoD M17.2: неделя цикла совпадает со старой чётностью на всём семестре
    for old in before["semesters"]:
        new = periods[str(old["id"])]
        spec = PeriodSpec(
            new["start_date"], new["end_date"], new["cycle_weeks"], new["first_cycle_week"]
        )
        for d in DateRange(old["start_date"], new["end_date"]).days():
            parity = old_parity(d, old["start_date"], old["first_week_parity"])
            assert cycle_week(d, spec) == (1 if parity == "odd" else 2), (old["name"], d)

    grids = query(db, "SELECT id, period_id, name, weekday, slots FROM slot_grids")
    assert {g["name"] for g in grids} == {"Звонки"}
    heads = {g["period_id"]: g for g in grids if g["weekday"] is None}
    assert set(heads) == {fall_old["id"], SPRING} or set(map(str, heads)) == {
        str(fall_old["id"]),
        SPRING,
    }
    spring_head = next(g for g in heads.values() if str(g["period_id"]) == SPRING)
    assert json.loads(spring_head["slots"]) == []  # добавлена пустая общая строка
    assert value(db, "SELECT count(*) FROM days_off WHERE period_id IS NOT NULL") == 0

    # ---------- M17.4: правила расписания ----------
    rules = {
        str(r["id"]): r
        for r in query(
            db,
            "SELECT id, event_type_id, area_id, period_id, slot_grid_id, pattern, start_time, "
            "end_time, slot_from, valid_from, valid_to, title, location, fields, note, "
            "deleted_at FROM schedule_rules",
        )
    }
    assert set(rules) == set(old_rules) | {str(r["id"]) for r in before["recurring_events"]}
    for rule_id, old in old_rules.items():
        new = rules[rule_id]
        assert new["event_type_id"] == cls["id"]
        assert new["area_id"] == old["subject_id"]
        assert new["period_id"] == old["semester_id"]
        mask = {"all": None, "odd": [1], "even": [2]}[old["parity"]]
        assert json.loads(new["pattern"]) == {
            "kind": "weekly",
            "weekdays": [old["weekday"]],
            "cycle_weeks": mask,
        }
        assert new["slot_from"] == old["pair_number"]
        assert (new["start_time"], new["location"]) == (old["start_time"], old["location"])
        if old["pair_number"] and old["start_time"] is None:
            assert new["slot_grid_id"] == heads[new["period_id"]]["id"]
    pool = next(r for r in rules.values() if r["title"] == "Бассейн")
    assert json.loads(pool["pattern"]) == {
        "kind": "weekly",
        "weekdays": [2, 4],
        "cycle_weeks": None,
    }
    assert (pool["event_type_id"], pool["valid_from"]) == (
        by_key["personal"]["id"],
        date(2026, 9, 1),
    )
    walk = next(r for r in rules.values() if r["title"] == "Прогулка")
    assert walk["event_type_id"] == by_key["rest"]["id"]
    monthly = rules[MONTHLY]
    assert json.loads(monthly["pattern"]) == {"kind": "rrule", "rrule": "FREQ=MONTHLY;BYDAY=2TU"}
    assert monthly["deleted_at"] is not None
    assert monthly["note"] == "взять книгу"
    # Вхождения остались привязаны к своим правилам
    linked = query(
        db,
        "SELECT e.template_type, r.id IS NOT NULL AS ok FROM events e "
        "LEFT JOIN schedule_rules r ON r.id = e.template_id WHERE e.template_id IS NOT NULL",
    )
    assert linked
    assert all(r["template_type"] == "schedule_rule" for r in linked)
    assert all(r["ok"] for r in linked)
    assert value(db, "SELECT to_regclass('class_rules')") is None
    assert value(db, "SELECT to_regclass('recurring_events')") is None
    assert value(db, "SELECT to_regclass('semesters')") is None
    assert value(db, "SELECT to_regclass('bell_schedules')") is None

    # ---------- downgrade: Part 1 строка в строку ----------
    command.downgrade(cfg, fixture_revision(FIXTURE))
    after = snapshot(db)
    for table in SNAPSHOT:
        assert after[table] == before[table], table
    assert value(db, "SELECT to_regclass('event_types')") is None
    assert value(db, "SELECT to_regclass('schedule_rules')") is None

    # И снова вверх — без ошибок
    command.upgrade(cfg, "head")
