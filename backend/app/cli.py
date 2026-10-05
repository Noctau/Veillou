"""Админские команды.

    python -m app.cli create-user me@example.com [--timezone Europe/Moscow]
    python -m app.cli set-password me@example.com

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


async def _run(args: argparse.Namespace) -> None:
    try:
        if args.command == "create-user":
            await _create_user(args.email, args.timezone)
        elif args.command == "set-password":
            await _set_password(args.email)
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

    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
