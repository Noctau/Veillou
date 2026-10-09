import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


# Подключается к роутеру API, чтобы формат ошибок попал в OpenAPI (и в TS-типы)
# 422 здесь же: тогда FastAPI не добавляет свой HTTPValidationError ({"detail": [...]})
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 413, 422, 429)
}


class AppError(Exception):
    """Доменное исключение. Сервисы бросают его, а не HTTPException.

    Ответ: {"error": {"code": "...", "message": "..."}}
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Bad request"
    headers: dict[str, str] | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if headers is not None:
            self.headers = headers
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Не найдено"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "Уже существует"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    message = "Нужно войти"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "Недостаточно прав"


class TooManyRequestsError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "too_many_requests"
    message = "Слишком много запросов — попробуйте позже"


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
        headers=exc.headers,
    )


async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    """Нарушение уникальности/ссылки при гонке параллельных запросов — 409, а не 500."""
    log.warning("IntegrityError: %s", exc.orig)
    return await app_error_handler(
        _, ConflictError("Данные изменились параллельно — повторите", code="conflict")
    )


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(422, "validation_error", format_validation_error(exc) or "Некорректные данные")


HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Ошибки Starlette (нет маршрута, не тот метод) — в том же формате."""
    code = HTTP_CODES.get(exc.status_code, f"http_{exc.status_code}")
    response = _error(exc.status_code, code, str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def internal_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Подробности — только в лог: наружу ни текста, ни стектрейса
    log.exception("Необработанная ошибка", exc_info=exc)
    return _error(500, "internal_error", "Внутренняя ошибка сервера — попробуйте позже")


def register_exception_handlers(app: FastAPI) -> None:
    # Сигнатуры обработчиков уже конкретных подтипов Exception — Starlette типизирует шире
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, internal_error_handler)


class InvalidDataError(AppError):
    """Итог частичного обновления не прошёл валидацию."""

    code = "invalid_data"
    message = "Некорректные данные"


# Первый элемент loc у ошибок запроса — откуда поле; пользователю это не нужно
_LOC_SOURCES = frozenset({"body", "query", "path", "header", "cookie"})


def format_validation_error(exc: Any) -> str:
    """Текст pydantic.ValidationError в одну строку для ответа API."""
    parts = []
    for err in exc.errors():
        loc_parts = list(err["loc"])
        if loc_parts and loc_parts[0] in _LOC_SOURCES:
            loc_parts = loc_parts[1:]
        loc = ".".join(str(p) for p in loc_parts)
        msg = str(err["msg"]).removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)
