"""Миграции M18 «до/после» на фикстуре студентки (tests/fixtures/student.sql).

Отдельная БД: схема до ревизии фикстуры → строки фикстуры (+ пользователь с
полным набором старых настроек дня) → `upgrade head` → режимы «Будни» /
«Выходные», настройки без сна, обеда и рабочих часов, смещения сводки и разбора
→ `downgrade` до ревизии фикстуры → настройки те же, что были.
"""

import json
import uuid
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

OWL = str(uuid.UUID("0b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e"))
OWL_SETTINGS = {
    "sleep": {"start": "02:00", "end": "10:00"},
    "lunch": {"start": "15:00", "end": "15:30"},
    "work_hours": {
        "weekdays": {"start": "11:00", "end": "23:00"},
        "weekends": {"start": "12:00", "end": "20:00"},
    },
    "schedule": {"morning_digest": "10:15", "evening_review": "01:00", "weekly_review": "18:00"},
    "deadline_buffer_days": 2,
}


@pytest.fixture(scope="module")
def db() -> Iterator[str]:
    name = f"{settings.POSTGRES_DB}_m18"
    original = settings.POSTGRES_DB
    recreate(name)
    settings.POSTGRES_DB = name
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
        "INSERT INTO users (id, email, password_hash, timezone, settings) "
        "VALUES ($1, 'owl@example.com', 'x', 'Europe/Moscow', $2::jsonb)",
        OWL,
        json.dumps(OWL_SETTINGS),
    )


def _settings(db: str, user: str) -> dict:
    return json.loads(str(value(db, "SELECT settings FROM users WHERE id = $1", user)))


def _profiles(db: str, user: str) -> list[dict]:
    rows = query(
        db,
        "SELECT p.key, p.name, to_char(p.wake, 'HH24:MI') AS wake, "
        "to_char(p.sleep, 'HH24:MI') AS sleep, to_char(p.lunch_start, 'HH24:MI') AS lunch_start, "
        "to_char(p.lunch_end, 'HH24:MI') AS lunch_end, p.work_windows, p.rest_evening_ok, "
        "p.rest_halfday_ok, p.quiet_follows_sleep, r.kind, r.weekdays "
        "FROM day_profiles p JOIN day_profile_rules r ON r.profile_id = p.id "
        "WHERE p.user_id = $1 ORDER BY p.position",
        user,
    )
    result = []
    for r in rows:
        row = dict(r)
        row["work_windows"] = json.loads(row["work_windows"])
        row["weekdays"] = json.loads(row["weekdays"])
        result.append(row)
    return result


def test_upgrade_then_downgrade(db: str):
    before = {u: _settings(db, u) for u in (STUDENT, OWL)}
    cfg = _alembic()
    command.upgrade(cfg, "head")

    # ---------- режимы ----------
    student = _profiles(db, STUDENT)
    common = {
        "wake": "08:00",
        "sleep": "00:00",
        "lunch_start": "13:00",
        "lunch_end": "14:00",
        "rest_evening_ok": True,
        "quiet_follows_sleep": False,
        "kind": "weekdays",
    }
    assert student == [
        {
            **common,
            "key": "weekdays",
            "name": "Будни",
            "work_windows": [{"start": "09:00", "end": "22:00"}],
            "rest_halfday_ok": False,
            "weekdays": [1, 2, 3, 4, 5],
        },
        {
            **common,
            "key": "weekends",
            "name": "Выходные",
            "work_windows": [{"start": "11:00", "end": "19:00"}],
            "rest_halfday_ok": True,
            "weekdays": [6, 7],
        },
    ]
    owl = _profiles(db, OWL)
    assert [(p["wake"], p["sleep"], p["lunch_start"], p["lunch_end"]) for p in owl] == [
        ("10:00", "02:00", "15:00", "15:30")
    ] * 2
    assert [p["work_windows"] for p in owl] == [
        [{"start": "11:00", "end": "23:00"}],
        [{"start": "12:00", "end": "20:00"}],
    ]
    users = int(str(value(db, "SELECT count(*) FROM users")))
    assert value(db, "SELECT count(*) FROM day_profiles") == 2 * users

    # ---------- настройки ----------
    s = _settings(db, STUDENT)
    assert not {"sleep", "lunch", "work_hours"} & s.keys()
    # сводка в 8:00 = подъём, разбор в 21:30 при отбое 00:00
    assert s["schedule"] == {
        "morning_digest_after_wake_min": 0,
        "evening_review_before_sleep_min": 150,
    }
    s = _settings(db, OWL)
    s.pop("about")  # «о себе» — миграция M21.2
    assert s == {
        "schedule": {
            "morning_digest_after_wake_min": 15,
            "evening_review_before_sleep_min": 60,
            "weekly_review": "18:00",
        },
        "deadline_buffer_days": 2,
    }

    # ---------- downgrade: настройки Part 1 как были ----------
    command.downgrade(cfg, fixture_revision(FIXTURE))
    assert {u: _settings(db, u) for u in (STUDENT, OWL)} == before
    assert value(db, "SELECT to_regclass('day_profiles')") is None

    command.upgrade(cfg, "head")
    assert len(_profiles(db, STUDENT)) == 2
