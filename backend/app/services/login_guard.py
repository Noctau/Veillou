"""Защита от перебора пароля.

Каждый неудачный вход пишется дважды: на адрес клиента и на аккаунт (email).
Пока за последние LOGIN_WINDOW_MIN минут ошибок больше лимита, вход отвечает 429
ещё до проверки пароля — argon2 не тратится. Удачный вход сбрасывает счётчик
аккаунта (опечатка владельца не копится), счётчик адреса живёт до конца окна.
Счётчики в БД: общие для процессов и переживают рестарт.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import TooManyRequestsError
from app.core.time import now_utc
from app.models import LoginFailure


class TooManyLoginAttemptsError(TooManyRequestsError):
    code = "too_many_login_attempts"
    message = "Слишком много неудачных попыток входа — попробуйте позже"


def ip_key(ip: str | None) -> str:
    return f"ip:{ip or 'unknown'}"


def account_key(email: str) -> str:
    return f"email:{email.strip().lower()[:320]}"


def _window() -> timedelta:
    return timedelta(minutes=settings.LOGIN_WINDOW_MIN)


async def _oldest_if_over(
    db: AsyncSession, key: str, limit: int, since: datetime
) -> datetime | None:
    """Самая ранняя ошибка в окне, если их уже `limit` или больше."""
    count, oldest = (
        await db.execute(
            select(func.count(), func.min(LoginFailure.created_at)).where(
                LoginFailure.key == key, LoginFailure.created_at > since
            )
        )
    ).one()
    return oldest if count >= limit else None


async def check(db: AsyncSession, *, ip: str | None, email: str) -> None:
    """429, если с этого адреса или в этот аккаунт уже слишком много ошибок."""
    now = now_utc()
    since = now - _window()
    limits = (
        (ip_key(ip), settings.LOGIN_MAX_FAILURES_PER_IP),
        (account_key(email), settings.LOGIN_MAX_FAILURES_PER_ACCOUNT),
    )
    for key, limit in limits:
        oldest = await _oldest_if_over(db, key, limit, since)
        if oldest is not None:
            retry = max(1, int((oldest + _window() - now).total_seconds()) + 1)
            raise TooManyLoginAttemptsError(headers={"Retry-After": str(retry)})


async def record_failure(db: AsyncSession, *, ip: str | None, email: str) -> None:
    """Запоминает неудачу. Коммитит: ответ — ошибка, но счётчик должен остаться."""
    db.add_all([LoginFailure(key=ip_key(ip)), LoginFailure(key=account_key(email))])
    await db.commit()


async def clear_account(db: AsyncSession, email: str) -> None:
    """Удачный вход: ошибки аккаунта больше не в счёт. Не коммитит."""
    await db.execute(delete(LoginFailure).where(LoginFailure.key == account_key(email)))


async def prune(db: AsyncSession, now: datetime | None = None) -> None:
    """Ночная чистка: ошибки старше окна не нужны."""
    cutoff = (now or now_utc()) - _window()
    await db.execute(delete(LoginFailure).where(LoginFailure.created_at <= cutoff))
    await db.commit()
