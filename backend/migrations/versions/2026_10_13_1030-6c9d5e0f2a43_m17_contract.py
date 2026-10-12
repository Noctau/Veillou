"""M17 contract: удаление старого после переключения кода

- `events.class_type`, `events.teacher` → поля события (M17.1);
- `periods.classes_end`, `session_start`, `session_end`, `first_week_parity` →
  `end_date`, `pauses`, `cycle_weeks`, `first_cycle_week` (M17.2);
- `class_rules`, `recurring_events` → `schedule_rules` (M17.4);
- `settings.travel_buffer_min`, `settings.reminders.before_class` → флаги типа
  занятости «Пара» (M17.1).

Downgrade собирает старое обратно: правила «Пары» по одному дню недели в периоде —
в `class_rules`, правила с настенным временем — в `recurring_events` (паттерны,
которых нет в RRULE Part 1, — приближённо), остальное не выражается.

Revision ID: 6c9d5e0f2a43
Revises: 5b8c4d9e1f32
Create Date: 2026-10-13 10:30:00.000000

"""

import json
import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c9d5e0f2a43"
down_revision: str | Sequence[str] | None = "5b8c4d9e1f32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLASS_TYPES = {"лекция": "lecture", "семинар": "seminar", "лаба": "lab"}
DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
CHANNELS = ["push", "telegram"]


def _timestamps() -> list[sa.Column[Any]]:
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
    ]


def upgrade() -> None:
    bind = op.get_bind()
    op.drop_column("events", "class_type")
    op.drop_column("events", "teacher")
    for column in ("classes_end", "session_start", "session_end", "first_week_parity"):
        op.drop_column("periods", column)
    op.drop_index(op.f("ix_class_rules_area_id"), table_name="class_rules")
    op.drop_index(op.f("ix_class_rules_semester_id"), table_name="class_rules")
    op.drop_index(op.f("ix_class_rules_user_id"), table_name="class_rules")
    op.drop_table("class_rules")
    op.drop_index(op.f("ix_recurring_events_user_id"), table_name="recurring_events")
    op.drop_table("recurring_events")
    bind.execute(
        sa.text(
            "UPDATE users SET settings = (settings - 'travel_buffer_min') "
            "#- '{reminders,before_class}'"
        )
    )


# ---------- downgrade ----------


def period_columns(row: Any) -> dict[str, Any]:
    """Пауза в конце периода (цепочка подряд идущих пауз) — сессия, до неё — занятия."""
    pauses = sorted(
        (
            (date.fromisoformat(p["from"]), date.fromisoformat(p["to"]))
            for p in row.pauses or []
            if p.get("from") and p.get("to")
        ),
        reverse=True,
    )
    chain: list[tuple[date, date]] = []
    edge = row.end_date
    for start, end in pauses:
        if end == edge:
            chain.append((start, end))
            edge = start - timedelta(days=1)
    session = chain[0] if chain else None
    return {
        "classes_end": (chain[-1][0] - timedelta(days=1)) if chain else row.end_date,
        "session_start": session[0] if session else None,
        "session_end": session[1] if session else None,
        "parity": "even" if row.cycle_weeks == 2 and row.first_cycle_week == 2 else "odd",
    }


def rrule_text(pattern: dict[str, Any]) -> tuple[str, date | None]:
    """Паттерн → RRULE Part 1 и дата начала, если её задаёт паттерн."""
    kind = pattern.get("kind")
    if kind == "weekly":
        days = ",".join(DAYS[d - 1] for d in sorted(pattern.get("weekdays") or [1]))
        return f"FREQ=WEEKLY;BYDAY={days}", None
    if kind == "day_cycle":
        length = int(pattern.get("on", 1)) + int(pattern.get("off", 0))
        return f"FREQ=DAILY;INTERVAL={max(length, 1)}", date.fromisoformat(pattern["anchor"])
    if kind == "once":
        return "FREQ=DAILY;COUNT=1", date.fromisoformat(pattern["date"])
    return str(pattern.get("rrule") or "FREQ=WEEKLY"), None


def _create_old_tables() -> None:
    op.create_table(
        "class_rules",
        sa.Column("semester_id", sa.Uuid(), nullable=False),
        sa.Column("area_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("pair_number", sa.SmallInteger(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("parity", sa.String(length=8), nullable=False),
        sa.Column("class_type", sa.String(length=20), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("teacher", sa.String(length=200), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["semester_id"],
            ["periods.id"],
            name="fk_class_rules_semester_id_semesters",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["area_id"], ["areas.id"], name="fk_class_rules_area_id_areas", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_class_rules_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_class_rules"),
    )
    op.create_index(op.f("ix_class_rules_semester_id"), "class_rules", ["semester_id"])
    op.create_index(op.f("ix_class_rules_area_id"), "class_rules", ["area_id"])
    op.create_index(op.f("ix_class_rules_user_id"), "class_rules", ["user_id"])
    op.create_table(
        "recurring_events",
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("rrule", sa.String(length=500), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("until", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_recurring_events_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recurring_events"),
    )
    op.create_index(op.f("ix_recurring_events_user_id"), "recurring_events", ["user_id"])


def _restore_rules(bind: Any) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT r.*, t.key AS type_key, t.is_rest, t.name AS type_name, "
            "a.name AS area_name, p.start_date AS period_start "
            "FROM schedule_rules r JOIN event_types t ON t.id = r.event_type_id "
            "LEFT JOIN areas a ON a.id = r.area_id LEFT JOIN periods p ON p.id = r.period_id"
        )
    ).all()
    class_insert = sa.text(
        "INSERT INTO class_rules (id, user_id, semester_id, area_id, weekday, pair_number, "
        "start_time, end_time, parity, class_type, location, teacher, valid_from, valid_to, "
        "created_at, updated_at, deleted_at) VALUES (:id, :user_id, :period_id, :area_id, "
        ":weekday, :slot, :start_time, :end_time, :parity, :class_type, :location, :teacher, "
        ":valid_from, :valid_to, :created_at, :updated_at, :deleted_at)"
    )
    rec_insert = sa.text(
        "INSERT INTO recurring_events (id, user_id, kind, title, rrule, start_date, until, "
        "start_time, end_time, location, color, note, created_at, updated_at, deleted_at) "
        "VALUES (:id, :user_id, :kind, :title, :rrule, :start_date, :until, :start_time, "
        ":end_time, :location, :color, :note, :created_at, :updated_at, :deleted_at)"
    )
    for r in rows:
        pattern = r.pattern or {}
        fields = r.fields or {}
        common = {
            "user_id": r.user_id,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "deleted_at": r.deleted_at,
            "location": r.location,
        }
        is_class = (
            r.type_key == "class"
            and pattern.get("kind") == "weekly"
            and r.period_id is not None
            and r.area_id is not None
        )
        if is_class:
            mask = pattern.get("cycle_weeks")
            parity = {(1,): "odd", (2,): "even"}.get(tuple(mask or ()), "all")
            for i, weekday in enumerate(sorted(pattern.get("weekdays") or [])):
                bind.execute(
                    class_insert,
                    {
                        **common,
                        "id": r.id if i == 0 else uuid.uuid4(),
                        "period_id": r.period_id,
                        "area_id": r.area_id,
                        "weekday": weekday,
                        "slot": r.slot_from,
                        "start_time": r.start_time,
                        "end_time": r.end_time,
                        "parity": parity,
                        "class_type": CLASS_TYPES.get(fields.get("class_type"), "other"),
                        "teacher": fields.get("teacher"),
                        "valid_from": r.valid_from,
                        "valid_to": r.valid_to,
                    },
                )
            continue
        if r.start_time is None or r.end_time is None:
            continue  # слоты без настенного времени Part 1 не выражает
        text, anchor = rrule_text(pattern)
        start = r.valid_from or anchor or r.period_start or r.created_at.date()
        bind.execute(
            rec_insert,
            {
                **common,
                "id": r.id,
                "kind": "rest" if r.is_rest else "personal",
                "title": r.title or r.area_name or r.type_name,
                "rrule": text,
                "start_date": start,
                "until": r.valid_to,
                "start_time": r.start_time,
                "end_time": r.end_time,
                "color": r.color,
                "note": r.note,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()

    # ---------- настройки из «Пары» ----------
    update = sa.text("UPDATE users SET settings = CAST(:settings AS jsonb) WHERE id = :id")
    for u in bind.execute(
        sa.text(
            "SELECT u.id, u.settings, t.buffer_before_min, t.remind_before_min, "
            "t.remind_channels FROM users u JOIN event_types t ON t.user_id = u.id "
            "AND t.key = 'class' AND t.deleted_at IS NULL"
        )
    ).all():
        settings = dict(u.settings or {})
        if u.buffer_before_min != 60:
            settings["travel_buffer_min"] = u.buffer_before_min
        rule: dict[str, Any] = {}
        if u.remind_before_min is None:
            rule["enabled"] = False
        elif u.remind_before_min != 15:
            rule["minutes_before"] = u.remind_before_min
        if list(u.remind_channels or CHANNELS) != CHANNELS:
            rule["channels"] = list(u.remind_channels or [])
        if rule:
            settings["reminders"] = {**(settings.get("reminders") or {}), "before_class": rule}
        bind.execute(update, {"id": u.id, "settings": json.dumps(settings, ensure_ascii=False)})

    # ---------- правила ----------
    _create_old_tables()
    _restore_rules(bind)

    # ---------- период ----------
    op.add_column("periods", sa.Column("classes_end", sa.Date(), nullable=True))
    op.add_column("periods", sa.Column("session_start", sa.Date(), nullable=True))
    op.add_column("periods", sa.Column("session_end", sa.Date(), nullable=True))
    op.add_column("periods", sa.Column("first_week_parity", sa.String(length=8), nullable=True))
    period_update = sa.text(
        "UPDATE periods SET classes_end = :classes_end, session_start = :session_start, "
        "session_end = :session_end, first_week_parity = :parity WHERE id = :id"
    )
    for row in bind.execute(
        sa.text("SELECT id, end_date, cycle_weeks, first_cycle_week, pauses FROM periods")
    ).all():
        bind.execute(period_update, {"id": row.id, **period_columns(row)})

    # ---------- события ----------
    op.add_column("events", sa.Column("teacher", sa.String(length=200), nullable=True))
    op.add_column("events", sa.Column("class_type", sa.String(length=20), nullable=True))
    event_update = sa.text(
        "UPDATE events SET class_type = :class_type, teacher = :teacher WHERE id = :id"
    )
    for e in bind.execute(
        sa.text(
            "SELECT e.id, e.fields FROM events e JOIN event_types t ON t.id = e.event_type_id "
            "WHERE t.key = 'class'"
        )
    ).all():
        fields = e.fields or {}
        bind.execute(
            event_update,
            {
                "id": e.id,
                "class_type": CLASS_TYPES.get(fields.get("class_type"), "other"),
                "teacher": fields.get("teacher"),
            },
        )
