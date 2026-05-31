from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_auth_context
from app.db.session import get_session
from app.modules.auth.context import AuthContext
from app.modules.auth.policy import PolicyService, ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN
from app.modules.integrations.bitrix24.repository import (
    Bitrix24SyncRepository,
    BitrixUserMappingRepository,
)
from app.modules.integrations.bitrix24.schemas import (
    BitrixRetryFailedSyncRead,
    BitrixTaskSyncStatusRead,
    BitrixTaskSyncRead,
    BitrixUserMappingCreate,
    BitrixUserMappingRead,
    BitrixUserMappingUpdate,
)
from app.modules.integrations.bitrix24.service import Bitrix24SyncService, BitrixUserMappingService

router = APIRouter(tags=["integrations", "bitrix24"])
policy_service = PolicyService()


def get_bitrix_user_mapping_service(
    session: AsyncSession = Depends(get_session),
) -> BitrixUserMappingService:
    return BitrixUserMappingService(
        repository=BitrixUserMappingRepository(session),
        session=session,
    )


def get_bitrix24_sync_service(
    session: AsyncSession = Depends(get_session),
) -> Bitrix24SyncService:
    return Bitrix24SyncService(
        repository=Bitrix24SyncRepository(session),
        session=session,
    )


@router.post(
    "/user-mappings",
    response_model=BitrixUserMappingRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_bitrix_user_mapping(
    payload: BitrixUserMappingCreate,
    service: BitrixUserMappingService = Depends(get_bitrix_user_mapping_service),
    context: AuthContext = Depends(get_auth_context),
) -> BitrixUserMappingRead:
    _ensure_can_manage_bitrix_mapping(context, payload.organization_id)
    return await service.create(payload)


@router.get("/user-mappings", response_model=list[BitrixUserMappingRead])
async def list_bitrix_user_mappings(
    organization_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    bitrix_user_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    service: BitrixUserMappingService = Depends(get_bitrix_user_mapping_service),
    context: AuthContext = Depends(get_auth_context),
) -> list[BitrixUserMappingRead]:
    if organization_id is None:
        _ensure_super_admin_or_forbid(context)
    else:
        _ensure_can_manage_bitrix_mapping(context, organization_id)
    return await service.list(
        organization_id=organization_id,
        user_id=user_id,
        bitrix_user_id=bitrix_user_id,
        is_active=is_active,
    )


@router.get("/user-mappings/{mapping_id}", response_model=BitrixUserMappingRead)
async def get_bitrix_user_mapping(
    mapping_id: UUID,
    service: BitrixUserMappingService = Depends(get_bitrix_user_mapping_service),
    context: AuthContext = Depends(get_auth_context),
) -> BitrixUserMappingRead:
    mapping = await service.get(mapping_id)
    _ensure_can_manage_bitrix_mapping(context, mapping.organization_id)
    return mapping


@router.patch("/user-mappings/{mapping_id}", response_model=BitrixUserMappingRead)
async def update_bitrix_user_mapping(
    mapping_id: UUID,
    payload: BitrixUserMappingUpdate,
    service: BitrixUserMappingService = Depends(get_bitrix_user_mapping_service),
    context: AuthContext = Depends(get_auth_context),
) -> BitrixUserMappingRead:
    mapping = await service.get(mapping_id)
    _ensure_can_manage_bitrix_mapping(context, mapping.organization_id)
    if payload.organization_id is not None:
        _ensure_can_manage_bitrix_mapping(context, payload.organization_id)
    return await service.update(mapping_id, payload)


@router.delete("/user-mappings/{mapping_id}", response_model=BitrixUserMappingRead)
async def delete_bitrix_user_mapping(
    mapping_id: UUID,
    service: BitrixUserMappingService = Depends(get_bitrix_user_mapping_service),
    context: AuthContext = Depends(get_auth_context),
) -> BitrixUserMappingRead:
    mapping = await service.get(mapping_id)
    _ensure_can_manage_bitrix_mapping(context, mapping.organization_id)
    return await service.delete(mapping_id)


@router.post("/tasks/{task_id}/sync", response_model=BitrixTaskSyncRead)
async def sync_bitrix_task_create(
    task_id: UUID,
    service: Bitrix24SyncService = Depends(get_bitrix24_sync_service),
    context: AuthContext = Depends(get_auth_context),
) -> BitrixTaskSyncRead:
    task = await service.get_task_for_policy(task_id)
    if not policy_service.can_run_bitrix_sync(context, task):
        raise _forbidden()
    return await service.sync_task_create(task_id)


@router.get("/tasks/{task_id}/status", response_model=BitrixTaskSyncStatusRead)
async def get_bitrix_task_sync_status(
    task_id: UUID,
    service: Bitrix24SyncService = Depends(get_bitrix24_sync_service),
    context: AuthContext = Depends(get_auth_context),
) -> BitrixTaskSyncStatusRead:
    task = await service.get_task_for_policy(task_id)
    if not policy_service.can_view_task(context, task):
        raise _forbidden()
    return await service.get_task_sync_status(task_id)


@router.post("/retry-failed", response_model=BitrixRetryFailedSyncRead)
async def retry_failed_bitrix_sync(
    limit: int = 50,
    service: Bitrix24SyncService = Depends(get_bitrix24_sync_service),
    context: AuthContext = Depends(get_auth_context),
) -> BitrixRetryFailedSyncRead:
    _ensure_chat_admin_or_super_admin(context)
    return await service.retry_failed_sync(limit=limit)


def _ensure_can_manage_bitrix_mapping(context: AuthContext, organization_id: UUID) -> None:
    if not policy_service.can_manage_bitrix_mapping(context, organization_id):
        raise _forbidden()


def _ensure_chat_admin_or_super_admin(context: AuthContext) -> None:
    if _is_super_admin(context) or context.has_role(ROLE_CHAT_ADMIN):
        return
    raise _forbidden()


def _ensure_super_admin_or_forbid(context: AuthContext) -> None:
    if _is_super_admin(context):
        return
    raise _forbidden()


def _is_super_admin(context: AuthContext) -> bool:
    return context.is_super_admin or context.has_role(ROLE_SUPER_ADMIN)


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
    )
