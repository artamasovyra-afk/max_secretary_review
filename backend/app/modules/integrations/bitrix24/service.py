from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Protocol
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.integrations.bitrix24.client import Bitrix24Client
from app.modules.integrations.bitrix24.exceptions import Bitrix24ApiError, Bitrix24MappingError
from app.modules.integrations.bitrix24.mapper import Bitrix24TaskMapper
from app.modules.integrations.bitrix24.repository import (
    Bitrix24SyncRepository,
    BitrixUserMappingRepository,
)
from app.modules.integrations.bitrix24.schemas import (
    BitrixRetryFailedSyncRead,
    BitrixTaskSyncStatusRead,
    BitrixTaskSyncRead,
    BitrixUserMappingCreate,
    BitrixUserMappingUpdate,
)
from app.modules.integrations.enums import BitrixSyncStatus
from app.modules.integrations.models import BitrixTaskLink, BitrixUserMapping
from app.modules.tasks.enums import TaskStatus
from app.modules.tasks.models import Task, TaskResponse


class Bitrix24ClientProtocol(Protocol):
    def create_task(self, fields: Mapping[str, Any]) -> dict[str, Any]: ...

    def update_task(self, task_id: str | int, fields: Mapping[str, Any]) -> dict[str, Any]: ...

    def call_method(
        self,
        method_name: str,
        payload: Mapping[str, Any] | None = None,
        *,
        retry_safe: bool = False,
    ) -> dict[str, Any]: ...

    def close(self) -> None: ...


class BitrixUserMappingService:
    def __init__(self, repository: BitrixUserMappingRepository, session: AsyncSession) -> None:
        self.repository = repository
        self.session = session

    async def create(self, payload: BitrixUserMappingCreate) -> BitrixUserMapping:
        await self._ensure_organization_exists(payload.organization_id)
        await self._ensure_user_exists(payload.user_id)
        if payload.is_active:
            await self._ensure_no_active_mapping(
                organization_id=payload.organization_id,
                user_id=payload.user_id,
            )
        mapping = await self.repository.create(
            organization_id=payload.organization_id,
            user_id=payload.user_id,
            bitrix_user_id=payload.bitrix_user_id,
            match_source=payload.match_source.value,
            is_active=payload.is_active,
        )
        await self.session.commit()
        await self.session.refresh(mapping)
        return mapping

    async def list(
        self,
        *,
        organization_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        bitrix_user_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> list[BitrixUserMapping]:
        return await self.repository.list(
            organization_id=organization_id,
            user_id=user_id,
            bitrix_user_id=bitrix_user_id,
            is_active=is_active,
        )

    async def get(self, mapping_id: UUID) -> BitrixUserMapping:
        mapping = await self.repository.get(mapping_id)
        if mapping is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bitrix24 user mapping not found",
            )
        return mapping

    async def update(self, mapping_id: UUID, payload: BitrixUserMappingUpdate) -> BitrixUserMapping:
        mapping = await self.get(mapping_id)
        values = payload.model_dump(exclude_unset=True)
        if "match_source" in values:
            values["match_source"] = values["match_source"].value
        if "organization_id" in values:
            await self._ensure_organization_exists(values["organization_id"])
        if "user_id" in values:
            await self._ensure_user_exists(values["user_id"])

        target_organization_id = values.get("organization_id", mapping.organization_id)
        target_user_id = values.get("user_id", mapping.user_id)
        target_is_active = values.get("is_active", mapping.is_active)
        if target_is_active:
            await self._ensure_no_active_mapping(
                organization_id=target_organization_id,
                user_id=target_user_id,
                exclude_mapping_id=mapping.id,
            )

        mapping = await self.repository.update(mapping, values=values)
        await self.session.commit()
        await self.session.refresh(mapping)
        return mapping

    async def delete(self, mapping_id: UUID) -> BitrixUserMapping:
        mapping = await self.get(mapping_id)
        mapping = await self.repository.update(mapping, values={"is_active": False})
        await self.session.commit()
        await self.session.refresh(mapping)
        return mapping

    async def _ensure_organization_exists(self, organization_id: UUID) -> None:
        if not await self.repository.organization_exists(organization_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

    async def _ensure_user_exists(self, user_id: UUID) -> None:
        if not await self.repository.user_exists(user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    async def _ensure_no_active_mapping(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        exclude_mapping_id: Optional[UUID] = None,
    ) -> None:
        existing_mapping = await self.repository.get_active_for_user(
            organization_id=organization_id,
            user_id=user_id,
            exclude_mapping_id=exclude_mapping_id,
        )
        if existing_mapping is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active Bitrix24 user mapping already exists",
            )


class Bitrix24SyncService:
    def __init__(
        self,
        *,
        repository: Bitrix24SyncRepository,
        session: AsyncSession,
        settings: Settings | None = None,
        mapper: Bitrix24TaskMapper | None = None,
        client_factory: Callable[[], Bitrix24ClientProtocol] | None = None,
    ) -> None:
        self.repository = repository
        self.session = session
        self.settings = settings or get_settings()
        self.mapper = mapper or Bitrix24TaskMapper(settings=self.settings)
        self.client_factory = client_factory or (lambda: Bitrix24Client(settings=self.settings))

    async def sync_task_create(self, task_id: UUID) -> BitrixTaskSyncRead:
        task = await self._get_task(task_id)
        if not self.settings.bitrix24_enabled:
            link = await self._mark_disabled(task)
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="disabled",
                detail="Bitrix24 integration is disabled.",
            )

        existing_link = await self.repository.get_active_task_link(task.id)
        if existing_link is not None and existing_link.bitrix_task_id:
            return self._build_result(
                task=task,
                link=existing_link,
                action="already_synced",
                detail="Bitrix24 task link already exists; duplicate task was not created.",
            )

        link = existing_link or await self.repository.get_latest_task_link(task.id)
        try:
            fields = await self._build_task_add_fields(task)
            client = self.client_factory()
            try:
                response = client.create_task(fields)
            finally:
                client.close()
            bitrix_task_id = self._extract_bitrix_task_id(response)
            link = await self._upsert_link(
                task=task,
                link=link,
                values={
                    "bitrix_task_id": bitrix_task_id,
                    "sync_status": BitrixSyncStatus.SYNCED.value,
                    "last_sync_at": self._now(),
                    "last_error": None,
                },
            )
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="created",
                detail="Task synchronized to Bitrix24.",
            )
        except (Bitrix24ApiError, Bitrix24MappingError, ValueError) as exc:
            link = await self._mark_error(task=task, link=link, error=exc)
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="error",
                detail="Bitrix24 task synchronization failed.",
            )

    async def get_task_sync_status(self, task_id: UUID) -> BitrixTaskSyncStatusRead:
        task = await self._get_task(task_id)
        link = await self.repository.get_latest_task_link(task.id)
        if link is None:
            return BitrixTaskSyncStatusRead(
                task_id=task.id,
                sync_status=BitrixSyncStatus.PENDING,
                detail="Bitrix24 task has not been synchronized yet.",
                link=None,
            )
        return BitrixTaskSyncStatusRead(
            task_id=task.id,
            sync_status=link.sync_status,
            detail=self._status_detail(link.sync_status),
            link=link,
        )

    async def sync_task_update(self, task_id: UUID) -> BitrixTaskSyncRead:
        task = await self._get_task(task_id)
        if not self.settings.bitrix24_enabled:
            link = await self._mark_disabled(task)
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="disabled",
                detail="Bitrix24 integration is disabled.",
            )

        link = await self.repository.get_active_task_link(task.id)
        if link is None or not link.bitrix_task_id:
            link = await self._mark_error(
                task=task,
                link=link,
                error=ValueError("Active Bitrix24 task link with bitrix_task_id was not found."),
            )
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="error",
                detail="Bitrix24 task update requires an existing task link.",
            )

        try:
            fields = await self._build_task_add_fields(task)
            client = self.client_factory()
            try:
                client.update_task(link.bitrix_task_id, fields)
            finally:
                client.close()
            link = await self.repository.update_task_link(
                link,
                values={
                    "sync_status": BitrixSyncStatus.SYNCED.value,
                    "last_sync_at": self._now(),
                    "last_error": None,
                },
            )
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="updated",
                detail="Linked Bitrix24 task was updated.",
            )
        except (Bitrix24ApiError, Bitrix24MappingError, ValueError) as exc:
            link = await self._mark_error(task=task, link=link, error=exc)
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="error",
                detail="Bitrix24 task update failed.",
            )

    async def sync_task_status(self, task_id: UUID) -> BitrixTaskSyncRead:
        task = await self._get_task(task_id)
        link = await self._get_required_enabled_link(task)
        if link.sync_status == BitrixSyncStatus.DISABLED.value:
            return self._build_result(
                task=task,
                link=link,
                action="disabled",
                detail="Bitrix24 integration is disabled.",
            )
        if link.bitrix_task_id is None:
            return self._build_result(
                task=task,
                link=link,
                action="error",
                detail="Bitrix24 task status sync requires bitrix_task_id.",
            )

        try:
            fields = {"STATUS": self._map_task_status(task.status)}
            client = self.client_factory()
            try:
                client.update_task(link.bitrix_task_id, fields)
            finally:
                client.close()
            link = await self.repository.update_task_link(
                link,
                values={
                    "sync_status": BitrixSyncStatus.SYNCED.value,
                    "last_sync_at": self._now(),
                    "last_error": None,
                },
            )
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="status_synced",
                detail="Linked Bitrix24 task status was updated.",
            )
        except (Bitrix24ApiError, ValueError) as exc:
            link = await self._mark_error(task=task, link=link, error=exc)
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="error",
                detail="Bitrix24 task status sync failed.",
            )

    async def sync_task_response(self, task_id: UUID, response_id: UUID) -> BitrixTaskSyncRead:
        task = await self._get_task(task_id)
        response = await self._get_response(task_id=task.id, response_id=response_id)
        link = await self._get_required_enabled_link(task)
        if link.sync_status == BitrixSyncStatus.DISABLED.value:
            return self._build_result(
                task=task,
                link=link,
                action="disabled",
                detail="Bitrix24 integration is disabled.",
            )
        if link.bitrix_task_id is None:
            return self._build_result(
                task=task,
                link=link,
                action="error",
                detail="Bitrix24 response sync requires bitrix_task_id.",
            )

        try:
            client = self.client_factory()
            try:
                client.call_method(
                    "task.commentitem.add",
                    {
                        "taskId": link.bitrix_task_id,
                        "fields": {
                            "POST_MESSAGE": self._format_response_comment(response),
                        },
                    },
                    retry_safe=False,
                )
            finally:
                client.close()
            link = await self.repository.update_task_link(
                link,
                values={
                    "sync_status": BitrixSyncStatus.SYNCED.value,
                    "last_sync_at": self._now(),
                    "last_error": None,
                },
            )
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="response_synced",
                detail="Task response was synchronized to Bitrix24 as a comment.",
            )
        except Bitrix24ApiError as exc:
            link = await self._mark_error(task=task, link=link, error=exc)
            await self.session.commit()
            await self._refresh_link(link)
            return self._build_result(
                task=task,
                link=link,
                action="error",
                detail="Bitrix24 task response sync failed.",
            )

    async def retry_failed_sync(self, limit: int = 50) -> BitrixRetryFailedSyncRead:
        links = await self.repository.list_failed_task_links(limit=limit)
        results: list[BitrixTaskSyncRead] = []
        for link in links:
            if link.bitrix_task_id:
                results.append(await self.sync_task_update(link.task_id))
            else:
                results.append(await self.sync_task_create(link.task_id))
        return BitrixRetryFailedSyncRead(limit=limit, results=results)

    async def get_task_for_policy(self, task_id: UUID) -> Task:
        return await self._get_task(task_id)

    async def _get_task(self, task_id: UUID) -> Task:
        task = await self.repository.get_task_for_sync(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )
        return task

    async def _get_response(self, *, task_id: UUID, response_id: UUID) -> TaskResponse:
        response = await self.repository.get_response(task_id=task_id, response_id=response_id)
        if response is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task response not found",
            )
        return response

    async def _get_required_enabled_link(self, task: Task) -> BitrixTaskLink:
        if not self.settings.bitrix24_enabled:
            link = await self._mark_disabled(task)
            await self.session.commit()
            await self._refresh_link(link)
            return link

        link = await self.repository.get_active_task_link(task.id)
        if link is None:
            link = await self._mark_error(
                task=task,
                link=None,
                error=ValueError("Active Bitrix24 task link was not found."),
            )
            await self.session.commit()
            await self._refresh_link(link)
        return link

    async def _build_task_add_fields(self, task: Task) -> dict[str, Any]:
        user_mappings = await self.repository.list_active_user_mappings(task.organization_id)
        return self.mapper.to_task_add_fields(task=task, user_mappings=user_mappings)

    async def _mark_disabled(self, task: Task) -> BitrixTaskLink:
        link = await self.repository.get_latest_task_link(task.id)
        return await self._upsert_link(
            task=task,
            link=link,
            values={
                "sync_status": BitrixSyncStatus.DISABLED.value,
                "last_error": "Bitrix24 integration is disabled.",
            },
        )

    async def _mark_error(
        self,
        *,
        task: Task,
        link: BitrixTaskLink | None,
        error: Exception,
    ) -> BitrixTaskLink:
        return await self._upsert_link(
            task=task,
            link=link,
            values={
                "sync_status": BitrixSyncStatus.ERROR.value,
                "last_error": self._safe_error(error),
            },
        )

    async def _upsert_link(
        self,
        *,
        task: Task,
        link: BitrixTaskLink | None,
        values: Mapping[str, Any],
    ) -> BitrixTaskLink:
        if link is not None:
            return await self.repository.update_task_link(link, values=values)
        return await self.repository.create_task_link(
            task_id=task.id,
            organization_id=task.organization_id,
            bitrix_task_id=values.get("bitrix_task_id"),
            sync_status=values["sync_status"],
            last_sync_at=values.get("last_sync_at"),
            last_error=values.get("last_error"),
        )

    def _build_result(
        self,
        *,
        task: Task,
        link: BitrixTaskLink,
        action: str,
        detail: str,
    ) -> BitrixTaskSyncRead:
        return BitrixTaskSyncRead(
            task_id=task.id,
            organization_id=task.organization_id,
            sync_status=link.sync_status,
            action=action,
            detail=detail,
            bitrix_task_id=link.bitrix_task_id,
            last_error=link.last_error,
            link=link,
        )

    def _extract_bitrix_task_id(self, response: Mapping[str, Any]) -> str:
        result = response.get("result")
        if isinstance(result, (str, int)):
            return str(result)
        if not isinstance(result, Mapping):
            raise ValueError("Bitrix24 response does not contain result.")

        task_payload = result.get("task")
        if isinstance(task_payload, Mapping):
            task_id = task_payload.get("id") or task_payload.get("ID")
            if task_id is not None:
                return str(task_id)

        task_id = (
            result.get("taskId")
            or result.get("TASK_ID")
            or result.get("ID")
            or result.get("id")
        )
        if task_id is None:
            raise ValueError("Bitrix24 response does not contain task id.")
        return str(task_id)

    def _map_task_status(self, local_status: str) -> str:
        status_map = {
            TaskStatus.NEW.value: "2",
            TaskStatus.IN_PROGRESS.value: "3",
            TaskStatus.WAITING_RESPONSE.value: "3",
            TaskStatus.WAITING_ACCEPTANCE.value: "4",
            TaskStatus.DONE.value: "5",
            TaskStatus.OVERDUE.value: "3",
            TaskStatus.REJECTED.value: "3",
            TaskStatus.CANCELLED.value: "6",
        }
        return status_map.get(local_status, "3")

    def _format_response_comment(self, response: TaskResponse) -> str:
        text = response.text or ""
        lines = [
            "Ответ исполнителя из max_secretary",
            f"Local response_id: {response.id}",
            f"Local user_id: {response.user_id}",
        ]
        if response.source_message_id:
            lines.append(f"Source message ID: {response.source_message_id}")
        if text:
            lines.extend(["", text])
        return "\n".join(lines)

    async def _refresh_link(self, link: BitrixTaskLink) -> None:
        await self.session.refresh(link)

    def _safe_error(self, error: Exception) -> str:
        return str(error)[:500]

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _status_detail(self, sync_status: str) -> str:
        details = {
            BitrixSyncStatus.PENDING.value: "Bitrix24 synchronization is pending.",
            BitrixSyncStatus.SYNCED.value: "Bitrix24 task is synchronized.",
            BitrixSyncStatus.ERROR.value: "Bitrix24 synchronization failed.",
            BitrixSyncStatus.DISABLED.value: "Bitrix24 integration is disabled.",
        }
        return details.get(sync_status, "Unknown Bitrix24 synchronization status.")
