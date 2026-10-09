"""M-02: push-подписка принимается только на известные push-сервисы, без редиректов."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PushSubscription, User
from app.notify import notifier as notifier_module
from app.notify.message import Message
from app.notify.notifier import DeliveryStatus, WebPushSender, push_host_allowed

API = "/api/v1"
KEYS = {"p256dh": "k" * 20, "auth": "a" * 10}


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/QGbc",
        "https://wns2-par02p.notify.windows.com/w/?token=abc",
    ],
)
def test_known_push_services_allowed(endpoint: str):
    assert push_host_allowed(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://evil.example/collect",
        "https://172.30.0.1:11434/api/chat",
        "https://localhost/x",
        "https://fcm.googleapis.com.evil.example/x",
        "https://user@fcm.googleapis.com/x",
        "https://fcm.googleapis.com:8443/x",
        "http://fcm.googleapis.com/x",
    ],
)
def test_other_hosts_rejected(endpoint: str):
    assert not push_host_allowed(endpoint)


async def test_subscribe_rejects_unknown_service(auth_client: AsyncClient):
    resp = await auth_client.post(
        f"{API}/me/push/subscriptions",
        json={"endpoint": "https://172.30.0.1:11434/api/chat", "keys": KEYS},
    )
    assert resp.status_code == 422
    ok = await auth_client.post(
        f"{API}/me/push/subscriptions",
        json={"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": KEYS},
    )
    assert ok.status_code == 204


async def test_sender_skips_stored_unknown_endpoint(
    session: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
):
    """Строки, сохранённые до проверки, не отправляются, но и не удаляются (allowlist
    мог не учесть реальный сервис — тогда хватит дописать его в настройку)."""
    session.add(
        PushSubscription(user_id=user.id, endpoint="https://evil.example/x", p256dh="k", auth="a")
    )
    await session.commit()
    called: list[str] = []
    monkeypatch.setattr(
        notifier_module, "webpush", lambda subscription_info, **kw: called.append("x")
    )
    result = await WebPushSender("pub", "priv", "mailto:x").send(
        session, user, Message(title="Т"), 60
    )
    assert called == []
    assert result.status == DeliveryStatus.skipped
    assert len(list(await session.scalars(select(PushSubscription)))) == 1


async def test_sender_does_not_follow_redirects(
    session: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
):
    session.add(
        PushSubscription(
            user_id=user.id, endpoint="https://fcm.googleapis.com/fcm/send/a", p256dh="k", auth="a"
        )
    )
    await session.commit()
    seen: dict = {}

    def fake_webpush(**kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(notifier_module, "webpush", fake_webpush)
    await WebPushSender("pub", "priv", "mailto:x").send(session, user, Message(title="Т"), 60)
    assert seen["requests_session"].max_redirects == 0
