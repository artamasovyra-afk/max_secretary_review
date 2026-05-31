from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import OrganizationCreate, OrganizationUpdate


class OrganizationService:
    def __init__(self, repository: OrganizationRepository, session: AsyncSession) -> None:
        self.repository = repository
        self.session = session

    async def create(self, payload: OrganizationCreate) -> Organization:
        organization = await self.repository.create(
            name=payload.name,
            status=payload.status,
        )
        await self.session.commit()
        await self.session.refresh(organization)
        return organization

    async def list(self) -> list[Organization]:
        return await self.repository.list()

    async def get(self, organization_id: UUID) -> Organization:
        organization = await self.repository.get(organization_id)
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
    ) -> Organization:
        organization = await self.get(organization_id)
        organization = await self.repository.update(
            organization,
            name=payload.name,
            status=payload.status,
        )
        await self.session.commit()
        await self.session.refresh(organization)
        return organization
