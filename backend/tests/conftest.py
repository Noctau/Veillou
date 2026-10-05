import asyncio
import os

# Тесты всегда идут в отдельную БД. Должно выполниться до импорта app.*
os.environ["POSTGRES_DB"] = os.environ.get("TEST_POSTGRES_DB", "veillou_test")
os.environ["ENV"] = "test"

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.db import Base, engine, session_factory
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


async def _reset_schema() -> None:
    tmp = create_async_engine(settings.DATABASE_URL)
    async with tmp.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await tmp.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> None:
    """Схема создаётся настоящими миграциями — заодно проверяем их."""
    asyncio.run(_reset_schema())
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    yield
    tables = [t.name for t in Base.metadata.sorted_tables]
    if tables:
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engine() -> AsyncIterator[None]:
    yield
    await engine.dispose()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
