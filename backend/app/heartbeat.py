"""Heartbeat фоновых процессов (worker, bot) для healthcheck в docker compose.

Процесс периодически трогает файл; проверка — `python -m app.heartbeat worker 300`:
код 0, если файл обновлялся не дольше 300 с назад. Так зависший цикл (а не только
упавший процесс) виден в `docker compose ps` как unhealthy.
"""

import sys
import time
from pathlib import Path

import anyio

from app.core.config import settings


def _path(name: str) -> Path:
    return Path(settings.HEARTBEAT_DIR) / f"{name}.heartbeat"


async def beat(name: str) -> None:
    path = anyio.Path(_path(name))
    await path.parent.mkdir(parents=True, exist_ok=True)
    await path.touch()


def is_alive(name: str, max_age_sec: float, now: float | None = None) -> bool:
    try:
        mtime = _path(name).stat().st_mtime
    except FileNotFoundError:
        return False
    return (now or time.time()) - mtime <= max_age_sec


if __name__ == "__main__":
    sys.exit(0 if is_alive(sys.argv[1], float(sys.argv[2])) else 1)
