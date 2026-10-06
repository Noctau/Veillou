"""Админские команды.

    python -m app.cli create-user me@example.com [--timezone Europe/Moscow]
    python -m app.cli set-password me@example.com
    python -m app.cli roll-series   # докатить повторы и регулярные задания (как ночная джоба)
    python -m app.cli vapid-keys    # сгенерировать ключи Web Push для .env

Пароль спрашивается интерактивно (или берётся из VEILLOU_PASSWORD — для скриптов).
"""

import argparse
import asyncio
import getpass
import os
import sys

from app.core.config import settings
from app.core.db import engine, session_factory
from app.core.exceptions import AppError
from app.services import users
from app.services.recurring_tasks import roll_all_recurring_tasks
from app.services.schedule_sync import roll_all_users


def _read_password() -> str:
    if env := os.environ.get("VEILLOU_PASSWORD"):
        return env
    first = getpass.getpass("Пароль: ")
    if getpass.getpass("Ещё раз: ") != first:
        sys.exit("Пароли не совпадают")
    return first


async def _create_user(email: str, timezone: str) -> None:
    password = _read_password()
    async with session_factory() as db:
        user = await users.create_user(db, email=email, password=password, timezone=timezone)
    print(f"Создан пользователь {user.email} ({user.id}), TZ {user.timezone}")


async def _set_password(email: str) -> None:
    async with session_factory() as db:
        user = await users.get_user_by_email(db, email)
        if user is None:
            sys.exit(f"Пользователь {email} не найден")
        await users.set_password(db, user, _read_password())
    print(f"Пароль для {email} обновлён")


async def _roll_series() -> None:
    async with session_factory() as db:
        created = await roll_all_users(db)
        subtasks = await roll_all_recurring_tasks(db)
    print(f"Создано вхождений: {created}, подзадач регулярных заданий: {subtasks}")


def _vapid_keys() -> None:
    """Пара ключей P-256 в формате, который ждут браузер (applicationServerKey) и pywebpush."""
    import base64

    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    print(f"VAPID_PUBLIC_KEY={b64(public)}")
    print(f"VAPID_PRIVATE_KEY={b64(private)}")


async def _run(args: argparse.Namespace) -> None:
    try:
        if args.command == "create-user":
            await _create_user(args.email, args.timezone)
        elif args.command == "set-password":
            await _set_password(args.email)
        elif args.command == "roll-series":
            await _roll_series()
    except (AppError, ValueError) as exc:
        sys.exit(f"Ошибка: {exc}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user", help="создать пользователя")
    create.add_argument("email")
    create.add_argument("--timezone", default=settings.DEFAULT_TIMEZONE)

    setpw = sub.add_parser("set-password", help="сменить пароль")
    setpw.add_argument("email")

    sub.add_parser("roll-series", help="докатить повторы и регулярные задания")
    sub.add_parser("vapid-keys", help="сгенерировать VAPID-ключи для Web Push")

    args = parser.parse_args()
    if args.command == "vapid-keys":
        _vapid_keys()
        return
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
