from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.chats.schemas import ChatConnectionStatus, ChatMemberRole


class SuperAdminLoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class SuperAdminSessionRead(BaseModel):
    authenticated: bool
    login: str
    session_expires_at: datetime | None = None


class SuperAdminLogoutRead(BaseModel):
    status: str


class SuperAdminChatRead(BaseModel):
    id: UUID
    display_title: str
    display_title_source: Literal["manual", "real", "fallback"] = "fallback"
    status: ChatConnectionStatus
    type: str
    deadline_reminders_enabled: bool = False
    members_count: int
    chat_admins_count: int
    max_admins_count: int | None = None
    created_at: datetime
    updated_at: datetime


class SuperAdminChatStatusUpdate(BaseModel):
    status: ChatConnectionStatus


class SuperAdminChatSettingsUpdate(BaseModel):
    deadline_reminders_enabled: bool


class SuperAdminChatMemberRead(BaseModel):
    id: UUID
    user_id: UUID
    display_name: str
    username: str | None = None
    role_in_dyak: ChatMemberRole
    is_active: bool
    is_max_chat_admin: bool | None = None
    has_max_user_id: bool
    updated_at: datetime


class SuperAdminChatMemberRoleUpdate(BaseModel):
    role: Literal["member", "chat_admin"]
    allow_remove_last_admin: bool = False

    @field_validator("role")
    @classmethod
    def reject_super_admin_role(cls, value: str) -> str:
        if value == "super_admin":
            raise ValueError("super_admin cannot be assigned as a chat member role")
        return value


class SuperAdminChatDisplayTitleUpdate(BaseModel):
    display_title: str | None = Field(default=None, max_length=255)

    @field_validator("display_title")
    @classmethod
    def normalize_display_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class SuperAdminMaxAdminSyncRead(BaseModel):
    checked_members_count: int
    max_admins_count: int
    matched_admins_count: int
    unknown_count: int
    checked_at: datetime


class SuperAdminMaxChatInfoSyncRead(BaseModel):
    title_updated: bool
    title_source: Literal["max_api", "manual", "fallback"]
    display_title: str
