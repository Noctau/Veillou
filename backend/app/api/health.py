from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import SessionDep

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str
    db: str


@router.get("/health")
async def health(session: SessionDep) -> Health:
    await session.execute(text("SELECT 1"))
    return Health(status="ok", db="ok")
