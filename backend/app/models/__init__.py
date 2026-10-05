"""Импорт всех моделей, чтобы они попали в Base.metadata (Alembic, тесты)."""

from app.models.session import UserSession
from app.models.user import User

__all__ = ["User", "UserSession"]
