"""M17.1: типы занятости (expand + backfill)

- `event_types` — справочник жёстких событий с флагами поведения;
- каждому пользователю — типы «Пара» (key=class: дорога = `travel_buffer_min` до и
  после со склейкой, напоминание = `reminders.before_class`, «Сейчас / Дальше», поля
  «Вид занятия» и «Преподаватель»), «Личное» (personal), «Отдых» (rest, `is_rest`),
  «Экзамен» (exam: подготовка, «Сейчас / Дальше»);
- `events`: `event_type_id`, `fields`, `pair_number` → `slot`; kind
  class/personal/rest/exam → busy + тип, exam_prep → prep; `class_type`, `teacher`
  → поля (старые колонки удаляет contract-миграция M17);
- `load_budget_members.event_type_id` — жёсткие события в лимитах;
- `backlog_items.days_event_type_id` — чип «в дни пар» → «в дни событий типа»;
- напоминания before_class → before_event.

Revision ID: 3e6f2a7b9c10
Revises: 7ca8b1acd149
Create Date: 2026-10-13 10:00:00.000000

"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3e6f2a7b9c10"
down_revision: str | Sequence[str] | None = "7ca8b1acd149"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLASS_TYPES = {"lecture": "лекция", "seminar": "семинар", "lab": "лаба"}
CLASS_FIELDS = [
    {
        "id": "class_type",
        "label": "Вид занятия",
        "type": "select",
        "options": list(CLASS_TYPES.values()),
        "multiple": False,
        "show_in_reminder": True,
        "required": False,
        "deleted": False,
    },
    {
        "id": "teacher",
        "label": "Преподаватель",
        "type": "text",
        "options": [],
        "multiple": False,
        "show_in_reminder": True,
        "required": False,
        "deleted": False,
    },
]
CHANNELS = ["push", "telegram"]
# kind Part 1 → ключ типа занятости
KIND_KEYS = {"class": "class", "personal": "personal", "rest": "rest", "exam": "exam"}


def class_type_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """Флаги «Пары» из переопределений настроек Part 1 (дефолты — как в UserSettings)."""
    settings = settings or {}
    buffer = settings.get("travel_buffer_min", 60)
    rule = (settings.get("reminders") or {}).get("before_class") or {}
    channels = list(dict.fromkeys(rule.get("channels", CHANNELS)))
    enabled = rule.get("enabled", True) and bool(channels)
    return {
        "buffer": int(buffer),
        "remind": int(rule.get("minutes_before", 15)) if enabled else None,
        "channels": channels or CHANNELS,
    }


def event_fields(class_type: str | None, teacher: str | None) -> dict[str, str]:
    fields = {}
    if class_type in CLASS_TYPES:
        fields["class_type"] = CLASS_TYPES[class_type]
    if teacher and teacher.strip():
        fields["teacher"] = teacher.strip()
    return fields


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
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "event_types",
        sa.Column("key", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_plural", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=40), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False),
        sa.Column("buffer_before_min", sa.SmallInteger(), nullable=False),
        sa.Column("buffer_after_min", sa.SmallInteger(), nullable=False),
        sa.Column("merge_buffers", sa.Boolean(), nullable=False),
        sa.Column("remind_before_min", sa.SmallInteger(), nullable=True),
        sa.Column("remind_channels", jsonb, nullable=False),
        sa.Column("show_now_next", sa.Boolean(), nullable=False),
        sa.Column("is_rest", sa.Boolean(), nullable=False),
        sa.Column("supports_prep", sa.Boolean(), nullable=False),
        sa.Column("location_label", sa.String(length=20), nullable=False),
        sa.Column("default_area_type_id", sa.Uuid(), nullable=True),
        sa.Column("fields", jsonb, nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["default_area_type_id"],
            ["area_types.id"],
            name=op.f("fk_event_types_default_area_type_id_area_types"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_event_types_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_types")),
    )
    op.create_index(op.f("ix_event_types_user_id"), "event_types", ["user_id"], unique=False)
    op.create_index(
        "uq_event_types_user_key",
        "event_types",
        ["user_id", "key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND key IS NOT NULL"),
    )

    # ---------- events ----------
    op.add_column("events", sa.Column("event_type_id", sa.Uuid(), nullable=True))
    op.add_column(
        "events",
        sa.Column("fields", jsonb, server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.alter_column("events", "fields", server_default=None)
    op.alter_column("events", "pair_number", new_column_name="slot")
    op.create_index(op.f("ix_events_event_type_id"), "events", ["event_type_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_events_event_type_id_event_types"),
        "events",
        "event_types",
        ["event_type_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---------- лимиты и ящик ----------
    op.add_column("load_budget_members", sa.Column("event_type_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_load_budget_members_event_type_id_event_types"),
        "load_budget_members",
        "event_types",
        ["event_type_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_load_budget_members_event_type",
        "load_budget_members",
        ["budget_id", "event_type_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.add_column("backlog_items", sa.Column("days_event_type_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_backlog_items_days_event_type_id_event_types"),
        "backlog_items",
        "event_types",
        ["days_event_type_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---------- backfill ----------
    bind = op.get_bind()
    insert = sa.text(
        "INSERT INTO event_types (id, user_id, key, name, name_plural, icon, color, "
        "buffer_before_min, buffer_after_min, merge_buffers, remind_before_min, "
        "remind_channels, show_now_next, is_rest, supports_prep, location_label, fields, "
        "position) VALUES (gen_random_uuid(), :user_id, :key, :name, :plural, :icon, :color, "
        ":buffer, :buffer, :merge, :remind, CAST(:channels AS jsonb), :now_next, :rest, :prep, "
        ":label, CAST(:fields AS jsonb), :position)"
    )
    for user in bind.execute(sa.text("SELECT id, settings FROM users")).all():
        cls = class_type_settings(user.settings)
        rows = [
            {
                "key": "class",
                "name": "Пара",
                "plural": "Пары",
                "icon": "graduation-cap",
                "color": "#3b82f6",
                "buffer": cls["buffer"],
                "merge": True,
                "remind": cls["remind"],
                "channels": cls["channels"],
                "now_next": True,
                "rest": False,
                "prep": False,
                "label": "ауд.",
                "fields": CLASS_FIELDS,
            },
            {
                "key": "personal",
                "name": "Личное",
                "plural": "Личное",
                "icon": "user",
                "color": "#64748b",
                "label": "",
            },
            {
                "key": "rest",
                "name": "Отдых",
                "plural": "Отдых",
                "icon": "coffee",
                "color": "#22c55e",
                "rest": True,
                "label": "",
            },
            {
                "key": "exam",
                "name": "Экзамен",
                "plural": "Экзамены",
                "icon": "clipboard-check",
                "color": "#ef4444",
                "now_next": True,
                "prep": True,
                "label": "ауд.",
            },
        ]
        for position, row in enumerate(rows):
            params = {
                "buffer": 0,
                "merge": False,
                "remind": None,
                "channels": CHANNELS,
                "now_next": False,
                "rest": False,
                "prep": False,
                "fields": [],
                **row,
            }
            params["channels"] = json.dumps(params["channels"])
            params["fields"] = json.dumps(params["fields"], ensure_ascii=False)
            bind.execute(insert, {"user_id": user.id, "position": position, **params})

    for kind, key in KIND_KEYS.items():
        bind.execute(
            sa.text(
                "UPDATE events e SET kind = 'busy', event_type_id = t.id FROM event_types t "
                "WHERE e.kind = :kind AND t.user_id = e.user_id AND t.key = :key"
            ),
            {"kind": kind, "key": key},
        )
    bind.execute(sa.text("UPDATE events SET kind = 'prep' WHERE kind = 'exam_prep'"))
    update = sa.text("UPDATE events SET fields = CAST(:fields AS jsonb) WHERE id = :id")
    for row in bind.execute(
        sa.text(
            "SELECT id, class_type, teacher FROM events "
            "WHERE class_type IS NOT NULL OR teacher IS NOT NULL"
        )
    ).all():
        if fields := event_fields(row.class_type, row.teacher):
            bind.execute(update, {"id": row.id, "fields": json.dumps(fields, ensure_ascii=False)})

    bind.execute(
        sa.text(
            "UPDATE backlog_items b SET days_event_type_id = t.id, "
            "conditions = b.conditions - 'on_class_days' FROM event_types t "
            "WHERE b.conditions ? 'on_class_days' AND t.user_id = b.user_id AND t.key = 'class'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE reminders SET kind = 'before_event', "
            "dedupe_key = 'before_event:' || substr(dedupe_key, length('before_class:') + 1) "
            "WHERE kind = 'before_class'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE reminders SET kind = 'before_class', "
            "dedupe_key = 'before_class:' || substr(dedupe_key, length('before_event:') + 1) "
            "WHERE kind = 'before_event'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE backlog_items SET conditions = conditions || '[\"on_class_days\"]'::jsonb "
            "WHERE days_event_type_id IS NOT NULL AND NOT conditions ? 'on_class_days'"
        )
    )
    for kind, key in KIND_KEYS.items():
        bind.execute(
            sa.text(
                "UPDATE events e SET kind = :kind FROM event_types t "
                "WHERE e.kind = 'busy' AND t.id = e.event_type_id AND t.key = :key"
            ),
            {"kind": kind, "key": key},
        )
    # Без типа (или со своим типом) — личное
    bind.execute(sa.text("UPDATE events SET kind = 'personal' WHERE kind = 'busy'"))
    bind.execute(sa.text("UPDATE events SET kind = 'exam_prep' WHERE kind = 'prep'"))

    op.drop_constraint(
        op.f("fk_backlog_items_days_event_type_id_event_types"), "backlog_items", type_="foreignkey"
    )
    op.drop_column("backlog_items", "days_event_type_id")
    op.drop_index(
        "uq_load_budget_members_event_type",
        table_name="load_budget_members",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_constraint(
        op.f("fk_load_budget_members_event_type_id_event_types"),
        "load_budget_members",
        type_="foreignkey",
    )
    # Участники-типы занятости в Part 1 не выражаются
    bind.execute(sa.text("DELETE FROM load_budget_members WHERE event_type_id IS NOT NULL"))
    op.drop_column("load_budget_members", "event_type_id")

    op.drop_constraint(op.f("fk_events_event_type_id_event_types"), "events", type_="foreignkey")
    op.drop_index(op.f("ix_events_event_type_id"), table_name="events")
    op.alter_column("events", "slot", new_column_name="pair_number")
    op.drop_column("events", "fields")
    op.drop_column("events", "event_type_id")

    op.drop_index(
        "uq_event_types_user_key",
        table_name="event_types",
        postgresql_where=sa.text("deleted_at IS NULL AND key IS NOT NULL"),
    )
    op.drop_index(op.f("ix_event_types_user_id"), table_name="event_types")
    op.drop_table("event_types")
