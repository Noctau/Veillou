"""M15.1: справочник типов задач вместо enum TaskType (expand + backfill)

Каждому пользователю — типы из enum Part 1 с прежними названиями и синонимами
быстрого ввода и тип «Задание с работы» (срок = выдача + 14 дней, проект бывшего
`is_work_default`, категория «Работа»). Ссылки `task_type_id` у заданий, калибровки
и шаблонов разбивки. `other` → NULL («без типа»). Задание без типа с датой выдачи —
бывшее «задание с работы».

Старые колонки удаляет contract-миграция M15.

Revision ID: cc7d94f8bf9c
Revises: d44f1cf514e5
Create Date: 2026-10-11 10:00:00.000000

"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "cc7d94f8bf9c"
down_revision: str | Sequence[str] | None = "d44f1cf514e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# key, название, иконка, синонимы (слова из quickparse.TASK_TYPES)
SEED = [
    ("homework", "ДЗ", "pencil", ["дз", "домашка", "домашнее задание", "упражнение"]),
    ("report", "Доклад", "presentation", ["доклад", "презентация", "выступление"]),
    ("essay", "Реферат", "file-text", ["реферат", "эссе"]),
    ("lab", "Лабораторная", "flask-conical", ["лаба", "лабораторная", "практикум"]),
    ("coursework", "Курсовая", "graduation-cap", ["курсовая", "курсач"]),
    ("reading", "Чтение", "book-open", ["прочитать", "дочитать", "чтение", "глава"]),
    (
        "exam_prep",
        "Подготовка к экзамену",
        "clipboard-check",
        ["экзамен", "зачёт", "коллоквиум", "контрольная"],
    ),
]
WORK = ("work", "Задание с работы", "briefcase")
WORK_RULE = {"kind": "days", "days": 14}


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
        "task_types",
        sa.Column("key", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=40), nullable=False),
        sa.Column("synonyms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("default_action_type_id", sa.Uuid(), nullable=True),
        sa.Column("default_category_id", sa.Uuid(), nullable=True),
        sa.Column("default_estimate_min", sa.Integer(), nullable=True),
        sa.Column("deadline_rule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("default_project_id", sa.Uuid(), nullable=True),
        sa.Column("default_template_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["default_action_type_id"],
            ["action_types.id"],
            name=op.f("fk_task_types_default_action_type_id_action_types"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["default_category_id"],
            ["categories.id"],
            name=op.f("fk_task_types_default_category_id_categories"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["default_project_id"],
            ["projects.id"],
            name=op.f("fk_task_types_default_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["default_template_id"],
            ["breakdown_templates.id"],
            name=op.f("fk_task_types_default_template_id_breakdown_templates"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_task_types_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_types")),
    )
    op.create_index(op.f("ix_task_types_user_id"), "task_types", ["user_id"], unique=False)
    op.create_index(
        "uq_task_types_user_key",
        "task_types",
        ["user_id", "key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND key IS NOT NULL"),
    )

    op.add_column("tasks", sa.Column("task_type_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_tasks_task_type_id"), "tasks", ["task_type_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_tasks_task_type_id_task_types"),
        "tasks",
        "task_types",
        ["task_type_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("calibrations", sa.Column("task_type_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_calibrations_task_type_id_task_types"),
        "calibrations",
        "task_types",
        ["task_type_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column("breakdown_templates", sa.Column("task_type_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_breakdown_templates_task_type_id_task_types"),
        "breakdown_templates",
        "task_types",
        ["task_type_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---------- backfill ----------
    bind = op.get_bind()
    seed = sa.text(
        "INSERT INTO task_types (id, user_id, key, name, icon, synonyms, position) "
        "SELECT gen_random_uuid(), u.id, :key, :name, :icon, CAST(:synonyms AS jsonb), :position "
        "FROM users u"
    )
    for position, (key, name, icon, synonyms) in enumerate(SEED):
        bind.execute(
            seed,
            {
                "key": key,
                "name": name,
                "icon": icon,
                "synonyms": json.dumps(synonyms, ensure_ascii=False),
                "position": position,
            },
        )
    key, name, icon = WORK
    bind.execute(
        sa.text(
            "INSERT INTO task_types (id, user_id, key, name, icon, synonyms, position, "
            "deadline_rule, default_project_id, default_category_id) "
            "SELECT gen_random_uuid(), u.id, :key, :name, :icon, '[]'::jsonb, :position, "
            "CAST(:rule AS jsonb), "
            "(SELECT p.id FROM projects p WHERE p.user_id = u.id AND p.deleted_at IS NULL "
            " AND p.is_work_default ORDER BY p.created_at LIMIT 1), "
            "(SELECT c.id FROM categories c WHERE c.user_id = u.id AND c.deleted_at IS NULL "
            " AND c.key = 'work' LIMIT 1) "
            "FROM users u"
        ),
        {
            "key": key,
            "name": name,
            "icon": icon,
            "position": len(SEED),
            "rule": json.dumps(WORK_RULE),
        },
    )
    for table, column in (
        ("tasks", "task_type"),
        ("calibrations", "task_type"),
        ("breakdown_templates", "task_type"),
    ):
        bind.execute(
            sa.text(
                f"UPDATE {table} x SET task_type_id = tt.id FROM task_types tt "  # noqa: S608  # nosec B608
                f"WHERE tt.user_id = x.user_id AND tt.key = x.{column} "
                "AND tt.deleted_at IS NULL AND tt.key <> 'work'"
            )
        )
    bind.execute(
        sa.text(
            "UPDATE tasks t SET task_type_id = tt.id FROM task_types tt "
            "WHERE t.task_type = 'other' AND t.issued_at IS NOT NULL "
            "AND tt.user_id = t.user_id AND tt.key = 'work' AND tt.deleted_at IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_breakdown_templates_task_type_id_task_types"),
        "breakdown_templates",
        type_="foreignkey",
    )
    op.drop_column("breakdown_templates", "task_type_id")
    op.drop_constraint(
        op.f("fk_calibrations_task_type_id_task_types"), "calibrations", type_="foreignkey"
    )
    op.drop_column("calibrations", "task_type_id")
    op.drop_constraint(op.f("fk_tasks_task_type_id_task_types"), "tasks", type_="foreignkey")
    op.drop_index(op.f("ix_tasks_task_type_id"), table_name="tasks")
    op.drop_column("tasks", "task_type_id")
    op.drop_index(
        "uq_task_types_user_key",
        table_name="task_types",
        postgresql_where=sa.text("deleted_at IS NULL AND key IS NOT NULL"),
    )
    op.drop_index(op.f("ix_task_types_user_id"), table_name="task_types")
    op.drop_table("task_types")
