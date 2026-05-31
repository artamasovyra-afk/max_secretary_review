from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.tasks.enums import ScheduledTaskScheduleType


class ScheduledTaskCreate(BaseModel):
    template_id: UUID
    organization_id: UUID
    chat_id: UUID
    created_by_user_id: UUID
    schedule_type: ScheduledTaskScheduleType = ScheduledTaskScheduleType.ONE_TIME
    scheduled_for: Optional[datetime] = None
    repeat_rule: Optional[dict[str, Any]] = None
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    next_run_at: datetime
    is_active: bool = True


class ScheduledTaskUpdate(BaseModel):
    template_id: Optional[UUID] = None
    organization_id: Optional[UUID] = None
    chat_id: Optional[UUID] = None
    created_by_user_id: Optional[UUID] = None
    schedule_type: Optional[ScheduledTaskScheduleType] = None
    scheduled_for: Optional[datetime] = None
    repeat_rule: Optional[dict[str, Any]] = None
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=100)
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    is_active: Optional[bool] = None
    last_error: Optional[str] = None

    @field_validator(
        "template_id",
        "organization_id",
        "chat_id",
        "created_by_user_id",
        "schedule_type",
        "timezone",
        "next_run_at",
        "is_active",
    )
    @classmethod
    def reject_required_field_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class ScheduledTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    organization_id: UUID
    chat_id: UUID
    created_by_user_id: UUID
    schedule_type: ScheduledTaskScheduleType
    scheduled_for: Optional[datetime]
    repeat_rule: Optional[dict[str, Any]]
    timezone: str
    next_run_at: datetime
    last_run_at: Optional[datetime]
    is_active: bool
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime
