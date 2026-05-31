from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.api.users import get_user_service
from app.core.config import get_settings
from app.main import create_app
from app.modules.users.schemas import UserCreate, UserUpdate


class UserRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    max_user_id: Optional[str]
    display_name: str
    username: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    created_at: datetime
    updated_at: datetime


class FakeUserService:
    def __init__(self) -> None:
        self.users: dict[UUID, UserRecord] = {}

    async def create(self, payload: UserCreate) -> UserRecord:
        now = datetime.now(timezone.utc)
        user = UserRecord(
            id=uuid4(),
            max_user_id=payload.max_user_id,
            display_name=payload.display_name,
            username=payload.username,
            phone=payload.phone,
            email=payload.email,
            created_at=now,
            updated_at=now,
        )
        self.users[user.id] = user
        return user

    async def list(self) -> list[UserRecord]:
        return list(self.users.values())

    async def get(self, user_id: UUID) -> UserRecord:
        user = self.users.get(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    async def update(self, user_id: UUID, payload: UserUpdate) -> UserRecord:
        user = await self.get(user_id)
        values = payload.model_dump(exclude_unset=True)
        values["updated_at"] = datetime.now(timezone.utc)
        updated = user.model_copy(update=values)
        self.users[user_id] = updated
        return updated


def _auth_headers(*, user_id: UUID | None = None, roles: str = "super_admin") -> dict[str, str]:
    return {
        "X-User-Id": str(user_id or uuid4()),
        "X-Roles": roles,
    }


@pytest.fixture()
def users_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeUserService]:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    app = create_app()
    service = FakeUserService()
    app.dependency_overrides[get_user_service] = lambda: service
    with TestClient(app, headers=_auth_headers()) as client:
        yield client, service


def test_create_user(users_client: tuple[TestClient, FakeUserService]) -> None:
    client, _service = users_client

    response = client.post(
        "/api/users",
        json={
            "max_user_id": None,
            "display_name": "Ivan Petrov",
            "username": "ivan",
            "phone": None,
            "email": "ivan@example.com",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["max_user_id"] is None
    assert payload["display_name"] == "Ivan Petrov"
    assert payload["username"] == "ivan"
    assert payload["phone"] is None
    assert payload["email"] == "ivan@example.com"
    assert payload["id"]


def test_list_users_requires_auth(users_client: tuple[TestClient, FakeUserService]) -> None:
    client, _service = users_client

    with TestClient(client.app) as unauthenticated_client:
        response = unauthenticated_client.get("/api/users")

    assert response.status_code == 401


def test_list_users_requires_admin_role(users_client: tuple[TestClient, FakeUserService]) -> None:
    client, _service = users_client

    response = client.get("/api/users", headers=_auth_headers(roles="member"))

    assert response.status_code == 403


def test_user_can_get_self(users_client: tuple[TestClient, FakeUserService]) -> None:
    client, _service = users_client
    created = client.post("/api/users", json={"display_name": "Self User"}).json()
    user_id = UUID(created["id"])

    response = client.get(f"/api/users/{user_id}", headers=_auth_headers(user_id=user_id, roles="member"))

    assert response.status_code == 200
    assert response.json()["display_name"] == "Self User"


def test_user_cannot_get_other_user(users_client: tuple[TestClient, FakeUserService]) -> None:
    client, _service = users_client
    created = client.post("/api/users", json={"display_name": "Other User"}).json()

    response = client.get(f"/api/users/{created['id']}", headers=_auth_headers(roles="member"))

    assert response.status_code == 403


def test_create_user_requires_display_name(
    users_client: tuple[TestClient, FakeUserService],
) -> None:
    client, _service = users_client

    response = client.post("/api/users", json={"username": "missing-name"})

    assert response.status_code == 422


def test_list_users(users_client: tuple[TestClient, FakeUserService]) -> None:
    client, _service = users_client
    client.post("/api/users", json={"display_name": "First User"})
    client.post("/api/users", json={"display_name": "Second User"})

    response = client.get("/api/users")

    assert response.status_code == 200
    assert [item["display_name"] for item in response.json()] == [
        "First User",
        "Second User",
    ]


def test_get_user(users_client: tuple[TestClient, FakeUserService]) -> None:
    client, _service = users_client
    created = client.post("/api/users", json={"display_name": "Lookup User"}).json()

    response = client.get(f"/api/users/{created['id']}")

    assert response.status_code == 200
    assert response.json()["display_name"] == "Lookup User"


def test_get_user_returns_404_for_missing_id(
    users_client: tuple[TestClient, FakeUserService],
) -> None:
    client, _service = users_client

    response = client.get(f"/api/users/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_update_user(users_client: tuple[TestClient, FakeUserService]) -> None:
    client, _service = users_client
    created = client.post(
        "/api/users",
        json={
            "display_name": "Old User",
            "username": "old",
        },
    ).json()

    response = client.patch(
        f"/api/users/{created['id']}",
        json={
            "max_user_id": "max-123",
            "display_name": "New User",
            "username": "new",
            "phone": "+70000000000",
            "email": "new@example.com",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["max_user_id"] == "max-123"
    assert payload["display_name"] == "New User"
    assert payload["username"] == "new"
    assert payload["phone"] == "+70000000000"
    assert payload["email"] == "new@example.com"


def test_update_user_can_clear_nullable_fields(
    users_client: tuple[TestClient, FakeUserService],
) -> None:
    client, _service = users_client
    created = client.post(
        "/api/users",
        json={
            "display_name": "Nullable User",
            "max_user_id": "max-456",
            "username": "nullable",
            "phone": "+71111111111",
            "email": "nullable@example.com",
        },
    ).json()

    response = client.patch(
        f"/api/users/{created['id']}",
        json={
            "max_user_id": None,
            "username": None,
            "phone": None,
            "email": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["display_name"] == "Nullable User"
    assert payload["max_user_id"] is None
    assert payload["username"] is None
    assert payload["phone"] is None
    assert payload["email"] is None


def test_update_user_rejects_null_display_name(
    users_client: tuple[TestClient, FakeUserService],
) -> None:
    client, _service = users_client
    created = client.post("/api/users", json={"display_name": "Stable User"}).json()

    response = client.patch(
        f"/api/users/{created['id']}",
        json={"display_name": None},
    )

    assert response.status_code == 422
