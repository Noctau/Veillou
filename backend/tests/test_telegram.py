from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.types import Chat, Message, MessageEntity, Update
from aiogram.types import User as TgUser
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.app import create_dispatcher
from app.core.config import settings
from app.core.time import now_utc
from app.models import TelegramLinkCode, User
from app.services import telegram

URL = "/api/v1/me/telegram"
TG_ID = 555_000_111
STRANGER_ID = 999_000_222


class CapturingSession(BaseSession):
    """HTTP-сессия бота без сети: запоминает запросы к Telegram API."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[TelegramMethod[Any]] = []

    # сигнатура из aiogram BaseSession
    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109
    ):
        self.sent.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=len(self.sent),
                date=datetime.now(UTC),
                chat=Chat(id=int(method.chat_id), type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""

    async def close(self) -> None:
        pass

    @property
    def texts(self) -> list[str]:
        return [m.text for m in self.sent if isinstance(m, SendMessage)]


_ids = count(1)


def make_update(text: str, tg_id: int = TG_ID, chat_type: str = "private") -> Update:
    entities = None
    if text.startswith("/"):
        entities = [MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))]
    return Update(
        update_id=next(_ids),
        message=Message(
            message_id=next(_ids),
            date=datetime.now(UTC),
            chat=Chat(id=tg_id if chat_type == "private" else -100, type=chat_type),
            from_user=TgUser(id=tg_id, is_bot=False, first_name="Аня"),
            text=text,
            entities=entities,
        ),
    )


class BotHarness:
    def __init__(self) -> None:
        self.session = CapturingSession()
        self.bot = Bot("42:TEST", session=self.session)
        self.dp = create_dispatcher()

    async def send(self, text: str, **kwargs: Any) -> list[str]:
        before = len(self.session.texts)
        await self.dp.feed_update(self.bot, make_update(text, **kwargs))
        return self.session.texts[before:]


@pytest.fixture
def tg() -> BotHarness:
    return BotHarness()


async def fresh_user(session: AsyncSession, user: User) -> User:
    user_id = user.id
    session.expire_all()
    return await session.scalar(select(User).where(User.id == user_id))


# ---------- привязка через бота ----------


async def test_link_flow(tg: BotHarness, session: AsyncSession, user: User):
    code = await telegram.create_link_code(session, user)
    replies = await tg.send(f"/start {code.code}")
    assert len(replies) == 1 and "привязан" in replies[0] and user.email in replies[0]
    assert (await fresh_user(session, user)).tg_user_id == TG_ID

    # Теперь пользователь «свой»: бот отвечает на обычные сообщения
    assert len(await tg.send("привет")) == 1
    assert len(await tg.send("/start")) == 1


async def test_code_is_single_use(tg: BotHarness, session: AsyncSession, user: User):
    code = await telegram.create_link_code(session, user)
    await tg.send(f"/start {code.code}")
    replies = await tg.send(f"/start {code.code}", tg_id=STRANGER_ID)
    assert replies == ["Код недействителен или истёк. Получите новый в Настройках."]


async def test_expired_code(tg: BotHarness, session: AsyncSession, user: User):
    code = await telegram.create_link_code(session, user)
    await session.execute(
        update(TelegramLinkCode).values(expires_at=now_utc() - timedelta(seconds=1))
    )
    await session.commit()
    replies = await tg.send(f"/start {code.code}")
    assert "недействителен" in replies[0]
    assert (await fresh_user(session, user)).tg_user_id is None


async def test_new_code_invalidates_previous(tg: BotHarness, session: AsyncSession, user: User):
    old = await telegram.create_link_code(session, user)
    new = await telegram.create_link_code(session, user)
    assert "недействителен" in (await tg.send(f"/start {old.code}"))[0]
    assert "привязан" in (await tg.send(f"/start {new.code}"))[0]


async def test_wrong_code(tg: BotHarness, user: User):
    assert "недействителен" in (await tg.send("/start nonsense"))[0]


async def test_tg_account_linked_to_another_user(tg: BotHarness, session: AsyncSession, user: User):
    from app.services.users import create_user

    from .conftest import PASSWORD

    other = await create_user(session, email="other@example.com", password=PASSWORD)
    await tg.send(f"/start {(await telegram.create_link_code(session, other)).code}")
    replies = await tg.send(f"/start {(await telegram.create_link_code(session, user)).code}")
    assert "другому аккаунту" in replies[0]
    assert (await fresh_user(session, user)).tg_user_id is None


async def test_relink_same_account_is_ok(tg: BotHarness, session: AsyncSession, user: User):
    await tg.send(f"/start {(await telegram.create_link_code(session, user)).code}")
    replies = await tg.send(f"/start {(await telegram.create_link_code(session, user)).code}")
    assert "привязан" in replies[0]


# ---------- чужие игнорируются ----------


@pytest.mark.parametrize("text", ["привет", "/start", "/today", "/start@veillou_bot"])
async def test_stranger_is_ignored(tg: BotHarness, user: User, text: str):
    assert await tg.send(text, tg_id=STRANGER_ID) == []
    assert tg.session.sent == []


async def test_group_chat_is_ignored_even_for_owner(
    tg: BotHarness, session: AsyncSession, user: User
):
    await tg.send(f"/start {(await telegram.create_link_code(session, user)).code}")
    assert await tg.send("привет", chat_type="group") == []


async def test_deleted_user_is_ignored(tg: BotHarness, session: AsyncSession, user: User):
    await tg.send(f"/start {(await telegram.create_link_code(session, user)).code}")
    await session.execute(update(User).values(deleted_at=now_utc()))
    await session.commit()
    assert await tg.send("привет") == []


# ---------- API ----------


async def test_api_requires_auth(client: AsyncClient):
    assert (await client.get(URL)).status_code == 401
    assert (await client.post(f"{URL}/link-code")).status_code == 401
    assert (await client.delete(URL)).status_code == 401


async def test_api_link_code_and_status(
    auth_client: AsyncClient, tg: BotHarness, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", "veillou_bot")
    assert (await auth_client.get(URL)).json() == {"linked": False, "bot_username": "veillou_bot"}

    resp = await auth_client.post(f"{URL}/link-code")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deep_link"] == f"https://t.me/veillou_bot?start={data['code']}"
    expires_at = datetime.fromisoformat(data["expires_at"])
    assert timedelta(minutes=9) < expires_at - now_utc() <= timedelta(minutes=10)

    await tg.send(f"/start {data['code']}")
    assert (await auth_client.get(URL)).json()["linked"] is True

    assert (await auth_client.delete(URL)).status_code == 204
    assert (await auth_client.get(URL)).json()["linked"] is False
    assert await tg.send("привет") == []  # после отвязки бот снова не отвечает


async def test_api_deep_link_without_bot_username(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", None)
    data = (await auth_client.post(f"{URL}/link-code")).json()
    assert data["deep_link"] is None and len(data["code"]) == 16
