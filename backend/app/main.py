from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from app.api import health
from app.core.config import settings
from app.core.db import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


def _operation_id(route: APIRoute) -> str:
    # Короткие operationId -> аккуратные имена в сгенерированных TS-типах
    return route.name


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )

    api = APIRouter(prefix=settings.API_PREFIX)
    api.include_router(health.router)
    app.include_router(api)
    return app


app = create_app()
