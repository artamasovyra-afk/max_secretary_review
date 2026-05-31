from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, name: str, status: str) -> Organization:
        organization = Organization(name=name, status=status)
        self.session.add(organization)
        await self.session.flush()
        return organization

    async def list(self) -> list[Organization]:
        result = await self.session.scalars(
            select(Organization).order_by(Organization.created_at.desc())
        )
        return list(result)

    async def get(self, organization_id: UUID) -> Optional[Organization]:
        return await self.session.get(Organization, organization_id)

    async def get_by_name(self, name: str) -> Optional[Organization]:
        result = await self.session.scalars(select(Organization).where(Organization.name == name))
        return result.one_or_none()

    async def update(
        self,
        organization: Organization,
        *,
        name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Organization:
        if name is not None:
            organization.name = name
        if status is not None:
            organization.status = status
        await self.session.flush()
        return organization
