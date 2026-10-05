"""Импорт всех моделей, чтобы они попали в Base.metadata (Alembic, тесты)."""

from app.models.session import UserSession
from app.models.telegram import TelegramLinkCode
from app.models.user import User

__all__ = ["TelegramLinkCode", "User", "UserSession"]
