"""M16 contract: удаление колонок предметов, переехавших в поля сферы

`areas.teachers`, `areas.control_form`, `areas.links` → `areas.fields` (M16.2).
Downgrade собирает их обратно из полей `teachers`, `control_form`, `links`.

Revision ID: 7ca8b1acd149
Revises: feb25238680f
Create Date: 2026-10-12 10:10:00.000000

"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7ca8b1acd149"
down_revision: str | Sequence[str] | None = "feb25238680f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONTROL_FORMS = {
    "Экзамен": "exam",
    "Зачёт": "credit",
    "Дифзачёт": "graded_credit",
    "Курсовая": "coursework",
}


def teacher(contact: dict[str, Any]) -> dict[str, str]:
    """Поле contact → преподаватель Part 1 `{name, role, contact}`."""
    rest = [str(contact[k]) for k in ("email", "phone", "link", "note") if contact.get(k)]
    return {
        "name": str(contact.get("name") or contact.get("role") or "—"),
        "role": str(contact.get("role") or ""),
        "contact": ", ".join(rest),
    }


def upgrade() -> None:
    op.drop_column("areas", "teachers")
    op.drop_column("areas", "control_form")
    op.drop_column("areas", "links")


def downgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.add_column(
        "areas",
        sa.Column("teachers", jsonb, server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column(
        "areas",
        sa.Column("control_form", sa.String(length=20), server_default="none", nullable=False),
    )
    op.add_column(
        "areas", sa.Column("links", jsonb, server_default=sa.text("'[]'::jsonb"), nullable=False)
    )
    for column in ("teachers", "control_form", "links"):
        op.alter_column("areas", column, server_default=None)

    bind = op.get_bind()
    update = sa.text(
        "UPDATE areas SET teachers = CAST(:teachers AS jsonb), control_form = :control_form, "
        "links = CAST(:links AS jsonb) WHERE id = :id"
    )
    for row in bind.execute(sa.text("SELECT id, fields FROM areas")).all():
        fields = row.fields or {}
        contacts = fields.get("teachers") or []
        links = fields.get("links") or []
        bind.execute(
            update,
            {
                "id": row.id,
                "teachers": json.dumps(
                    [teacher(c) for c in contacts if isinstance(c, dict)], ensure_ascii=False
                ),
                "control_form": CONTROL_FORMS.get(fields.get("control_form"), "none"),
                "links": json.dumps(
                    [
                        {"title": str(x.get("title") or ""), "url": str(x["url"])}
                        for x in links
                        if isinstance(x, dict) and x.get("url")
                    ],
                    ensure_ascii=False,
                ),
            },
        )
