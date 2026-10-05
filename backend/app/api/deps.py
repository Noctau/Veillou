from typing import Annotated

from fastapi import Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.exceptions import UnauthorizedError
from app.models import User
from app.services import auth

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        token,
        max_age=int(auth.session_ttl().total_seconds()),
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


SessionToken = Annotated[
    str | None, Cookie(alias=settings.SESSION_COOKIE_NAME, include_in_schema=False)
]


async def get_current_user(db: SessionDep, response: Response, token: SessionToken = None) -> User:
    if not token:
        raise UnauthorizedError()
    active = await auth.resolve_session(db, token)
    if active is None:
        raise UnauthorizedError("Сессия истекла, войдите снова", code="session_expired")
    if active.renewed:
        set_session_cookie(response, token)
    return active.user


CurrentUser = Annotated[User, Depends(get_current_user)]
