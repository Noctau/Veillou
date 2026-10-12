"""SQL-фикстура студентки для `make migrate-check` (M14.2).

Фикстура — «старые данные» на ревизии, где её сняли: каждая будущая миграция
поднимает её до head. Поэтому её не пересобирают без нужды — пересборка на новой
ревизии перестаёт проверять миграции до неё. Пересобрать: `make migrate-fixture`
(WRITE_MIGRATION_FIXTURE=1). Без флага тест только проверяет, что фикстура на месте.
"""

import json
import os
import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import Base, session_factory
from app.models import User
from app.services.reminders import sync_user_reminders
from app.services.replan import ReplanService

from .student import NOW, build_student

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURE = BACKEND_DIR / "tests" / "fixtures" / "student.sql"
REVISION_RE = re.compile(r"^-- revision: (\w+)$", re.MULTILINE)
# Служебное и секреты: сессии, коды привязки, попытки входа, подписки браузера
SKIP_TABLES = {"sessions", "telegram_link_codes", "login_failures", "push_subscriptions"}
# Хэш пароля фикстуре не нужен (и не должен выглядеть как секрет в репозитории)
PLACEHOLDERS = {("users", "password_hash"): "fixture-no-login"}


def _scripts() -> ScriptDirectory:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(cfg)


def test_fixture_revision_is_known():
    match = REVISION_RE.search(FIXTURE.read_text())
    assert match, "в фикстуре нет строки «-- revision: …»"
    assert _scripts().get_revision(match.group(1)) is not None


@pytest.mark.skipif(os.environ.get("WRITE_MIGRATION_FIXTURE") != "1", reason="make migrate-fixture")
async def test_write_fixture(clock, auth_client: AsyncClient, user):
    await build_student(auth_client)
    # Как в жизни: план применён, напоминания собраны
    async with session_factory() as db:
        svc = ReplanService(db, await db.get(User, user.id), NOW)
        rev = await svc.preview(force=True)
        assert rev is not None
        await svc.apply(rev.id)
    async with session_factory() as db:
        await sync_user_reminders(db, user.id, NOW)
    parts: list[str] = []
    async with session_factory() as db:
        revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
        generated = set(
            (
                await db.execute(
                    text(
                        "SELECT table_name, column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND is_generated = 'ALWAYS'"
                    )
                )
            ).all()
        )
        for table in Base.metadata.sorted_tables:
            if table.name in SKIP_TABLES:
                continue
            order = "id" if "id" in table.columns else "1"
            rows = [
                json.loads(raw)
                for raw in await db.scalars(
                    text(f'SELECT row_to_json(t)::text FROM "{table.name}" t ORDER BY {order}')  # noqa: S608
                )
            ]
            if not rows:
                continue
            for row in rows:
                for (name, column), value in PLACEHOLDERS.items():
                    if name == table.name and column in row:
                        row[column] = value
            columns = ", ".join(
                f'"{c.name}"' for c in table.columns if (table.name, c.name) not in generated
            )
            data = ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
            parts.append(
                f'INSERT INTO "{table.name}" ({columns})\n'
                f'SELECT {columns} FROM json_populate_recordset(NULL::"{table.name}", $json$[\n'
                f"{data}\n]$json$);"
            )
    header = (
        "-- Фикстура «студентка» (tests/student.py) для make migrate-check (M14.2).\n"
        "-- Сгенерирована make migrate-fixture; данные — до применения миграций после ревизии.\n"
        f"-- revision: {revision}\n"
    )
    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_text(header + "\n" + "\n\n".join(parts) + "\n")
