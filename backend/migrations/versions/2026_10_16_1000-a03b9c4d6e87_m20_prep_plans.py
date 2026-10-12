"""M20.1: подготовка к событию вместо экзаменов (expand + backfill)

Переименование на месте (id и ссылки сохраняются):
- `exams` → `prep_plans`: `prep_days` → `start_days_before`, `plan_enabled` → `enabled`,
  + `event_id` (событие экзамена — бывшее `events.source_type = 'exam'`), `date` (план без
  события — дата экзамена), `strategy` (`spaced`); `area_id` — необязательная;
- `exam_questions` → `prep_items` (`exam_id` → `plan_id`);
- `exam_sessions` → `prep_sessions` (`exam_id` → `plan_id`, `question_ids` → `item_ids`);
- `events.source_type`: `exam_session` → `prep_session`; `exam` → без источника
  (событие экзамена — обычное событие, план ссылается на него сам);
- `plan_revisions`: причина `exam` → `prep`, ожидающее превью устарело (в нём старые
  источники); то же — у ожидающих джоб превью.

Колонки экзамена (`starts_at`, `duration_min`, `location`) удаляет contract-миграция
M20. Заодно: у `slot_grids.name` нет серверного умолчания (расхождение модели из M17).

Revision ID: a03b9c4d6e87
Revises: 9f2a8b3c5d76
Create Date: 2026-10-16 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a03b9c4d6e87"
down_revision: str | Sequence[str] | None = "9f2a8b3c5d76"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (таблица, старое имя, новое имя) — ограничения и индексы
RENAMES = {
    "constraints": [
        ("prep_plans", "pk_exams", "pk_prep_plans"),
        ("prep_plans", "fk_exams_area_id_areas", "fk_prep_plans_area_id_areas"),
        ("prep_plans", "fk_exams_user_id_users", "fk_prep_plans_user_id_users"),
        ("prep_items", "pk_exam_questions", "pk_prep_items"),
        ("prep_items", "fk_exam_questions_exam_id_exams", "fk_prep_items_plan_id_prep_plans"),
        ("prep_items", "fk_exam_questions_user_id_users", "fk_prep_items_user_id_users"),
        ("prep_sessions", "pk_exam_sessions", "pk_prep_sessions"),
        (
            "prep_sessions",
            "fk_exam_sessions_exam_id_exams",
            "fk_prep_sessions_plan_id_prep_plans",
        ),
        ("prep_sessions", "fk_exam_sessions_user_id_users", "fk_prep_sessions_user_id_users"),
    ],
    "indexes": [
        ("ix_exams_area_id", "ix_prep_plans_area_id"),
        ("ix_exams_user_id", "ix_prep_plans_user_id"),
        ("ix_exam_questions_exam_id", "ix_prep_items_plan_id"),
        ("ix_exam_questions_exam_number", "ix_prep_items_plan_number"),
        ("ix_exam_questions_user_id", "ix_prep_items_user_id"),
        ("ix_exam_sessions_exam_id", "ix_prep_sessions_plan_id"),
        ("ix_exam_sessions_user_id", "ix_prep_sessions_user_id"),
        ("uq_exam_sessions_key", "uq_prep_sessions_key"),
    ],
}
TABLES = [
    ("exams", "prep_plans"),
    ("exam_questions", "prep_items"),
    ("exam_sessions", "prep_sessions"),
]


def _rename_all(forward: bool) -> None:
    tables = TABLES if forward else [(b, a) for a, b in TABLES]
    for old, new in tables:
        op.rename_table(old, new)
    for table, old, new in RENAMES["constraints"]:
        if not forward:
            table = dict((b, a) for a, b in TABLES)[table]
            old, new = new, old
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"')
    for old, new in RENAMES["indexes"]:
        if not forward:
            old, new = new, old
        # Индекс первичного ключа переименовывается вместе с ограничением
        op.execute(f'ALTER INDEX IF EXISTS "{old}" RENAME TO "{new}"')


def upgrade() -> None:
    _rename_all(forward=True)
    op.alter_column("prep_plans", "prep_days", new_column_name="start_days_before")
    op.alter_column("prep_plans", "plan_enabled", new_column_name="enabled")
    op.alter_column("prep_plans", "area_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("prep_plans", sa.Column("event_id", sa.Uuid(), nullable=True))
    op.add_column("prep_plans", sa.Column("date", sa.Date(), nullable=True))
    op.add_column(
        "prep_plans",
        sa.Column("strategy", sa.String(length=10), server_default="spaced", nullable=False),
    )
    op.alter_column("prep_plans", "strategy", server_default=None)
    op.create_foreign_key(
        op.f("fk_prep_plans_event_id_events"),
        "prep_plans",
        "events",
        ["event_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_prep_plans_event_id"), "prep_plans", ["event_id"], unique=False)
    op.alter_column("prep_items", "exam_id", new_column_name="plan_id")
    op.alter_column("prep_sessions", "exam_id", new_column_name="plan_id")
    op.alter_column("prep_sessions", "question_ids", new_column_name="item_ids")

    # ---------- backfill ----------
    op.execute(
        "UPDATE prep_plans p SET event_id = e.id FROM events e "
        "WHERE e.source_type = 'exam' AND e.source_id = p.id AND e.user_id = p.user_id"
    )
    op.execute(
        "UPDATE prep_plans p SET date = (p.starts_at AT TIME ZONE u.timezone)::date "
        "FROM users u WHERE u.id = p.user_id AND p.event_id IS NULL"
    )
    op.execute("UPDATE events SET source_type = 'prep_session' WHERE source_type = 'exam_session'")
    op.execute("UPDATE events SET source_type = NULL, source_id = NULL WHERE source_type = 'exam'")
    op.execute("UPDATE plan_revisions SET status = 'superseded' WHERE status = 'proposed'")
    op.execute(
        "UPDATE plan_revisions SET reasons = (SELECT jsonb_agg(CASE WHEN r = 'exam' "
        "THEN 'prep' ELSE r END) FROM jsonb_array_elements_text(reasons) r) "
        "WHERE reasons ? 'exam'"
    )
    op.execute(
        "UPDATE jobs SET payload = jsonb_set(payload, '{reasons}', (SELECT jsonb_agg(CASE "
        "WHEN r = 'exam' THEN 'prep' ELSE r END) FROM jsonb_array_elements_text("
        "payload->'reasons') r)) WHERE status = 'pending' AND payload->'reasons' ? 'exam'"
    )
    op.alter_column("slot_grids", "name", server_default=None)


def downgrade() -> None:
    op.alter_column("slot_grids", "name", server_default=sa.text("''"))
    op.execute(
        "UPDATE jobs SET payload = jsonb_set(payload, '{reasons}', (SELECT jsonb_agg(CASE "
        "WHEN r = 'prep' THEN 'exam' ELSE r END) FROM jsonb_array_elements_text("
        "payload->'reasons') r)) WHERE status = 'pending' AND payload->'reasons' ? 'prep'"
    )
    op.execute(
        "UPDATE plan_revisions SET reasons = (SELECT jsonb_agg(CASE WHEN r = 'prep' "
        "THEN 'exam' ELSE r END) FROM jsonb_array_elements_text(reasons) r) "
        "WHERE reasons ? 'prep'"
    )
    op.execute("UPDATE plan_revisions SET status = 'superseded' WHERE status = 'proposed'")
    op.execute(
        "UPDATE events e SET source_type = 'exam', source_id = p.id FROM prep_plans p "
        "WHERE p.event_id = e.id"
    )
    op.execute("UPDATE events SET source_type = 'exam_session' WHERE source_type = 'prep_session'")
    # Экзамен Part 1 — всегда сфера и момент: планы без сферы не выражаются
    op.execute("DELETE FROM prep_plans WHERE area_id IS NULL")
    op.alter_column("prep_sessions", "item_ids", new_column_name="question_ids")
    op.alter_column("prep_sessions", "plan_id", new_column_name="exam_id")
    op.alter_column("prep_items", "plan_id", new_column_name="exam_id")
    op.drop_index(op.f("ix_prep_plans_event_id"), table_name="prep_plans")
    op.drop_constraint(op.f("fk_prep_plans_event_id_events"), "prep_plans", type_="foreignkey")
    for col in ("strategy", "date", "event_id"):
        op.drop_column("prep_plans", col)
    op.alter_column("prep_plans", "area_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("prep_plans", "enabled", new_column_name="plan_enabled")
    op.alter_column("prep_plans", "start_days_before", new_column_name="prep_days")
    _rename_all(forward=False)
