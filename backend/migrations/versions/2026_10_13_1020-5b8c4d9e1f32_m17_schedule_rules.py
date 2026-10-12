"""M17.4: правила расписания (expand + backfill)

- `schedule_rules` вместо `class_rules` и `recurring_events`; id правил те же, так
  что вхождения в `events` остаются привязанными (`template_type` → schedule_rule);
- правило пары → тип «Пара», паттерн weekly с маской недель цикла из `parity`
  (odd → [1], even → [2]), слот из `pair_number` (сетка — общая строка звонков
  периода), своё время — как есть, `class_type` / `teacher` → поля;
- личный повтор → тип «Личное» / «Отдых»; простой «FREQ=WEEKLY;BYDAY=…» → weekly,
  остальное — rrule; `start_date` / `until` → `valid_from` / `valid_to`.

Старые таблицы удаляет contract-миграция M17.

Revision ID: 5b8c4d9e1f32
Revises: 4a7b3c8d0e21
Create Date: 2026-10-13 10:20:00.000000

"""

import json
import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5b8c4d9e1f32"
down_revision: str | Sequence[str] | None = "4a7b3c8d0e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLASS_TYPES = {"lecture": "лекция", "seminar": "семинар", "lab": "лаба"}
DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
_WEEKLY = re.compile(
    r"^FREQ=WEEKLY;BYDAY=((?:MO|TU|WE|TH|FR|SA|SU)(?:,(?:MO|TU|WE|TH|FR|SA|SU))*)$"
)


def class_pattern(weekday: int, parity: str) -> dict[str, Any]:
    mask = {"odd": [1], "even": [2]}.get(parity)
    return {"kind": "weekly", "weekdays": [weekday], "cycle_weeks": mask}


def rrule_pattern(value: str) -> dict[str, Any]:
    text = value.strip().removeprefix("RRULE:").upper()
    if m := _WEEKLY.match(text):
        days = sorted({DAYS.index(d) + 1 for d in m.group(1).split(",")})
        return {"kind": "weekly", "weekdays": days, "cycle_weeks": None}
    return {"kind": "rrule", "rrule": value.strip().removeprefix("RRULE:")}


def rule_fields(class_type: str | None, teacher: str | None) -> dict[str, str]:
    fields = {}
    if class_type in CLASS_TYPES:
        fields["class_type"] = CLASS_TYPES[class_type]
    if teacher and teacher.strip():
        fields["teacher"] = teacher.strip()
    return fields


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "schedule_rules",
        sa.Column("event_type_id", sa.Uuid(), nullable=False),
        sa.Column("area_id", sa.Uuid(), nullable=True),
        sa.Column("period_id", sa.Uuid(), nullable=True),
        sa.Column("slot_grid_id", sa.Uuid(), nullable=True),
        sa.Column("pattern", jsonb, nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("slot_from", sa.SmallInteger(), nullable=True),
        sa.Column("slot_to", sa.SmallInteger(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("fields", jsonb, nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
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
            ["area_id"],
            ["areas.id"],
            name=op.f("fk_schedule_rules_area_id_areas"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_type_id"],
            ["event_types.id"],
            name=op.f("fk_schedule_rules_event_type_id_event_types"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["periods.id"],
            name=op.f("fk_schedule_rules_period_id_periods"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["slot_grid_id"],
            ["slot_grids.id"],
            name=op.f("fk_schedule_rules_slot_grid_id_slot_grids"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_schedule_rules_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedule_rules")),
    )
    for column in ("area_id", "event_type_id", "period_id", "user_id"):
        op.create_index(
            op.f(f"ix_schedule_rules_{column}"), "schedule_rules", [column], unique=False
        )

    bind = op.get_bind()
    insert = sa.text(
        "INSERT INTO schedule_rules (id, event_type_id, area_id, period_id, slot_grid_id, "
        "pattern, start_time, end_time, slot_from, slot_to, valid_from, valid_to, title, "
        "location, color, fields, note, user_id, created_at, updated_at, deleted_at) "
        "VALUES (:id, :event_type_id, :area_id, "
        ":period_id, :slot_grid_id, CAST(:pattern AS jsonb), :start_time, :end_time, "
        ":slot_from, :slot_to, :valid_from, :valid_to, :title, :location, :color, "
        "CAST(:fields AS jsonb), :note, :user_id, :created_at, :updated_at, :deleted_at)"
    )
    types = {
        (r.user_id, r.key): r.id
        for r in bind.execute(
            sa.text("SELECT id, user_id, key FROM event_types WHERE key IS NOT NULL")
        ).all()
    }
    grids = {
        r.period_id: r.id
        for r in bind.execute(
            sa.text(
                "SELECT DISTINCT ON (period_id) period_id, id FROM slot_grids "
                "WHERE weekday IS NULL AND deleted_at IS NULL ORDER BY period_id, name"
            )
        ).all()
    }
    for r in bind.execute(sa.text("SELECT * FROM class_rules")).all():
        slot = r.pair_number
        own_time = r.start_time is not None and r.end_time is not None
        bind.execute(
            insert,
            {
                "id": r.id,
                "event_type_id": types[(r.user_id, "class")],
                "area_id": r.area_id,
                "period_id": r.semester_id,
                "slot_grid_id": grids.get(r.semester_id) if slot and not own_time else None,
                "pattern": json.dumps(class_pattern(r.weekday, r.parity)),
                "start_time": r.start_time if own_time else None,
                "end_time": r.end_time if own_time else None,
                "slot_from": slot,
                "slot_to": None,
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
                "title": None,
                "location": r.location,
                "color": None,
                "fields": json.dumps(rule_fields(r.class_type, r.teacher), ensure_ascii=False),
                "note": "",
                "user_id": r.user_id,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "deleted_at": r.deleted_at,
            },
        )
    for r in bind.execute(sa.text("SELECT * FROM recurring_events")).all():
        key = "rest" if r.kind == "rest" else "personal"
        bind.execute(
            insert,
            {
                "id": r.id,
                "event_type_id": types[(r.user_id, key)],
                "area_id": None,
                "period_id": None,
                "slot_grid_id": None,
                "pattern": json.dumps(rrule_pattern(r.rrule)),
                "start_time": r.start_time,
                "end_time": r.end_time,
                "slot_from": None,
                "slot_to": None,
                "valid_from": r.start_date,
                "valid_to": r.until,
                "title": r.title,
                "location": r.location,
                "color": r.color,
                "fields": "{}",
                "note": r.note,
                "user_id": r.user_id,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "deleted_at": r.deleted_at,
            },
        )
    bind.execute(
        sa.text(
            "UPDATE events SET template_type = 'schedule_rule' "
            "WHERE template_type IN ('class_rule', 'recurring')"
        )
    )


def downgrade() -> None:
    # Таблицы Part 1 к этому моменту восстановила contract-миграция при откате
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE events e SET template_type = 'class_rule' FROM class_rules r "
            "WHERE e.template_type = 'schedule_rule' AND r.id = e.template_id"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE events e SET template_type = 'recurring' FROM recurring_events r "
            "WHERE e.template_type = 'schedule_rule' AND r.id = e.template_id"
        )
    )
    # Вхождения правил, которые Part 1 не выражает, остаются разовыми событиями
    bind.execute(
        sa.text(
            "UPDATE events SET template_type = NULL, template_id = NULL, occurrence_date = NULL "
            "WHERE template_type = 'schedule_rule'"
        )
    )
    for column in ("user_id", "period_id", "event_type_id", "area_id"):
        op.drop_index(op.f(f"ix_schedule_rules_{column}"), table_name="schedule_rules")
    op.drop_table("schedule_rules")
