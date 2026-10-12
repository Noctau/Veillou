"""M21.1: словарь быстрого ввода — синонимы справочников

- `action_types.synonyms`, `event_types.synonyms` (JSONB, по умолчанию `[]`);
- слова быстрого ввода Part 1 (бывшие regex `quickparse.ACTION_TYPES` / `TASK_TYPES`,
  в M15 — `catalog.ACTION_TYPE_WORDS` / `TASK_TYPE_WORDS`) дописываются в синонимы
  засеянных типов по ключу сида: «научрук», «деканат», «читать» … — у всех, у кого эти
  типы есть (новых пользователей сид создаёт уже с нейтральными словами).

Downgrade убирает колонки и дописанные слова типов задач.

Revision ID: c25d1e6f8a09
Revises: b14c0d5e7f98
Create Date: 2026-10-17 10:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c25d1e6f8a09"
down_revision: str | Sequence[str] | None = "b14c0d5e7f98"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Ключ сида → слова Part 1 (по смыслу regex, в форме синонимов: падежи — сами)
ACTION_WORDS: dict[str, list[str]] = {
    "institutions": [
        "деканат",
        "библиотека",
        "врач",
        "стоматолог",
        "поликлиника",
        "больница",
        "мфц",
        "банк",
        "паспорт",
        "справка",
        "военкомат",
        "налоговая",
        "нотариус",
        "записаться",
        "запись",
    ],
    "people": [
        "научрук",
        "руководитель",
        "препод*",
        "преподаватель",
        "староста",
        "куратор",
        "одногруппник",
        "позвонить",
        "созвониться",
        "спросить",
        "договориться",
        "согласовать",
    ],
    "outside": [
        "купить",
        "магазин",
        "аптека",
        "посылка",
        "почта",
        "забрать",
        "отнести",
        "химчистка",
        "ремонт",
    ],
    "home": [
        "убрать",
        "убраться",
        "уборка",
        "постирать",
        "стирка",
        "приготовить",
        "готовка",
        "помыть",
        "пропылесосить",
        "разобрать",
        "погладить",
        "полить",
        "вынести",
    ],
    "personal": [
        "спорт",
        "зал",
        "бассейн",
        "йога",
        "пробежка",
        "кино",
        "прогулка",
        "погулять",
        "подруга",
        "друзья",
        "день рождения",
    ],
}

# Слова regex Part 1, которых не было в синонимах типов задач после M15.1
TASK_WORDS: dict[str, list[str]] = {
    "reading": ["читать", "прочесть"],
    "lab": ["лаборатор*"],
}


def _jsonb(words: list[str]) -> str:
    return json.dumps(words, ensure_ascii=False)


def upgrade() -> None:
    for table in ("action_types", "event_types"):
        op.add_column(
            table,
            sa.Column(
                "synonyms",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="[]",
            ),
        )
    for key, words in ACTION_WORDS.items():
        op.execute(
            sa.text(
                "UPDATE action_types SET synonyms = CAST(:words AS jsonb) WHERE key = :key"
            ).bindparams(words=_jsonb(words), key=key)
        )
    # Дописываем недостающие слова, не трогая свои синонимы пользователя
    for key, words in TASK_WORDS.items():
        for word in words:
            op.execute(
                sa.text(
                    "UPDATE task_types SET synonyms = synonyms || CAST(:word AS jsonb) "
                    "WHERE key = :key AND NOT synonyms @> CAST(:word AS jsonb)"
                ).bindparams(word=_jsonb([word]), key=key)
            )


def downgrade() -> None:
    for key, words in TASK_WORDS.items():
        for word in words:
            op.execute(
                sa.text(
                    "UPDATE task_types SET synonyms = synonyms - :word WHERE key = :key"
                ).bindparams(word=word, key=key)
            )
    for table in ("event_types", "action_types"):
        op.drop_column(table, "synonyms")
