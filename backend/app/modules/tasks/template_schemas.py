from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.tasks.enums import TaskTemplateAudienceType, TaskType


class TaskTemplateCreate(BaseModel):
    organization_id: UUID
    chat_id: UUID
    created_by_user_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    task_type: TaskType = TaskType.GROUP_ASSIGNMENT
    response_required: bool = True
    default_deadline_rule: Optional[str] = Field(default=None, max_length=255)
    audience_type: TaskTemplateAudienceType = TaskTemplateAudienceType.ALL_CHAT_MEMBERS
    exclude_creator: bool = True
    settings: Optional[dict[str, Any]] = None
    is_active: bool = True


class TaskTemplateUpdate(BaseModel):
    organization_id: Optional[UUID] = None
    chat_id: Optional[UUID] = None
    created_by_user_id: Optional[UUID] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    task_type: Optional[TaskType] = None
    response_required: Optional[bool] = None
    default_deadline_rule: Optional[str] = Field(default=None, max_length=255)
    audience_type: Optional[TaskTemplateAudienceType] = None
    exclude_creator: Optional[bool] = None
    settings: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None

    @field_validator(
        "organization_id",
        "chat_id",
        "created_by_user_id",
        "title",
        "task_type",
        "response_required",
        "audience_type",
        "exclude_creator",
        "is_active",
    )
    @classmethod
    def reject_required_field_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class TaskTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    chat_id: UUID
    created_by_user_id: UUID
    title: str
    description: Optional[str]
    task_type: TaskType
    response_required: bool
    default_deadline_rule: Optional[str]
    audience_type: TaskTemplateAudienceType
    exclude_creator: bool
    settings: Optional[dict[str, Any]]
    is_active: bool
    created_at: datetime
    updated_at: datetime
