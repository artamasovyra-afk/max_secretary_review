from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.auth import get_auth_context
from app.core.config import DEV_AUTH_PRODUCTION_ERROR, get_settings
from app.modules.auth.context import AuthContext
from app.modules.auth.session import create_session_token


@pytest.fixture()
def auth_client() -> TestClient:
    app = FastAPI()

    @app.get("/protected")
    def protected(context: AuthContext = Depends(get_auth_context)) -> dict[str, object]:
        return {
            "user_id": str(context.user_id),
            "organization_id": str(context.organization_id) if context.organization_id else None,
            "chat_id": str(context.chat_id) if context.chat_id else None,
            "roles": context.roles,
            "is_super_admin": context.is_super_admin,
        }

    return TestClient(app)


def test_local_env_headers_build_auth_context(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    organization_id = uuid4()
    chat_id = uuid4()
    monkeypatch.setenv("APP_ENV", "local")
    get_settings.cache_clear()

    response = auth_client.get(
        "/protected",
        headers={
            "X-User-Id": str(user_id),
            "X-Organization-Id": str(organization_id),
            "X-Chat-Id": str(chat_id),
            "X-Roles": "member, chat_admin, super_admin",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user_id),
        "organization_id": str(organization_id),
        "chat_id": str(chat_id),
        "roles": ["member", "chat_admin", "super_admin"],
        "is_super_admin": True,
    }


def test_dev_env_headers_require_dev_auth_enabled(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")
    get_settings.cache_clear()

    response = auth_client.get(
        "/protected",
        headers={
            "X-User-Id": str(user_id),
            "X-Roles": "chat_admin",
        },
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == str(user_id)
    assert response.json()["roles"] == ["chat_admin"]


def test_staging_env_does_not_accept_dev_headers(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")
    get_settings.cache_clear()

    response = auth_client.get("/protected", headers={"X-User-Id": str(uuid4())})

    assert response.status_code == 401
    assert response.json()["detail"] == "Header auth is disabled"


def test_missing_auth_context_returns_401(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    response = auth_client.get("/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication context is required"


def test_webapp_session_cookie_builds_auth_context(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    organization_id = uuid4()
    chat_id = uuid4()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_WEBAPP_AUTH_ENABLED", "true")
    monkeypatch.setenv("MAX_WEBAPP_SESSION_SECRET", "session-secret-value")
    monkeypatch.setenv("MAX_BOT_TOKEN", "bot-token-value")
    monkeypatch.setenv("MAX_WEBAPP_SESSION_COOKIE_NAME", "test_session")
    get_settings.cache_clear()
    token = create_session_token(
        user_id=user_id,
        max_user_id="max-user-001",
        roles=["member"],
        organization_id=organization_id,
        chat_id=chat_id,
        ttl_seconds=600,
        secret="session-secret-value",
        now_ts=4_000_000_000,
    )

    auth_client.cookies.set("test_session", token)
    response = auth_client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user_id),
        "organization_id": str(organization_id),
        "chat_id": str(chat_id),
        "roles": ["member"],
        "is_super_admin": False,
    }


def test_invalid_webapp_session_cookie_returns_401(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_WEBAPP_AUTH_ENABLED", "true")
    monkeypatch.setenv("MAX_WEBAPP_SESSION_SECRET", "session-secret-value")
    monkeypatch.setenv("MAX_BOT_TOKEN", "bot-token-value")
    get_settings.cache_clear()

    auth_client.cookies.set("max_secretary_session", "invalid")
    response = auth_client.get("/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid WebApp session"


def test_query_user_id_is_not_auth_source(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    response = auth_client.get(f"/protected?user_id={uuid4()}")

    assert response.status_code == 401


def test_production_rejects_dev_headers_by_default(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "false")
    get_settings.cache_clear()

    response = auth_client.get("/protected", headers={"X-User-Id": str(uuid4())})

    assert response.status_code == 401
    assert response.json()["detail"] == "Header auth is disabled"


def test_production_forbids_dev_headers_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEV_AUTH_ENABLED", "true")
    get_settings.cache_clear()

    with pytest.raises(ValidationError, match=DEV_AUTH_PRODUCTION_ERROR):
        get_settings()


def test_invalid_header_uuid_returns_401(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    response = auth_client.get("/protected", headers={"X-User-Id": "not-a-uuid"})

    assert response.status_code == 401
    assert response.json()["detail"] == "X-User-Id must be a valid UUID"
