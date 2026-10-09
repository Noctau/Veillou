"""Конфигурация: секреты не утекают через repr, ошибки — сразу при старте (L-08, L-09, L-20)."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

SECRET = "s3cr3t-audit-password"


def make(**over: Any) -> Settings:
    return Settings(_env_file=None, **over)  # type: ignore[call-arg]


def test_db_password_not_in_repr_or_dump():
    s = make(POSTGRES_PASSWORD=SECRET)
    assert SECRET not in repr(s)
    assert SECRET not in str(s.model_dump())
    assert SECRET in s.DATABASE_URL  # а подключению он доступен


def test_prod_needs_long_secret_key():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make(ENV="prod", SECRET_KEY="short-secret")
    assert make(ENV="prod", SECRET_KEY="x" * 32).ENV == "prod"


def test_unknown_default_timezone_fails_fast():
    with pytest.raises(ValidationError, match="DEFAULT_TIMEZONE"):
        make(DEFAULT_TIMEZONE="Mars/Olympus")


@pytest.mark.parametrize("url", ["veillou.example.com", "ftp://x.ru", "https://"])
def test_app_url_must_be_http_url(url: str):
    with pytest.raises(ValidationError, match="APP_URL"):
        make(APP_URL=url)


def test_app_url_ok():
    assert make(APP_URL="https://veillou.example.com/").APP_URL == "https://veillou.example.com"


def test_fallback_llm_needs_url_and_model():
    with pytest.raises(ValidationError, match="LLM_FALLBACK"):
        make(LLM_FALLBACK_PROVIDER="openai", LLM_FALLBACK_BASE_URL="https://api.x/v1")
    s = make(
        LLM_FALLBACK_PROVIDER="openai",
        LLM_FALLBACK_BASE_URL="https://api.x/v1",
        LLM_FALLBACK_MODEL="gpt",
    )
    assert s.LLM_FALLBACK_MODEL == "gpt"


def test_vapid_subject_format():
    with pytest.raises(ValidationError, match="VAPID_SUBJECT"):
        make(VAPID_SUBJECT="admin@example.com")
