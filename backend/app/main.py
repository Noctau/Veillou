from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from app.api import auth, catalog, events, health, me, quickadd, schedule, tasks, telegram
from app.core.config import settings
from app.core.db import engine
from app.core.exceptions import ERROR_RESPONSES, register_exception_handlers


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

    register_exception_handlers(app)

    api = APIRouter(prefix=settings.API_PREFIX, responses=ERROR_RESPONSES)
    api.include_router(health.router)
    api.include_router(auth.router)
    api.include_router(me.router)
    api.include_router(telegram.router)
    api.include_router(schedule.router)
    api.include_router(events.router)
    api.include_router(events.calendar_router)
    api.include_router(events.recurring_router)
    api.include_router(catalog.router)
    api.include_router(tasks.router)
    api.include_router(quickadd.router)
    app.include_router(api)
    return app


app = create_app()
