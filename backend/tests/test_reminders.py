import asyncio
import uuid
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import func, select

from app.core.db import session_factory
from app.core.security import hash_token
from app.core.time import get_tz, now_utc, wall_to_utc
from app.domain.enums import (
    EventKind,
    EventStatus,
    JobKind,
    JobStatus,
    ReminderAction,
    ReminderKind,
    ReminderStatus,
    TaskStatus,
)
from app.models import Event, Job, Reminder, Task
from app.notify.message import Message
from app.notify.notifier import SENT, Delivery, Notifier, failed, skipped
from app.services import jobs
from app.services.dispatch import dispatch_due
from app.services.reminder_actions import ReminderActionError, perform_by_token
from app.services.reminders import handle_sync_job, sync_user_reminders

API = "/api/v1"
TZ = get_tz("Europe/Moscow")


class FakeSender:
    def __init__(self, result: Delivery = SENT, delay: float = 0) -> None:
        self.sent: list[Message] = []
        self.result = result
        self.delay = delay

    async def send(self, db, user, msg, ttl):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.sent.append(msg)
        return self.result


def notifier(**senders: FakeSender) -> Notifier:
    return Notifier(dict(senders))


async def add_reminder(session, user, **kw) -> Reminder:
    now = now_utc()
    fire_at = kw.pop("fire_at", now - timedelta(hours=1))
    r = Reminder(
        user_id=user.id,
        kind=kw.pop("kind", ReminderKind.test),
        fire_at=fire_at,
        due_at=kw.pop("due_at", fire_at),
        channels=kw.pop("channels", ["push", "telegram"]),
        payload=kw.pop("payload", {}),
        dedupe_key=kw.pop("dedupe_key", f"t:{uuid.uuid4().hex}"),
        is_auto=kw.pop("is_auto", False),
        status=ReminderStatus.pending,
        sent_channels=[],
        attempts=kw.pop("attempts", 0),
        **kw,
    )
    session.add(r)
    await session.commit()
    return r


async def reload(session, r: Reminder) -> Reminder:
    await session.refresh(r)
    return r


# ---------- M6.1: досылка ровно один раз ----------


async def test_overdue_reminder_sent_exactly_once_after_restart(session, user):
    """Воркер лежал час: просроченное напоминание уходит в первом цикле и только один раз."""
    r = await add_reminder(session, user)
    push, tg = FakeSender(), FakeSender()
    n = notifier(push=push, telegram=tg)

    assert await dispatch_due(session_factory, n) == 1
    # «Рестарт»: новый цикл, новый Notifier — повторно не уходит
    push2, tg2 = FakeSender(), FakeSender()
    assert await dispatch_due(session_factory, notifier(push=push2, telegram=tg2)) == 0

    assert len(push.sent) == len(tg.sent) == 1
    assert push2.sent == tg2.sent == []
    r = await reload(session, r)
    assert r.status == ReminderStatus.sent
    assert sorted(r.sent_channels) == ["push", "telegram"]


async def test_crashed_worker_lease_expires_and_reminder_is_resent_once(session, user):
    """Воркер захватил напоминание и упал: после истечения аренды его досылают один раз."""
    now = now_utc()
    r = await add_reminder(session, user, attempts=1, locked_until=now - timedelta(seconds=1))
    push = FakeSender()
    assert await dispatch_due(session_factory, notifier(push=push, telegram=FakeSender())) == 1
    assert await dispatch_due(session_factory, notifier(push=push, telegram=FakeSender())) == 0
    assert len(push.sent) == 1
    assert (await reload(session, r)).status == ReminderStatus.sent


async def test_locked_reminder_is_not_taken_twice(session, user):
    await add_reminder(session, user, attempts=1, locked_until=now_utc() + timedelta(minutes=1))
    push = FakeSender()
    assert await dispatch_due(session_factory, notifier(push=push)) == 0
    assert push.sent == []


async def test_concurrent_workers_send_once(session, user):
    await add_reminder(session, user, channels=["push"])
    push = FakeSender(delay=0.05)
    n = notifier(push=push)
    results = await asyncio.gather(*(dispatch_due(session_factory, n) for _ in range(3)))
    assert sum(results) == 1
    assert len(push.sent) == 1


async def test_future_reminder_waits(session, user):
    await add_reminder(session, user, fire_at=now_utc() + timedelta(minutes=5))
    push = FakeSender()
    assert await dispatch_due(session_factory, notifier(push=push)) == 0


async def test_failed_channel_retried_without_duplicating_ok_channel(session, user):
    r = await add_reminder(session, user)
    push, tg = FakeSender(), FakeSender(failed("telegram down"))
    await dispatch_due(session_factory, notifier(push=push, telegram=tg))
    r = await reload(session, r)
    assert r.status == ReminderStatus.pending
    assert r.sent_channels == ["push"]
    assert r.due_at > now_utc()
    assert "telegram down" in (r.last_error or "")

    # Ретрай: telegram ожил — push второй раз не уходит
    tg.result = SENT
    await dispatch_due(session_factory, notifier(push=push, telegram=tg), now=r.due_at)
    r = await reload(session, r)
    assert r.status == ReminderStatus.sent
    assert len(push.sent) == 1
    assert len(tg.sent) == 2


async def test_gives_up_after_max_attempts(session, user):
    r = await add_reminder(session, user, channels=["push"], attempts=4)
    await dispatch_due(session_factory, notifier(push=FakeSender(failed("boom"))))
    assert (await reload(session, r)).status == ReminderStatus.failed


async def test_skipped_channel_counts_as_done(session, user):
    r = await add_reminder(session, user)
    tg = FakeSender(skipped("не привязан"))
    await dispatch_due(session_factory, notifier(push=FakeSender(), telegram=tg))
    assert (await reload(session, r)).status == ReminderStatus.sent


async def test_expired_reminder_skipped(session, user):
    now = now_utc()
    r = await add_reminder(session, user, expires_at=now - timedelta(minutes=1))
    push = FakeSender()
    await dispatch_due(session_factory, notifier(push=push))
    assert push.sent == []
    assert (await reload(session, r)).status == ReminderStatus.skipped


async def test_simultaneous_reminders_merged_into_one_message(session, user):
    fire = now_utc() - timedelta(seconds=5)
    await add_reminder(session, user, fire_at=fire, channels=["push"])
    await add_reminder(session, user, fire_at=fire, channels=["push"])
    push = FakeSender()
    await dispatch_due(session_factory, notifier(push=push))
    assert len(push.sent) == 1
    assert push.sent[0].title == "Напоминания: 2"


# ---------- пересборка ----------


async def add_class(session, user, start: datetime, **kw) -> Event:
    e = Event(
        user_id=user.id,
        kind=EventKind.class_,
        title=kw.pop("title", "Климатология"),
        start=start,
        end=start + timedelta(minutes=95),
        is_fixed=True,
        status=EventStatus.planned,
        location=kw.pop("location", "1234"),
        **kw,
    )
    session.add(e)
    await session.commit()
    return e


async def pending(session, user, kind: ReminderKind | None = None) -> list[Reminder]:
    stmt = select(Reminder).where(
        Reminder.user_id == user.id, Reminder.status == ReminderStatus.pending
    )
    if kind:
        stmt = stmt.where(Reminder.kind == kind)
    return list(await session.scalars(stmt.order_by(Reminder.fire_at)))


def tomorrow_at(h: int, m: int = 0) -> datetime:
    d = now_utc().astimezone(TZ).date() + timedelta(days=1)
    return wall_to_utc(d, time(h, m), TZ)


async def test_sync_creates_before_class_and_digest(session, user):
    e = await add_class(session, user, tomorrow_at(10, 45))
    await sync_user_reminders(session, user.id)
    [r] = await pending(session, user, ReminderKind.before_class)
    assert r.fire_at == tomorrow_at(10, 30)
    assert r.entity_id == e.id
    assert r.is_auto
    digests = await pending(session, user, ReminderKind.morning_digest)
    assert tomorrow_at(8) in {d.fire_at for d in digests}


async def test_sync_follows_moved_and_cancelled_class(session, user):
    e = await add_class(session, user, tomorrow_at(10, 45))
    await sync_user_reminders(session, user.id)
    e.start, e.end = tomorrow_at(12, 30), tomorrow_at(14, 5)
    await session.commit()
    await sync_user_reminders(session, user.id)
    [r] = await pending(session, user, ReminderKind.before_class)
    assert r.fire_at == tomorrow_at(12, 15)

    e.status = EventStatus.cancelled
    await session.commit()
    await sync_user_reminders(session, user.id)
    assert await pending(session, user, ReminderKind.before_class) == []


async def test_sync_does_not_recreate_sent(session, user):
    await add_class(session, user, tomorrow_at(10, 45))
    await sync_user_reminders(session, user.id)
    [r] = await pending(session, user, ReminderKind.before_class)
    r.status = ReminderStatus.sent
    await session.commit()
    stats = await sync_user_reminders(session, user.id)
    assert stats.created == 0
    assert await pending(session, user, ReminderKind.before_class) == []


async def test_sync_is_idempotent(session, user):
    await add_class(session, user, tomorrow_at(10, 45))
    await sync_user_reminders(session, user.id)
    stats = await sync_user_reminders(session, user.id)
    assert (stats.created, stats.updated, stats.deleted) == (0, 0, 0)


async def test_sync_keeps_snoozed_and_overdue(session, user):
    manual = await add_reminder(session, user, fire_at=now_utc() + timedelta(hours=2))
    overdue = await add_reminder(session, user, is_auto=True, dedupe_key="before_class:x:y")
    await sync_user_reminders(session, user.id)
    ids = {r.id for r in await pending(session, user, ReminderKind.test)}
    assert {manual.id, overdue.id} <= ids


async def test_disabled_rule_removes_reminders(auth_client, session, user):
    await add_class(session, user, tomorrow_at(10, 45))
    await sync_user_reminders(session, user.id)
    resp = await auth_client.patch(
        f"{API}/me/settings", json={"reminders": {"before_class": {"enabled": False}}}
    )
    assert resp.status_code == 200
    await session.refresh(user)
    await sync_user_reminders(session, user.id)
    assert await pending(session, user, ReminderKind.before_class) == []


async def test_quiet_hours_and_minutes_from_settings(auth_client, session, user):
    await add_class(session, user, tomorrow_at(9, 0))
    await auth_client.patch(
        f"{API}/me/settings",
        json={
            "quiet_hours": {"start": "23:00", "end": "08:50"},
            "reminders": {"before_class": {"minutes_before": 20}},
        },
    )
    await session.refresh(user)
    await sync_user_reminders(session, user.id)
    [r] = await pending(session, user, ReminderKind.before_class)
    assert r.fire_at == tomorrow_at(8, 50)  # 8:40 в тихие часы → их конец


async def test_deadline_reminders_at_digest_time(auth_client, session, user):
    # Дедлайн послезавтра: «за 3 дня» — вчера в 8:00, прошло при любом времени запуска
    deadline = tomorrow_at(23, 59) + timedelta(days=1)
    resp = await auth_client.post(
        f"{API}/tasks", json={"title": "Реферат", "deadline": deadline.isoformat()}
    )
    assert resp.status_code == 201, resp.text
    await sync_user_reminders(session, user.id)
    rs = await pending(session, user, ReminderKind.deadline)
    assert [r.fire_at for r in rs] == [
        tomorrow_at(8),
        tomorrow_at(8) + timedelta(days=1),
    ]

    await auth_client.patch(f"{API}/tasks/{resp.json()['id']}", json={"status": "done"})
    await sync_user_reminders(session, user.id)
    assert await pending(session, user, ReminderKind.deadline) == []


async def test_digest_moved_to_past_time_fires_now_once(auth_client, session, user):
    """Сводку перенесли с 10:00 на 9:00 в 9:30 — сегодняшняя уходит сразу, без дублей."""
    today = now_utc().astimezone(TZ).date()
    now = wall_to_utc(today, time(9, 30), TZ)
    key = f"morning_digest:{today.isoformat()}"

    async def todays() -> list[Reminder]:
        rs = await pending(session, user, ReminderKind.morning_digest)
        return [r for r in rs if r.dedupe_key == key]

    async def set_digest(at: str) -> None:
        resp = await auth_client.patch(
            f"{API}/me/settings", json={"schedule": {"morning_digest": at}}
        )
        assert resp.status_code == 200, resp.text
        await session.refresh(user)

    await set_digest("10:00")
    await sync_user_reminders(session, user.id, now)
    assert [r.fire_at for r in await todays()] == [wall_to_utc(today, time(10), TZ)]

    await set_digest("09:00")
    await sync_user_reminders(session, user.id, now)
    [r] = await todays()
    assert r.fire_at == now

    r.status = ReminderStatus.sent
    await session.commit()
    await sync_user_reminders(session, user.id, now + timedelta(minutes=5))
    assert await todays() == []


async def test_next_due_at_waits_for_lease(session, user):
    """Захваченное напоминание не будит воркер раньше конца аренды."""
    from app.services.dispatch import next_due_at

    now = now_utc()
    await add_reminder(
        session, user, fire_at=now - timedelta(minutes=1), locked_until=now + timedelta(minutes=2)
    )
    assert await next_due_at(session) == now + timedelta(minutes=2)


# ---------- триггеры ----------


async def test_changes_enqueue_single_sync_job(auth_client, session, user):
    for title in ("a", "b", "c"):
        await auth_client.post(f"{API}/tasks", json={"title": title})
    count = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.kind == JobKind.reminders_sync,
            Job.user_id == user.id,
            Job.status == JobStatus.pending,
        )
    )
    assert count == 1


async def test_sync_job_runs_through_queue(auth_client, session, user):
    deadline = tomorrow_at(23, 59) + timedelta(days=1)
    await auth_client.post(f"{API}/tasks", json={"title": "ДЗ", "deadline": deadline.isoformat()})
    handlers = {JobKind.reminders_sync: handle_sync_job}
    later = now_utc() + timedelta(seconds=10)
    assert await jobs.run_one(session_factory, handlers, now=later)
    assert await pending(session, user, ReminderKind.deadline)
    job = await session.scalar(select(Job).where(Job.user_id == user.id))
    assert job is not None and job.status == JobStatus.done


async def test_failing_job_is_retried(session, user):
    await jobs.enqueue(session, "boom", user_id=user.id)
    await session.commit()

    async def boom(db, job):
        raise RuntimeError("nope")

    assert await jobs.run_one(session_factory, {"boom": boom})
    job = await session.scalar(select(Job).where(Job.kind == "boom"))
    assert job.status == JobStatus.pending and job.attempts == 1
    assert job.run_at > now_utc()
    assert "nope" in job.last_error


# ---------- рендер ----------


async def test_before_class_message(session, user):
    e = await add_class(session, user, now_utc() + timedelta(minutes=15), note="Взять калькулятор")
    await add_reminder(
        session,
        user,
        kind=ReminderKind.before_class,
        entity_type="event",
        entity_id=e.id,
        payload={"start": e.start.isoformat()},
        channels=["telegram"],
    )
    tg = FakeSender()
    await dispatch_due(session_factory, notifier(telegram=tg))
    [msg] = tg.sent
    assert msg.title == "Через 15 мин: Климатология"
    body = msg.plain_body()
    assert "ауд. 1234" in body
    assert "Взять калькулятор" in body


async def test_stale_class_reminder_skipped(session, user):
    e = await add_class(session, user, now_utc() + timedelta(minutes=15))
    r = await add_reminder(
        session,
        user,
        kind=ReminderKind.before_class,
        entity_type="event",
        entity_id=e.id,
        payload={"start": (e.start - timedelta(hours=1)).isoformat()},
    )
    push = FakeSender()
    await dispatch_due(session_factory, notifier(push=push))
    assert push.sent == []
    assert (await reload(session, r)).status == ReminderStatus.skipped


# ---------- кнопки ----------


async def make_deadline_reminder(session, user) -> tuple[Task, Reminder, str]:
    task = Task(
        user_id=user.id,
        title="Реферат",
        deadline=now_utc() + timedelta(days=2),
        status=TaskStatus.active,
    )
    session.add(task)
    await session.commit()
    token = "tok-" + uuid.uuid4().hex
    r = await add_reminder(
        session,
        user,
        kind=ReminderKind.deadline,
        entity_type="task",
        entity_id=task.id,
        payload={"deadline": task.deadline.isoformat(), "days_before": 2},
        action_token_hash=hash_token(token),
        expires_at=task.deadline,
    )
    return task, r, token


async def test_push_action_done_closes_task_once(client, session, user):
    task, _, token = await make_deadline_reminder(session, user)
    resp = await client.post(f"{API}/notifications/action", json={"token": token, "action": "done"})
    assert resp.status_code == 200, resp.text
    await session.refresh(task)
    assert task.status == TaskStatus.done
    again = await client.post(
        f"{API}/notifications/action", json={"token": token, "action": "done"}
    )
    assert again.status_code == 409


async def test_push_action_snooze_creates_reminder(session, user):
    _, r, token = await make_deadline_reminder(session, user)
    result = await perform_by_token(session, token, ReminderAction.snooze)
    assert result.message.startswith("Напомню")
    snoozed = await session.scalar(
        select(Reminder).where(Reminder.dedupe_key.startswith(f"{r.dedupe_key}:snooze:"))
    )
    assert snoozed is not None and not snoozed.is_auto
    assert snoozed.fire_at >= now_utc() + timedelta(minutes=14)


async def test_push_token_survives_telegram_on_same_reminder(session, user):
    """Push и Telegram в одном цикле: кнопки пуша работают (токен не перезаписан)."""
    _, r, _ = await make_deadline_reminder(session, user)
    r.action_token_hash = None
    await session.commit()
    push, tg = FakeSender(), FakeSender()
    await dispatch_due(session_factory, notifier(push=push, telegram=tg))
    [msg] = push.sent
    assert msg.action_token
    result = await perform_by_token(session, msg.action_token, ReminderAction.snooze)
    assert result.message.startswith("Напомню")


async def test_push_token_valid_for_reminder_created_long_ago(session, user):
    """Напоминания создаются за 8 дней до отправки — срок токена считается от отправки."""
    _, r, _ = await make_deadline_reminder(session, user)
    r.action_token_hash = None
    r.created_at = now_utc() - timedelta(days=8)
    await session.commit()
    push = FakeSender()
    await dispatch_due(session_factory, notifier(push=push))
    [msg] = push.sent
    result = await perform_by_token(session, msg.action_token, ReminderAction.snooze)
    assert result.message.startswith("Напомню")


async def test_bad_token_404(client):
    resp = await client.post(
        f"{API}/notifications/action", json={"token": "x" * 20, "action": "done"}
    )
    assert resp.status_code == 404


async def test_tomorrow_past_deadline_rejected(session, user):
    task, r, token = await make_deadline_reminder(session, user)
    task.deadline = now_utc() + timedelta(hours=3)
    r.expires_at = task.deadline
    await session.commit()
    with pytest.raises(ReminderActionError):
        await perform_by_token(session, token, ReminderAction.tomorrow)


async def test_subtask_tomorrow_moves_block(auth_client, session, user):
    task = (await auth_client.post(f"{API}/tasks", json={"title": "Курсовая"})).json()
    st = (
        await auth_client.post(f"{API}/tasks/{task['id']}/subtasks", json={"title": "Глава 1"})
    ).json()
    start = now_utc().replace(microsecond=0) + timedelta(minutes=5)
    await auth_client.post(f"{API}/subtasks/{st['id']}/schedule", json={"start": start.isoformat()})
    event = await session.scalar(select(Event).where(Event.source_id == uuid.UUID(st["id"])))
    token = "tok-" + uuid.uuid4().hex
    await add_reminder(
        session,
        user,
        kind=ReminderKind.subtask_start,
        entity_type="event",
        entity_id=event.id,
        payload={"start": event.start.isoformat()},
        action_token_hash=hash_token(token),
    )
    await perform_by_token(session, token, ReminderAction.tomorrow)
    await session.refresh(event)
    assert event.start == start + timedelta(days=1)


# ---------- API ----------


async def test_push_subscription_api(auth_client, session, user):
    body = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        "keys": {"p256dh": "BPk", "auth": "xyz"},
        "device_name": "Android",
    }
    assert (await auth_client.post(f"{API}/me/push/subscriptions", json=body)).status_code == 204
    # Повторная подписка того же браузера — upsert
    assert (await auth_client.post(f"{API}/me/push/subscriptions", json=body)).status_code == 204
    cfg = (await auth_client.get(f"{API}/me/push")).json()
    assert len(cfg["subscriptions"]) == 1
    assert cfg["subscriptions"][0]["device_name"] == "Android"
    resp = await auth_client.post(f"{API}/me/push/unsubscribe", json={"endpoint": body["endpoint"]})
    assert resp.status_code == 204
    assert (await auth_client.get(f"{API}/me/push")).json()["subscriptions"] == []


async def test_test_notification_reports_channels(auth_client):
    resp = await auth_client.post(f"{API}/me/notifications/test")
    assert resp.status_code == 200
    states = {c["channel"]: c for c in resp.json()["channels"]}
    assert set(states) == {"push", "telegram"}
    assert states["telegram"]["ready"] is False


async def test_upcoming_reminders_api(auth_client, session, user):
    await add_class(session, user, tomorrow_at(10, 45))
    await sync_user_reminders(session, user.id)
    items = (await auth_client.get(f"{API}/me/reminders")).json()
    labels = [i["label"] for i in items]
    assert "Перед парой: Климатология" in labels
    assert any(label.startswith("Утренняя сводка") for label in labels)


async def test_reminders_require_auth(client):
    assert (await client.get(f"{API}/me/reminders")).status_code == 401


async def test_morning_digest_with_deadline_goes_to_both_channels(auth_client, session, user):
    """Сводка в 8:00 и «дедлайн через 3 дня» склеиваются в одно сообщение на канал."""
    await add_class(session, user, tomorrow_at(10, 45))
    deadline = tomorrow_at(23, 59) + timedelta(days=3)
    await auth_client.post(
        f"{API}/tasks", json={"title": "Реферат", "deadline": deadline.isoformat()}
    )
    await sync_user_reminders(session, user.id)

    push, tg = FakeSender(), FakeSender()
    morning = tomorrow_at(8)
    await dispatch_due(session_factory, notifier(push=push, telegram=tg), now=morning)
    assert len(push.sent) == len(tg.sent) == 1
    msg = tg.sent[0]
    assert msg.title.startswith("Доброе утро!")
    html = msg.telegram_html()
    assert "Не забыть" in html and "Дедлайн через 3 дня: Реферат" in html
    assert "Климатология (лекция)" not in html  # тип пары не задан
    assert "10:45–12:20 Климатология · ауд. 1234" in html

    # Перед парой — отдельное сообщение в 10:30
    await dispatch_due(session_factory, notifier(push=push, telegram=tg), now=tomorrow_at(10, 30))
    assert push.sent[-1].title == "Через 15 мин: Климатология"
    assert tg.sent[-1].title == "Через 15 мин: Климатология"
