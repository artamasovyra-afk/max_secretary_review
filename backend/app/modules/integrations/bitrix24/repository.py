from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.integrations.enums import BitrixSyncStatus
from app.modules.integrations.models import BitrixTaskLink, BitrixUserMapping
from app.modules.organizations.models import Organization
from app.modules.tasks.models import Task, TaskAssignee, TaskObserver, TaskResponse
from app.modules.users.models import User


class BitrixUserMappingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def organization_exists(self, organization_id: UUID) -> bool:
        return await self.session.get(Organization, organization_id) is not None

    async def user_exists(self, user_id: UUID) -> bool:
        return await self.session.get(User, user_id) is not None

    async def create(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        bitrix_user_id: str,
        match_source: str,
        is_active: bool,
    ) -> BitrixUserMapping:
        mapping = BitrixUserMapping(
            organization_id=organization_id,
            user_id=user_id,
            bitrix_user_id=bitrix_user_id,
            match_source=match_source,
            is_active=is_active,
        )
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def list(
        self,
        *,
        organization_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        bitrix_user_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> list[BitrixUserMapping]:
        statement = select(BitrixUserMapping)
        if organization_id is not None:
            statement = statement.where(BitrixUserMapping.organization_id == organization_id)
        if user_id is not None:
            statement = statement.where(BitrixUserMapping.user_id == user_id)
        if bitrix_user_id is not None:
            statement = statement.where(BitrixUserMapping.bitrix_user_id == bitrix_user_id)
        if is_active is not None:
            statement = statement.where(BitrixUserMapping.is_active == is_active)

        result = await self.session.scalars(statement.order_by(BitrixUserMapping.created_at.desc()))
        return list(result)

    async def get(self, mapping_id: UUID) -> Optional[BitrixUserMapping]:
        return await self.session.get(BitrixUserMapping, mapping_id)

    async def get_active_for_user(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        exclude_mapping_id: Optional[UUID] = None,
    ) -> Optional[BitrixUserMapping]:
        statement = select(BitrixUserMapping).where(
            BitrixUserMapping.organization_id == organization_id,
            BitrixUserMapping.user_id == user_id,
            BitrixUserMapping.is_active.is_(True),
        )
        if exclude_mapping_id is not None:
            statement = statement.where(BitrixUserMapping.id != exclude_mapping_id)

        result = await self.session.scalars(statement)
        return result.first()

    async def update(
        self,
        mapping: BitrixUserMapping,
        *,
        values: Mapping[str, Any],
    ) -> BitrixUserMapping:
        for field_name in (
            "organization_id",
            "user_id",
            "bitrix_user_id",
            "match_source",
            "is_active",
        ):
            if field_name in values:
                setattr(mapping, field_name, values[field_name])
        await self.session.flush()
        return mapping


class Bitrix24SyncRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_task_for_sync(self, task_id: UUID) -> Optional[Task]:
        result = await self.session.scalars(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.assignees).selectinload(TaskAssignee.user),
                selectinload(Task.observers).selectinload(TaskObserver.user),
            )
        )
        return result.one_or_none()

    async def get_response(self, *, task_id: UUID, response_id: UUID) -> Optional[TaskResponse]:
        result = await self.session.scalars(
            select(TaskResponse).where(
                TaskResponse.task_id == task_id,
                TaskResponse.id == response_id,
            )
        )
        return result.one_or_none()

    async def list_active_user_mappings(self, organization_id: UUID) -> list[BitrixUserMapping]:
        result = await self.session.scalars(
            select(BitrixUserMapping).where(
                BitrixUserMapping.organization_id == organization_id,
                BitrixUserMapping.is_active.is_(True),
            )
        )
        return list(result)

    async def get_active_task_link(self, task_id: UUID) -> Optional[BitrixTaskLink]:
        result = await self.session.scalars(
            select(BitrixTaskLink)
            .where(
                BitrixTaskLink.task_id == task_id,
                BitrixTaskLink.sync_status != BitrixSyncStatus.DISABLED.value,
            )
            .order_by(BitrixTaskLink.created_at.desc())
        )
        return result.first()

    async def get_latest_task_link(self, task_id: UUID) -> Optional[BitrixTaskLink]:
        result = await self.session.scalars(
            select(BitrixTaskLink)
            .where(BitrixTaskLink.task_id == task_id)
            .order_by(BitrixTaskLink.created_at.desc())
        )
        return result.first()

    async def create_task_link(
        self,
        *,
        task_id: UUID,
        organization_id: UUID,
        bitrix_task_id: Optional[str] = None,
        sync_status: str,
        last_sync_at: Optional[datetime] = None,
        last_error: Optional[str] = None,
    ) -> BitrixTaskLink:
        link = BitrixTaskLink(
            task_id=task_id,
            organization_id=organization_id,
            bitrix_task_id=bitrix_task_id,
            sync_status=sync_status,
            last_sync_at=last_sync_at,
            last_error=last_error,
        )
        self.session.add(link)
        await self.session.flush()
        return link

    async def update_task_link(
        self,
        link: BitrixTaskLink,
        *,
        values: Mapping[str, Any],
    ) -> BitrixTaskLink:
        for field_name in (
            "bitrix_portal_url",
            "bitrix_task_id",
            "sync_status",
            "last_sync_at",
            "last_error",
        ):
            if field_name in values:
                setattr(link, field_name, values[field_name])
        await self.session.flush()
        return link

    async def list_failed_task_links(self, *, limit: int) -> list[BitrixTaskLink]:
        result = await self.session.scalars(
            select(BitrixTaskLink)
            .where(BitrixTaskLink.sync_status == BitrixSyncStatus.ERROR.value)
            .order_by(BitrixTaskLink.updated_at.asc())
            .limit(limit)
        )
        return list(result)
