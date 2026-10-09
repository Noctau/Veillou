"""ИИ за интерфейсом `LLMProvider` (M10). Провайдер выбирается в `.env`."""

from pydantic import SecretStr

from app.ai.provider import (
    Attempt,
    Completion,
    FallbackProvider,
    Image,
    LLMError,
    LLMInvalidError,
    LLMProvider,
    LLMRejectedError,
    LLMUnavailableError,
    Message,
    OllamaProvider,
    OpenAICompatProvider,
)
from app.core.config import settings

_provider: LLMProvider | None = None


def _secret(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value else None


def make_provider(
    kind: str,
    base_url: str,
    api_key: str | None,
    model: str,
    vision_model: str | None,
) -> LLMProvider:
    if kind == "openai":
        return OpenAICompatProvider(
            base_url,
            api_key,
            model,
            vision_model,
            timeout=settings.LLM_TIMEOUT_SEC,
            connect_timeout=settings.LLM_CONNECT_TIMEOUT_SEC,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
    return OllamaProvider(
        base_url,
        model,
        vision_model,
        timeout=settings.LLM_TIMEOUT_SEC,
        connect_timeout=settings.LLM_CONNECT_TIMEOUT_SEC,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
    )


def build_provider() -> LLMProvider:
    """Основной провайдер из `LLM_*`; с `LLM_FALLBACK_*` — ещё и запасной."""
    primary = make_provider(
        settings.LLM_PROVIDER,
        settings.LLM_BASE_URL,
        _secret(settings.LLM_API_KEY),
        settings.LLM_MODEL,
        settings.LLM_VISION_MODEL,
    )
    if not settings.LLM_FALLBACK_PROVIDER:
        return primary
    fallback = make_provider(
        settings.LLM_FALLBACK_PROVIDER,
        settings.LLM_FALLBACK_BASE_URL,
        _secret(settings.LLM_FALLBACK_API_KEY),
        settings.LLM_FALLBACK_MODEL,
        settings.LLM_FALLBACK_VISION_MODEL or None,
    )
    return FallbackProvider(primary, fallback, cooldown_sec=settings.LLM_PRIMARY_COOLDOWN_SEC)


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = build_provider()
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """Подменить провайдера (тесты). None — снова из настроек."""
    global _provider
    _provider = provider


__all__ = [
    "Attempt",
    "Completion",
    "Image",
    "LLMError",
    "LLMInvalidError",
    "LLMProvider",
    "LLMRejectedError",
    "LLMUnavailableError",
    "Message",
    "build_provider",
    "get_provider",
    "set_provider",
]
