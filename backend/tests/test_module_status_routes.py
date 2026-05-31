from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings


def test_module_status_routes_are_wired(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    headers = {
        "X-User-Id": str(uuid4()),
        "X-Roles": "super_admin",
    }
    for module in ("organizations", "chats", "users", "tasks"):
        response = client.get(f"/api/{module}/status", headers=headers)

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "module": module}
