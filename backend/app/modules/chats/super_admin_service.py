from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
import logging
from typing import Protocol
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.models import Chat, ChatMember
from app.modules.chats.repository import ChatRepository
from app.modules.chats.schemas import ChatConnectionStatus
from app.modules.chats.super_admin_schemas import (
    SuperAdminChatDisplayTitleUpdate,
    SuperAdminChatMemberRead,
    SuperAdminChatMemberRoleUpdate,
    SuperAdminChatRead,
    SuperAdminChatSettingsUpdate,
    SuperAdminMaxChatInfoSyncRead,
    SuperAdminMaxAdminSyncRead,
    SuperAdminChatStatusUpdate,
)
from app.modules.integrations.max.exceptions import MaxApiConfigurationError, MaxApiError

logger = logging.getLogger(__name__)

MAX_ADMIN_USER_IDS_KEY = "max_chat_admin_user_ids"
MAX_ADMIN_CHECKED_AT_KEY = "max_chat_admin_checked_at"
DEADLINE_REMINDERS_ENABLED_KEY = "deadline_reminders_enabled"


class MaxAdminClient(Protocol):
    def get_chat_admins(self, chat_id: str) -> list[dict[str, str | None]]:
        """Return normalized MAX chat admins for one chat."""


class MaxChatInfoClient(Protocol):
    def get_chat_info(self, chat_id: str) -> dict[str, str | None]:
        """Return normalized MAX chat info for one chat."""


class SuperAdminChatService:
    def __init__(self, repository: ChatRepository, session: AsyncSession) -> None:
        self.repository = repository
        self.session = session

    async def list_chats(
        self,
        *,
        status_filter: ChatConnectionStatus | None = None,
    ) -> list[SuperAdminChatRead]:
        chats = await self.repository.list_chats(status=status_filter.value if status_filter else None)
        return [await self._chat_read(chat) for chat in chats]

    async def list_members(self, chat_id: UUID) -> list[SuperAdminChatMemberRead]:
        await self._get_chat(chat_id)
        members = await self.repository.list_members(chat_id)
        return [self._member_read(member) for member in members]

    async def update_status(
        self,
        *,
        chat_id: UUID,
        payload: SuperAdminChatStatusUpdate,
        actor_login: str,
    ) -> SuperAdminChatRead:
        chat = await self._get_chat(chat_id)
        old_status = str(getattr(chat, "status", "active") or "active")
        chat = await self.repository.update_chat(chat, values={"status": payload.status.value})
        await self.repository.create_audit_log(
            organization_id=chat.organization_id,
            entity_type="chat",
            entity_id=chat.id,
            action="chat.status_changed",
            payload={
                "actor": actor_login,
                "old_status": old_status,
                "new_status": payload.status.value,
            },
        )
        logger.info(
            "super admin changed chat status actor=%s chat=%s old=%s new=%s",
            actor_login,
            _mask_uuid(chat.id),
            old_status,
            payload.status.value,
        )
        await self.session.commit()
        await self.session.refresh(chat)
        return await self._chat_read(chat)

    async def update_display_title(
        self,
        *,
        chat_id: UUID,
        payload: SuperAdminChatDisplayTitleUpdate,
        actor_login: str,
    ) -> SuperAdminChatRead:
        chat = await self._get_chat(chat_id)
        settings = dict(chat.settings or {})
        old_present = bool(chat.display_title)
        if payload.display_title is None:
            settings.pop("display_title", None)
        else:
            settings["display_title"] = payload.display_title
        chat = await self.repository.update_chat(chat, values={"settings": settings})
        await self.repository.create_audit_log(
            organization_id=chat.organization_id,
            entity_type="chat",
            entity_id=chat.id,
            action="chat.display_title_changed",
            payload={
                "actor": actor_login,
                "old_present": old_present,
                "new_present": bool(payload.display_title),
            },
        )
        logger.info(
            "super admin changed chat display title actor=%s chat=%s old_present=%s new_present=%s",
            actor_login,
            _mask_uuid(chat.id),
            old_present,
            bool(payload.display_title),
        )
        await self.session.commit()
        await self.session.refresh(chat)
        return await self._chat_read(chat)

    async def update_settings(
        self,
        *,
        chat_id: UUID,
        payload: SuperAdminChatSettingsUpdate,
        actor_login: str,
    ) -> SuperAdminChatRead:
        chat = await self._get_chat(chat_id)
        chat_status = str(getattr(chat, "status", "active") or "active")
        if chat_status != ChatConnectionStatus.active.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deadline reminders can be changed only for active chats",
            )
        settings = dict(chat.settings or {})
        old_enabled = _deadline_reminders_enabled(chat)
        settings[DEADLINE_REMINDERS_ENABLED_KEY] = payload.deadline_reminders_enabled
        chat = await self.repository.update_chat(chat, values={"settings": settings})
        await self.repository.create_audit_log(
            organization_id=chat.organization_id,
            entity_type="chat",
            entity_id=chat.id,
            action="chat.settings_changed",
            payload={
                "actor": actor_login,
                "deadline_reminders_old": old_enabled,
                "deadline_reminders_new": payload.deadline_reminders_enabled,
            },
        )
        logger.info(
            "super admin changed chat settings actor=%s chat=%s deadline_reminders_old=%s deadline_reminders_new=%s",
            actor_login,
            _mask_uuid(chat.id),
            old_enabled,
            payload.deadline_reminders_enabled,
        )
        await self.session.commit()
        await self.session.refresh(chat)
        return await self._chat_read(chat)

    async def update_member_role(
        self,
        *,
        chat_id: UUID,
        user_id: UUID,
        payload: SuperAdminChatMemberRoleUpdate,
        actor_login: str,
    ) -> SuperAdminChatMemberRead:
        chat = await self._get_chat(chat_id)
        member = await self.repository.get_member(chat_id=chat_id, user_id=user_id)
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat member not found")
        old_role = str(member.role)
        new_role = payload.role
        if old_role == "chat_admin" and new_role == "member":
            active_chat_admins = await self.repository.count_active_chat_admins(chat_id)
            if active_chat_admins <= 1 and not payload.allow_remove_last_admin:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot remove the last chat admin without confirmation",
                )
        member = await self.repository.update_member(member, values={"role": new_role})
        await self.repository.create_audit_log(
            organization_id=chat.organization_id,
            entity_type="chat_member",
            entity_id=member.id,
            action="chat_member.role_changed",
            payload={
                "actor": actor_login,
                "old_role": old_role,
                "new_role": new_role,
                "chat": _mask_uuid(chat.id),
                "member": _mask_uuid(member.id),
            },
        )
        logger.info(
            "super admin changed chat member role actor=%s chat=%s member=%s old=%s new=%s",
            actor_login,
            _mask_uuid(chat.id),
            _mask_uuid(member.id),
            old_role,
            new_role,
        )
        await self.session.commit()
        await self.session.refresh(member)
        return self._member_read(member)

    async def sync_max_admins(
        self,
        *,
        chat_id: UUID,
        actor_login: str,
        max_client: MaxAdminClient,
    ) -> SuperAdminMaxAdminSyncRead:
        chat = await self._get_chat(chat_id)
        if not chat.max_chat_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Chat has no MAX id for admin sync")

        try:
            admins = max_client.get_chat_admins(chat.max_chat_id)
        except MaxApiConfigurationError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MAX API is not configured") from exc
        except MaxApiError as exc:
            logger.warning(
                "MAX chat admin sync failed actor=%s chat=%s reason=%s",
                actor_login,
                _mask_uuid(chat.id),
                exc.__class__.__name__,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to sync MAX admin roles") from exc

        checked_at = datetime.now(tz=UTC)
        max_admin_ids = _normalize_max_user_ids(item.get("max_user_id") for item in admins)
        members = await self.repository.list_members(chat.id)
        matched_admins_count = 0
        unknown_count = 0
        for member in members:
            max_user_id = getattr(member.user, "max_user_id", None) if member.user is not None else None
            if not max_user_id:
                unknown_count += 1
                continue
            if str(max_user_id) in max_admin_ids:
                matched_admins_count += 1

        settings = dict(chat.settings or {})
        settings[MAX_ADMIN_USER_IDS_KEY] = sorted(max_admin_ids)
        settings[MAX_ADMIN_CHECKED_AT_KEY] = checked_at.isoformat()
        chat = await self.repository.update_chat(chat, values={"settings": settings})
        await self.repository.create_audit_log(
            organization_id=chat.organization_id,
            entity_type="chat",
            entity_id=chat.id,
            action="chat.max_admins_synced",
            payload={
                "actor": actor_login,
                "checked_members_count": len(members),
                "max_admins_count": len(max_admin_ids),
                "matched_admins_count": matched_admins_count,
                "unknown_count": unknown_count,
            },
        )
        logger.info(
            "super admin synced MAX chat admins actor=%s chat=%s checked=%s max_admins=%s matched=%s unknown=%s",
            actor_login,
            _mask_uuid(chat.id),
            len(members),
            len(max_admin_ids),
            matched_admins_count,
            unknown_count,
        )
        await self.session.commit()
        return SuperAdminMaxAdminSyncRead(
            checked_members_count=len(members),
            max_admins_count=len(max_admin_ids),
            matched_admins_count=matched_admins_count,
            unknown_count=unknown_count,
            checked_at=checked_at,
        )

    async def sync_max_chat_info(
        self,
        *,
        chat_id: UUID,
        actor_login: str,
        max_client: MaxChatInfoClient,
    ) -> SuperAdminMaxChatInfoSyncRead:
        chat = await self._get_chat(chat_id)
        if not chat.max_chat_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Chat has no MAX id for title sync")

        try:
            chat_info = max_client.get_chat_info(chat.max_chat_id)
        except MaxApiConfigurationError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MAX API is not configured") from exc
        except MaxApiError as exc:
            logger.warning(
                "MAX chat info sync failed actor=%s chat=%s reason=%s",
                actor_login,
                _mask_uuid(chat.id),
                exc.__class__.__name__,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to sync MAX chat info") from exc

        title = _normal_chat_title(chat_info.get("title"))
        title_updated = False
        if title and _is_generated_chat_title(chat.title):
            chat = await self.repository.update_chat(chat, values={"title": title})
            title_updated = True
            await self.repository.create_audit_log(
                organization_id=chat.organization_id,
                entity_type="chat",
                entity_id=chat.id,
                action="chat.max_info_synced",
                payload={
                    "actor": actor_login,
                    "title_updated": True,
                    "title_len": len(title),
                },
            )
            logger.info(
                "super admin synced MAX chat title actor=%s chat=%s title_updated=true title_len=%s",
                actor_login,
                _mask_uuid(chat.id),
                len(title),
            )
            await self.session.commit()
            await self.session.refresh(chat)
        elif title:
            await self.repository.create_audit_log(
                organization_id=chat.organization_id,
                entity_type="chat",
                entity_id=chat.id,
                action="chat.max_info_synced",
                payload={
                    "actor": actor_login,
                    "title_updated": False,
                    "title_len": len(title),
                },
            )
            await self.session.commit()

        display_title, display_title_source = _chat_display_title_with_source(chat)
        title_source = "manual" if display_title_source == "manual" else "max_api" if title else "fallback"
        return SuperAdminMaxChatInfoSyncRead(
            title_updated=title_updated,
            title_source=title_source,
            display_title=display_title,
        )

    async def _get_chat(self, chat_id: UUID) -> Chat:
        chat = await self.repository.get_chat(chat_id)
        if chat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
        return chat

    async def _chat_read(self, chat: Chat) -> SuperAdminChatRead:
        display_title, display_title_source = _chat_display_title_with_source(chat)
        return SuperAdminChatRead(
            id=chat.id,
            display_title=display_title,
            display_title_source=display_title_source,
            status=ChatConnectionStatus(str(getattr(chat, "status", "active") or "active")),
            type=chat.type,
            deadline_reminders_enabled=_deadline_reminders_enabled(chat),
            members_count=await self.repository.count_active_members(chat.id),
            chat_admins_count=await self.repository.count_active_chat_admins(chat.id),
            max_admins_count=_max_admin_count(chat),
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )

    def _member_read(self, member: ChatMember) -> SuperAdminChatMemberRead:
        user = member.user
        return SuperAdminChatMemberRead(
            id=member.id,
            user_id=member.user_id,
            display_name=getattr(user, "display_name", "Пользователь") if user is not None else "Пользователь",
            username=getattr(user, "username", None) if user is not None else None,
            role_in_dyak=member.role,
            is_active=member.is_active,
            is_max_chat_admin=_max_admin_marker(member),
            has_max_user_id=bool(getattr(user, "max_user_id", None)) if user is not None else False,
            updated_at=member.updated_at,
        )


def _chat_display_title(chat: Chat) -> str:
    return _chat_display_title_with_source(chat)[0]


def _chat_display_title_with_source(chat: Chat) -> tuple[str, str]:
    display_title = getattr(chat, "display_title", None)
    if not display_title:
        settings = getattr(chat, "settings", None)
        if isinstance(settings, dict):
            value = settings.get("display_title")
            if isinstance(value, str) and value.strip():
                display_title = value.strip()
    if display_title:
        return display_title, "manual"
    title = (chat.title or "").strip()
    if title and not _is_generated_chat_title(title):
        return title, "real"
    if "dialog" in (chat.type or "").lower():
        return "Личный чат", "fallback"
    return "Чат без названия", "fallback"


def _is_generated_chat_title(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        normalized.startswith("max chat #")
        or normalized.startswith("max dialog #")
        or normalized.startswith("max group #")
        or normalized in {"чат без названия", "личный чат", "групповой чат"}
        or _looks_like_identifier(value)
    )


def _normal_chat_title(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or _is_generated_chat_title(normalized):
        return None
    return normalized


def _looks_like_identifier(value: str) -> bool:
    normalized = value.strip()
    if normalized.startswith("mid."):
        return True
    return normalized.lstrip("-").isdigit()


def _max_admin_marker(member: ChatMember) -> bool | None:
    settings = getattr(member.chat, "settings", None)
    if not isinstance(settings, dict):
        return None
    values = settings.get(MAX_ADMIN_USER_IDS_KEY)
    if not isinstance(values, list):
        return None
    user = member.user
    max_user_id = getattr(user, "max_user_id", None) if user is not None else None
    if not max_user_id:
        return None
    return max_user_id in {str(value) for value in values}


def _max_admin_count(chat: Chat) -> int | None:
    settings = getattr(chat, "settings", None)
    if not isinstance(settings, dict):
        return None
    values = settings.get(MAX_ADMIN_USER_IDS_KEY)
    if not isinstance(values, list):
        return None
    return len(_normalize_max_user_ids(values))


def _deadline_reminders_enabled(chat: Chat) -> bool:
    settings = getattr(chat, "settings", None)
    if not isinstance(settings, dict):
        return False
    return settings.get(DEADLINE_REMINDERS_ENABLED_KEY) is True


def _normalize_max_user_ids(values: Iterable[object] | None) -> set[str]:
    if not values:
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def _mask_uuid(value: UUID) -> str:
    text = str(value)
    return f"{text[:8]}...{text[-4:]}"
