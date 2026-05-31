from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.max_webapp import VerifiedMaxWebAppUser
from app.modules.auth.policy import ROLE_MEMBER, ROLE_SUPER_ADMIN
from app.modules.chats.repository import ChatRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


@dataclass(frozen=True)
class WebAppChatContext:
    id: UUID
    organization_id: UUID
    title: str
    role: str


@dataclass(frozen=True)
class WebAppAuthenticatedUser:
    user: User
    roles: list[str]
    organization_id: UUID | None
    chat_id: UUID | None
    available_chats: list[WebAppChatContext]


class WebAppAuthServiceError(ValueError):
    """Raised when a WebApp session references an unavailable local user."""


class MaxWebAppAuthService:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        chat_repository: ChatRepository,
        session: AsyncSession,
    ) -> None:
        self.user_repository = user_repository
        self.chat_repository = chat_repository
        self.session = session

    async def resolve_verified_user(self, verified_user: VerifiedMaxWebAppUser) -> WebAppAuthenticatedUser:
        user = await self.user_repository.get_by_max_user_id(verified_user.max_user_id)
        if user is None:
            user = await self.user_repository.create(
                max_user_id=verified_user.max_user_id,
                display_name=_safe_display_name(verified_user),
                username=verified_user.username,
            )
        else:
            values: dict[str, str | None] = {}
            if _is_generated_display_name(user.display_name) and verified_user.display_name:
                values["display_name"] = verified_user.display_name
            if not user.username and verified_user.username:
                values["username"] = verified_user.username
            if values:
                user = await self.user_repository.update(user, values=values)

        await self.session.commit()
        await self.session.refresh(user)
        return await self.build_authenticated_user(user)

    async def get_authenticated_user(self, user_id: UUID) -> WebAppAuthenticatedUser:
        user = await self.user_repository.get(user_id)
        if user is None:
            raise WebAppAuthServiceError("WebApp session user was not found")
        return await self.build_authenticated_user(user)

    async def build_authenticated_user(self, user: User) -> WebAppAuthenticatedUser:
        memberships = await self.chat_repository.list_memberships_for_user(user.id)
        available_chats = [
            WebAppChatContext(
                id=member.chat.id,
                organization_id=member.chat.organization_id,
                title=member.chat.title,
                role=member.role,
            )
            for member in memberships
            if member.chat is not None
        ]
        primary_chat = available_chats[0] if available_chats else None
        roles = _deduplicate_roles([chat.role for chat in available_chats] or [ROLE_MEMBER])
        return WebAppAuthenticatedUser(
            user=user,
            roles=roles,
            organization_id=primary_chat.organization_id if primary_chat else None,
            chat_id=primary_chat.id if primary_chat else None,
            available_chats=available_chats,
        )


def _safe_display_name(verified_user: VerifiedMaxWebAppUser) -> str:
    if verified_user.display_name:
        return verified_user.display_name
    if verified_user.username:
        return verified_user.username
    return f"MAX user #{_short_external_id(verified_user.max_user_id)}"


def _is_generated_display_name(value: str) -> bool:
    return value.startswith("MAX user #")


def _short_external_id(value: str) -> str:
    return value[-8:] if len(value) > 8 else value


def _deduplicate_roles(roles: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_roles: list[str] = []
    for role in roles:
        if role in seen:
            continue
        seen.add(role)
        unique_roles.append(role)
    if ROLE_SUPER_ADMIN in seen and ROLE_SUPER_ADMIN not in unique_roles:
        unique_roles.append(ROLE_SUPER_ADMIN)
    return unique_roles
