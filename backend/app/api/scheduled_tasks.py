from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_auth_context
from app.db.session import get_session
from app.modules.auth.context import AuthContext
from app.modules.tasks.scheduled_repository import ScheduledTaskRepository
from app.modules.tasks.scheduled_schemas import (
    ScheduledTaskCreate,
    ScheduledTaskRead,
    ScheduledTaskUpdate,
)
from app.modules.tasks.scheduled_service import ScheduledTaskService

router = APIRouter(tags=["scheduled-tasks"])


def get_scheduled_task_service(
    session: AsyncSession = Depends(get_session),
) -> ScheduledTaskService:
    return ScheduledTaskService(
        repository=ScheduledTaskRepository(session),
        session=session,
    )


@router.post("", response_model=ScheduledTaskRead, status_code=status.HTTP_201_CREATED)
async def create_scheduled_task(
    payload: ScheduledTaskCreate,
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ScheduledTaskRead:
    return await service.create(payload, auth_context)


@router.get("", response_model=list[ScheduledTaskRead])
async def list_scheduled_tasks(
    organization_id: Optional[UUID] = None,
    chat_id: Optional[UUID] = None,
    created_by_user_id: Optional[UUID] = None,
    is_active: Optional[bool] = True,
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> list[ScheduledTaskRead]:
    return await service.list(
        auth_context=auth_context,
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=created_by_user_id,
        is_active=is_active,
    )


@router.get("/{scheduled_task_id}", response_model=ScheduledTaskRead)
async def get_scheduled_task(
    scheduled_task_id: UUID,
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ScheduledTaskRead:
    return await service.get(scheduled_task_id, auth_context)


@router.patch("/{scheduled_task_id}", response_model=ScheduledTaskRead)
async def update_scheduled_task(
    scheduled_task_id: UUID,
    payload: ScheduledTaskUpdate,
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ScheduledTaskRead:
    return await service.update(scheduled_task_id, payload, auth_context)


@router.delete("/{scheduled_task_id}", response_model=ScheduledTaskRead)
async def delete_scheduled_task(
    scheduled_task_id: UUID,
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ScheduledTaskRead:
    return await service.delete(scheduled_task_id, auth_context)
