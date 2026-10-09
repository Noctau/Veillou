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
        # БД одноразовая: коммиты без ожидания fsync (на медленном диске — в разы быстрее)
        await conn.execute(
            text(f'ALTER DATABASE "{settings.POSTGRES_DB}" SET synchronous_commit = off')
        )
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
    # DELETE, а не TRUNCATE: TRUNCATE пересоздаёт файлы таблиц и ждёт fsync — на Docker
    # Desktop это секунды на каждый тест. Дети раньше родителей — порядок по внешним ключам.
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


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


PASSWORD = "correct-horse-battery"


@pytest.fixture
async def user(session: AsyncSession):
    from app.services.users import create_user

    return await create_user(session, email="Student@Example.com", password=PASSWORD)


@pytest.fixture
async def auth_client(client: AsyncClient, user) -> AsyncClient:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "student@example.com", "password": PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return client
