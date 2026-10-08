"""Фоновые джобы, напоминания и push-подписки (M6).

`jobs` и `reminders` — очереди в Postgres: воркер забирает строки через
`FOR UPDATE SKIP LOCKED` и «арендует» их до `locked_until`. Если воркер упал
посреди работы, аренда истекает и строку подхватывает следующий цикл.

Очереди — служебные данные: отработанные строки не удаляются мягко, а
чистятся ночной джобой.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import JobStatus, ReminderStatus
from app.models.base import EntityMixin, UserOwnedMixin, UTCDateTime


class Job(EntityMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_run_at", "status", "run_at"),
        # Одна ожидающая джоба на ключ: десять правок подряд → одна пересборка
        Index(
            "uq_jobs_pending_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status = 'pending' AND dedupe_key IS NOT NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default=JobStatus.pending)
    run_at: Mapped[datetime] = mapped_column(UTCDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    last_error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Итог для того, кто ждёт джобу (фронт поллит GET /jobs/{id}): черновик разбивки и т. п.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Reminder(UserOwnedMixin, Base):
    """Одно напоминание. Текст собирается в момент отправки по сущности (`entity_*`),
    поэтому всегда свежий, а устаревшее (пару отменили, задание сделано) пропускается.
    """

    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminders_status_due", "status", "due_at"),
        Index("ix_reminders_entity", "entity_type", "entity_id"),
        # Один раз на ключ: отправленное не создаётся заново при пересборке
        Index(
            "uq_reminders_user_dedupe",
            "user_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    kind: Mapped[str] = mapped_column(String(30))
    # Когда должно прийти (после тихих часов, окон и склейки)
    fire_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Когда пробовать отправить: fire_at, а после сбоя — время ретрая
    due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Позже этого момента напоминание бессмысленно (пара началась, дедлайн прошёл)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    channels: Mapped[list[str]] = mapped_column(JSONB, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    entity_type: Mapped[str | None] = mapped_column(String(30))
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    dedupe_key: Mapped[str] = mapped_column(String(200))
    # Создано пересборкой (builder) — она же его двигает и удаляет. «+15 мин» и проверка — нет.
    is_auto: Mapped[bool] = mapped_column(Boolean, default=True)

    status: Mapped[str] = mapped_column(String(10), default=ReminderStatus.pending)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Каналы, куда уже доставлено: ретрай не дублирует успешные
    sent_channels: Mapped[list[str]] = mapped_column(JSONB, default=list)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)

    # Кнопки пуша: одноразовый токен (хранится sha256), срабатывает один раз
    action_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    action_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class PushSubscription(UserOwnedMixin, Base):
    """Подписка браузера на Web Push (одна на устройство/браузер)."""

    __tablename__ = "push_subscriptions"

    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    device_name: Mapped[str] = mapped_column(String(100), default="")
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
