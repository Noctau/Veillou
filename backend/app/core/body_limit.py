"""Лимит размера тела запроса — до роутинга, аутентификации и разбора тела.

FastAPI читает тело целиком (JSON — в память, multipart — во временные файлы)
раньше, чем выполнит зависимости, в том числе проверку сессии. Без этого
middleware аноним мог прислать на любой путь столько, сколько пропустит прокси.

Большой `Content-Length` отклоняется сразу; тело без длины (chunked) считается
по мере чтения, и при превышении приложение получает ошибку чтения, а клиент — 413.
"""

import contextlib
import json
import re
from collections.abc import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

MIB = 1024 * 1024


def request_body_limit(path: str) -> int:
    """Байт на тело: загрузка файлов — MAX_UPLOAD_MB (+1 МБ на multipart), остальное —
    MAX_REQUEST_BODY_KB (самый большой JSON — конспект до 200 000 символов)."""
    prefix = re.escape(settings.API_PREFIX)
    if re.fullmatch(rf"{prefix}/attachments(?:/[^/]+/replace)?", path):
        return (settings.MAX_UPLOAD_MB + 1) * MIB
    return settings.MAX_REQUEST_BODY_KB * 1024


class _BodyTooLargeError(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, limit_for: Callable[[str], int] = request_body_limit) -> None:
        self.app = app
        self.limit_for = limit_for

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope["path"])
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > limit:
            await _reject(send, limit)
            return

        received = 0
        exceeded = False
        started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLargeError
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if exceeded:
                return  # ответ приложения на оборванное тело (400/500) не нужен — будет 413
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        with contextlib.suppress(_BodyTooLargeError):
            await self.app(scope, limited_receive, guarded_send)
        if exceeded and not started:
            await _reject(send, limit)


async def _reject(send: Send, limit: int) -> None:
    size = f"{limit // MIB} МБ" if limit >= MIB else f"{limit // 1024} КБ"
    body = json.dumps(
        {"error": {"code": "request_too_large", "message": f"Запрос больше {size}"}},
        ensure_ascii=False,
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
