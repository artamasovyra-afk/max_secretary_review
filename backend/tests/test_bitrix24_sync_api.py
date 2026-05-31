from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.integrations_bitrix24 import get_bitrix24_sync_service
from app.main import create_app
from app.modules.integrations.bitrix24.schemas import (
    BitrixRetryFailedSyncRead,
    BitrixTaskSyncStatusRead,
    BitrixTaskSyncRead,
)
from app.modules.integrations.enums import BitrixSyncStatus


class FakeBitrix24SyncService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, UUID | None]] = []
        self.policy_tasks: dict[UUID, SimpleNamespace] = {}

    async def get_task_for_policy(self, task_id: UUID) -> SimpleNamespace:
        task = self.policy_tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return task

    async def sync_task_create(self, task_id: UUID) -> BitrixTaskSyncRead:
        self.calls.append(("create", task_id, None))
        return self._result(task_id=task_id, action="created")

    async def get_task_sync_status(self, task_id: UUID) -> BitrixTaskSyncStatusRead:
        self.calls.append(("status", task_id, None))
        return BitrixTaskSyncStatusRead(
            task_id=task_id,
            sync_status=BitrixSyncStatus.SYNCED,
            detail="Bitrix24 task is synchronized.",
            link=None,
        )

    async def retry_failed_sync(self, limit: int = 50) -> BitrixRetryFailedSyncRead:
        task_id = uuid4()
        self.calls.append(("retry", task_id, None))
        return BitrixRetryFailedSyncRead(
            limit=limit,
            results=[self._result(task_id=task_id, action="created")],
        )

    def _result(self, *, task_id: UUID, action: str) -> BitrixTaskSyncRead:
        now = datetime.now(timezone.utc)
        organization_id = uuid4()
        return BitrixTaskSyncRead(
            task_id=task_id,
            organization_id=organization_id,
            sync_status=BitrixSyncStatus.SYNCED,
            action=action,
            detail="ok",
            bitrix_task_id="bitrix-task-1",
            link={
                "id": uuid4(),
                "task_id": task_id,
                "organization_id": organization_id,
                "bitrix_portal_url": None,
                "bitrix_task_id": "bitrix-task-1",
                "sync_status": BitrixSyncStatus.SYNCED,
                "last_sync_at": now,
                "last_error": None,
                "created_at": now,
                "updated_at": now,
            },
        )


@pytest.fixture()
def bitrix_sync_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeBitrix24SyncService]:
    monkeypatch.setenv("APP_ENV", "test")
    app = create_app()
    service = FakeBitrix24SyncService()
    app.dependency_overrides[get_bitrix24_sync_service] = lambda: service
    with TestClient(app) as client:
        yield client, service


def auth_headers(
    *,
    user_id: UUID,
    organization_id: UUID | None = None,
    chat_id: UUID | None = None,
    roles: str = "member",
) -> dict[str, str]:
    headers = {
        "X-User-Id": str(user_id),
        "X-Roles": roles,
    }
    if organization_id is not None:
        headers["X-Organization-Id"] = str(organization_id)
    if chat_id is not None:
        headers["X-Chat-Id"] = str(chat_id)
    return headers


def register_policy_task(
    service: FakeBitrix24SyncService,
    task_id: UUID,
    *,
    organization_id: UUID | None = None,
    chat_id: UUID | None = None,
    created_by_user_id: UUID | None = None,
    assignee_ids: list[UUID] | None = None,
    observer_ids: list[UUID] | None = None,
) -> SimpleNamespace:
    task = SimpleNamespace(
        id=task_id,
        organization_id=organization_id or uuid4(),
        chat_id=chat_id or uuid4(),
        created_by_user_id=created_by_user_id or uuid4(),
        assignees=[SimpleNamespace(user_id=user_id) for user_id in (assignee_ids or [])],
        observers=[SimpleNamespace(user_id=user_id) for user_id in (observer_ids or [])],
    )
    service.policy_tasks[task_id] = task
    return task


def test_sync_task_create_endpoint(
    bitrix_sync_client: tuple[TestClient, FakeBitrix24SyncService],
) -> None:
    client, service = bitrix_sync_client
    task_id = uuid4()
    creator_id = uuid4()
    task = register_policy_task(service, task_id, created_by_user_id=creator_id)

    response = client.post(
        f"/api/integrations/bitrix24/tasks/{task_id}/sync",
        headers=auth_headers(
            user_id=creator_id,
            organization_id=task.organization_id,
            chat_id=task.chat_id,
        ),
    )

    assert response.status_code == 200
    assert response.json()["action"] == "created"
    assert service.calls == [("create", task_id, None)]


def test_get_sync_status_endpoint(
    bitrix_sync_client: tuple[TestClient, FakeBitrix24SyncService],
) -> None:
    client, service = bitrix_sync_client
    task_id = uuid4()
    observer_id = uuid4()
    task = register_policy_task(service, task_id, observer_ids=[observer_id])

    response = client.get(
        f"/api/integrations/bitrix24/tasks/{task_id}/status",
        headers=auth_headers(
            user_id=observer_id,
            organization_id=task.organization_id,
            chat_id=task.chat_id,
        ),
    )

    assert response.status_code == 200
    assert response.json()["sync_status"] == "synced"
    assert service.calls == [("status", task_id, None)]


def test_internal_update_endpoint_is_not_public(
    bitrix_sync_client: tuple[TestClient, FakeBitrix24SyncService],
) -> None:
    client, _service = bitrix_sync_client
    task_id = uuid4()

    response = client.post(f"/api/integrations/bitrix24/tasks/{task_id}/sync/update")

    assert response.status_code == 404


def test_retry_failed_sync_endpoint(
    bitrix_sync_client: tuple[TestClient, FakeBitrix24SyncService],
) -> None:
    client, service = bitrix_sync_client

    response = client.post(
        "/api/integrations/bitrix24/retry-failed",
        params={"limit": "3"},
        headers=auth_headers(user_id=uuid4(), roles="chat_admin"),
    )

    assert response.status_code == 200
    assert response.json()["limit"] == 3
    assert response.json()["results"][0]["action"] == "created"
    assert service.calls[0][0] == "retry"


def test_sync_endpoint_propagates_service_404(
    bitrix_sync_client: tuple[TestClient, FakeBitrix24SyncService],
) -> None:
    client, service = bitrix_sync_client
    task_id = uuid4()
    creator_id = uuid4()
    task = register_policy_task(service, task_id, created_by_user_id=creator_id)

    async def missing_task(_task_id: UUID) -> BitrixTaskSyncRead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    service.sync_task_create = missing_task  # type: ignore[method-assign]

    response = client.post(
        f"/api/integrations/bitrix24/tasks/{task_id}/sync",
        headers=auth_headers(
            user_id=creator_id,
            organization_id=task.organization_id,
            chat_id=task.chat_id,
        ),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_sync_endpoint_rejects_stranger(
    bitrix_sync_client: tuple[TestClient, FakeBitrix24SyncService],
) -> None:
    client, service = bitrix_sync_client
    task_id = uuid4()
    task = register_policy_task(service, task_id, created_by_user_id=uuid4())

    response = client.post(
        f"/api/integrations/bitrix24/tasks/{task_id}/sync",
        headers=auth_headers(
            user_id=uuid4(),
            organization_id=task.organization_id,
            chat_id=task.chat_id,
        ),
    )

    assert response.status_code == 403
    assert service.calls == []


def test_status_endpoint_rejects_user_without_view_permission(
    bitrix_sync_client: tuple[TestClient, FakeBitrix24SyncService],
) -> None:
    client, service = bitrix_sync_client
    task_id = uuid4()
    task = register_policy_task(service, task_id)

    response = client.get(
        f"/api/integrations/bitrix24/tasks/{task_id}/status",
        headers=auth_headers(
            user_id=uuid4(),
            organization_id=task.organization_id,
            chat_id=task.chat_id,
        ),
    )

    assert response.status_code == 403
    assert service.calls == []


def test_retry_failed_sync_rejects_manager(
    bitrix_sync_client: tuple[TestClient, FakeBitrix24SyncService],
) -> None:
    client, service = bitrix_sync_client

    response = client.post(
        "/api/integrations/bitrix24/retry-failed",
        headers=auth_headers(user_id=uuid4(), roles="manager"),
    )

    assert response.status_code == 403
    assert service.calls == []


def test_bitrix_sync_openapi_tags(
    bitrix_sync_client: tuple[TestClient, FakeBitrix24SyncService],
) -> None:
    client, _service = bitrix_sync_client

    response = client.get("/openapi.json")

    assert response.status_code == 200
    path = response.json()["paths"]["/api/integrations/bitrix24/tasks/{task_id}/sync"]["post"]
    assert path["tags"] == ["integrations", "bitrix24"]
