"""Проверка миграций на данных (M14.2): `make migrate-check [dump=…/db.dump]`.

1. Пересоздаёт отдельную БД `<POSTGRES_DB>_migrate_check` на сервере из настроек.
2. Загружает данные:
   - по умолчанию — фикстуру студентки `tests/fixtures/student.sql`: схема поднимается
     миграциями до ревизии фикстуры, строки вставляются как есть;
   - с `--dump` — дамп `pg_dump -Fc` (бэкап, обезличенный): pg_restore схемы и данных
     вместе с `alembic_version`.
3. `upgrade head` → проверки → `downgrade -1` → `upgrade head` → проверки.

Проверки:
- ни одна таблица, пережившая upgrade, не потеряла строк (кроме `SHRINK_OK`);
- после downgrade/upgrade счётчики те же, что после первого upgrade;
- инварианты `INVARIANTS` (SQL, который должен вернуть 0) — пропускаются, если нужных
  таблиц уже нет: переименовал таблицу миграцией — перепиши инвариант под новую схему;
- у дочерней строки тот же `user_id`, что у родительской (по всем внешним ключам);
- в схеме нет `timestamp without time zone`;
- настройки каждого пользователя проходят `UserSettings`.
"""

import argparse
import asyncio
import json
import shutil
import subprocess  # nosec B404 — pg_restore / docker compose с фиксированными аргументами
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config

from app.core.config import REPO_ROOT, settings
from app.models import User
from app.services.settings import effective_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURE = BACKEND_DIR / "tests" / "fixtures" / "student.sql"
COMPOSE_FILE = REPO_ROOT / "docker-compose.dev.yml"

# Таблицы, которым миграция законно уменьшает число строк (схлопывание дублей и т. п.)
SHRINK_OK: frozenset[str] = frozenset()
# Служебное, что миграции не трогают, а приложение меняет само
IGNORE_TABLES = frozenset({"alembic_version"})


@dataclass(frozen=True)
class Invariant:
    name: str
    tables: frozenset[str]
    sql: str  # число нарушений


INVARIANTS = (
    Invariant(
        "событие не короче нуля",
        frozenset({"events"}),
        'SELECT count(*) FROM events WHERE "end" <= start',
    ),
    Invariant(
        "вхождение пары ссылается на живое правило",
        frozenset({"events", "class_rules"}),
        "SELECT count(*) FROM events e WHERE e.template_type = 'class_rule' "
        "AND e.deleted_at IS NULL AND NOT EXISTS "
        "(SELECT 1 FROM class_rules r WHERE r.id = e.template_id)",
    ),
    Invariant(
        "вхождение повтора ссылается на правило",
        frozenset({"events", "recurring_events"}),
        "SELECT count(*) FROM events e WHERE e.template_type = 'recurring' "
        "AND e.deleted_at IS NULL AND NOT EXISTS "
        "(SELECT 1 FROM recurring_events r WHERE r.id = e.template_id)",
    ),
    Invariant(
        "гибкий блок ссылается на источник",
        frozenset({"events"}),
        "SELECT count(*) FROM events WHERE NOT is_fixed AND deleted_at IS NULL "
        "AND (source_type IS NULL OR source_id IS NULL)",
    ),
    Invariant(
        "у вхождения шаблона есть дата вхождения",
        frozenset({"events"}),
        "SELECT count(*) FROM events WHERE template_id IS NOT NULL AND occurrence_date IS NULL",
    ),
    Invariant(
        "тип действия по умолчанию (настройки) — живой тип того же пользователя",
        frozenset({"users", "action_types"}),
        "SELECT count(*) FROM users u WHERE u.settings ? 'default_action_type_id' "
        "AND u.settings->>'default_action_type_id' IS NOT NULL AND NOT EXISTS ("
        "SELECT 1 FROM action_types a WHERE a.id::text = u.settings->>'default_action_type_id' "
        "AND a.user_id = u.id AND a.deleted_at IS NULL)",
    ),
    Invariant(
        "подзадача — в задании того же пользователя",
        frozenset({"subtasks", "tasks"}),
        "SELECT count(*) FROM subtasks s JOIN tasks t ON t.id = s.task_id "
        "WHERE s.deleted_at IS NULL AND t.deleted_at IS NULL AND s.user_id <> t.user_id",
    ),
)


class CheckError(Exception):
    pass


def _dsn(db: str) -> str:
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD.get_secret_value()}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{db}"
    )


def _alembic() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


def _run[T](fn: Callable[[asyncpg.Connection], Awaitable[T]], db: str) -> T:
    async def go() -> T:
        conn = await asyncpg.connect(_dsn(db))
        try:
            return await fn(conn)
        finally:
            await conn.close()

    return asyncio.run(go())


def recreate(db: str) -> None:
    async def go(conn: asyncpg.Connection) -> None:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{db}"')

    _run(go, "postgres")


def fixture_revision(path: Path) -> str:
    for line in path.read_text().splitlines():
        if line.startswith("-- revision: "):
            return line.removeprefix("-- revision: ").strip()
    raise CheckError(f"{path}: нет строки «-- revision: …»")


def load_fixture(db: str, path: Path) -> None:
    sql = path.read_text()

    async def go(conn: asyncpg.Connection) -> None:
        async with conn.transaction():
            await conn.execute(sql)

    _run(go, db)


def restore_dump(db: str, dump: Path) -> None:
    """pg_restore: локальный, если есть, иначе — внутри контейнера dev-БД."""
    args = ["--no-owner", "--no-acl", "--exit-on-error"]
    if pg_restore := shutil.which("pg_restore"):
        cmd = [pg_restore, *args, "-d", _dsn(db), str(dump)]
        subprocess.run(cmd, check=True)  # noqa: S603  # nosec B603
        return
    docker = shutil.which("docker")
    if docker is None:
        raise CheckError("нужен pg_restore или docker")
    cmd = [
        docker, "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "db",
        "pg_restore", *args, "-U", settings.POSTGRES_USER, "-d", db,
    ]  # fmt: skip
    with dump.open("rb") as stdin:
        subprocess.run(cmd, check=True, stdin=stdin)  # noqa: S603  # nosec B603


async def _counts(conn: asyncpg.Connection) -> dict[str, int]:
    tables = await conn.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
    )
    result = {}
    for row in tables:
        name = row["table_name"]
        if name not in IGNORE_TABLES:
            result[name] = await conn.fetchval(f'SELECT count(*) FROM "{name}"')  # noqa: S608
    return result


def counts(db: str) -> dict[str, int]:
    return _run(_counts, db)


async def _violations(conn: asyncpg.Connection) -> list[str]:
    tables = set(await _counts(conn))
    problems: list[str] = []

    naive = await conn.fetch(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND data_type = 'timestamp without time zone'"
    )
    problems += [f"timestamp без зоны: {r['table_name']}.{r['column_name']}" for r in naive]

    for inv in INVARIANTS:
        if not inv.tables <= tables:
            print(f"  · пропущено (нет таблиц {sorted(inv.tables - tables)}): {inv.name}")
            continue
        if n := await conn.fetchval(inv.sql):
            problems.append(f"{inv.name}: {n}")

    # Внешний ключ между таблицами пользователя — строки одного и того же пользователя
    fks = await conn.fetch(
        """
        SELECT tc.table_name AS child, kcu.column_name AS col, ccu.table_name AS parent
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
          AND ccu.column_name = 'id'
        """
    )
    owned = {
        r["table_name"]
        for r in await conn.fetch(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'user_id'"
        )
    }
    for fk in fks:
        child, col, parent = fk["child"], fk["col"], fk["parent"]
        if child in owned and parent in owned and col != "user_id":
            n = await conn.fetchval(
                f'SELECT count(*) FROM "{child}" c JOIN "{parent}" p ON p.id = c."{col}" '  # noqa: S608  # nosec B608
                "WHERE c.user_id <> p.user_id"
            )
            if n:
                problems.append(f"{child}.{col} → {parent}: чужой user_id у {n} строк")

    for row in await conn.fetch("SELECT id, settings FROM users WHERE deleted_at IS NULL"):
        raw = row["settings"]
        user = User(settings=json.loads(raw) if isinstance(raw, str) else raw)
        try:
            effective_settings(user)
        except ValueError as exc:
            problems.append(f"настройки пользователя {row['id']} не проходят UserSettings: {exc}")
    return problems


def check(db: str, stage: str) -> dict[str, int]:
    print(f"\n== проверки: {stage}")
    problems = _run(_violations, db)
    for p in problems:
        print(f"  ✗ {p}")
    if problems:
        raise CheckError(f"{stage}: нарушено инвариантов — {len(problems)}")
    print("  ✓ инварианты")
    return counts(db)


def compare(before: dict[str, int], after: dict[str, int], stage: str, *, exact: bool) -> None:
    lost = [
        f"{t}: {before[t]} → {after[t]}"
        for t in sorted(before.keys() & after.keys())
        if (after[t] != before[t] if exact else after[t] < before[t]) and t not in SHRINK_OK
    ]
    if lost:
        raise CheckError(f"{stage}: изменилось число строк — " + "; ".join(lost))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument("--dump", type=Path, help="дамп pg_dump -Fc вместо фикстуры")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args(argv)

    db = f"{settings.POSTGRES_DB}_migrate_check"
    print(f"БД {db} на {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}")
    recreate(db)
    # env.py берёт адрес из настроек: переключаем их на проверочную БД
    settings.POSTGRES_DB = db
    cfg = _alembic()
    try:
        if args.dump:
            dump = args.dump.expanduser()
            dump = dump if dump.is_absolute() else REPO_ROOT / dump
            print(f"Данные: дамп {dump}")
            restore_dump(db, dump)
        else:
            revision = fixture_revision(args.fixture)
            print(f"Данные: фикстура {args.fixture.name} (ревизия {revision})")
            command.upgrade(cfg, revision)
            load_fixture(db, args.fixture)
        loaded = counts(db)

        command.upgrade(cfg, "head")
        upgraded = check(db, "upgrade head")
        compare(loaded, upgraded, "upgrade head", exact=False)

        command.downgrade(cfg, "-1")
        command.upgrade(cfg, "head")
        again = check(db, "downgrade -1 → upgrade head")
        compare(upgraded, again, "downgrade -1 → upgrade head", exact=True)
    except (CheckError, subprocess.CalledProcessError) as exc:
        print(f"\nmigrate-check: ПРОВАЛ — {exc}", file=sys.stderr)
        return 1

    width = max(map(len, again))
    print("\n== строки по таблицам (загружено → после проверки)")
    for table in sorted(again):
        print(f"  {table:<{width}}  {loaded.get(table, '—'):>6} → {again[table]:>6}")
    print("\nmigrate-check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
