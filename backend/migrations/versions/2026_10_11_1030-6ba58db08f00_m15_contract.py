"""M15 contract: удаление старого после переключения кода

- `tasks.task_type`, `breakdown_templates.task_type` → `task_type_id`;
- `calibrations.task_type` / `action_type` → `task_type_id` / `action_type_id`
  (уникальность — NULLS NOT DISTINCT: NULL = «без типа»);
- `projects.is_work_default` → тип задачи «Задание с работы»;
- `study_day_limits` и `settings.study_limit_min_per_day` → лимиты нагрузки.

Revision ID: 6ba58db08f00
Revises: 1a8382a7642b
Create Date: 2026-10-11 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6ba58db08f00"
down_revision: str | Sequence[str] | None = "1a8382a7642b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Ключи enum TaskType Part 1 (кроме other — это NULL)
TASK_TYPE_KEYS = ("homework", "report", "essay", "lab", "coursework", "reading", "exam_prep")


def upgrade() -> None:
    bind = op.get_bind()
    op.drop_column("tasks", "task_type")
    op.drop_column("breakdown_templates", "task_type")

    op.drop_index(
        "uq_calibrations_user_key",
        table_name="calibrations",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_column("calibrations", "task_type")
    op.drop_column("calibrations", "action_type")
    op.create_index(
        "uq_calibrations_user_key",
        "calibrations",
        ["user_id", "task_type_id", "action_type_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        postgresql_nulls_not_distinct=True,
    )

    op.drop_index(
        "uq_projects_user_work_default",
        table_name="projects",
        postgresql_where=sa.text("deleted_at IS NULL AND is_work_default"),
    )
    op.drop_column("projects", "is_work_default")

    op.drop_index(
        "uq_study_day_limits_user_date",
        table_name="study_day_limits",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(op.f("ix_study_day_limits_user_id"), table_name="study_day_limits")
    op.drop_table("study_day_limits")
    bind.execute(sa.text("UPDATE users SET settings = settings - 'study_limit_min_per_day'"))


def downgrade() -> None:
    bind = op.get_bind()
    # ---------- лимит учёбы ----------
    op.create_table(
        "study_day_limits",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_study_day_limits_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_study_day_limits")),
    )
    op.create_index(
        op.f("ix_study_day_limits_user_id"), "study_day_limits", ["user_id"], unique=False
    )
    op.create_index(
        "uq_study_day_limits_user_date",
        "study_day_limits",
        ["user_id", "date"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # Лимит, где участвует тип по умолчанию (или первый по порядку)
    bind.execute(
        sa.text(
            "WITH mb AS ("
            " SELECT DISTINCT ON (b.user_id) b.user_id, b.id FROM load_budgets b"
            " JOIN users u ON u.id = b.user_id"
            " LEFT JOIN load_budget_members m ON m.budget_id = b.id AND m.deleted_at IS NULL"
            " AND m.action_type_id::text = u.settings->>'default_action_type_id'"
            " WHERE b.deleted_at IS NULL"
            " ORDER BY b.user_id, (m.id IS NULL), b.position, b.created_at) "
            "INSERT INTO study_day_limits (id, user_id, date, minutes, created_at, updated_at) "
            "SELECT gen_random_uuid(), o.user_id, o.date, o.minutes, o.created_at, o.updated_at "
            "FROM budget_day_overrides o JOIN mb ON mb.id = o.budget_id "
            "WHERE o.deleted_at IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "WITH mb AS ("
            " SELECT DISTINCT ON (b.user_id) b.user_id, b.minutes_per_day FROM load_budgets b"
            " JOIN users u ON u.id = b.user_id"
            " LEFT JOIN load_budget_members m ON m.budget_id = b.id AND m.deleted_at IS NULL"
            " AND m.action_type_id::text = u.settings->>'default_action_type_id'"
            " WHERE b.deleted_at IS NULL"
            " ORDER BY b.user_id, (m.id IS NULL), b.position, b.created_at) "
            "UPDATE users u SET settings = jsonb_set(COALESCE(u.settings, '{}'::jsonb), "
            "'{study_limit_min_per_day}', to_jsonb(GREATEST(30, LEAST(960, mb.minutes_per_day)))) "
            "FROM mb WHERE mb.user_id = u.id"
        )
    )

    # ---------- проект для заданий с работы ----------
    op.add_column(
        "projects",
        sa.Column("is_work_default", sa.Boolean(), server_default="false", nullable=False),
    )
    bind.execute(
        sa.text(
            "UPDATE projects p SET is_work_default = true FROM ("
            " SELECT DISTINCT ON (tt.user_id) tt.default_project_id AS id FROM task_types tt"
            " WHERE tt.deleted_at IS NULL AND tt.deadline_rule IS NOT NULL"
            " AND tt.default_project_id IS NOT NULL"
            " ORDER BY tt.user_id, (tt.key = 'work') DESC, tt.position) w "
            "WHERE p.id = w.id"
        )
    )
    op.create_index(
        "uq_projects_user_work_default",
        "projects",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND is_work_default"),
    )

    # ---------- калибровка по ключам ----------
    op.drop_index(
        "uq_calibrations_user_key",
        table_name="calibrations",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.add_column(
        "calibrations",
        sa.Column("task_type", sa.String(length=20), server_default="other", nullable=False),
    )
    op.add_column(
        "calibrations",
        sa.Column("action_type", sa.String(length=20), server_default="study", nullable=False),
    )
    keys = {"keys": list(TASK_TYPE_KEYS)}
    bind.execute(
        sa.text(
            "UPDATE calibrations c SET task_type = tt.key FROM task_types tt "
            "WHERE tt.id = c.task_type_id AND tt.key = ANY(:keys)"
        ),
        keys,
    )
    bind.execute(
        sa.text(
            "UPDATE calibrations c SET action_type = a.key FROM action_types a "
            "WHERE a.id = c.action_type_id AND a.key IS NOT NULL"
        )
    )
    # Разные id могли схлопнуться в один ключ — оставляем строку с большим числом отметок
    bind.execute(
        sa.text(
            "DELETE FROM calibrations c USING calibrations d "
            "WHERE c.user_id = d.user_id AND c.task_type = d.task_type "
            "AND c.action_type = d.action_type AND c.deleted_at IS NULL AND d.deleted_at IS NULL "
            "AND (c.samples, c.id::text) < (d.samples, d.id::text)"
        )
    )
    op.create_index(
        "uq_calibrations_user_key",
        "calibrations",
        ["user_id", "task_type", "action_type"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ---------- тип задания ключом ----------
    op.add_column(
        "breakdown_templates", sa.Column("task_type", sa.String(length=20), nullable=True)
    )
    bind.execute(
        sa.text(
            "UPDATE breakdown_templates t SET task_type = tt.key FROM task_types tt "
            "WHERE tt.id = t.task_type_id AND tt.key = ANY(:keys)"
        ),
        keys,
    )
    op.add_column(
        "tasks",
        sa.Column("task_type", sa.String(length=20), server_default="other", nullable=False),
    )
    bind.execute(
        sa.text(
            "UPDATE tasks t SET task_type = tt.key FROM task_types tt "
            "WHERE tt.id = t.task_type_id AND tt.key = ANY(:keys)"
        ),
        keys,
    )
