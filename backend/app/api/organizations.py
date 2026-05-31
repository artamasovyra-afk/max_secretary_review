from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_auth_context
from app.db.session import get_session
from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_SUPER_ADMIN
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import (
    OrganizationCreate,
    OrganizationRead,
    OrganizationStatus,
    OrganizationUpdate,
)
from app.modules.organizations.service import OrganizationService

router = APIRouter(tags=["organizations"], dependencies=[Depends(get_auth_context)])


def get_organization_service(
    session: AsyncSession = Depends(get_session),
) -> OrganizationService:
    return OrganizationService(
        repository=OrganizationRepository(session),
        session=session,
    )


@router.get("/status", response_model=OrganizationStatus)
def organizations_status() -> OrganizationStatus:
    return OrganizationStatus(status="ok", module="organizations")


@router.post(
    "",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    payload: OrganizationCreate,
    service: OrganizationService = Depends(get_organization_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> OrganizationRead:
    _ensure_super_admin(auth_context)
    return await service.create(payload)


@router.get("", response_model=list[OrganizationRead])
async def list_organizations(
    service: OrganizationService = Depends(get_organization_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> list[OrganizationRead]:
    organizations = await service.list()
    if _is_super_admin(auth_context):
        return organizations
    if auth_context.organization_id is None:
        raise _forbidden("Organization scope is required")
    return [organization for organization in organizations if organization.id == auth_context.organization_id]


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(
    organization_id: UUID,
    service: OrganizationService = Depends(get_organization_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> OrganizationRead:
    _ensure_organization_scope(auth_context, organization_id)
    return await service.get(organization_id)


@router.patch("/{organization_id}", response_model=OrganizationRead)
async def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    service: OrganizationService = Depends(get_organization_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> OrganizationRead:
    _ensure_super_admin(auth_context)
    return await service.update(organization_id, payload)


def _is_super_admin(auth_context: AuthContext) -> bool:
    return auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN)


def _ensure_super_admin(auth_context: AuthContext) -> None:
    if not _is_super_admin(auth_context):
        raise _forbidden("Super admin role is required")


def _ensure_organization_scope(auth_context: AuthContext, organization_id: UUID) -> None:
    if _is_super_admin(auth_context):
        return
    if auth_context.organization_id == organization_id:
        return
    raise _forbidden("Organization scope mismatch")


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
