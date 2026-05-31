from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

POSTGRESQL_ASYNCPG_PREFIX = "postgresql+asyncpg://"
DEFAULT_SERVICE_NAME = "max_secretary_backend"
DEFAULT_MAX_API_BASE_URL = "https://platform-api.max.ru"
BITRIX24_CONFIGURATION_ERROR = "BITRIX24_WEBHOOK_URL is required when BITRIX24_ENABLED=true."
DEV_AUTH_PRODUCTION_ERROR = "DEV_AUTH_ENABLED cannot be true in production."
MAX_WEBAPP_SESSION_SECRET_PRODUCTION_ERROR = (
    "MAX_WEBAPP_SESSION_SECRET is required when MAX_WEBAPP_AUTH_ENABLED=true in production."
)
MAX_WEBAPP_BOT_TOKEN_PRODUCTION_ERROR = "MAX_BOT_TOKEN is required when MAX_WEBAPP_AUTH_ENABLED=true in production."
TASK_NUMBER_ALLOWLIST_ERROR = (
    "TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS must be a comma-separated list of positive integers."
)
PRODUCTION_APP_ENVS = frozenset({"production"})


class Settings(BaseSettings):
    app_name: str = DEFAULT_SERVICE_NAME
    app_env: str = "production"
    debug: bool = False
    dev_auth_enabled: bool = False

    database_url: Optional[str] = None
    redis_url: Optional[str] = None

    max_bot_token: SecretStr = SecretStr("")
    max_api_base_url: str = DEFAULT_MAX_API_BASE_URL
    max_webhook_secret: SecretStr = SecretStr("")
    max_webhook_enabled: bool = False
    max_webhook_debug_log: bool = False
    max_sender_enabled: bool = False
    max_interactive_responses_enabled: bool = True
    max_background_notifications_enabled: bool = False
    max_request_timeout_seconds: int = 10
    max_bot_username: str = ""
    task_wizard_delete_user_inputs: bool = False
    webapp_base_url: str = "https://maxsecretary.ru"
    max_webapp_auth_enabled: bool = False
    max_webapp_session_secret: SecretStr = SecretStr("")
    max_webapp_session_cookie_name: str = "max_secretary_session"
    max_webapp_session_ttl_seconds: int = 86400
    max_webapp_initdata_max_age_seconds: int = 86400
    max_webapp_cookie_secure: bool = True
    max_webapp_cookie_samesite: str = "lax"
    super_admin_login: str = ""
    super_admin_password: SecretStr = SecretStr("")
    super_admin_session_secret: SecretStr = SecretStr("")
    super_admin_login_diagnostic: bool = False
    super_admin_session_cookie_name: str = "max_secretary_super_admin"
    super_admin_session_ttl_seconds: int = 28800
    super_admin_cookie_secure: bool = True
    super_admin_cookie_samesite: str = "lax"
    bitrix24_enabled: bool = False
    bitrix24_webhook_url: SecretStr = SecretStr("")
    bitrix24_request_timeout_seconds: int = 15
    bitrix24_sync_on_task_create: bool = False
    bitrix24_sync_on_status_change: bool = False
    bitrix24_sync_on_acceptance: bool = False
    bitrix24_default_responsible_id: Optional[str] = None
    bitrix24_default_created_by_id: Optional[str] = None
    bitrix24_project_group_id: Optional[str] = None
    bitrix24_use_task_control: bool = True

    ai_enabled: bool = False
    ai_provider: str = "none"

    reminders_enabled: bool = True
    reminder_poll_interval_seconds: int = 60
    daily_summary_time: str = "09:00"
    task_deadline_chat_reminders_enabled: bool = False
    task_overdue_notification_lookback_hours: int = Field(default=6, ge=1)
    task_deadline_reminder_allowed_task_numbers: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    @model_validator(mode="after")
    def validate_security_settings(self) -> Settings:
        validate_dev_auth_environment(self.app_env, self.dev_auth_enabled)
        validate_max_webapp_auth_environment(
            self.app_env,
            self.max_webapp_auth_enabled,
            self.max_webapp_session_secret,
            self.max_bot_token,
        )
        return self

    @field_validator("task_deadline_reminder_allowed_task_numbers")
    @classmethod
    def validate_task_deadline_reminder_allowed_task_numbers(cls, value: str) -> str:
        parse_task_number_allowlist(value)
        return value.strip()


def validate_dev_auth_environment(app_env: str, dev_auth_enabled: bool) -> None:
    if app_env.strip().lower() in PRODUCTION_APP_ENVS and dev_auth_enabled:
        raise ValueError(DEV_AUTH_PRODUCTION_ERROR)


def validate_max_webapp_auth_environment(
    app_env: str,
    max_webapp_auth_enabled: bool,
    session_secret: SecretStr,
    bot_credential: SecretStr,
) -> None:
    if app_env.strip().lower() not in PRODUCTION_APP_ENVS or not max_webapp_auth_enabled:
        return
    if not session_secret.get_secret_value():
        raise ValueError(MAX_WEBAPP_SESSION_SECRET_PRODUCTION_ERROR)
    if not bot_credential.get_secret_value():
        raise ValueError(MAX_WEBAPP_BOT_TOKEN_PRODUCTION_ERROR)


def parse_task_number_allowlist(value: str | None) -> frozenset[int] | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None

    numbers: set[int] = set()
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if not item.isdecimal():
            raise ValueError(TASK_NUMBER_ALLOWLIST_ERROR)
        number = int(item)
        if number <= 0:
            raise ValueError(TASK_NUMBER_ALLOWLIST_ERROR)
        numbers.add(number)
    return frozenset(numbers) or None


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_database_url() -> str:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required. max_secretary uses PostgreSQL; "
            "set DATABASE_URL like postgresql+asyncpg://user:password@postgres:5432/max_secretary."
        )
    if not database_url.startswith(POSTGRESQL_ASYNCPG_PREFIX):
        raise RuntimeError("DATABASE_URL must use PostgreSQL asyncpg format: postgresql+asyncpg://...")
    return database_url


def get_bitrix24_webhook_url() -> str:
    settings = get_settings()
    if not settings.bitrix24_enabled:
        return ""
    webhook_url = settings.bitrix24_webhook_url.get_secret_value()
    if not webhook_url:
        raise RuntimeError(BITRIX24_CONFIGURATION_ERROR)
    return webhook_url
