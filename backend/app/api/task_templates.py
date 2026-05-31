from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_auth_context
from app.db.session import get_session
from app.modules.auth.context import AuthContext
from app.modules.tasks.template_repository import TaskTemplateRepository
from app.modules.tasks.template_schemas import (
    TaskTemplateCreate,
    TaskTemplateRead,
    TaskTemplateUpdate,
)
from app.modules.tasks.template_service import TaskTemplateService

router = APIRouter(tags=["task-templates"])


def get_task_template_service(
    session: AsyncSession = Depends(get_session),
) -> TaskTemplateService:
    return TaskTemplateService(
        repository=TaskTemplateRepository(session),
        session=session,
    )


@router.post("", response_model=TaskTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_task_template(
    payload: TaskTemplateCreate,
    service: TaskTemplateService = Depends(get_task_template_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> TaskTemplateRead:
    return await service.create(payload, auth_context)


@router.get("", response_model=list[TaskTemplateRead])
async def list_task_templates(
    organization_id: Optional[UUID] = None,
    chat_id: Optional[UUID] = None,
    created_by_user_id: Optional[UUID] = None,
    is_active: Optional[bool] = True,
    service: TaskTemplateService = Depends(get_task_template_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> list[TaskTemplateRead]:
    return await service.list(
        auth_context=auth_context,
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=created_by_user_id,
        is_active=is_active,
    )


@router.get("/{template_id}", response_model=TaskTemplateRead)
async def get_task_template(
    template_id: UUID,
    service: TaskTemplateService = Depends(get_task_template_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> TaskTemplateRead:
    return await service.get(template_id, auth_context)


@router.patch("/{template_id}", response_model=TaskTemplateRead)
async def update_task_template(
    template_id: UUID,
    payload: TaskTemplateUpdate,
    service: TaskTemplateService = Depends(get_task_template_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> TaskTemplateRead:
    return await service.update(template_id, payload, auth_context)


@router.delete("/{template_id}", response_model=TaskTemplateRead)
async def delete_task_template(
    template_id: UUID,
    service: TaskTemplateService = Depends(get_task_template_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> TaskTemplateRead:
    return await service.delete(template_id, auth_context)
