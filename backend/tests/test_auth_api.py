from __future__ import annotations

import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from urllib import parse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_max_webapp_auth_service
from app.core.config import get_settings
from app.main import create_app
from app.modules.auth.max_webapp import VerifiedMaxWebAppUser
from app.modules.auth.webapp_service import (
    WebAppAuthenticatedUser,
    WebAppAuthServiceError,
    WebAppChatContext,
)

TEST_BOT_TOKEN = "test-bot-token"


@pytest.fixture()
def auth_api_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeMaxWebAppAuthService]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MAX_WEBAPP_AUTH_ENABLED", "true")
    monkeypatch.setenv("MAX_WEBAPP_SESSION_SECRET", "session-secret-value")
    monkeypatch.setenv("MAX_WEBAPP_SESSION_COOKIE_NAME", "test_session")
    monkeypatch.setenv("MAX_WEBAPP_SESSION_TTL_SECONDS", "600")
    monkeypatch.setenv("MAX_WEBAPP_COOKIE_SECURE", "false")
    monkeypatch.setenv("MAX_BOT_TOKEN", TEST_BOT_TOKEN)
    get_settings.cache_clear()

    service = FakeMaxWebAppAuthService()
    app = create_app()
    app.dependency_overrides[get_max_webapp_auth_service] = lambda: service
    return TestClient(app), service


def test_create_max_webapp_session_sets_cookie(
    auth_api_client: tuple[TestClient, "FakeMaxWebAppAuthService"],
) -> None:
    client, service = auth_api_client
    init_data = _build_init_data(
        credential=TEST_BOT_TOKEN,
        user={"user_id": "max-user-001", "display_name": "Ivan"},
    )

    response = client.post("/api/auth/max-webapp/session", json={"init_data": init_data})

    assert response.status_code == 200
    assert "test_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json()["user"]["display_name"] == "Ivan"
    assert response.json()["user"]["roles"] == ["member"]
    assert response.json()["context"]["available_chats"][0]["role"] == "member"
    assert service.create_count == 1


def test_create_max_webapp_session_reuses_existing_user(
    auth_api_client: tuple[TestClient, "FakeMaxWebAppAuthService"],
) -> None:
    client, service = auth_api_client
    existing_user = service.add_user(max_user_id="max-user-001", display_name="Existing User")
    init_data = _build_init_data(
        credential=TEST_BOT_TOKEN,
        user={"user_id": "max-user-001", "display_name": "New Name"},
    )

    response = client.post("/api/auth/max-webapp/session", json={"initData": init_data})

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(existing_user.id)
    assert response.json()["user"]["display_name"] == "Existing User"
    assert service.create_count == 0


def test_create_max_webapp_session_rejects_invalid_init_data(
    auth_api_client: tuple[TestClient, "FakeMaxWebAppAuthService"],
) -> None:
    client, service = auth_api_client
    init_data = _build_init_data(
        credential="wrong-token",
        user={"user_id": "max-user-001"},
    )

    response = client.post("/api/auth/max-webapp/session", json={"init_data": init_data})

    assert response.status_code == 401
    assert response.json()["detail"] == "initData signature mismatch"
    assert service.create_count == 0


def test_get_me_with_session_cookie(
    auth_api_client: tuple[TestClient, "FakeMaxWebAppAuthService"],
) -> None:
    client, service = auth_api_client
    service.add_user(max_user_id="max-user-001", display_name="Ivan")
    init_data = _build_init_data(
        credential=TEST_BOT_TOKEN,
        user={"user_id": "max-user-001"},
    )

    session_response = client.post("/api/auth/max-webapp/session", json={"init_data": init_data})
    response = client.get("/api/auth/me")

    assert session_response.status_code == 200
    assert response.status_code == 200
    assert response.json()["user"]["display_name"] == "Ivan"
    assert response.json()["session_expires_at"] is not None


def test_get_me_without_session_cookie_returns_401(
    auth_api_client: tuple[TestClient, "FakeMaxWebAppAuthService"],
) -> None:
    client, _service = auth_api_client

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_query_user_id_does_not_authenticate_me(
    auth_api_client: tuple[TestClient, "FakeMaxWebAppAuthService"],
) -> None:
    client, _service = auth_api_client

    response = client.get(f"/api/auth/me?user_id={uuid4()}")

    assert response.status_code == 401


def test_logout_clears_cookie(
    auth_api_client: tuple[TestClient, "FakeMaxWebAppAuthService"],
) -> None:
    client, service = auth_api_client
    service.add_user(max_user_id="max-user-001", display_name="Ivan")
    init_data = _build_init_data(
        credential=TEST_BOT_TOKEN,
        user={"user_id": "max-user-001"},
    )
    client.post("/api/auth/max-webapp/session", json={"init_data": init_data})

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "test_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


class FakeMaxWebAppAuthService:
    def __init__(self) -> None:
        self.users_by_max_id: dict[str, SimpleNamespace] = {}
        self.users_by_id: dict[UUID, SimpleNamespace] = {}
        self.create_count = 0
        self.organization_id = uuid4()
        self.chat_id = uuid4()

    def add_user(self, *, max_user_id: str, display_name: str) -> SimpleNamespace:
        user = SimpleNamespace(
            id=uuid4(),
            max_user_id=max_user_id,
            display_name=display_name,
            username=None,
        )
        self.users_by_max_id[max_user_id] = user
        self.users_by_id[user.id] = user
        return user

    async def resolve_verified_user(self, verified_user: VerifiedMaxWebAppUser) -> WebAppAuthenticatedUser:
        user = self.users_by_max_id.get(verified_user.max_user_id)
        if user is None:
            self.create_count += 1
            user = self.add_user(
                max_user_id=verified_user.max_user_id,
                display_name=verified_user.display_name or "MAX test user",
            )
        return self._authenticated_user(user)

    async def get_authenticated_user(self, user_id: UUID) -> WebAppAuthenticatedUser:
        user = self.users_by_id.get(user_id)
        if user is None:
            raise WebAppAuthServiceError("missing user")
        return self._authenticated_user(user)

    def _authenticated_user(self, user: SimpleNamespace) -> WebAppAuthenticatedUser:
        return WebAppAuthenticatedUser(
            user=user,
            roles=["member"],
            organization_id=self.organization_id,
            chat_id=self.chat_id,
            available_chats=[
                WebAppChatContext(
                    id=self.chat_id,
                    organization_id=self.organization_id,
                    title="MAX test chat",
                    role="member",
                )
            ],
        )


def _build_init_data(*, credential: str, user: dict[str, object]) -> str:
    params = {
        "auth_date": str(int(time.time())),
        "user": json.dumps(user, sort_keys=True, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", credential.encode("utf-8"), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return parse.urlencode(params)
