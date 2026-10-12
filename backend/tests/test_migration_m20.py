"""Миграции M20 «до/после» на фикстуре студентки: экзамен → план подготовки к событию.

Отдельная БД: схема до ревизии фикстуры → строки фикстуры → `upgrade head` → план
ссылается на событие экзамена, пункты и дни — на план, у событий новые источники →
`downgrade` до ревизии фикстуры → экзамены, вопросы, дни и источники событий те же.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command

from app.core.config import settings
from scripts.migrate_check import FIXTURE, _alembic, fixture_revision, load_fixture, recreate

from .test_migration_m15 import STUDENT, query, value

SNAPSHOT = {
    "exams": "SELECT id, user_id, subject_id AS area_id, title, starts_at, duration_min, "
    "location, note, prep_days, learn_min, review_min, run_min, plan_enabled, deleted_at "
    "FROM exams",
    "exam_questions": "SELECT id, exam_id, number, text, status, learned_on, reviews_done "
    "FROM exam_questions",
    "exam_sessions": "SELECT id, exam_id, date, kind, question_ids, minutes, status "
    "FROM exam_sessions",
    "events": "SELECT id, kind, source_type, source_id FROM events",
}


@pytest.fixture(scope="module")
def db() -> Iterator[str]:
    name = f"{settings.POSTGRES_DB}_m20"
    original = settings.POSTGRES_DB
    recreate(name)
    settings.POSTGRES_DB = name
    try:
        command.upgrade(_alembic(), fixture_revision(FIXTURE))
        load_fixture(name, FIXTURE)
        yield name
    finally:
        settings.POSTGRES_DB = original
        recreate(name)


def snapshot(db: str) -> dict[str, list[dict[str, Any]]]:
    return {t: [dict(r) for r in query(db, f"{sql} ORDER BY id")] for t, sql in SNAPSHOT.items()}


def test_upgrade_then_downgrade(db: str):
    before = snapshot(db)
    [exam] = before["exams"]
    exam_event = next(e for e in before["events"] if e["source_type"] == "exam")
    sessions = len(before["exam_sessions"])
    assert sessions
    assert before["exam_questions"]

    cfg = _alembic()
    command.upgrade(cfg, "head")

    [plan] = query(
        db,
        "SELECT id, event_id, area_id, date, strategy, start_days_before, enabled, learn_min "
        "FROM prep_plans WHERE user_id = $1",
        STUDENT,
    )
    assert plan["id"] == exam["id"]
    assert plan["event_id"] == exam_event["id"]
    assert (plan["area_id"], plan["date"], plan["strategy"]) == (exam["area_id"], None, "spaced")
    assert (plan["start_days_before"], plan["enabled"]) == (exam["prep_days"], True)
    assert value(db, "SELECT count(*) FROM prep_items WHERE plan_id = $1", plan["id"]) == len(
        before["exam_questions"]
    )
    assert (
        value(db, "SELECT count(*) FROM prep_sessions WHERE plan_id = $1", plan["id"]) == sessions
    )
    kinds = {r["source_type"] for r in query(db, "SELECT DISTINCT source_type FROM events")}
    assert "exam" not in kinds
    assert "exam_session" not in kinds
    assert "prep_session" in kinds
    event = query(db, "SELECT source_type, source_id FROM events WHERE id = $1", exam_event["id"])
    assert dict(event[0]) == {"source_type": None, "source_id": None}
    assert value(db, "SELECT to_regclass('exams')") is None
    columns = {
        r["column_name"]
        for r in query(
            db,
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'prep_plans'",
        )
    }
    assert not {"starts_at", "duration_min", "location"} & columns

    # ---------- downgrade: Part 1 строка в строку ----------
    command.downgrade(cfg, fixture_revision(FIXTURE))
    after = snapshot(db)
    for table in SNAPSHOT:
        assert after[table] == before[table], table
    assert value(db, "SELECT to_regclass('prep_plans')") is None

    command.upgrade(cfg, "head")
    assert value(db, "SELECT count(*) FROM prep_plans") == 1
