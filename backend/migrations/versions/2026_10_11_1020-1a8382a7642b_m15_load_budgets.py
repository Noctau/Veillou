"""M15.3: лимиты нагрузки вместо единого лимита учёбы

`load_budgets`, `load_budget_members`, `budget_day_overrides`. Пользователю Part 1 —
лимит «Учёба» (бывший `study_limit_min_per_day`, по умолчанию 360) с участником
«Самостоятельная учёба»; разовые лимиты дня (`study_day_limits`) → переопределения.
Старая таблица и ключ настроек уходят в contract.

Revision ID: 1a8382a7642b
Revises: bc784b67db01
Create Date: 2026-10-11 10:20:00.000000

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a8382a7642b"
down_revision: str | Sequence[str] | None = "bc784b67db01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STUDY_LIMIT_DEFAULT = 360


def _common(table: str) -> list[sa.Column[Any] | sa.Constraint]:
    return [
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f(f"fk_{table}_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def upgrade() -> None:
    op.create_table(
        "load_budgets",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("minutes_per_day", sa.Integer(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        *_common("load_budgets"),
    )
    op.create_index(op.f("ix_load_budgets_user_id"), "load_budgets", ["user_id"], unique=False)

    op.create_table(
        "load_budget_members",
        sa.Column("budget_id", sa.Uuid(), nullable=False),
        sa.Column("action_type_id", sa.Uuid(), nullable=True),
        *_common("load_budget_members"),
        sa.ForeignKeyConstraint(
            ["budget_id"],
            ["load_budgets.id"],
            name=op.f("fk_load_budget_members_budget_id_load_budgets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["action_type_id"],
            ["action_types.id"],
            name=op.f("fk_load_budget_members_action_type_id_action_types"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_load_budget_members_user_id"), "load_budget_members", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_load_budget_members_budget_id"), "load_budget_members", ["budget_id"], unique=False
    )
    op.create_index(
        "uq_load_budget_members_action_type",
        "load_budget_members",
        ["budget_id", "action_type_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "budget_day_overrides",
        sa.Column("budget_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        *_common("budget_day_overrides"),
        sa.ForeignKeyConstraint(
            ["budget_id"],
            ["load_budgets.id"],
            name=op.f("fk_budget_day_overrides_budget_id_load_budgets"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_budget_day_overrides_user_id"), "budget_day_overrides", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_budget_day_overrides_budget_id"),
        "budget_day_overrides",
        ["budget_id"],
        unique=False,
    )
    op.create_index(
        "uq_budget_day_overrides_budget_date",
        "budget_day_overrides",
        ["budget_id", "date"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ---------- backfill: лимит «Учёба» ----------
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO load_budgets (id, user_id, name, minutes_per_day, position) "
            "SELECT gen_random_uuid(), a.user_id, 'Учёба', "
            "COALESCE((u.settings->>'study_limit_min_per_day')::int, :default), 0 "
            "FROM action_types a JOIN users u ON u.id = a.user_id "
            "WHERE a.key = 'study' AND a.deleted_at IS NULL"
        ),
        {"default": STUDY_LIMIT_DEFAULT},
    )
    bind.execute(
        sa.text(
            "INSERT INTO load_budget_members (id, user_id, budget_id, action_type_id) "
            "SELECT gen_random_uuid(), b.user_id, b.id, a.id "
            "FROM load_budgets b JOIN action_types a ON a.user_id = b.user_id "
            "WHERE a.key = 'study' AND a.deleted_at IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO budget_day_overrides (id, user_id, budget_id, date, minutes, "
            "created_at, updated_at) "
            "SELECT gen_random_uuid(), l.user_id, b.id, l.date, l.minutes, l.created_at, "
            "l.updated_at FROM study_day_limits l JOIN load_budgets b ON b.user_id = l.user_id "
            "WHERE l.deleted_at IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "uq_budget_day_overrides_budget_date",
        table_name="budget_day_overrides",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(op.f("ix_budget_day_overrides_budget_id"), table_name="budget_day_overrides")
    op.drop_index(op.f("ix_budget_day_overrides_user_id"), table_name="budget_day_overrides")
    op.drop_table("budget_day_overrides")
    op.drop_index(
        "uq_load_budget_members_action_type",
        table_name="load_budget_members",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(op.f("ix_load_budget_members_budget_id"), table_name="load_budget_members")
    op.drop_index(op.f("ix_load_budget_members_user_id"), table_name="load_budget_members")
    op.drop_table("load_budget_members")
    op.drop_index(op.f("ix_load_budgets_user_id"), table_name="load_budgets")
    op.drop_table("load_budgets")
