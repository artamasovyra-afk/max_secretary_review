from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        display_name: str,
        max_user_id: Optional[str] = None,
        username: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> User:
        user = User(
            max_user_id=max_user_id,
            display_name=display_name,
            username=username,
            phone=phone,
            email=email,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def list(self) -> list[User]:
        result = await self.session.scalars(select(User).order_by(User.created_at.desc()))
        return list(result)

    async def get(self, user_id: UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def get_by_max_user_id(self, max_user_id: str) -> Optional[User]:
        result = await self.session.scalars(select(User).where(User.max_user_id == max_user_id))
        return result.one_or_none()

    async def find_by_display_name(self, display_name: str) -> list[User]:
        normalized_display_name = display_name.strip().lower()
        result = await self.session.scalars(
            select(User).where(func.lower(User.display_name) == normalized_display_name)
        )
        return list(result)

    async def update(
        self,
        user: User,
        *,
        values: Mapping[str, Any],
    ) -> User:
        for field_name in ("max_user_id", "display_name", "username", "phone", "email"):
            if field_name in values:
                setattr(user, field_name, values[field_name])
        await self.session.flush()
        return user
