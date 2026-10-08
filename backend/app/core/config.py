from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import PostgresDsn, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV_SECRET = "dev-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env лежит в корне монорепо (его же читает docker compose)
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Veillou"
    ENV: Literal["dev", "test", "prod"] = "dev"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str = "veillou"
    POSTGRES_PASSWORD: SecretStr = SecretStr("veillou")
    POSTGRES_DB: str = "veillou"

    DEFAULT_TIMEZONE: str = "Europe/Moscow"

    SESSION_COOKIE_NAME: str = "veillou_session"
    SESSION_TTL_DAYS: int = 30
    # В проде фронт и /api на одном HTTPS-домене -> Secure. В dev по LAN — http.
    SESSION_COOKIE_SECURE: bool = False

    # Перебор пароля: неудачные входы за окно — с одного адреса и в один аккаунт
    LOGIN_WINDOW_MIN: int = 15
    LOGIN_MAX_FAILURES_PER_IP: int = 20
    LOGIN_MAX_FAILURES_PER_ACCOUNT: int = 50

    # Подпись ссылок на файлы. В проде — длинная случайная строка в .env
    SECRET_KEY: SecretStr = SecretStr(DEV_SECRET)

    # Файлы (вложения, фото конспектов). MVP — диск сервера.
    STORAGE_DIR: Path = REPO_ROOT / "data" / "files"
    MAX_UPLOAD_MB: int = 100
    FILE_URL_TTL_MIN: int = 60

    TELEGRAM_BOT_TOKEN: SecretStr | None = None
    TELEGRAM_BOT_USERNAME: str | None = None  # без @, для ссылки t.me/<bot>?start=<код>
    TELEGRAM_LINK_CODE_TTL_MIN: int = 10

    # Публичный адрес приложения (https://…) — для кнопки «Открыть» в Telegram.
    # Без него ссылок в боте нет: Telegram не принимает http://localhost.
    APP_URL: str | None = None

    # Web Push (VAPID). Ключи: `make vapid-keys`. Subject — mailto: или https: владельца.
    VAPID_PUBLIC_KEY: str | None = None
    VAPID_PRIVATE_KEY: SecretStr | None = None
    VAPID_SUBJECT: str = "mailto:admin@localhost"

    # Как часто воркер проверяет очереди (точность напоминаний — не хуже минуты)
    WORKER_POLL_SEC: float = 10.0

    # ИИ (M10). ollama — нативный /api/chat; openai — любой OpenAI-совместимый API
    # (base url вида https://…/v1). Модели: текст и картинки (фото задания).
    LLM_PROVIDER: Literal["ollama", "openai"] = "ollama"
    LLM_BASE_URL: str = "http://localhost:11434"
    LLM_API_KEY: SecretStr | None = None
    LLM_MODEL: str = "qwen3:8b"
    LLM_VISION_MODEL: str = "qwen2.5vl:7b"
    LLM_TIMEOUT_SEC: float = 180.0
    # Подключение — коротко: выключенный домашний компьютер не должен держать запрос
    LLM_CONNECT_TIMEOUT_SEC: float = 5.0
    LLM_TEMPERATURE: float = 0.2
    # Потолок длины ответа: локальные модели с JSON-грамматикой иногда «зацикливаются»
    LLM_MAX_TOKENS: int = 2048
    # Запасной провайдер: если основной недоступен или ответил не по схеме.
    # Пусто — без запасного. После сбоя основного LLM_PRIMARY_COOLDOWN_SEC сразу в запасной.
    LLM_FALLBACK_PROVIDER: Literal["ollama", "openai"] | None = None
    LLM_FALLBACK_BASE_URL: str = ""
    LLM_FALLBACK_API_KEY: SecretStr | None = None
    LLM_FALLBACK_MODEL: str = ""
    LLM_FALLBACK_VISION_MODEL: str = ""  # пусто — та же модель
    LLM_PRIMARY_COOLDOWN_SEC: float = 300.0
    # Ни один провайдер не отвечает — запросы ждут в очереди и выполняются по одному,
    # когда ИИ появится. Дольше этого ожидание бессмысленно — запрос отменяется.
    LLM_QUEUE_MAX_HOURS: float = 72.0
    # Хранить ai_log столько дней
    AI_LOG_KEEP_DAYS: int = 90

    @field_validator("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_USERNAME", mode="before")
    @classmethod
    def _empty_is_none(cls, value: Any) -> Any:
        # `TELEGRAM_BOT_TOKEN=` в .env означает «не задан»
        if isinstance(value, str):
            value = value.strip().removeprefix("@")
        return value or None

    @field_validator(
        "APP_URL",
        "VAPID_PUBLIC_KEY",
        "VAPID_PRIVATE_KEY",
        "LLM_API_KEY",
        "LLM_FALLBACK_PROVIDER",
        "LLM_FALLBACK_API_KEY",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip().rstrip("/")
        return value or None

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def _empty_secret(cls, value: Any) -> Any:
        # `SECRET_KEY=` в .env — не задан
        return value or DEV_SECRET

    @model_validator(mode="after")
    def _prod_secret(self) -> "Settings":
        if self.ENV == "prod" and self.SECRET_KEY.get_secret_value() == DEV_SECRET:
            raise ValueError("В проде задайте SECRET_KEY в .env")
        return self

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD.get_secret_value(),
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        ).unicode_string()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
