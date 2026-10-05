from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import PostgresDsn, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


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

    TELEGRAM_BOT_TOKEN: SecretStr | None = None
    TELEGRAM_BOT_USERNAME: str | None = None  # без @, для ссылки t.me/<bot>?start=<код>
    TELEGRAM_LINK_CODE_TTL_MIN: int = 10

    @field_validator("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_USERNAME", mode="before")
    @classmethod
    def _empty_is_none(cls, value: Any) -> Any:
        # `TELEGRAM_BOT_TOKEN=` в .env означает «не задан»
        if isinstance(value, str):
            value = value.strip().removeprefix("@")
        return value or None

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
