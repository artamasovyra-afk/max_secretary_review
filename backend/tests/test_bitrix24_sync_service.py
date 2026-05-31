from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.modules.integrations.bitrix24.service import Bitrix24SyncService
from app.modules.integrations.enums import BitrixSyncStatus, BitrixUserMatchSource
from app.modules.tasks.enums import TaskStatus


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, _instance: object) -> None:
        return None


class FakeBitrix24Client:
    def __init__(self) -> None:
        self.created_fields: list[dict[str, object]] = []
        self.updated_tasks: list[tuple[str | int, dict[str, object]]] = []
        self.called_methods: list[tuple[str, dict[str, object]]] = []
        self.closed = False
        self.create_response: dict[str, object] = {"result": {"task": {"id": "bitrix-task-1"}}}

    def create_task(self, fields: dict[str, object]) -> dict[str, object]:
        self.created_fields.append(fields)
        return self.create_response

    def update_task(self, task_id: str | int, fields: dict[str, object]) -> dict[str, object]:
        self.updated_tasks.append((task_id, fields))
        return {"result": True}

    def call_method(
        self,
        method_name: str,
        payload: dict[str, object] | None = None,
        *,
        retry_safe: bool = False,
    ) -> dict[str, object]:
        self.called_methods.append((method_name, payload or {}))
        return {"result": True}

    def close(self) -> None:
        self.closed = True


class FakeBitrix24SyncRepository:
    def __init__(self, task: SimpleNamespace) -> None:
        self.task = task
        self.links: dict[UUID, SimpleNamespace] = {}
        self.mappings: list[SimpleNamespace] = []
        self.responses: dict[UUID, SimpleNamespace] = {}

    async def get_task_for_sync(self, task_id: UUID) -> SimpleNamespace | None:
        return self.task if task_id == self.task.id else None

    async def get_response(self, *, task_id: UUID, response_id: UUID) -> SimpleNamespace | None:
        response = self.responses.get(response_id)
        if response is None or response.task_id != task_id:
            return None
        return response

    async def list_active_user_mappings(self, organization_id: UUID) -> list[SimpleNamespace]:
        return [
            mapping
            for mapping in self.mappings
            if mapping.organization_id == organization_id and mapping.is_active
        ]

    async def get_active_task_link(self, task_id: UUID) -> SimpleNamespace | None:
        for link in self.links.values():
            if link.task_id == task_id and link.sync_status != BitrixSyncStatus.DISABLED.value:
                return link
        return None

    async def get_latest_task_link(self, task_id: UUID) -> SimpleNamespace | None:
        for link in self.links.values():
            if link.task_id == task_id:
                return link
        return None

    async def create_task_link(
        self,
        *,
        task_id: UUID,
        organization_id: UUID,
        bitrix_task_id: str | None = None,
        sync_status: str,
        last_sync_at: datetime | None = None,
        last_error: str | None = None,
    ) -> SimpleNamespace:
        now = datetime.now(timezone.utc)
        link = SimpleNamespace(
            id=uuid4(),
            task_id=task_id,
            organization_id=organization_id,
            bitrix_portal_url=None,
            bitrix_task_id=bitrix_task_id,
            sync_status=sync_status,
            last_sync_at=last_sync_at,
            last_error=last_error,
            created_at=now,
            updated_at=now,
        )
        self.links[link.id] = link
        return link

    async def update_task_link(
        self,
        link: SimpleNamespace,
        *,
        values: dict[str, object],
    ) -> SimpleNamespace:
        for key, value in values.items():
            setattr(link, key, value)
        link.updated_at = datetime.now(timezone.utc)
        return link

    async def list_failed_task_links(self, *, limit: int) -> list[SimpleNamespace]:
        return [
            link
            for link in self.links.values()
            if link.sync_status == BitrixSyncStatus.ERROR.value
        ][:limit]


def make_participant(user_id: UUID, display_name: str) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, user=SimpleNamespace(display_name=display_name))


def make_mapping(*, organization_id: UUID, user_id: UUID, bitrix_user_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        user_id=user_id,
        bitrix_user_id=bitrix_user_id,
        match_source=BitrixUserMatchSource.MANUAL.value,
        is_active=True,
    )


def make_task() -> SimpleNamespace:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    observer_id = uuid4()
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        chat_id=uuid4(),
        source_message_id="max-message-1",
        title="Подготовить отчет",
        description="Описание задачи",
        created_by_user_id=creator_id,
        deadline_at=None,
        status=TaskStatus.NEW.value,
        assignees=[make_participant(assignee_id, "Исполнитель")],
        observers=[make_participant(observer_id, "Наблюдатель")],
        creator_id=creator_id,
        assignee_id=assignee_id,
        observer_id=observer_id,
    )


def make_service(
    *,
    task: SimpleNamespace | None = None,
    settings: Settings | None = None,
    client: FakeBitrix24Client | None = None,
) -> tuple[Bitrix24SyncService, FakeBitrix24SyncRepository, FakeSession, FakeBitrix24Client]:
    task = task or make_task()
    repository = FakeBitrix24SyncRepository(task)
    add_default_mappings(repository)
    session = FakeSession()
    client = client or FakeBitrix24Client()
    service = Bitrix24SyncService(
        repository=repository,
        session=session,
        settings=settings or Settings(bitrix24_enabled=True),
        client_factory=lambda: client,
    )
    return service, repository, session, client


def add_default_mappings(repository: FakeBitrix24SyncRepository) -> None:
    task = repository.task
    repository.mappings = [
        make_mapping(
            organization_id=task.organization_id,
            user_id=task.assignee_id,
            bitrix_user_id="101",
        ),
        make_mapping(
            organization_id=task.organization_id,
            user_id=task.creator_id,
            bitrix_user_id="301",
        ),
        make_mapping(
            organization_id=task.organization_id,
            user_id=task.observer_id,
            bitrix_user_id="201",
        ),
    ]


@pytest.mark.anyio
async def test_sync_task_create_creates_bitrix_task_and_link() -> None:
    service, repository, session, client = make_service()

    result = await service.sync_task_create(repository.task.id)

    assert result.sync_status == BitrixSyncStatus.SYNCED
    assert result.action == "created"
    assert result.bitrix_task_id == "bitrix-task-1"
    assert len(client.created_fields) == 1
    assert client.created_fields[0]["RESPONSIBLE_ID"] == "101"
    assert session.commits == 1


@pytest.mark.anyio
async def test_sync_task_create_does_not_duplicate_existing_link() -> None:
    service, repository, _session, client = make_service()
    await repository.create_task_link(
        task_id=repository.task.id,
        organization_id=repository.task.organization_id,
        bitrix_task_id="already-created",
        sync_status=BitrixSyncStatus.SYNCED.value,
    )

    result = await service.sync_task_create(repository.task.id)

    assert result.action == "already_synced"
    assert result.bitrix_task_id == "already-created"
    assert client.created_fields == []


@pytest.mark.anyio
async def test_sync_task_create_returns_disabled_without_http_request() -> None:
    service, repository, session, client = make_service(settings=Settings(bitrix24_enabled=False))

    result = await service.sync_task_create(repository.task.id)

    assert result.sync_status == BitrixSyncStatus.DISABLED
    assert result.action == "disabled"
    assert client.created_fields == []
    assert session.commits == 1


@pytest.mark.anyio
async def test_get_task_sync_status_returns_pending_without_link() -> None:
    service, repository, _session, _client = make_service()

    result = await service.get_task_sync_status(repository.task.id)

    assert result.task_id == repository.task.id
    assert result.sync_status == BitrixSyncStatus.PENDING
    assert result.link is None


@pytest.mark.anyio
async def test_get_task_sync_status_returns_existing_link_status() -> None:
    service, repository, _session, _client = make_service()
    link = await repository.create_task_link(
        task_id=repository.task.id,
        organization_id=repository.task.organization_id,
        bitrix_task_id="bitrix-task-1",
        sync_status=BitrixSyncStatus.SYNCED.value,
    )

    result = await service.get_task_sync_status(repository.task.id)

    assert result.sync_status == BitrixSyncStatus.SYNCED
    assert result.link is not None
    assert result.link.id == link.id


@pytest.mark.anyio
async def test_sync_task_create_saves_error_when_mapping_fails() -> None:
    service, repository, _session, client = make_service(
        settings=Settings(bitrix24_enabled=True, bitrix24_default_responsible_id=None)
    )
    repository.mappings = []

    result = await service.sync_task_create(repository.task.id)

    assert result.sync_status == BitrixSyncStatus.ERROR
    assert result.action == "error"
    assert result.last_error is not None
    assert "RESPONSIBLE_ID cannot be resolved" in result.last_error
    assert client.created_fields == []


@pytest.mark.anyio
async def test_sync_task_update_updates_existing_link() -> None:
    service, repository, _session, client = make_service()
    await repository.create_task_link(
        task_id=repository.task.id,
        organization_id=repository.task.organization_id,
        bitrix_task_id="bitrix-task-1",
        sync_status=BitrixSyncStatus.SYNCED.value,
    )

    result = await service.sync_task_update(repository.task.id)

    assert result.action == "updated"
    assert client.updated_tasks[0][0] == "bitrix-task-1"
    assert "TITLE" in client.updated_tasks[0][1]


@pytest.mark.anyio
async def test_sync_task_status_updates_existing_link_status() -> None:
    service, repository, _session, client = make_service()
    repository.task.status = TaskStatus.DONE.value
    await repository.create_task_link(
        task_id=repository.task.id,
        organization_id=repository.task.organization_id,
        bitrix_task_id="bitrix-task-1",
        sync_status=BitrixSyncStatus.SYNCED.value,
    )

    result = await service.sync_task_status(repository.task.id)

    assert result.action == "status_synced"
    assert client.updated_tasks == [("bitrix-task-1", {"STATUS": "5"})]


@pytest.mark.anyio
async def test_sync_task_response_adds_bitrix_comment() -> None:
    service, repository, _session, client = make_service()
    response_id = uuid4()
    repository.responses[response_id] = SimpleNamespace(
        id=response_id,
        task_id=repository.task.id,
        user_id=repository.task.assignee_id,
        text="Готово",
        source_message_id="max-response-1",
    )
    await repository.create_task_link(
        task_id=repository.task.id,
        organization_id=repository.task.organization_id,
        bitrix_task_id="bitrix-task-1",
        sync_status=BitrixSyncStatus.SYNCED.value,
    )

    result = await service.sync_task_response(repository.task.id, response_id)

    assert result.action == "response_synced"
    assert client.called_methods[0][0] == "task.commentitem.add"
    assert client.called_methods[0][1]["taskId"] == "bitrix-task-1"


@pytest.mark.anyio
async def test_retry_failed_sync_retries_failed_create() -> None:
    service, repository, _session, client = make_service()
    await repository.create_task_link(
        task_id=repository.task.id,
        organization_id=repository.task.organization_id,
        sync_status=BitrixSyncStatus.ERROR.value,
        last_error="temporary",
    )

    result = await service.retry_failed_sync(limit=50)

    assert len(result.results) == 1
    assert result.results[0].sync_status == BitrixSyncStatus.SYNCED
    assert client.created_fields
