from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate, UserUpdate


class UserService:
    def __init__(self, repository: UserRepository, session: AsyncSession) -> None:
        self.repository = repository
        self.session = session

    async def create(self, payload: UserCreate) -> User:
        user = await self.repository.create(
            max_user_id=payload.max_user_id,
            display_name=payload.display_name,
            username=payload.username,
            phone=payload.phone,
            email=payload.email,
        )
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list(self) -> list[User]:
        return await self.repository.list()

    async def get(self, user_id: UUID) -> User:
        user = await self.repository.get(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    async def update(self, user_id: UUID, payload: UserUpdate) -> User:
        user = await self.get(user_id)
        values = payload.model_dump(exclude_unset=True)
        user = await self.repository.update(
            user,
            values=values,
        )
        await self.session.commit()
        await self.session.refresh(user)
        return user
