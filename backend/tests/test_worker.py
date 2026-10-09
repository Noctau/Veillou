"""Воркер: heartbeat, остановка по SIGTERM, паузы очереди ИИ, ночное время (L-19, L-21)."""

import asyncio
import os
import signal
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import heartbeat
from app.core.config import settings
from app.services import jobs
from app.worker import __main__ as worker


@pytest.fixture
def hb_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "HEARTBEAT_DIR", tmp_path / "hb")
    return tmp_path / "hb"


async def test_heartbeat(hb_dir: Path):
    assert not heartbeat.is_alive("worker", 60)
    await heartbeat.beat("worker")
    assert heartbeat.is_alive("worker", 60)
    assert not heartbeat.is_alive("worker", 60, now=time.time() + 120)


async def test_sigterm_cancels_main_task():
    async def main() -> str:
        task = asyncio.current_task()
        assert task is not None
        worker.stop_on_signals(task)
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            return "stopped"
        finally:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)
        return "not stopped"

    assert await asyncio.wait_for(asyncio.create_task(main()), 3) == "stopped"


def test_ai_pause_backs_off_while_unavailable():
    assert worker.ai_pause(None, 0) == (worker.AI_POLL_SEC, 0)
    assert worker.ai_pause(jobs.JobOutcome.done, 3) == (0.0, 0)
    pauses = []
    misses = 0
    for _ in range(6):
        pause, misses = worker.ai_pause(jobs.JobOutcome.deferred, misses)
        pauses.append(pause)
    assert pauses == [30, 60, 120, 300, 300, 300]


def test_seconds_until_nightly_in_default_timezone():
    # 23:00 по Москве (20:00 UTC) → до 03:00 — 4 часа
    now = datetime(2026, 10, 8, 20, 0, tzinfo=UTC)
    assert worker.seconds_until(worker.NIGHTLY_AT, now) == 4 * 3600
    # Ровно 03:00 — следующая через сутки
    at_three = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
    assert worker.seconds_until(worker.NIGHTLY_AT, at_three) == 24 * 3600


async def test_safely_swallows_errors(monkeypatch: pytest.MonkeyPatch):
    logged: list[tuple[object, ...]] = []
    monkeypatch.setattr(worker.log, "exception", lambda *args: logged.append(args))

    async def boom() -> None:
        raise RuntimeError("БД ещё не поднялась")

    await worker.safely("шаг", boom)
    assert logged == [("%s: ошибка", "шаг")]


def test_build_notifier_without_channels(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", None)
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", None)
    notifier, closers = worker.build_notifier()
    assert notifier.senders == {}
    assert closers == []
