from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.chats.models import Chat, ChatMember
from app.modules.organizations.models import Organization
from app.modules.tasks.models import AuditLog
from app.modules.users.models import User


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def organization_exists(self, organization_id: UUID) -> bool:
        return await self.session.get(Organization, organization_id) is not None

    async def user_exists(self, user_id: UUID) -> bool:
        return await self.session.get(User, user_id) is not None

    async def create_chat(
        self,
        *,
        organization_id: UUID,
        title: str,
        type: str,
        max_chat_id: Optional[str] = None,
        status: str = "active",
        settings: Optional[dict[str, Any]] = None,
    ) -> Chat:
        chat = Chat(
            organization_id=organization_id,
            max_chat_id=max_chat_id,
            title=title,
            type=type,
            status=status,
            settings=settings,
        )
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def list_chats(self, *, status: str | None = None) -> list[Chat]:
        query = select(Chat)
        if status is not None:
            query = query.where(Chat.status == status)
        result = await self.session.scalars(query.order_by(Chat.created_at.desc()))
        return list(result)

    async def get_chat(self, chat_id: UUID) -> Optional[Chat]:
        return await self.session.get(Chat, chat_id)

    async def get_chat_by_max_chat_id(
        self,
        *,
        organization_id: UUID,
        max_chat_id: str,
    ) -> Optional[Chat]:
        result = await self.session.scalars(
            select(Chat).where(
                Chat.organization_id == organization_id,
                Chat.max_chat_id == max_chat_id,
            )
        )
        return result.one_or_none()

    async def update_chat(
        self,
        chat: Chat,
        *,
        values: Mapping[str, Any],
    ) -> Chat:
        for field_name in ("organization_id", "max_chat_id", "title", "type", "status", "settings"):
            if field_name in values:
                setattr(chat, field_name, values[field_name])
        await self.session.flush()
        return chat

    async def count_members(self, chat_id: UUID) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(ChatMember).where(ChatMember.chat_id == chat_id)
        )
        return int(result or 0)

    async def count_active_members(self, chat_id: UUID) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(ChatMember).where(
                ChatMember.chat_id == chat_id,
                ChatMember.is_active.is_(True),
            )
        )
        return int(result or 0)

    async def count_active_chat_admins(self, chat_id: UUID) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(ChatMember).where(
                ChatMember.chat_id == chat_id,
                ChatMember.role == "chat_admin",
                ChatMember.is_active.is_(True),
            )
        )
        return int(result or 0)

    async def create_member(
        self,
        *,
        chat_id: UUID,
        user_id: UUID,
        role: str,
        is_active: bool,
    ) -> ChatMember:
        member = ChatMember(
            chat_id=chat_id,
            user_id=user_id,
            role=role,
            is_active=is_active,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def create_audit_log(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID | None,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            organization_id=organization_id,
            user_id=None,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            payload=payload,
        )
        self.session.add(audit_log)
        await self.session.flush()
        return audit_log

    async def list_members(self, chat_id: UUID) -> list[ChatMember]:
        result = await self.session.scalars(
            select(ChatMember)
            .where(ChatMember.chat_id == chat_id)
            .options(selectinload(ChatMember.user), selectinload(ChatMember.chat))
            .order_by(ChatMember.created_at.desc())
        )
        return list(result)

    async def list_memberships_for_user(self, user_id: UUID) -> list[ChatMember]:
        result = await self.session.scalars(
            select(ChatMember)
            .where(
                ChatMember.user_id == user_id,
                ChatMember.is_active.is_(True),
            )
            .options(selectinload(ChatMember.chat))
            .order_by(ChatMember.created_at.desc())
        )
        return list(result)

    async def get_member(
        self,
        *,
        chat_id: UUID,
        user_id: UUID,
    ) -> Optional[ChatMember]:
        result = await self.session.scalars(
            select(ChatMember)
            .where(
                ChatMember.chat_id == chat_id,
                ChatMember.user_id == user_id,
            )
            .options(selectinload(ChatMember.user))
        )
        return result.one_or_none()

    async def update_member(
        self,
        member: ChatMember,
        *,
        values: Mapping[str, Any],
    ) -> ChatMember:
        for field_name in ("role", "is_active"):
            if field_name in values:
                setattr(member, field_name, values[field_name])
        await self.session.flush()
        return member
