"""M17.2: периоды и сетки слотов (expand + backfill)

- `semesters` → `periods` на месте (id и ссылки сохраняются): `end_date` (конец
  сессии, без неё — последний день занятий), `cycle_weeks = 2`, `first_cycle_week`
  из `first_week_parity` (odd → 1, even → 2), `pauses` — дни после последнего дня
  занятий до конца сессии («Перерыв» до начала сессии и «Сессия»): правила в паузы
  не генерируются, как раньше пары не генерировались после `classes_end`;
- `bell_schedules` → `slot_grids`: `semester_id` → `period_id` (nullable), `name`
  («Звонки»); у сетки всегда есть общая строка (weekday = NULL) — на неё ссылаются
  правила расписания (у периода только с переопределениями дней — добавляется пустая);
- `days_off.period_id` (NULL — во всех периодах, так мигрируют все исключения);
- `areas.period_id` теперь ссылается на `periods`.

Старые колонки периода удаляет contract-миграция M17.

Revision ID: 4a7b3c8d0e21
Revises: 3e6f2a7b9c10
Create Date: 2026-10-13 10:10:00.000000

"""

import json
from collections.abc import Sequence
from datetime import date, timedelta

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4a7b3c8d0e21"
down_revision: str | Sequence[str] | None = "3e6f2a7b9c10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRID_NAME = "Звонки"
PAUSE_TITLE = "Сессия"
GAP_TITLE = "Перерыв"
ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def session_pauses(classes_end: date, start: date | None, end: date | None) -> list[dict[str, str]]:
    """Дни после последнего дня занятий до конца сессии: «Перерыв» до сессии (если
    есть) и «Сессия» — по паузам contract-миграция при откате восстановит даты."""
    if start is None or end is None or end <= classes_end:
        return []
    pauses = []
    if start > classes_end + timedelta(days=1):
        gap = {"from": classes_end + timedelta(days=1), "to": start - timedelta(days=1)}
        pauses.append({**gap, "title": GAP_TITLE})
    pauses.append(
        {"from": max(start, classes_end + timedelta(days=1)), "to": end, "title": PAUSE_TITLE}
    )
    return [{**p, "from": p["from"].isoformat(), "to": p["to"].isoformat()} for p in pauses]


def _rename(kind: str, old: str, new: str, table: str | None = None) -> None:
    if kind == "index":
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")
    else:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}")


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    bind = op.get_bind()

    # ---------- semesters → periods ----------
    op.rename_table("semesters", "periods")
    _rename("constraint", "pk_semesters", "pk_periods", "periods")
    _rename("constraint", "fk_semesters_user_id_users", "fk_periods_user_id_users", "periods")
    _rename("index", "ix_semesters_user_id", "ix_periods_user_id")
    _rename("constraint", "fk_areas_period_id_semesters", "fk_areas_period_id_periods", "areas")
    op.add_column("periods", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column(
        "periods",
        sa.Column("cycle_weeks", sa.SmallInteger(), server_default="1", nullable=False),
    )
    op.add_column(
        "periods",
        sa.Column("first_cycle_week", sa.SmallInteger(), server_default="1", nullable=False),
    )
    op.add_column(
        "periods", sa.Column("pauses", jsonb, server_default=sa.text("'[]'::jsonb"), nullable=False)
    )
    for column in ("cycle_weeks", "first_cycle_week", "pauses"):
        op.alter_column("periods", column, server_default=None)
    # Новые периоды не знают о «днях занятий» и чётности — до contract-миграции
    for column in ("classes_end", "first_week_parity"):
        op.alter_column("periods", column, nullable=True)

    update = sa.text(
        "UPDATE periods SET end_date = :end, cycle_weeks = 2, first_cycle_week = :first, "
        "pauses = CAST(:pauses AS jsonb) WHERE id = :id"
    )
    for row in bind.execute(
        sa.text(
            "SELECT id, classes_end, session_start, session_end, first_week_parity FROM periods"
        )
    ).all():
        pauses = session_pauses(row.classes_end, row.session_start, row.session_end)
        end = row.session_end if pauses else row.classes_end
        bind.execute(
            update,
            {
                "id": row.id,
                "end": end,
                "first": 2 if row.first_week_parity == "even" else 1,
                "pauses": json.dumps(pauses, ensure_ascii=False),
            },
        )
    op.alter_column("periods", "end_date", nullable=False)

    # ---------- bell_schedules → slot_grids ----------
    op.drop_index(
        "uq_bell_schedules_semester_weekday",
        table_name="bell_schedules",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.rename_table("bell_schedules", "slot_grids")
    _rename("constraint", "pk_bell_schedules", "pk_slot_grids", "slot_grids")
    _rename(
        "constraint", "fk_bell_schedules_user_id_users", "fk_slot_grids_user_id_users", "slot_grids"
    )
    _rename("index", "ix_bell_schedules_user_id", "ix_slot_grids_user_id")
    op.alter_column("slot_grids", "semester_id", new_column_name="period_id", nullable=True)
    _rename(
        "constraint",
        "fk_bell_schedules_semester_id_semesters",
        "fk_slot_grids_period_id_periods",
        "slot_grids",
    )
    _rename("index", "ix_bell_schedules_semester_id", "ix_slot_grids_period_id")
    op.add_column(
        "slot_grids",
        sa.Column("name", sa.String(length=100), server_default=GRID_NAME, nullable=False),
    )
    op.alter_column("slot_grids", "name", server_default="")
    op.create_index(
        "uq_slot_grids_group_weekday",
        "slot_grids",
        [
            "user_id",
            sa.literal_column(f"coalesce(period_id, '{ZERO_UUID}'::uuid)"),
            "name",
            sa.literal_column("coalesce(weekday, 0)"),
        ],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    bind.execute(
        sa.text(
            "INSERT INTO slot_grids (id, user_id, period_id, name, weekday, slots) "
            "SELECT DISTINCT ON (g.period_id) gen_random_uuid(), g.user_id, g.period_id, "
            "g.name, NULL, '[]'::jsonb FROM slot_grids g "
            "WHERE g.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM slot_grids d "
            "WHERE d.period_id = g.period_id AND d.weekday IS NULL AND d.deleted_at IS NULL)"
        )
    )

    # ---------- days_off.period_id ----------
    op.add_column("days_off", sa.Column("period_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_days_off_period_id"), "days_off", ["period_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_days_off_period_id_periods"),
        "days_off",
        "periods",
        ["period_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_constraint(op.f("fk_days_off_period_id_periods"), "days_off", type_="foreignkey")
    op.drop_index(op.f("ix_days_off_period_id"), table_name="days_off")
    op.drop_column("days_off", "period_id")

    # Сетки без периода в Part 1 не выражаются; из групп периода остаётся одна
    # (первая по имени), пустая общая строка, добавленная миграцией, — удаляется
    bind.execute(sa.text("DELETE FROM slot_grids WHERE period_id IS NULL"))
    bind.execute(
        sa.text(
            "DELETE FROM slot_grids g USING (SELECT period_id, min(name) AS name "
            "FROM slot_grids WHERE deleted_at IS NULL GROUP BY period_id) k "
            "WHERE g.period_id = k.period_id AND g.name <> k.name AND g.deleted_at IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM slot_grids WHERE weekday IS NULL AND slots = '[]'::jsonb "
            "AND deleted_at IS NULL"
        )
    )
    op.drop_index(
        "uq_slot_grids_group_weekday",
        table_name="slot_grids",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_column("slot_grids", "name")
    _rename("index", "ix_slot_grids_period_id", "ix_bell_schedules_semester_id")
    _rename(
        "constraint",
        "fk_slot_grids_period_id_periods",
        "fk_bell_schedules_semester_id_semesters",
        "slot_grids",
    )
    op.alter_column("slot_grids", "period_id", new_column_name="semester_id", nullable=False)
    _rename("index", "ix_slot_grids_user_id", "ix_bell_schedules_user_id")
    _rename(
        "constraint", "fk_slot_grids_user_id_users", "fk_bell_schedules_user_id_users", "slot_grids"
    )
    _rename("constraint", "pk_slot_grids", "pk_bell_schedules", "slot_grids")
    op.rename_table("slot_grids", "bell_schedules")
    op.create_index(
        "uq_bell_schedules_semester_weekday",
        "bell_schedules",
        ["semester_id", sa.literal_column("coalesce(weekday, 0)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Старые колонки периода заполнила contract-миграция при откате
    for column in ("classes_end", "first_week_parity"):
        op.alter_column("periods", column, nullable=False)
    op.drop_column("periods", "pauses")
    op.drop_column("periods", "first_cycle_week")
    op.drop_column("periods", "cycle_weeks")
    op.drop_column("periods", "end_date")
    _rename("constraint", "fk_areas_period_id_periods", "fk_areas_period_id_semesters", "areas")
    _rename("index", "ix_periods_user_id", "ix_semesters_user_id")
    _rename("constraint", "fk_periods_user_id_users", "fk_semesters_user_id_users", "periods")
    _rename("constraint", "pk_periods", "pk_semesters", "periods")
    op.rename_table("periods", "semesters")
