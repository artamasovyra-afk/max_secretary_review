from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_SUPER_ADMIN
from app.modules.chats.models import Chat, ChatMember
from app.modules.chats.repository import ChatRepository
from app.modules.chats.schemas import ChatCreate, ChatMemberCreate, ChatMemberUpdate, ChatUpdate


class ChatService:
    def __init__(self, repository: ChatRepository, session: AsyncSession) -> None:
        self.repository = repository
        self.session = session

    async def create(self, payload: ChatCreate) -> Chat:
        await self._ensure_organization_exists(payload.organization_id)
        chat = await self.repository.create_chat(
            organization_id=payload.organization_id,
            max_chat_id=payload.max_chat_id,
            title=payload.title,
            type=payload.type,
            status=payload.status.value,
            settings=payload.settings,
        )
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def list(self) -> list[Chat]:
        return await self.repository.list_chats()

    async def list_for_auth_context(self, auth_context: AuthContext) -> list[Chat]:
        if auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN):
            return await self.list()

        memberships = await self.repository.list_memberships_for_user(auth_context.user_id)
        chats = [
            membership.chat
            for membership in memberships
            if membership.chat is not None and membership.is_active
        ]
        if auth_context.organization_id is not None:
            chats = [chat for chat in chats if chat.organization_id == auth_context.organization_id]
        return chats

    async def get(self, chat_id: UUID) -> Chat:
        chat = await self.repository.get_chat(chat_id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found",
            )
        return chat

    async def update(self, chat_id: UUID, payload: ChatUpdate) -> Chat:
        chat = await self.get(chat_id)
        values = payload.model_dump(exclude_unset=True)
        if "status" in values:
            values["status"] = values["status"].value
        if "display_title" in values:
            display_title = values.pop("display_title")
            settings = dict(values.get("settings") or chat.settings or {})
            if display_title:
                settings["display_title"] = display_title
            else:
                settings.pop("display_title", None)
            values["settings"] = settings or None
        if "organization_id" in values:
            await self._ensure_organization_exists(values["organization_id"])
        chat = await self.repository.update_chat(chat, values=values)
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def add_member(self, chat_id: UUID, payload: ChatMemberCreate) -> ChatMember:
        await self.get(chat_id)
        await self._ensure_user_exists(payload.user_id)
        existing_member = await self.repository.get_member(
            chat_id=chat_id,
            user_id=payload.user_id,
        )
        if existing_member is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chat member already exists",
            )
        member = await self.repository.create_member(
            chat_id=chat_id,
            user_id=payload.user_id,
            role=payload.role.value,
            is_active=payload.is_active,
        )
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def list_members(self, chat_id: UUID) -> list[ChatMember]:
        await self.get(chat_id)
        return await self.repository.list_members(chat_id)

    async def update_member(
        self,
        *,
        chat_id: UUID,
        user_id: UUID,
        payload: ChatMemberUpdate,
    ) -> ChatMember:
        await self.get(chat_id)
        member = await self.repository.get_member(chat_id=chat_id, user_id=user_id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat member not found",
            )
        values = payload.model_dump(exclude_unset=True)
        if "role" in values:
            values["role"] = values["role"].value
        member = await self.repository.update_member(member, values=values)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def _ensure_organization_exists(self, organization_id: UUID) -> None:
        if not await self.repository.organization_exists(organization_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

    async def _ensure_user_exists(self, user_id: UUID) -> None:
        if not await self.repository.user_exists(user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
