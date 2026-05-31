from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.api.integrations_bitrix24 import get_bitrix_user_mapping_service
from app.main import create_app
from app.modules.integrations.bitrix24.repository import BitrixUserMappingRepository
from app.modules.integrations.bitrix24.schemas import BitrixUserMappingCreate, BitrixUserMappingUpdate


class BitrixUserMappingRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    bitrix_user_id: str
    match_source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FakeBitrixUserMappingService:
    def __init__(self) -> None:
        self.mappings: dict[UUID, BitrixUserMappingRecord] = {}

    async def create(self, payload: BitrixUserMappingCreate) -> BitrixUserMappingRecord:
        if payload.is_active and self._active_mapping_exists(
            organization_id=payload.organization_id,
            user_id=payload.user_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active Bitrix24 user mapping already exists",
            )
        now = datetime.now(timezone.utc)
        mapping = BitrixUserMappingRecord(
            id=uuid4(),
            organization_id=payload.organization_id,
            user_id=payload.user_id,
            bitrix_user_id=payload.bitrix_user_id,
            match_source=payload.match_source.value,
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
        self.mappings[mapping.id] = mapping
        return mapping

    async def list(
        self,
        *,
        organization_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        bitrix_user_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> list[BitrixUserMappingRecord]:
        mappings = list(self.mappings.values())
        if organization_id is not None:
            mappings = [mapping for mapping in mappings if mapping.organization_id == organization_id]
        if user_id is not None:
            mappings = [mapping for mapping in mappings if mapping.user_id == user_id]
        if bitrix_user_id is not None:
            mappings = [mapping for mapping in mappings if mapping.bitrix_user_id == bitrix_user_id]
        if is_active is not None:
            mappings = [mapping for mapping in mappings if mapping.is_active is is_active]
        return mappings

    async def get(self, mapping_id: UUID) -> BitrixUserMappingRecord:
        mapping = self.mappings.get(mapping_id)
        if mapping is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bitrix24 user mapping not found",
            )
        return mapping

    async def update(self, mapping_id: UUID, payload: BitrixUserMappingUpdate) -> BitrixUserMappingRecord:
        mapping = await self.get(mapping_id)
        values = payload.model_dump(exclude_unset=True)
        if "match_source" in values:
            values["match_source"] = values["match_source"].value

        target_organization_id = values.get("organization_id", mapping.organization_id)
        target_user_id = values.get("user_id", mapping.user_id)
        target_is_active = values.get("is_active", mapping.is_active)
        if target_is_active and self._active_mapping_exists(
            organization_id=target_organization_id,
            user_id=target_user_id,
            exclude_mapping_id=mapping_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active Bitrix24 user mapping already exists",
            )

        values["updated_at"] = datetime.now(timezone.utc)
        updated = mapping.model_copy(update=values)
        self.mappings[mapping_id] = updated
        return updated

    async def delete(self, mapping_id: UUID) -> BitrixUserMappingRecord:
        mapping = await self.get(mapping_id)
        updated = mapping.model_copy(
            update={
                "is_active": False,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self.mappings[mapping_id] = updated
        return updated

    def _active_mapping_exists(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        exclude_mapping_id: Optional[UUID] = None,
    ) -> bool:
        return any(
            mapping.organization_id == organization_id
            and mapping.user_id == user_id
            and mapping.is_active
            and mapping.id != exclude_mapping_id
            for mapping in self.mappings.values()
        )


@pytest.fixture()
def bitrix_user_mappings_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeBitrixUserMappingService]:
    monkeypatch.setenv("APP_ENV", "test")
    app = create_app()
    service = FakeBitrixUserMappingService()
    app.dependency_overrides[get_bitrix_user_mapping_service] = lambda: service
    with TestClient(app) as client:
        yield client, service


def mapping_payload(
    *,
    organization_id: UUID | None = None,
    user_id: UUID | None = None,
    bitrix_user_id: str = "bitrix-user-1",
    match_source: str = "manual",
    is_active: bool = True,
) -> dict[str, object]:
    return {
        "organization_id": str(organization_id or uuid4()),
        "user_id": str(user_id or uuid4()),
        "bitrix_user_id": bitrix_user_id,
        "match_source": match_source,
        "is_active": is_active,
    }


def admin_headers(organization_id: UUID | None = None) -> dict[str, str]:
    headers = {
        "X-User-Id": str(uuid4()),
        "X-Roles": "chat_admin",
    }
    if organization_id is not None:
        headers["X-Organization-Id"] = str(organization_id)
    return headers


def test_bitrix_user_mapping_repository_exposes_service_methods() -> None:
    for method_name in ("list", "get", "get_active_for_user", "update"):
        assert callable(getattr(BitrixUserMappingRepository, method_name))


def test_create_bitrix_user_mapping(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client
    organization_id = uuid4()
    user_id = uuid4()

    response = client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(organization_id=organization_id, user_id=user_id),
        headers=admin_headers(organization_id),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["organization_id"] == str(organization_id)
    assert payload["user_id"] == str(user_id)
    assert payload["bitrix_user_id"] == "bitrix-user-1"
    assert payload["match_source"] == "manual"
    assert payload["is_active"] is True


def test_create_bitrix_user_mapping_rejects_duplicate_active_mapping(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client
    organization_id = uuid4()
    user_id = uuid4()
    client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(organization_id=organization_id, user_id=user_id),
        headers=admin_headers(organization_id),
    )

    response = client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(
            organization_id=organization_id,
            user_id=user_id,
            bitrix_user_id="bitrix-user-2",
        ),
        headers=admin_headers(organization_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Active Bitrix24 user mapping already exists"


def test_create_inactive_mapping_for_same_user_is_allowed(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client
    organization_id = uuid4()
    user_id = uuid4()
    client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(organization_id=organization_id, user_id=user_id),
        headers=admin_headers(organization_id),
    )

    response = client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(
            organization_id=organization_id,
            user_id=user_id,
            bitrix_user_id="bitrix-user-inactive",
            is_active=False,
        ),
        headers=admin_headers(organization_id),
    )

    assert response.status_code == 201
    assert response.json()["is_active"] is False


def test_list_bitrix_user_mappings_with_filters(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client
    organization_id = uuid4()
    user_id = uuid4()
    client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(organization_id=organization_id, user_id=user_id, bitrix_user_id="target"),
        headers=admin_headers(organization_id),
    )
    other_organization_id = uuid4()
    client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(
            organization_id=other_organization_id,
            bitrix_user_id="other",
            is_active=False,
        ),
        headers=admin_headers(other_organization_id),
    )

    response = client.get(
        "/api/integrations/bitrix24/user-mappings",
        params={
            "organization_id": str(organization_id),
            "user_id": str(user_id),
            "bitrix_user_id": "target",
            "is_active": "true",
        },
        headers=admin_headers(organization_id),
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["bitrix_user_id"] == "target"


def test_get_bitrix_user_mapping(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client
    organization_id = uuid4()
    created = client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(organization_id=organization_id),
        headers=admin_headers(organization_id),
    ).json()

    response = client.get(
        f"/api/integrations/bitrix24/user-mappings/{created['id']}",
        headers=admin_headers(UUID(created["organization_id"])),
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_bitrix_user_mapping_returns_404_for_missing_id(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client

    response = client.get(
        f"/api/integrations/bitrix24/user-mappings/{uuid4()}",
        headers=admin_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Bitrix24 user mapping not found"


def test_update_bitrix_user_mapping(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client
    organization_id = uuid4()
    created = client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(organization_id=organization_id),
        headers=admin_headers(organization_id),
    ).json()

    response = client.patch(
        f"/api/integrations/bitrix24/user-mappings/{created['id']}",
        json={
            "bitrix_user_id": "bitrix-user-updated",
            "match_source": "email",
            "is_active": False,
        },
        headers=admin_headers(UUID(created["organization_id"])),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["bitrix_user_id"] == "bitrix-user-updated"
    assert payload["match_source"] == "email"
    assert payload["is_active"] is False


def test_update_bitrix_user_mapping_rejects_duplicate_active_target(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client
    organization_id = uuid4()
    user_id = uuid4()
    client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(organization_id=organization_id, user_id=user_id),
        headers=admin_headers(organization_id),
    )
    inactive = client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(
            organization_id=organization_id,
            user_id=user_id,
            bitrix_user_id="inactive",
            is_active=False,
        ),
        headers=admin_headers(organization_id),
    ).json()

    response = client.patch(
        f"/api/integrations/bitrix24/user-mappings/{inactive['id']}",
        json={"is_active": True},
        headers=admin_headers(organization_id),
    )

    assert response.status_code == 409


def test_delete_bitrix_user_mapping_soft_deletes(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client
    organization_id = uuid4()
    created = client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=mapping_payload(organization_id=organization_id),
        headers=admin_headers(organization_id),
    ).json()

    response = client.delete(
        f"/api/integrations/bitrix24/user-mappings/{created['id']}",
        headers=admin_headers(UUID(created["organization_id"])),
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_create_bitrix_user_mapping_rejects_unknown_match_source(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client
    organization_id = uuid4()
    payload = mapping_payload(organization_id=organization_id)
    payload["match_source"] = "unknown"

    response = client.post(
        "/api/integrations/bitrix24/user-mappings",
        json=payload,
        headers=admin_headers(organization_id),
    )

    assert response.status_code == 422


def test_bitrix_user_mapping_openapi_tags(
    bitrix_user_mappings_client: tuple[TestClient, FakeBitrixUserMappingService],
) -> None:
    client, _service = bitrix_user_mappings_client

    response = client.get("/openapi.json")

    assert response.status_code == 200
    path = response.json()["paths"]["/api/integrations/bitrix24/user-mappings"]["post"]
    assert path["tags"] == ["integrations", "bitrix24"]
