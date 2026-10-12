"""M21.2: «о себе» для ИИ — у пользователей Part 1 из бывшего зашитого описания

До M21.2 каждый промпт начинался с описания студентки (`ai/prompts.WHO`) — у всех
пользователей. Теперь описание — это `settings.about`; существующим пользователям
оно переносится, чтобы ответы ИИ не изменились. Своё «о себе» не трогаем.

Revision ID: d36e2f7a9b10
Revises: c25d1e6f8a09
Create Date: 2026-10-17 10:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d36e2f7a9b10"
down_revision: str | Sequence[str] | None = "c25d1e6f8a09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ABOUT = (
    "Студентка 4 курса бакалавриата: МГУ, географический факультет, "
    "кафедра метеорологии и климатологии."
)


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE users SET settings = jsonb_set(COALESCE(settings, '{}'::jsonb), "
            "'{about}', to_jsonb(CAST(:about AS text))) "
            "WHERE NOT (COALESCE(settings, '{}'::jsonb) ? 'about')"
        ).bindparams(about=ABOUT)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE users SET settings = settings - 'about' WHERE settings->>'about' = :about"
        ).bindparams(about=ABOUT)
    )
