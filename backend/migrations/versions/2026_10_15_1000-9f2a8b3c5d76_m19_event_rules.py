"""M19.1: автозадачи от событий

- `event_rules` — «до / после каждого вхождения создать задачу» у типа занятости
  или у правила расписания;
- `tasks`: `earliest` (не раньше), `deadline_auto` (срок «к следующему вхождению»
  пересчитывается сам), `origin_event_id`, `origin_rule_id` (+ одна живая задача на
  правило и вхождение). Статус задачи `proposed` — строка, схема не меняется.

Данных Part 1 миграция не трогает.

Revision ID: 9f2a8b3c5d76
Revises: 8e1f7a2b4c65
Create Date: 2026-10-15 10:00:00.000000

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f2a8b3c5d76"
down_revision: str | Sequence[str] | None = "8e1f7a2b4c65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[Any]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "event_rules",
        sa.Column("event_type_id", sa.Uuid(), nullable=True),
        sa.Column("schedule_rule_id", sa.Uuid(), nullable=True),
        sa.Column("when", sa.String(length=10), nullable=False),
        sa.Column("title_template", sa.String(length=300), nullable=False),
        sa.Column("estimate_min", sa.Integer(), nullable=False),
        sa.Column("action_type_id", sa.Uuid(), nullable=True),
        sa.Column("task_type_id", sa.Uuid(), nullable=True),
        sa.Column("offset_min", sa.Integer(), nullable=False),
        sa.Column("within_days", sa.SmallInteger(), nullable=True),
        sa.Column("until_next", sa.Boolean(), nullable=False),
        sa.Column("confirm", sa.Boolean(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["event_type_id"],
            ["event_types.id"],
            name=op.f("fk_event_rules_event_type_id_event_types"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["schedule_rule_id"],
            ["schedule_rules.id"],
            name=op.f("fk_event_rules_schedule_rule_id_schedule_rules"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["action_type_id"],
            ["action_types.id"],
            name=op.f("fk_event_rules_action_type_id_action_types"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_type_id"],
            ["task_types.id"],
            name=op.f("fk_event_rules_task_type_id_task_types"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_event_rules_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_rules")),
    )
    for col in ("user_id", "event_type_id", "schedule_rule_id"):
        op.create_index(op.f(f"ix_event_rules_{col}"), "event_rules", [col], unique=False)

    op.add_column("tasks", sa.Column("earliest", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("deadline_auto", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("tasks", "deadline_auto", server_default=None)
    op.add_column("tasks", sa.Column("origin_event_id", sa.Uuid(), nullable=True))
    op.add_column("tasks", sa.Column("origin_rule_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_tasks_origin_event_id_events"),
        "tasks",
        "events",
        ["origin_event_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_tasks_origin_rule_id_event_rules"),
        "tasks",
        "event_rules",
        ["origin_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_tasks_origin_event_id"), "tasks", ["origin_event_id"], unique=False)
    op.create_index(op.f("ix_tasks_origin_rule_id"), "tasks", ["origin_rule_id"], unique=False)
    op.create_index(
        "uq_tasks_origin",
        "tasks",
        ["origin_rule_id", "origin_event_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND origin_rule_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Предложения — не задачи Part 1: убираем, остальное остаётся обычными задачами
    op.execute("DELETE FROM tasks WHERE status = 'proposed'")
    op.drop_index(
        "uq_tasks_origin",
        table_name="tasks",
        postgresql_where=sa.text("deleted_at IS NULL AND origin_rule_id IS NOT NULL"),
    )
    op.drop_index(op.f("ix_tasks_origin_rule_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_origin_event_id"), table_name="tasks")
    op.drop_constraint(op.f("fk_tasks_origin_rule_id_event_rules"), "tasks", type_="foreignkey")
    op.drop_constraint(op.f("fk_tasks_origin_event_id_events"), "tasks", type_="foreignkey")
    for col in ("origin_rule_id", "origin_event_id", "deadline_auto", "earliest"):
        op.drop_column("tasks", col)
    for col in ("schedule_rule_id", "event_type_id", "user_id"):
        op.drop_index(op.f(f"ix_event_rules_{col}"), table_name="event_rules")
    op.drop_table("event_rules")
