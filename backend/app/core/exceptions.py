from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


# Подключается к роутеру API, чтобы формат ошибок попал в OpenAPI (и в TS-типы)
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409)
}


class AppError(Exception):
    """Доменное исключение. Сервисы бросают его, а не HTTPException.

    Ответ: {"error": {"code": "...", "message": "..."}}
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Bad request"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
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


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]


class InvalidDataError(AppError):
    """Итог частичного обновления не прошёл валидацию."""

    code = "invalid_data"
    message = "Некорректные данные"


def format_validation_error(exc: Any) -> str:
    """Текст pydantic.ValidationError в одну строку для ответа API."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        msg = str(err["msg"]).removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)
