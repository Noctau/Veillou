"""M20 contract: колонки экзамена в плане подготовки

`prep_plans.starts_at`, `duration_min`, `location` — теперь у события плана (или дата
плана без события). Downgrade собирает их обратно из события (или из даты, 00:00).

Revision ID: b14c0d5e7f98
Revises: a03b9c4d6e87
Create Date: 2026-10-16 10:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b14c0d5e7f98"
down_revision: str | Sequence[str] | None = "a03b9c4d6e87"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for col in ("starts_at", "duration_min", "location"):
        op.drop_column("prep_plans", col)


def downgrade() -> None:
    op.add_column("prep_plans", sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("prep_plans", sa.Column("duration_min", sa.Integer(), nullable=True))
    op.add_column("prep_plans", sa.Column("location", sa.String(length=200), nullable=True))
    op.execute(
        "UPDATE prep_plans p SET starts_at = e.start, location = e.location, "
        'duration_min = GREATEST(1, (EXTRACT(EPOCH FROM e."end" - e.start) / 60)::int) '
        "FROM events e WHERE e.id = p.event_id"
    )
    op.execute(
        "UPDATE prep_plans p SET starts_at = (p.date::timestamp AT TIME ZONE u.timezone), "
        "duration_min = 180 FROM users u WHERE u.id = p.user_id AND p.starts_at IS NULL "
        "AND p.date IS NOT NULL"
    )
    # Без события и даты экзамен не выражается
    op.execute("DELETE FROM prep_plans WHERE starts_at IS NULL")
    op.alter_column("prep_plans", "starts_at", nullable=False)
    op.alter_column("prep_plans", "duration_min", nullable=False)
