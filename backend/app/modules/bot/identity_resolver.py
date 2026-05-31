from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.policy import ROLE_MEMBER
from app.modules.chats.schemas import ChatConnectionStatus
from app.modules.bot.schemas import NormalizedBotEvent
from app.modules.chats.models import Chat
from app.modules.chats.repository import ChatRepository
from app.modules.organizations.models import Organization
from app.modules.organizations.repository import OrganizationRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.integrations.max.exceptions import MaxApiError

DEFAULT_MAX_ORGANIZATION_NAME = "MAX default organization"
DEFAULT_MAX_ORGANIZATION_STATUS = "active"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedMaxIdentity:
    user: User
    chat: Chat
    organization: Organization


class MaxIdentityResolverError(Exception):
    """Raised when a MAX webhook identity cannot be mapped to local records."""


class MaxChatInfoClient(Protocol):
    def get_chat_info(self, chat_id: str) -> dict[str, str | None]:
        """Return normalized MAX chat info for one chat."""


class MaxIdentityResolver:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        chat_repository: ChatRepository,
        organization_repository: OrganizationRepository,
        session: AsyncSession,
        max_chat_info_client: MaxChatInfoClient | None = None,
    ) -> None:
        self.user_repository = user_repository
        self.chat_repository = chat_repository
        self.organization_repository = organization_repository
        self.session = session
        self.max_chat_info_client = max_chat_info_client

    async def resolve_event(self, event: NormalizedBotEvent) -> ResolvedMaxIdentity:
        organization = await self.get_or_create_default_max_organization()
        user = await self.resolve_max_user(event)
        chat = await self.resolve_max_chat(event, organization=organization)
        await self.ensure_chat_member(chat=chat, user=user)
        await self.session.commit()
        return ResolvedMaxIdentity(user=user, chat=chat, organization=organization)

    async def get_or_create_default_max_organization(self) -> Organization:
        organization = await self.organization_repository.get_by_name(DEFAULT_MAX_ORGANIZATION_NAME)
        if organization is not None:
            return organization
        return await self.organization_repository.create(
            name=DEFAULT_MAX_ORGANIZATION_NAME,
            status=DEFAULT_MAX_ORGANIZATION_STATUS,
        )

    async def resolve_max_user(self, event: NormalizedBotEvent) -> User:
        max_user_id = _required_external_id(event.user_id, field_name="user_id")
        internal_user_id = parse_internal_uuid(max_user_id)
        if internal_user_id is not None:
            user_by_internal_id = await self.user_repository.get(internal_user_id)
            if user_by_internal_id is not None:
                return user_by_internal_id

        user = await self.user_repository.get_by_max_user_id(max_user_id)
        display_name = _safe_user_display_name(
            max_user_id=max_user_id,
            sender_display_name=event.sender_display_name,
            sender_username=event.sender_username,
        )
        if user is None:
            return await self.user_repository.create(
                max_user_id=max_user_id,
                display_name=display_name,
                username=event.sender_username,
            )

        values: dict[str, str | None] = {}
        if _is_generated_user_display_name(user.display_name) and event.sender_display_name:
            values["display_name"] = event.sender_display_name
        if not user.username and event.sender_username:
            values["username"] = event.sender_username
        if values:
            user = await self.user_repository.update(user, values=values)
        return user

    async def resolve_max_chat(
        self,
        event: NormalizedBotEvent,
        *,
        organization: Organization,
    ) -> Chat:
        max_chat_id = _required_external_id(event.chat_id, field_name="chat_id")
        internal_chat_id = parse_internal_uuid(max_chat_id)
        if internal_chat_id is not None:
            chat_by_internal_id = await self.chat_repository.get_chat(internal_chat_id)
            if chat_by_internal_id is not None:
                return chat_by_internal_id

        chat = await self.chat_repository.get_chat_by_max_chat_id(
            organization_id=organization.id,
            max_chat_id=max_chat_id,
        )
        chat_type = _safe_chat_type(event.chat_type)
        real_title = _normal_chat_title(event.chat_title)
        if real_title is None and _should_lookup_max_chat_title(chat=chat, chat_type=chat_type):
            real_title = self._lookup_max_chat_title(max_chat_id)
        title = _safe_chat_title(
            max_chat_id=max_chat_id,
            chat_type=event.chat_type,
            chat_title=real_title,
        )
        if chat is None:
            return await self.chat_repository.create_chat(
                organization_id=organization.id,
                max_chat_id=max_chat_id,
                title=title,
                type=chat_type,
                status=_initial_chat_status(chat_type),
                settings={"source": "max_webhook"},
            )

        values: dict[str, object] = {}
        if not chat.type:
            values["type"] = chat_type
        if real_title is not None and _is_generated_chat_title(chat.title) and real_title != chat.title:
            values["title"] = real_title
        if values:
            chat = await self.chat_repository.update_chat(chat, values=values)
        return chat

    def _lookup_max_chat_title(self, max_chat_id: str) -> str | None:
        if self.max_chat_info_client is None:
            return None
        try:
            chat_info = self.max_chat_info_client.get_chat_info(max_chat_id)
        except MaxApiError as exc:
            logger.warning(
                "MAX chat title lookup failed chat=%s reason=%s",
                _mask_external_id(max_chat_id),
                exc.__class__.__name__,
            )
            return None
        return _normal_chat_title(chat_info.get("title"))

    async def ensure_chat_member(self, *, chat: Chat, user: User) -> None:
        member = await self.chat_repository.get_member(chat_id=chat.id, user_id=user.id)
        if member is None:
            await self.chat_repository.create_member(
                chat_id=chat.id,
                user_id=user.id,
                role=ROLE_MEMBER,
                is_active=True,
            )
            return
        if not member.is_active:
            await self.chat_repository.update_member(member, values={"is_active": True})


def _required_external_id(value: str | None, *, field_name: str) -> str:
    if value is None or not value.strip():
        raise MaxIdentityResolverError(f"Поле {field_name} обязательно для MAX identity mapping.")
    return value.strip()


def _safe_user_display_name(
    *,
    max_user_id: str,
    sender_display_name: str | None,
    sender_username: str | None,
) -> str:
    if sender_display_name and sender_display_name.strip():
        return sender_display_name.strip()
    if sender_username and sender_username.strip():
        return sender_username.strip()
    return f"Пользователь #{_short_external_id(max_user_id)}"


def _safe_chat_title(
    *,
    max_chat_id: str,
    chat_type: str | None,
    chat_title: str | None = None,
) -> str:
    normalized_title = _normal_chat_title(chat_title)
    if normalized_title is not None:
        return normalized_title
    if chat_type == "dialog":
        return f"MAX dialog #{_short_external_id(max_chat_id)}"
    return f"MAX chat #{_short_external_id(max_chat_id)}"


def _safe_chat_type(chat_type: str | None) -> str:
    if chat_type == "dialog":
        return "max_dialog"
    if chat_type:
        return f"max_{chat_type}"[:50]
    return "max_chat"


def _initial_chat_status(chat_type: str) -> str:
    if chat_type == "max_dialog":
        return ChatConnectionStatus.active.value
    return ChatConnectionStatus.pending_approval.value


def _short_external_id(value: str) -> str:
    return value[-8:] if len(value) > 8 else value


def _mask_external_id(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}...{value[-3:]}"


def _is_generated_user_display_name(value: str) -> bool:
    return value.startswith("Пользователь #")


def _is_generated_chat_title(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        normalized.startswith("max chat #")
        or normalized.startswith("max dialog #")
        or normalized.startswith("max group #")
        or normalized in {"чат без названия", "личный чат", "групповой чат"}
        or normalized.startswith("mid.")
        or UUID_LIKE_RE.match(value.strip()) is not None
        or value.strip().lstrip("-").isdigit()
    )


UUID_LIKE_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _normal_chat_title(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or _is_generated_chat_title(normalized):
        return None
    return normalized


def _should_lookup_max_chat_title(*, chat: Chat | None, chat_type: str) -> bool:
    if chat_type == "max_dialog":
        return False
    if chat is None:
        return True
    return _is_generated_chat_title(chat.title)


def parse_internal_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
