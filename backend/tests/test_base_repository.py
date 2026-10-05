"""Базовый репозиторий: фильтр по user_id и мягкое удаление.

Модели здесь отдельные (своя схема `repo_test`), чтобы не зависеть от
реальных таблиц и не попадать в миграции.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from sqlalchemy import MetaData, String, select, text
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import engine
from app.core.exceptions import NotFoundError
from app.models.base import EntityMixin, UserOwnedMixin
from app.services.base import UserScopedRepository


class RepoTestBase(DeclarativeBase):
    metadata = MetaData(schema="repo_test")


class FakeUser(EntityMixin, RepoTestBase):
    __tablename__ = "users"


class Item(UserOwnedMixin, RepoTestBase):
    __tablename__ = "items"
    title: Mapped[str] = mapped_column(String(100))


class ItemRepository(UserScopedRepository[Item]):
    model = Item


@pytest.fixture(scope="module", autouse=True)
async def _tables() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS repo_test CASCADE"))
        await conn.execute(text("CREATE SCHEMA repo_test"))
        await conn.run_sync(RepoTestBase.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA repo_test CASCADE"))


@pytest.fixture
async def users(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    me, other = FakeUser(), FakeUser()
    session.add_all([me, other])
    await session.commit()
    return me.id, other.id


async def test_add_sets_user_and_timestamps(session: AsyncSession, users):
    me, _ = users
    repo = ItemRepository(session, me)
    item = repo.add(Item(title="a"))
    await session.commit()
    await session.refresh(item)
    assert item.user_id == me
    assert item.created_at.tzinfo is not None
    assert item.deleted_at is None


async def test_other_users_rows_are_invisible(session: AsyncSession, users):
    me, other = users
    theirs = ItemRepository(session, other).add(Item(title="чужое"))
    ItemRepository(session, me).add(Item(title="моё"))
    await session.commit()

    repo = ItemRepository(session, me)
    assert [i.title for i in await repo.find_all()] == ["моё"]
    assert await repo.get(theirs.id) is None
    with pytest.raises(NotFoundError):
        await repo.get_or_404(theirs.id)


async def test_soft_delete_hides_but_keeps_row(session: AsyncSession, users):
    me, _ = users
    repo = ItemRepository(session, me)
    item = repo.add(Item(title="удалить"))
    keep = repo.add(Item(title="оставить"))
    await session.commit()

    repo.soft_delete(item)
    await session.commit()

    assert await repo.get(item.id) is None
    assert [i.id for i in await repo.find_all()] == [keep.id]
    raw = await session.scalar(select(Item.deleted_at).where(Item.id == item.id))
    assert isinstance(raw, datetime)


async def test_list_filters_order_paging(session: AsyncSession, users):
    me, _ = users
    repo = ItemRepository(session, me)
    for t in ["c", "a", "b"]:
        repo.add(Item(title=t))
    await session.commit()
    items = await repo.find_all(Item.title != "c", order_by=[Item.title])
    assert [i.title for i in items] == ["a", "b"]
    page = await repo.find_all(order_by=[Item.title], offset=1, limit=1)
    assert [i.title for i in page] == ["b"]


async def test_naive_datetime_rejected_on_write(session: AsyncSession, users):
    me, _ = users
    repo = ItemRepository(session, me)
    item = repo.add(Item(title="x"))
    item.deleted_at = datetime(2026, 1, 1)
    with pytest.raises(StatementError):
        await session.commit()
    await session.rollback()
