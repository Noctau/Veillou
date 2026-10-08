"""ИИ (M10): журнал вызовов и шаблоны разбивки."""

import uuid
from typing import Any

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UserOwnedMixin


class AILog(UserOwnedMixin, Base):
    """Одна попытка вызова ИИ: запрос, ответ, токены, время. Чистится ночной джобой."""

    __tablename__ = "ai_log"
    __table_args__ = (Index("ix_ai_log_created_at", "created_at"),)

    purpose: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    # Сообщения без картинок (только их число)
    request: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    response: Mapped[str] = mapped_column(Text, default="")
    job_id: Mapped[uuid.UUID | None] = mapped_column()


class BreakdownTemplate(UserOwnedMixin, Base):
    """Сохранённая разбивка — применяется без ИИ (M10.4).

    `steps`: [{title, estimate_min, action_type (ключ), depends_on: [индексы], note}].
    Тип действия хранится ключом, а не id: шаблон переживает пересоздание справочника.
    """

    __tablename__ = "breakdown_templates"

    name: Mapped[str] = mapped_column(String(200))
    task_type: Mapped[str | None] = mapped_column(String(20))
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
