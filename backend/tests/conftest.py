from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

APP_ENV_KEYS = (
    "APP_NAME",
    "APP_ENV",
    "DEBUG",
    "DEV_AUTH_ENABLED",
    "DATABASE_URL",
    "REDIS_URL",
    "MAX_BOT_TOKEN",
    "MAX_API_BASE_URL",
    "MAX_WEBHOOK_SECRET",
    "MAX_WEBHOOK_ENABLED",
    "MAX_WEBHOOK_DEBUG_LOG",
    "MAX_SENDER_ENABLED",
    "MAX_INTERACTIVE_RESPONSES_ENABLED",
    "MAX_BACKGROUND_NOTIFICATIONS_ENABLED",
    "MAX_REQUEST_TIMEOUT_SECONDS",
    "MAX_WEBAPP_AUTH_ENABLED",
    "MAX_WEBAPP_SESSION_SECRET",
    "MAX_WEBAPP_SESSION_COOKIE_NAME",
    "MAX_WEBAPP_SESSION_TTL_SECONDS",
    "MAX_WEBAPP_INITDATA_MAX_AGE_SECONDS",
    "MAX_WEBAPP_COOKIE_SECURE",
    "MAX_WEBAPP_COOKIE_SAMESITE",
    "SUPER_ADMIN_LOGIN",
    "SUPER_ADMIN_PASSWORD",
    "SUPER_ADMIN_SESSION_SECRET",
    "SUPER_ADMIN_LOGIN_DIAGNOSTIC",
    "SUPER_ADMIN_SESSION_COOKIE_NAME",
    "SUPER_ADMIN_SESSION_TTL_SECONDS",
    "SUPER_ADMIN_COOKIE_SECURE",
    "SUPER_ADMIN_COOKIE_SAMESITE",
    "BITRIX24_ENABLED",
    "BITRIX24_WEBHOOK_URL",
    "BITRIX24_REQUEST_TIMEOUT_SECONDS",
    "BITRIX24_SYNC_ON_TASK_CREATE",
    "BITRIX24_SYNC_ON_STATUS_CHANGE",
    "BITRIX24_SYNC_ON_ACCEPTANCE",
    "BITRIX24_DEFAULT_RESPONSIBLE_ID",
    "BITRIX24_DEFAULT_CREATED_BY_ID",
    "BITRIX24_PROJECT_GROUP_ID",
    "BITRIX24_USE_TASK_CONTROL",
    "AI_ENABLED",
    "AI_PROVIDER",
    "REMINDERS_ENABLED",
    "REMINDER_POLL_INTERVAL_SECONDS",
    "DAILY_SUMMARY_TIME",
)


@pytest.fixture(autouse=True)
def isolated_settings_env() -> Iterator[None]:
    original_values = {key: os.environ.get(key) for key in APP_ENV_KEYS}
    for key in APP_ENV_KEYS:
        os.environ.pop(key, None)
    get_settings.cache_clear()
    yield
    for key, value in original_values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client
