from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.api.organizations import get_organization_service
from app.core.config import get_settings
from app.main import create_app
from app.modules.organizations.schemas import OrganizationCreate, OrganizationUpdate


class OrganizationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class FakeOrganizationService:
    def __init__(self) -> None:
        self.organizations: dict[UUID, OrganizationRecord] = {}

    async def create(self, payload: OrganizationCreate) -> OrganizationRecord:
        now = datetime.now(timezone.utc)
        organization = OrganizationRecord(
            id=uuid4(),
            name=payload.name,
            status=payload.status,
            created_at=now,
            updated_at=now,
        )
        self.organizations[organization.id] = organization
        return organization

    async def list(self) -> list[OrganizationRecord]:
        return list(self.organizations.values())

    async def get(self, organization_id: UUID) -> OrganizationRecord:
        organization = self.organizations.get(organization_id)
        if organization is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
        return organization

    async def update(
        self,
        organization_id: UUID,
        payload: OrganizationUpdate,
    ) -> OrganizationRecord:
        organization = await self.get(organization_id)
        updated = organization.model_copy(
            update={
                "name": payload.name if payload.name is not None else organization.name,
                "status": payload.status
                if payload.status is not None
                else organization.status,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self.organizations[organization_id] = updated
        return updated


def _auth_headers(
    *,
    user_id: UUID | None = None,
    organization_id: UUID | None = None,
    roles: str = "super_admin",
) -> dict[str, str]:
    headers = {
        "X-User-Id": str(user_id or uuid4()),
        "X-Roles": roles,
    }
    if organization_id is not None:
        headers["X-Organization-Id"] = str(organization_id)
    return headers


@pytest.fixture()
def organizations_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, FakeOrganizationService]:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    app = create_app()
    service = FakeOrganizationService()
    app.dependency_overrides[get_organization_service] = lambda: service
    with TestClient(app, headers=_auth_headers()) as client:
        yield client, service


def test_create_organization(
    organizations_client: tuple[TestClient, FakeOrganizationService],
) -> None:
    client, _service = organizations_client

    response = client.post(
        "/api/organizations",
        json={"name": "Max Secretary", "status": "active"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Max Secretary"
    assert payload["status"] == "active"
    assert payload["id"]
    assert payload["created_at"]
    assert payload["updated_at"]


def test_create_organization_requires_auth(
    organizations_client: tuple[TestClient, FakeOrganizationService],
) -> None:
    client, _service = organizations_client

    with TestClient(client.app) as unauthenticated_client:
        response = unauthenticated_client.post(
            "/api/organizations",
            json={"name": "Max Secretary", "status": "active"},
        )

    assert response.status_code == 401


def test_create_organization_requires_super_admin(
    organizations_client: tuple[TestClient, FakeOrganizationService],
) -> None:
    client, _service = organizations_client

    response = client.post(
        "/api/organizations",
        json={"name": "Max Secretary", "status": "active"},
        headers=_auth_headers(roles="member"),
    )

    assert response.status_code == 403


def test_list_organizations(
    organizations_client: tuple[TestClient, FakeOrganizationService],
) -> None:
    client, _service = organizations_client
    client.post("/api/organizations", json={"name": "Org 1", "status": "active"})
    client.post("/api/organizations", json={"name": "Org 2", "status": "paused"})

    response = client.get("/api/organizations")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Org 1", "Org 2"]


def test_get_organization(
    organizations_client: tuple[TestClient, FakeOrganizationService],
) -> None:
    client, _service = organizations_client
    created = client.post(
        "/api/organizations",
        json={"name": "Lookup Org", "status": "active"},
    ).json()

    response = client.get(f"/api/organizations/{created['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Lookup Org"


def test_get_organization_returns_404_for_missing_id(
    organizations_client: tuple[TestClient, FakeOrganizationService],
) -> None:
    client, _service = organizations_client

    response = client.get(f"/api/organizations/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"


def test_update_organization(
    organizations_client: tuple[TestClient, FakeOrganizationService],
) -> None:
    client, _service = organizations_client
    created = client.post(
        "/api/organizations",
        json={"name": "Old Name", "status": "active"},
    ).json()

    response = client.patch(
        f"/api/organizations/{created['id']}",
        json={"name": "New Name", "status": "archived"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "New Name"
    assert payload["status"] == "archived"
