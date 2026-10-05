from fastapi import APIRouter, Request, Response, status

from app.api.deps import (
    SessionDep,
    SessionToken,
    clear_session_cookie,
    set_session_cookie,
)
from app.schemas.user import LoginRequest, UserRead
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    data: LoginRequest, request: Request, response: Response, db: SessionDep
) -> UserRead:
    user, token = await auth.login(
        db,
        email=data.email,
        password=data.password,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    set_session_cookie(response, token)
    return UserRead.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, db: SessionDep, token: SessionToken = None) -> None:
    if token:
        await auth.logout(db, token)
    clear_session_cookie(response)
