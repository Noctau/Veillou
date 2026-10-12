"""M18.1: режимы дня (expand + backfill)

- `day_profiles` — подъём, отбой, обед, общие рабочие окна, флаги отдыха и тихих
  часов; `day_profile_rules` — какой режим у даты (даты, события, дни недели);
- каждому пользователю — «Будни» (Пн–Пт) и «Выходные» (Сб–Вс) из переопределений
  `work_hours`, `sleep`, `lunch` (дефолты — как в UserSettings Part 1). Тихие часы
  у мигрированных режимов не следуют за сном: остаются `quiet_hours` из настроек.

Старые ключи настроек удаляет contract-миграция M18.

Revision ID: 7d0e6f1a3b54
Revises: 6c9d5e0f2a43
Create Date: 2026-10-14 10:00:00.000000

"""

import json
from collections.abc import Sequence
from datetime import time
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7d0e6f1a3b54"
down_revision: str | Sequence[str] | None = "6c9d5e0f2a43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Дефолты UserSettings Part 1
DEFAULTS: dict[str, Any] = {
    "sleep": {"start": "23:30", "end": "07:30"},
    "lunch": {"start": "13:00", "end": "14:00"},
    "work_hours": {
        "weekdays": {"start": "09:00", "end": "21:00"},
        "weekends": {"start": "11:00", "end": "19:00"},
    },
}


def old_day_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """Сон, обед и рабочие часы Part 1 с дефолтами."""
    settings = settings or {}
    work = settings.get("work_hours") or {}
    return {
        "sleep": {**DEFAULTS["sleep"], **(settings.get("sleep") or {})},
        "lunch": {**DEFAULTS["lunch"], **(settings.get("lunch") or {})},
        "weekdays": {**DEFAULTS["work_hours"]["weekdays"], **(work.get("weekdays") or {})},
        "weekends": {**DEFAULTS["work_hours"]["weekends"], **(work.get("weekends") or {})},
    }


def profiles_of(settings: dict[str, Any] | None) -> list[dict[str, Any]]:
    """«Будни» и «Выходные»: строки `day_profiles` и дни недели их правил."""
    old = old_day_settings(settings)
    common = {
        "wake": old["sleep"]["end"],
        "sleep": old["sleep"]["start"],
        "lunch_start": old["lunch"]["start"],
        "lunch_end": old["lunch"]["end"],
        "rest_evening_ok": True,
        "quiet_follows_sleep": False,
    }
    return [
        {
            **common,
            "key": "weekdays",
            "name": "Будни",
            "work": [old["weekdays"]],
            "rest_halfday_ok": False,
            "weekdays": [1, 2, 3, 4, 5],
        },
        {
            **common,
            "key": "weekends",
            "name": "Выходные",
            "work": [old["weekends"]],
            "rest_halfday_ok": True,
            "weekdays": [6, 7],
        },
    ]


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
        "day_profiles",
        sa.Column("key", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("wake", sa.Time(), nullable=False),
        sa.Column("sleep", sa.Time(), nullable=False),
        sa.Column("lunch_start", sa.Time(), nullable=True),
        sa.Column("lunch_end", sa.Time(), nullable=True),
        sa.Column("work_windows", jsonb, nullable=False),
        sa.Column("rest_evening_ok", sa.Boolean(), nullable=False),
        sa.Column("rest_halfday_ok", sa.Boolean(), nullable=False),
        sa.Column("quiet_follows_sleep", sa.Boolean(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_day_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_day_profiles")),
    )
    op.create_index(op.f("ix_day_profiles_user_id"), "day_profiles", ["user_id"], unique=False)
    op.create_index(
        "uq_day_profiles_user_key",
        "day_profiles",
        ["user_id", "key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND key IS NOT NULL"),
    )
    op.create_table(
        "day_profile_rules",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("event_type_id", sa.Uuid(), nullable=True),
        sa.Column("weekdays", jsonb, nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["day_profiles.id"],
            name=op.f("fk_day_profile_rules_profile_id_day_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_type_id"],
            ["event_types.id"],
            name=op.f("fk_day_profile_rules_event_type_id_event_types"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_day_profile_rules_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_day_profile_rules")),
    )
    op.create_index(
        op.f("ix_day_profile_rules_user_id"), "day_profile_rules", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_day_profile_rules_profile_id"), "day_profile_rules", ["profile_id"], unique=False
    )

    # ---------- backfill ----------
    bind = op.get_bind()
    insert_profile = sa.text(
        "INSERT INTO day_profiles (id, user_id, key, name, wake, sleep, lunch_start, lunch_end, "
        "work_windows, rest_evening_ok, rest_halfday_ok, quiet_follows_sleep, position) "
        "VALUES (gen_random_uuid(), :user_id, :key, :name, :wake, "
        ":sleep, :lunch_start, :lunch_end, "
        "CAST(:work AS jsonb), :rest_evening_ok, :rest_halfday_ok, :quiet_follows_sleep, "
        ":position) RETURNING id"
    )
    insert_rule = sa.text(
        "INSERT INTO day_profile_rules (id, user_id, profile_id, kind, weekdays, position) "
        "VALUES (gen_random_uuid(), :user_id, :profile_id, 'weekdays', CAST(:weekdays AS jsonb), "
        ":position)"
    )
    for user in bind.execute(sa.text("SELECT id, settings FROM users")).all():
        for i, p in enumerate(profiles_of(user.settings)):
            profile_id = bind.execute(
                insert_profile,
                {
                    "user_id": user.id,
                    "key": p["key"],
                    "name": p["name"],
                    "wake": time.fromisoformat(p["wake"]),
                    "sleep": time.fromisoformat(p["sleep"]),
                    "lunch_start": time.fromisoformat(p["lunch_start"]),
                    "lunch_end": time.fromisoformat(p["lunch_end"]),
                    "work": json.dumps(p["work"]),
                    "rest_evening_ok": p["rest_evening_ok"],
                    "rest_halfday_ok": p["rest_halfday_ok"],
                    "quiet_follows_sleep": p["quiet_follows_sleep"],
                    "position": i,
                },
            ).scalar_one()
            bind.execute(
                insert_rule,
                {
                    "user_id": user.id,
                    "profile_id": profile_id,
                    "weekdays": json.dumps(p["weekdays"]),
                    "position": i,
                },
            )


def downgrade() -> None:
    op.drop_index(op.f("ix_day_profile_rules_profile_id"), table_name="day_profile_rules")
    op.drop_index(op.f("ix_day_profile_rules_user_id"), table_name="day_profile_rules")
    op.drop_table("day_profile_rules")
    op.drop_index(
        "uq_day_profiles_user_key",
        table_name="day_profiles",
        postgresql_where=sa.text("deleted_at IS NULL AND key IS NOT NULL"),
    )
    op.drop_index(op.f("ix_day_profiles_user_id"), table_name="day_profiles")
    op.drop_table("day_profiles")
