from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatStatus(BaseModel):
    status: str
    module: str


class ChatMemberRole(str, Enum):
    member = "member"
    chat_admin = "chat_admin"
    super_admin = "super_admin"


class ChatConnectionStatus(str, Enum):
    pending_approval = "pending_approval"
    active = "active"
    rejected = "rejected"
    suspended = "suspended"


class ChatCreate(BaseModel):
    organization_id: UUID
    max_chat_id: Optional[str] = Field(default=None, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=50)
    status: ChatConnectionStatus = ChatConnectionStatus.active
    settings: Optional[dict[str, Any]] = None


class ChatUpdate(BaseModel):
    organization_id: Optional[UUID] = None
    max_chat_id: Optional[str] = Field(default=None, max_length=255)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    status: Optional[ChatConnectionStatus] = None
    settings: Optional[dict[str, Any]] = None
    display_title: Optional[str] = Field(default=None, max_length=255)

    @field_validator("organization_id", "title", "type", "status")
    @classmethod
    def reject_required_field_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value

    @field_validator("display_title")
    @classmethod
    def normalize_display_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ChatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    max_chat_id: Optional[str]
    title: str
    type: str
    status: ChatConnectionStatus = ChatConnectionStatus.active
    settings: Optional[dict[str, Any]]
    display_title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ChatMemberCreate(BaseModel):
    user_id: UUID
    role: ChatMemberRole = ChatMemberRole.member
    is_active: bool = True


class ChatMemberUpdate(BaseModel):
    role: Optional[ChatMemberRole] = None
    is_active: Optional[bool] = None

    @field_validator("role", "is_active")
    @classmethod
    def reject_member_field_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class ChatMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_id: UUID
    user_id: UUID
    role: ChatMemberRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
