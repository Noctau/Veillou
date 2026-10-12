"""Миграция M21.1 «до/после» на фикстуре студентки: слова быстрого ввода Part 1 —
в синонимах её типов действий и задач; downgrade убирает колонки и дописанные слова.
"""

import json
from collections.abc import Iterator

import pytest
from alembic import command

from app.core.config import settings
from scripts.migrate_check import FIXTURE, _alembic, fixture_revision, load_fixture, recreate

from .student import M21, _migration
from .test_migration_m15 import STUDENT, query, value

M21_ABOUT = _migration("m21_about")


@pytest.fixture(scope="module")
def db() -> Iterator[str]:
    name = f"{settings.POSTGRES_DB}_m21"
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


def synonyms(db: str, table: str) -> dict[str, list[str]]:
    rows = query(
        db,
        f"SELECT key, synonyms FROM {table} WHERE user_id = $1 AND key IS NOT NULL",  # noqa: S608
        STUDENT,
    )
    return {r["key"]: json.loads(r["synonyms"]) for r in rows}


def columns(db: str, table: str) -> set[str]:
    rows = query(
        db, "SELECT column_name FROM information_schema.columns WHERE table_name = $1", table
    )
    return {r["column_name"] for r in rows}


def test_upgrade_then_downgrade(db: str):
    cfg = _alembic()
    command.upgrade(cfg, M21.down_revision)
    tasks_before = synonyms(db, "task_types")
    assert "synonyms" not in columns(db, "action_types")

    command.upgrade(cfg, "head")
    actions = synonyms(db, "action_types")
    for key, words in M21.ACTION_WORDS.items():
        assert actions[key] == words, key
    assert actions["study"] == []
    assert {"научрук", "препод*", "деканат"} <= {w for ws in actions.values() for w in ws}
    tasks = synonyms(db, "task_types")
    assert tasks["reading"] == [*tasks_before["reading"], "читать", "прочесть"]
    assert tasks["essay"] == tasks_before["essay"]
    assert value(db, "SELECT count(*) FROM event_types WHERE synonyms <> '[]'") == 0
    # «О себе» — бывшее зашитое описание из промптов (M21.2)
    about = value(db, "SELECT settings->>'about' FROM users WHERE id = $1", STUDENT)
    assert about == M21_ABOUT.ABOUT

    # Повтор upgrade (после downgrade) не дублирует слова
    command.downgrade(cfg, M21.down_revision)
    assert synonyms(db, "task_types") == tasks_before
    assert value(db, "SELECT settings ? 'about' FROM users WHERE id = $1", STUDENT) is False
    assert "synonyms" not in columns(db, "action_types") | columns(db, "event_types")
    command.upgrade(cfg, "head")
    assert synonyms(db, "task_types") == tasks
