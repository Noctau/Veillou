"""M16.2: сферы вместо предметов (expand + backfill)

- `subjects` → `areas` на месте (id те же), `semester_id` → `period_id` (до M17.2
  ссылается на `semesters`), новые `area_type_id`, `fields`, `archived_at`;
- `subject_id` → `area_id` в `events`, `tasks`, `notes`, `sources`, `exams`,
  `class_rules`; `projects.area_id` — новая необязательная ссылка;
- каждому пользователю — тип сферы «Предмет» (`key=subject`) с полями
  «Преподаватели» (contact, много), «Форма контроля» (select) и «Ссылки» (link, много);
  `teachers`, `control_form`, `links` → `fields`.

Старые колонки удаляет contract-миграция M16.

Revision ID: feb25238680f
Revises: 6ba58db08f00
Create Date: 2026-10-12 10:00:00.000000

"""

import json
import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "feb25238680f"
down_revision: str | Sequence[str] | None = "6ba58db08f00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REFERRERS = ("events", "tasks", "notes", "sources", "exams", "class_rules")

CONTROL_FORMS = {
    "exam": "Экзамен",
    "credit": "Зачёт",
    "graded_credit": "Дифзачёт",
    "coursework": "Курсовая",
}
SUBJECT_FIELDS = [
    {
        "id": "teachers",
        "label": "Преподаватели",
        "type": "contact",
        "options": [],
        "multiple": True,
        "show_in_reminder": False,
        "required": False,
        "deleted": False,
    },
    {
        "id": "control_form",
        "label": "Форма контроля",
        "type": "select",
        "options": list(CONTROL_FORMS.values()),
        "multiple": False,
        "show_in_reminder": False,
        "required": False,
        "deleted": False,
    },
    {
        "id": "links",
        "label": "Ссылки",
        "type": "link",
        "options": [],
        "multiple": True,
        "show_in_reminder": False,
        "required": False,
        "deleted": False,
    },
]
SUBJECT_SECTIONS = ["schedule", "tasks", "notes", "materials", "prep"]

_PHONE = re.compile(r"^\+?[\d\s()\-.]{5,}$")


def contact(teacher: dict[str, Any]) -> dict[str, str]:
    """Преподаватель Part 1 `{name, role, contact}` → поле contact.

    Свободная строка `contact` раскладывается по частям (через «,» или «;»):
    с «@» — email, http(s) — ссылка, похожее на номер — телефон, остальное — note.
    """
    result = {k: str(teacher[k]).strip() for k in ("name", "role") if teacher.get(k)}
    notes: list[str] = []
    for part in re.split(r"[;,]", str(teacher.get("contact") or "")):
        part = part.strip()
        if not part:
            continue
        if "@" in part and " " not in part and "email" not in result:
            result["email"] = part
        elif re.match(r"^https?://\S+$", part) and "link" not in result:
            result["link"] = part
        elif _PHONE.match(part) and "phone" not in result:
            result["phone"] = part
        else:
            notes.append(part)
    if notes:
        result["note"] = ", ".join(notes)
    return {k: v for k, v in result.items() if v}


def subject_fields(row: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    teachers = [c for c in (contact(t) for t in row.teachers or []) if c]
    if teachers:
        fields["teachers"] = teachers
    if row.control_form in CONTROL_FORMS:
        fields["control_form"] = CONTROL_FORMS[row.control_form]
    links = [
        {"title": str(link.get("title") or ""), "url": str(link["url"])}
        for link in row.links or []
        if link.get("url")
    ]
    if links:
        fields["links"] = links
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


def _rename(kind: str, old: str, new: str, table: str | None = None) -> None:
    if kind == "index":
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")
    else:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}")


def upgrade() -> None:
    op.create_table(
        "area_types",
        sa.Column("key", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_plural", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=40), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_area_types_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_area_types")),
    )
    op.create_index(op.f("ix_area_types_user_id"), "area_types", ["user_id"], unique=False)
    op.create_index(
        "uq_area_types_user_key",
        "area_types",
        ["user_id", "key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND key IS NOT NULL"),
    )

    # ---------- subjects → areas (на месте: id и ссылки сохраняются) ----------
    op.rename_table("subjects", "areas")
    _rename("constraint", "pk_subjects", "pk_areas", "areas")
    _rename("constraint", "fk_subjects_user_id_users", "fk_areas_user_id_users", "areas")
    _rename("index", "ix_subjects_user_id", "ix_areas_user_id")
    op.alter_column("areas", "semester_id", new_column_name="period_id")
    _rename(
        "constraint", "fk_subjects_semester_id_semesters", "fk_areas_period_id_semesters", "areas"
    )
    _rename("index", "ix_subjects_semester_id", "ix_areas_period_id")
    op.add_column("areas", sa.Column("area_type_id", sa.Uuid(), nullable=True))
    op.add_column(
        "areas",
        sa.Column(
            "fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("areas", "fields", server_default=None)
    op.add_column("areas", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_areas_area_type_id"), "areas", ["area_type_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_areas_area_type_id_area_types"),
        "areas",
        "area_types",
        ["area_type_id"],
        ["id"],
        ondelete="CASCADE",
    )

    for table in REFERRERS:
        op.alter_column(table, "subject_id", new_column_name="area_id")
        _rename("constraint", f"fk_{table}_subject_id_subjects", f"fk_{table}_area_id_areas", table)
        _rename("index", f"ix_{table}_subject_id", f"ix_{table}_area_id")

    op.add_column("projects", sa.Column("area_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_projects_area_id"), "projects", ["area_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_projects_area_id_areas"),
        "projects",
        "areas",
        ["area_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---------- backfill ----------
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO area_types "
            "(id, user_id, key, name, name_plural, icon, color, fields, sections, position) "
            "SELECT gen_random_uuid(), u.id, 'subject', 'Предмет', 'Предметы', "
            "'graduation-cap', '#3b82f6', CAST(:fields AS jsonb), CAST(:sections AS jsonb), 0 "
            "FROM users u"
        ),
        {
            "fields": json.dumps(SUBJECT_FIELDS, ensure_ascii=False),
            "sections": json.dumps(SUBJECT_SECTIONS),
        },
    )
    bind.execute(
        sa.text(
            "UPDATE areas a SET area_type_id = t.id FROM area_types t "
            "WHERE t.user_id = a.user_id AND t.key = 'subject'"
        )
    )
    rows = bind.execute(sa.text("SELECT id, teachers, control_form, links FROM areas")).all()
    update = sa.text("UPDATE areas SET fields = CAST(:fields AS jsonb) WHERE id = :id")
    for row in rows:
        fields = subject_fields(row)
        if fields:
            bind.execute(update, {"id": row.id, "fields": json.dumps(fields, ensure_ascii=False)})
    op.alter_column("areas", "area_type_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint(op.f("fk_projects_area_id_areas"), "projects", type_="foreignkey")
    op.drop_index(op.f("ix_projects_area_id"), table_name="projects")
    op.drop_column("projects", "area_id")

    for table in REFERRERS:
        _rename("index", f"ix_{table}_area_id", f"ix_{table}_subject_id")
        _rename("constraint", f"fk_{table}_area_id_areas", f"fk_{table}_subject_id_subjects", table)
        op.alter_column(table, "area_id", new_column_name="subject_id")

    op.drop_constraint(op.f("fk_areas_area_type_id_area_types"), "areas", type_="foreignkey")
    op.drop_index(op.f("ix_areas_area_type_id"), table_name="areas")
    op.drop_column("areas", "archived_at")
    op.drop_column("areas", "fields")
    op.drop_column("areas", "area_type_id")
    _rename("index", "ix_areas_period_id", "ix_subjects_semester_id")
    _rename(
        "constraint", "fk_areas_period_id_semesters", "fk_subjects_semester_id_semesters", "areas"
    )
    op.alter_column("areas", "period_id", new_column_name="semester_id")
    _rename("index", "ix_areas_user_id", "ix_subjects_user_id")
    _rename("constraint", "fk_areas_user_id_users", "fk_subjects_user_id_users", "areas")
    _rename("constraint", "pk_areas", "pk_subjects", "areas")
    op.rename_table("areas", "subjects")

    op.drop_index(
        "uq_area_types_user_key",
        table_name="area_types",
        postgresql_where=sa.text("deleted_at IS NULL AND key IS NOT NULL"),
    )
    op.drop_index(op.f("ix_area_types_user_id"), table_name="area_types")
    op.drop_table("area_types")
