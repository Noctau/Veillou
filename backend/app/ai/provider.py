"""`LLMProvider`: JSON-ответ по Pydantic-схеме, валидация и один повтор.

Провайдер отвечает только за HTTP-вызов (`_chat`); разбор ответа, проверка
схемой и повтор с текстом ошибки — общие. Каждая попытка возвращается в
`Completion.attempts` (или в `LLMError.attempts`) — сервис пишет их в `ai_log`.
Без БД: модуль можно вызывать из скриптов (ai/evals).
"""

import base64
import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol, cast

import httpx
from pydantic import BaseModel, ValidationError

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Image:
    data: bytes
    mime: str = "image/jpeg"

    def b64(self) -> str:
        return base64.b64encode(self.data).decode()


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    images: tuple[Image, ...] = ()


@dataclass(frozen=True)
class RawReply:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class Attempt:
    """Одна попытка (HTTP-вызов) — строка `ai_log`."""

    provider: str
    model: str
    ok: bool
    latency_ms: int
    request: list[dict[str, Any]]
    response: str = ""
    error: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class Completion[T: BaseModel]:
    value: T
    attempts: list[Attempt] = field(default_factory=list)


class LLMError(Exception):
    """ИИ не дал ответа. `message` — для пользователя."""

    message = "ИИ не ответил — попробуйте ещё раз"

    def __init__(self, message: str | None = None, attempts: Sequence[Attempt] = ()) -> None:
        if message is not None:
            self.message = message
        self.attempts = list(attempts)
        super().__init__(self.message)


class LLMUnavailableError(LLMError):
    message = "ИИ сейчас недоступен — попробуйте позже"


class LLMInvalidError(LLMError):
    message = "ИИ ответил непонятно — попробуйте ещё раз"


class LLMRejectedError(LLMError):
    """API отклонил запрос (4xx: ключ, модель, формат) — ждать бессмысленно."""

    message = "ИИ отклонил запрос — проверьте ключ и модель в настройках сервера"


# 4xx, после которых стоит повторить позже (перегрузка, таймаут прокси)
TRANSIENT_STATUSES = frozenset({408, 409, 425, 429})


def _rejected(exc: Exception) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    code = exc.response.status_code
    return 400 <= code < 500 and code not in TRANSIENT_STATUSES


class LLMProvider(Protocol):
    name: str

    async def complete_json[T: BaseModel](
        self,
        messages: Sequence[Message],
        schema: type[T],
        images: Sequence[Image] | None = None,
    ) -> Completion[T]: ...


# ---------- разбор ответа ----------

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def extract_json(text: str) -> Any:
    """JSON из ответа модели: без <think>, ```-обёртки и текста вокруг объекта."""
    text = _FENCE.sub("", _THINK.sub("", text).strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        lo, hi = text.find("{"), text.rfind("}")
        if lo == -1 or hi <= lo:
            raise
        return json.loads(text[lo : hi + 1])


def parse_reply[T: BaseModel](text: str, schema: type[T]) -> T:
    return schema.model_validate(extract_json(text))


def _error_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors()[:10]:
            loc = ".".join(str(p) for p in err["loc"])
            parts.append(f"{loc}: {err['msg']}" if loc else str(err["msg"]))
        return "; ".join(parts)
    return f"{type(exc).__name__}: {exc}"


# Схема для модели проще, чем для проверки (её делает Pydantic): грамматика Ollama
# не понимает длины строк («failed to load model vocabulary required for format»),
# `format: date` и `$ref` внутри `anyOf` — на таких полях модель может вывести только null.
_STRIP_KEYS = frozenset({"maxLength", "minLength", "format", "title", "default"})


def model_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema для провайдера: `$ref` встроены, без длин строк и `format`."""
    full = schema.model_json_schema()
    defs = full.pop("$defs", {})

    def clean(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                target = defs[node["$ref"].rsplit("/", 1)[-1]]
                extra = {k: v for k, v in node.items() if k != "$ref"}
                return clean({**target, **extra})
            result = {k: clean(v) for k, v in node.items() if k not in _STRIP_KEYS}
            if isinstance(node.get("properties"), dict):
                # Имена полей (в т. ч. «title») — не служебные ключи
                result["properties"] = {k: clean(v) for k, v in node["properties"].items()}
            return result
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    return cast(dict[str, Any], clean(full))


FIX_PROMPT = (
    "Ответ не прошёл проверку: {error}\nИсправь и верни только JSON строго по схеме, без пояснений."
)


def _with_images(messages: Sequence[Message], images: Sequence[Image] | None) -> list[Message]:
    """Картинки прикрепляются к последнему сообщению пользователя."""
    result = list(messages)
    if images:
        for i in range(len(result) - 1, -1, -1):
            if result[i].role == "user":
                result[i] = replace(result[i], images=(*result[i].images, *images))
                break
    return result


def _log_request(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Запрос для ai_log: текст целиком, картинки — только количеством."""
    return [
        {"role": m.role, "content": m.content, **({"images": len(m.images)} if m.images else {})}
        for m in messages
    ]


class ChatProvider:
    """Общая часть: JSON по схеме, проверка, один повтор с текстом ошибки."""

    name = "base"

    def __init__(self, model: str, vision_model: str | None = None) -> None:
        self.model = model
        self.vision_model = vision_model or model

    async def _chat(
        self, messages: Sequence[Message], json_schema: dict[str, Any], model: str, name: str
    ) -> RawReply:
        raise NotImplementedError

    async def complete_json[T: BaseModel](
        self,
        messages: Sequence[Message],
        schema: type[T],
        images: Sequence[Image] | None = None,
    ) -> Completion[T]:
        json_schema = model_schema(schema)
        model = self.vision_model if images else self.model
        msgs = _with_images(messages, images)
        attempts: list[Attempt] = []
        for _ in range(2):
            started = time.monotonic()
            request = _log_request(msgs)
            try:
                raw = await self._chat(msgs, json_schema, model, schema.__name__)
            # Index/TypeError — ответ не того формата (прокси отдал не то): как недоступность
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                attempts.append(
                    Attempt(
                        self.name,
                        model,
                        ok=False,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        request=request,
                        error=_error_text(exc)[:2000],
                    )
                )
                if _rejected(exc):
                    raise LLMRejectedError(attempts=attempts) from exc
                raise LLMUnavailableError(attempts=attempts) from exc
            latency = int((time.monotonic() - started) * 1000)
            try:
                value = parse_reply(raw.text, schema)
            except (ValueError, ValidationError) as exc:
                error = _error_text(exc)
                attempts.append(
                    Attempt(
                        self.name,
                        raw.model,
                        ok=False,
                        latency_ms=latency,
                        request=request,
                        response=raw.text,
                        error=error[:2000],
                        prompt_tokens=raw.prompt_tokens,
                        completion_tokens=raw.completion_tokens,
                    )
                )
                # Картинки второй раз не шлём: ответ уже есть, правим только формат
                msgs = [
                    *msgs,
                    Message("assistant", raw.text),
                    Message("user", FIX_PROMPT.format(error=error[:1500])),
                ]
                continue
            attempts.append(
                Attempt(
                    self.name,
                    raw.model,
                    ok=True,
                    latency_ms=latency,
                    request=request,
                    response=raw.text,
                    prompt_tokens=raw.prompt_tokens,
                    completion_tokens=raw.completion_tokens,
                )
            )
            return Completion(value, attempts)
        raise LLMInvalidError(attempts=attempts)


class HttpProvider(ChatProvider):
    """HTTP-часть: общий клиент (тесты подставляют свой) и раздельные таймауты.

    Подключение — коротко: выключенный домашний компьютер за туннелем должен
    отвалиться за секунды и отдать запрос запасному провайдеру, а не ждать 3 минуты.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        vision_model: str | None = None,
        *,
        timeout: float = 180.0,
        connect_timeout: float = 5.0,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(model, vision_model)
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout, connect=connect_timeout)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = client

    async def _post(
        self, path: str, body: dict[str, Any], headers: dict[str, str] | None = None
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        if self.client is not None:
            return await self.client.post(url, json=body, headers=headers, timeout=self.timeout)
        async with httpx.AsyncClient() as client:
            return await client.post(url, json=body, headers=headers, timeout=self.timeout)


class OllamaProvider(HttpProvider):
    """Нативный `/api/chat` Ollama: `format` = JSON Schema (structured outputs)."""

    name = "ollama"

    async def _chat(
        self, messages: Sequence[Message], json_schema: dict[str, Any], model: str, name: str
    ) -> RawReply:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    **({"images": [i.b64() for i in m.images]} if m.images else {}),
                }
                for m in messages
            ],
            "format": json_schema,
            "stream": False,
            # Рассуждения qwen3 удлиняют ответ в разы, а JSON по схеме от них не лучше
            "think": False,
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
        }
        resp = await self._post("/api/chat", body)
        if resp.status_code == 400 and "think" in resp.text:
            # Модель без режима рассуждений
            body.pop("think")
            resp = await self._post("/api/chat", body)
        resp.raise_for_status()
        data = resp.json()
        return RawReply(
            text=data["message"]["content"],
            model=data.get("model", model),
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
        )


SCHEMA_HINT = "Ответ — только JSON-объект по этой JSON Schema:\n{schema}"


class OpenAICompatProvider(HttpProvider):
    """`/chat/completions` любого OpenAI-совместимого API (Timeweb AI, OpenRouter…).

    Просит `response_format=json_schema`; если прокси или модель его не знают (400),
    переходит на `json_object`, а схему кладёт текстом в системное сообщение.
    """

    name = "openai"

    def __init__(self, base_url: str, api_key: str | None, *args: Any, **kwargs: Any) -> None:
        super().__init__(base_url, *args, **kwargs)
        self.api_key = api_key
        # Узнали, что json_schema не поддерживается, — больше не пробуем
        self.json_object = False

    @staticmethod
    def _content(m: Message) -> str | list[dict[str, Any]]:
        if not m.images:
            return m.content
        return [
            {"type": "text", "text": m.content},
            *(
                {"type": "image_url", "image_url": {"url": f"data:{i.mime};base64,{i.b64()}"}}
                for i in m.images
            ),
        ]

    def _body(
        self, messages: Sequence[Message], json_schema: dict[str, Any], model: str, name: str
    ) -> dict[str, Any]:
        msgs = [{"role": m.role, "content": self._content(m)} for m in messages]
        if self.json_object:
            hint = SCHEMA_HINT.format(schema=json.dumps(json_schema, ensure_ascii=False))
            msgs.insert(0, {"role": "system", "content": hint})
            response_format: dict[str, Any] = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": json_schema},
            }
        return {
            "model": model,
            "messages": msgs,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": response_format,
        }

    async def _chat(
        self, messages: Sequence[Message], json_schema: dict[str, Any], model: str, name: str
    ) -> RawReply:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = self._body(messages, json_schema, model, name)
        resp = await self._post("/chat/completions", body, headers)
        if resp.status_code in (400, 422) and not self.json_object:
            self.json_object = True
            body = self._body(messages, json_schema, model, name)
            resp = await self._post("/chat/completions", body, headers)
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage") or {}
        return RawReply(
            text=data["choices"][0]["message"]["content"] or "",
            model=data.get("model", model),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


class FallbackProvider:
    """Основной провайдер, а если он не ответил — запасной.

    Основной — домашняя Ollama за туннелем, запасной — облачный API. После сбоя
    основного (недоступен) следующие `cooldown_sec` сразу идём в запасной, чтобы
    не ждать таймаут подключения на каждом запросе. Ответ не по схеме тоже уходит
    в запасной: облачная модель сильнее. Все попытки — в `attempts` (→ ai_log).
    """

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
        *,
        cooldown_sec: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.cooldown_sec = cooldown_sec
        self.clock = clock
        self.down_until = 0.0
        self.name = f"{primary.name}+{fallback.name}"

    async def complete_json[T: BaseModel](
        self,
        messages: Sequence[Message],
        schema: type[T],
        images: Sequence[Image] | None = None,
    ) -> Completion[T]:
        attempts: list[Attempt] = []
        if self.clock() >= self.down_until:
            try:
                return await self.primary.complete_json(messages, schema, images)
            except LLMUnavailableError as exc:
                attempts += exc.attempts
                self.down_until = self.clock() + self.cooldown_sec
            except (LLMInvalidError, LLMRejectedError) as exc:
                # Не по схеме или отклонён (ключ/модель) — запасной, но без паузы:
                # основной доступен
                attempts += exc.attempts
        try:
            result = await self.fallback.complete_json(messages, schema, images)
        except LLMError as exc:
            raise type(exc)(attempts=[*attempts, *exc.attempts]) from exc
        result.attempts = [*attempts, *result.attempts]
        return result
