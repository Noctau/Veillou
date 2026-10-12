"""M15.2: открытые типы действий (свои без ключа, prefer_morning, тип по умолчанию)

- `action_types.key` — nullable (только сид), флаг `prefer_morning` (бывшая логика на
  ключе `people`);
- `settings.default_action_type_id` — бывшая «Самостоятельная учёба»;
- калибровка — по `action_type_id` (старая колонка `action_type` уходит в contract);
- шаги шаблонов разбивки — `action_type_id` вместо ключа;
- чип ящика «часы учреждений» → `backlog_items.hours_action_type_id` (окна этого типа).

Revision ID: bc784b67db01
Revises: cc7d94f8bf9c
Create Date: 2026-10-11 10:10:00.000000

"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bc784b67db01"
down_revision: str | Sequence[str] | None = "cc7d94f8bf9c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rewrite_steps(bind: sa.Connection, convert: Any) -> None:
    """Шаги шаблонов: `convert(step, types)` → новый шаг; types — (user_id) → {key: id}."""
    types: dict[Any, dict[str, str]] = {}
    for user_id, key, id in bind.execute(
        sa.text("SELECT user_id, key, id FROM action_types WHERE deleted_at IS NULL")
    ):
        types.setdefault(user_id, {})[key] = str(id)
    rows = bind.execute(sa.text("SELECT id, user_id, steps FROM breakdown_templates")).all()
    for id, user_id, steps in rows:
        new = [convert(dict(s), types.get(user_id, {})) for s in steps or []]
        bind.execute(
            sa.text("UPDATE breakdown_templates SET steps = CAST(:steps AS jsonb) WHERE id = :id"),
            {"steps": json.dumps(new, ensure_ascii=False), "id": id},
        )


def upgrade() -> None:
    bind = op.get_bind()
    op.alter_column("action_types", "key", existing_type=sa.String(length=20), nullable=True)
    op.drop_index(
        "uq_action_types_user_key",
        table_name="action_types",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_action_types_user_key",
        "action_types",
        ["user_id", "key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND key IS NOT NULL"),
    )
    op.add_column(
        "action_types",
        sa.Column("prefer_morning", sa.Boolean(), server_default="false", nullable=False),
    )
    bind.execute(sa.text("UPDATE action_types SET prefer_morning = true WHERE key = 'people'"))

    # Тип по умолчанию — бывшая «Самостоятельная учёба»
    bind.execute(
        sa.text(
            "UPDATE users u SET settings = jsonb_set(COALESCE(u.settings, '{}'::jsonb), "
            "'{default_action_type_id}', to_jsonb(a.id::text)) "
            "FROM action_types a "
            "WHERE a.user_id = u.id AND a.key = 'study' AND a.deleted_at IS NULL"
        )
    )

    op.add_column("calibrations", sa.Column("action_type_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_calibrations_action_type_id_action_types"),
        "calibrations",
        "action_types",
        ["action_type_id"],
        ["id"],
        ondelete="CASCADE",
    )
    bind.execute(
        sa.text(
            "UPDATE calibrations c SET action_type_id = a.id FROM action_types a "
            "WHERE a.user_id = c.user_id AND a.key = c.action_type AND a.deleted_at IS NULL"
        )
    )

    def to_id(step: dict[str, Any], types: dict[str, str]) -> dict[str, Any]:
        key = step.pop("action_type", None)
        step["action_type_id"] = types.get(key) if key else None
        return step

    _rewrite_steps(bind, to_id)

    op.add_column("backlog_items", sa.Column("hours_action_type_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_backlog_items_hours_action_type_id_action_types"),
        "backlog_items",
        "action_types",
        ["hours_action_type_id"],
        ["id"],
        ondelete="SET NULL",
    )
    bind.execute(
        sa.text(
            "UPDATE backlog_items b SET hours_action_type_id = a.id FROM action_types a "
            "WHERE b.conditions ? 'institution_hours' AND a.user_id = b.user_id "
            "AND a.key = 'institutions' AND a.deleted_at IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE backlog_items SET conditions = conditions - 'institution_hours' "
            "WHERE conditions ? 'institution_hours'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE backlog_items SET conditions = conditions || '[\"institution_hours\"]'::jsonb "
            "WHERE hours_action_type_id IS NOT NULL"
        )
    )
    op.drop_constraint(
        op.f("fk_backlog_items_hours_action_type_id_action_types"),
        "backlog_items",
        type_="foreignkey",
    )
    op.drop_column("backlog_items", "hours_action_type_id")

    def to_key(step: dict[str, Any], types: dict[str, str]) -> dict[str, Any]:
        id = step.pop("action_type_id", None)
        step["action_type"] = next((k for k, v in types.items() if v == id and k), None)
        return step

    _rewrite_steps(bind, to_key)

    op.drop_constraint(
        op.f("fk_calibrations_action_type_id_action_types"), "calibrations", type_="foreignkey"
    )
    op.drop_column("calibrations", "action_type_id")
    bind.execute(sa.text("UPDATE users SET settings = settings - 'default_action_type_id'"))
    op.drop_column("action_types", "prefer_morning")
    # Свои типы без ключа в Part 1 невозможны: прячем их, ключ — чтобы пройти NOT NULL
    bind.execute(
        sa.text(
            "UPDATE action_types SET key = 'c' || left(replace(id::text, '-', ''), 12), "
            "deleted_at = COALESCE(deleted_at, now()) WHERE key IS NULL"
        )
    )
    op.drop_index(
        "uq_action_types_user_key",
        table_name="action_types",
        postgresql_where=sa.text("deleted_at IS NULL AND key IS NOT NULL"),
    )
    op.create_index(
        "uq_action_types_user_key",
        "action_types",
        ["user_id", "key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.alter_column("action_types", "key", existing_type=sa.String(length=20), nullable=False)
