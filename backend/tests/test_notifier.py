import json
import uuid

from pywebpush import WebPushException
from requests import Response
from sqlalchemy import select

from app.domain.enums import ReminderAction, ReminderKind
from app.models import PushSubscription
from app.notify import notifier as notifier_module
from app.notify.message import Message, Section, combine
from app.notify.notifier import (
    DeliveryStatus,
    TelegramSender,
    WebPushSender,
    push_payload,
    telegram_markup,
)

ACTIONS = (ReminderAction.done, ReminderAction.snooze, ReminderAction.tomorrow)


def msg(**kw) -> Message:
    return Message(title="Дедлайн: <Реферат>", sections=(Section(None, ("a & b",)),), **kw)


def test_telegram_html_escapes():
    assert msg().telegram_html() == "<b>Дедлайн: &lt;Реферат&gt;</b>\n\na &amp; b"


def test_telegram_markup_buttons_and_link():
    rid = uuid.uuid4()
    markup = telegram_markup(msg(actions=ACTIONS, reminder_id=rid, url="/tasks/1"), "https://v.app")
    [actions, link] = markup.inline_keyboard
    assert [b.text for b in actions] == ["Сделано", "+15 мин", "На завтра"]
    assert actions[0].callback_data == f"ra:done:{rid.hex}"
    assert link[0].url == "https://v.app/tasks/1"
    assert telegram_markup(msg(), None) is None


def test_push_payload_actions_only_with_token():
    assert json.loads(push_payload(msg(actions=ACTIONS)))["actions"] == []
    data = json.loads(push_payload(msg(actions=ACTIONS, action_token="tok", url="/tasks/1")))
    assert [a["action"] for a in data["actions"]] == ["done", "snooze", "tomorrow"]
    assert data["token"] == "tok" and data["url"] == "/tasks/1"
    assert data["body"] == "a & b"


def test_combine_without_digest():
    merged = combine([msg(actions=ACTIONS), msg()])
    assert merged.title == "Напоминания: 2"
    assert merged.actions == ()


def test_combine_puts_others_into_digest():
    digest = Message(
        title="Доброе утро!",
        sections=(Section("Пары", ("09:00 Физика",)),),
        kind=ReminderKind.morning_digest,
    )
    merged = combine([digest, msg(actions=ACTIONS)])
    assert merged.title == "Доброе утро!"
    assert merged.sections[0].heading == "Не забыть"
    assert merged.actions == ()


async def test_telegram_not_linked_is_skipped(session, user):
    sender = TelegramSender(bot=None)  # type: ignore[arg-type]
    result = await sender.send(session, user, msg(), 60)
    assert result.status == DeliveryStatus.skipped


async def _subscribe(session, user, endpoint: str) -> PushSubscription:
    sub = PushSubscription(user_id=user.id, endpoint=endpoint, p256dh="k", auth="a")
    session.add(sub)
    await session.commit()
    return sub


def _gone(code: int) -> WebPushException:
    response = Response()
    response.status_code = code
    return WebPushException("gone", response=response)


async def test_push_removes_expired_subscriptions(session, user, monkeypatch):
    await _subscribe(session, user, "https://push/ok")
    await _subscribe(session, user, "https://push/gone")
    sent: list[str] = []

    def fake_webpush(subscription_info, **kwargs):
        if subscription_info["endpoint"].endswith("gone"):
            raise _gone(410)
        sent.append(subscription_info["endpoint"])

    monkeypatch.setattr(notifier_module, "webpush", fake_webpush)
    sender = WebPushSender("pub", "priv", "mailto:x@y.z")
    result = await sender.send(session, user, msg(), 60)
    assert result.status == DeliveryStatus.sent
    assert sent == ["https://push/ok"]
    endpoints = list(await session.scalars(select(PushSubscription.endpoint)))
    assert endpoints == ["https://push/ok"]


async def test_push_temporary_error_fails(session, user, monkeypatch):
    await _subscribe(session, user, "https://push/a")

    def fake_webpush(**kwargs):
        raise _gone(500)

    monkeypatch.setattr(notifier_module, "webpush", fake_webpush)
    result = await WebPushSender("pub", "priv", "mailto:x").send(session, user, msg(), 60)
    assert result.status == DeliveryStatus.failed


async def test_push_without_subscriptions_skipped(session, user):
    result = await WebPushSender("pub", "priv", "mailto:x").send(session, user, msg(), 60)
    assert result.status == DeliveryStatus.skipped
