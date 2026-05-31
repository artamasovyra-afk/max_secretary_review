from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    DEV_AUTH_PRODUCTION_ERROR,
    MAX_WEBAPP_BOT_TOKEN_PRODUCTION_ERROR,
    MAX_WEBAPP_SESSION_SECRET_PRODUCTION_ERROR,
    Settings,
    get_bitrix24_webhook_url,
    get_database_url,
    get_settings,
    parse_task_number_allowlist,
)


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        get_database_url()


def test_database_url_must_be_postgresql_asyncpg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

    with pytest.raises(RuntimeError, match="PostgreSQL asyncpg"):
        get_database_url()


def test_database_url_accepts_postgresql_asyncpg(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql+asyncpg://max_secretary:CHANGE_ME@postgres:5432/max_secretary"
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert get_database_url() == database_url


def test_settings_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "max_secretary_test")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:password@postgres:5432/max_secretary")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/1")
    monkeypatch.setenv("MAX_BOT_TOKEN", "bot-token-value")
    monkeypatch.setenv("MAX_API_BASE_URL", "https://max-api.example.invalid")
    monkeypatch.setenv("MAX_WEBHOOK_SECRET", "webhook-secret-value")
    monkeypatch.setenv("MAX_WEBHOOK_ENABLED", "false")
    monkeypatch.setenv("MAX_WEBHOOK_DEBUG_LOG", "true")
    monkeypatch.setenv("MAX_SENDER_ENABLED", "true")
    monkeypatch.setenv("MAX_INTERACTIVE_RESPONSES_ENABLED", "true")
    monkeypatch.setenv("MAX_BACKGROUND_NOTIFICATIONS_ENABLED", "false")
    monkeypatch.setenv("MAX_REQUEST_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("MAX_BOT_USERNAME", "secretary_oren_bot")
    monkeypatch.setenv("MAX_WEBAPP_AUTH_ENABLED", "true")
    monkeypatch.setenv("MAX_WEBAPP_SESSION_SECRET", "session-secret-value")
    monkeypatch.setenv("MAX_WEBAPP_SESSION_COOKIE_NAME", "test_session")
    monkeypatch.setenv("MAX_WEBAPP_SESSION_TTL_SECONDS", "600")
    monkeypatch.setenv("MAX_WEBAPP_INITDATA_MAX_AGE_SECONDS", "300")
    monkeypatch.setenv("MAX_WEBAPP_COOKIE_SECURE", "false")
    monkeypatch.setenv("MAX_WEBAPP_COOKIE_SAMESITE", "strict")
    monkeypatch.setenv("BITRIX24_ENABLED", "true")
    monkeypatch.setenv("BITRIX24_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("BITRIX24_REQUEST_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("BITRIX24_SYNC_ON_TASK_CREATE", "true")
    monkeypatch.setenv("BITRIX24_SYNC_ON_STATUS_CHANGE", "true")
    monkeypatch.setenv("BITRIX24_SYNC_ON_ACCEPTANCE", "true")
    monkeypatch.setenv("BITRIX24_DEFAULT_RESPONSIBLE_ID", "101")
    monkeypatch.setenv("BITRIX24_DEFAULT_CREATED_BY_ID", "102")
    monkeypatch.setenv("BITRIX24_PROJECT_GROUP_ID", "103")
    monkeypatch.setenv("BITRIX24_USE_TASK_CONTROL", "false")
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("AI_PROVIDER", "none")
    monkeypatch.setenv("REMINDERS_ENABLED", "false")
    monkeypatch.setenv("REMINDER_POLL_INTERVAL_SECONDS", "120")
    monkeypatch.setenv("DAILY_SUMMARY_TIME", "10:30")
    monkeypatch.setenv("TASK_DEADLINE_CHAT_REMINDERS_ENABLED", "true")
    monkeypatch.setenv("TASK_OVERDUE_NOTIFICATION_LOOKBACK_HOURS", "12")
    monkeypatch.setenv("TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS", "53, 54")

    settings = get_settings()

    assert settings.app_name == "max_secretary_test"
    assert settings.app_env == "test"
    assert settings.debug is True
    assert settings.dev_auth_enabled is True
    assert settings.database_url == "postgresql+asyncpg://user:password@postgres:5432/max_secretary"
    assert settings.redis_url == "redis://redis:6379/1"
    assert settings.max_bot_token.get_secret_value() == "bot-token-value"
    assert settings.max_api_base_url == "https://max-api.example.invalid"
    assert settings.max_webhook_secret.get_secret_value() == "webhook-secret-value"
    assert settings.max_webhook_enabled is False
    assert settings.max_webhook_debug_log is True
    assert settings.max_sender_enabled is True
    assert settings.max_interactive_responses_enabled is True
    assert settings.max_background_notifications_enabled is False
    assert settings.max_request_timeout_seconds == 15
    assert settings.max_bot_username == "secretary_oren_bot"
    assert settings.max_webapp_auth_enabled is True
    assert settings.max_webapp_session_secret.get_secret_value() == "session-secret-value"
    assert settings.max_webapp_session_cookie_name == "test_session"
    assert settings.max_webapp_session_ttl_seconds == 600
    assert settings.max_webapp_initdata_max_age_seconds == 300
    assert settings.max_webapp_cookie_secure is False
    assert settings.max_webapp_cookie_samesite == "strict"
    assert settings.bitrix24_enabled is True
    assert settings.bitrix24_webhook_url.get_secret_value() == "https://example.invalid/webhook"
    assert settings.bitrix24_request_timeout_seconds == 20
    assert settings.bitrix24_sync_on_task_create is True
    assert settings.bitrix24_sync_on_status_change is True
    assert settings.bitrix24_sync_on_acceptance is True
    assert settings.bitrix24_default_responsible_id == "101"
    assert settings.bitrix24_default_created_by_id == "102"
    assert settings.bitrix24_project_group_id == "103"
    assert settings.bitrix24_use_task_control is False
    assert settings.ai_enabled is True
    assert settings.ai_provider == "none"
    assert settings.reminders_enabled is False
    assert settings.reminder_poll_interval_seconds == 120
    assert settings.daily_summary_time == "10:30"
    assert settings.task_deadline_chat_reminders_enabled is True
    assert settings.task_overdue_notification_lookback_hours == 12
    assert settings.task_deadline_reminder_allowed_task_numbers == "53, 54"
    assert "bot-token-value" not in repr(settings)
    assert "webhook-secret-value" not in repr(settings)
    assert "session-secret-value" not in repr(settings)
    assert "https://example.invalid/webhook" not in repr(settings)


def test_parse_task_number_allowlist() -> None:
    assert parse_task_number_allowlist("") is None
    assert parse_task_number_allowlist("  ") is None
    assert parse_task_number_allowlist("53") == frozenset({53})
    assert parse_task_number_allowlist("53, 54,53") == frozenset({53, 54})


def test_settings_rejects_invalid_task_number_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS", "53, nope")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert "TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS" in str(exc_info.value)


def test_settings_rejects_dev_auth_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("MAX_BOT_TOKEN", "bot-token-value")
    monkeypatch.setenv("MAX_WEBHOOK_SECRET", "webhook-secret-value")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    error = str(exc_info.value)
    assert DEV_AUTH_PRODUCTION_ERROR in error
    assert "bot-token-value" not in error
    assert "webhook-secret-value" not in error


def test_settings_allows_production_without_dev_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "false")

    settings = Settings()

    assert settings.app_env == "production"
    assert settings.dev_auth_enabled is False


def test_settings_requires_webapp_session_secret_when_enabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_WEBAPP_AUTH_ENABLED", "true")
    monkeypatch.setenv("MAX_BOT_TOKEN", "bot-token-value")
    monkeypatch.delenv("MAX_WEBAPP_SESSION_SECRET", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    error = str(exc_info.value)
    assert MAX_WEBAPP_SESSION_SECRET_PRODUCTION_ERROR in error
    assert "bot-token-value" not in error


def test_settings_requires_webapp_bot_token_when_enabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_WEBAPP_AUTH_ENABLED", "true")
    monkeypatch.setenv("MAX_WEBAPP_SESSION_SECRET", "session-secret-value")
    monkeypatch.delenv("MAX_BOT_TOKEN", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    error = str(exc_info.value)
    assert MAX_WEBAPP_BOT_TOKEN_PRODUCTION_ERROR in error
    assert "session-secret-value" not in error


def test_settings_allows_webapp_auth_in_test_with_local_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MAX_WEBAPP_AUTH_ENABLED", "true")

    settings = Settings()

    assert settings.max_webapp_auth_enabled is True


@pytest.mark.parametrize("app_env", ["local", "dev", "test"])
def test_settings_allows_dev_auth_outside_production(
    app_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")

    settings = Settings()

    assert settings.app_env == app_env
    assert settings.dev_auth_enabled is True


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "cached_service")

    first = get_settings()
    second = get_settings()

    assert first is second


def test_bitrix24_webhook_url_not_required_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITRIX24_ENABLED", "false")
    monkeypatch.setenv("BITRIX24_WEBHOOK_URL", "https://example.invalid/webhook")

    assert get_bitrix24_webhook_url() == ""


def test_bitrix24_webhook_url_required_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITRIX24_ENABLED", "true")
    monkeypatch.delenv("BITRIX24_WEBHOOK_URL", raising=False)

    with pytest.raises(RuntimeError, match="BITRIX24_WEBHOOK_URL is required"):
        get_bitrix24_webhook_url()


def test_bitrix24_webhook_url_returns_secret_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    webhook_url = "https://example.invalid/webhook"
    monkeypatch.setenv("BITRIX24_ENABLED", "true")
    monkeypatch.setenv("BITRIX24_WEBHOOK_URL", webhook_url)

    assert get_bitrix24_webhook_url() == webhook_url
