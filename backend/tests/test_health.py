from fastapi.testclient import TestClient

from app.main import create_app


def test_api_health(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "max_secretary_backend"


def test_api_health_supports_head(client: TestClient) -> None:
    response = client.head("/api/health")

    assert response.status_code == 200


def test_openapi_supports_head(client: TestClient) -> None:
    response = client.head("/openapi.json")

    assert response.status_code == 200


def test_api_health_uses_app_name(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "max_secretary")
    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["service"] == "max_secretary"
