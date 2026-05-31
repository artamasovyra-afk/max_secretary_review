from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.tasks.enums import TaskStatus


class ReminderType(str, Enum):
    TASK_DUE_IN_1H = "task_due_in_1h"
    TASK_OVERDUE = "task_overdue"
    BEFORE_DEADLINE = "before_deadline"
    AT_DEADLINE = "at_deadline"
    AFTER_DEADLINE = "after_deadline"
    NO_RESPONSE_AFTER_DEADLINE = "no_response_after_deadline"
    WITHOUT_RESPONSE_AFTER_DEADLINE = "no_response_after_deadline"
    WAITING_ACCEPTANCE = "waiting_acceptance"
    DAILY_SUMMARY = "daily_summary"
    DAILY_MANAGER_SUMMARY = "daily_manager_summary"


class ReminderRuleCreate(BaseModel):
    reminder_type: ReminderType
    offset_minutes: Optional[int] = Field(default=None, ge=0)
    repeat_interval_minutes: Optional[int] = Field(default=None, ge=1)
    max_repeats: Optional[int] = Field(default=None, ge=1)
    is_active: bool = True


class ReminderRuleUpdate(BaseModel):
    reminder_type: Optional[ReminderType] = None
    offset_minutes: Optional[int] = Field(default=None, ge=0)
    repeat_interval_minutes: Optional[int] = Field(default=None, ge=1)
    max_repeats: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None

    @field_validator("reminder_type", "is_active")
    @classmethod
    def reject_required_field_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class ReminderRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    chat_id: Optional[UUID]
    task_id: Optional[UUID]
    reminder_type: ReminderType
    offset_minutes: Optional[int]
    repeat_interval_minutes: Optional[int]
    max_repeats: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ReminderTaskPayload(BaseModel):
    task_id: UUID
    organization_id: UUID
    chat_id: UUID
    task_number: Optional[int] = None
    title: str
    status: TaskStatus
    deadline_at: Optional[datetime] = None
    created_by_user_id: UUID
    assignee_ids: list[UUID] = Field(default_factory=list)
    observer_ids: list[UUID] = Field(default_factory=list)
    response_id: Optional[UUID] = None
    response_user_id: Optional[UUID] = None
    response_user_display_name: Optional[str] = None


class ReminderPayload(BaseModel):
    reminder_type: ReminderType
    generated_at: datetime
    tasks: list[ReminderTaskPayload] = Field(default_factory=list)


class DailySummaryPayload(BaseModel):
    user_id: UUID
    date: date
    generated_at: datetime
    my_tasks: list[ReminderTaskPayload] = Field(default_factory=list)
    created_by_me: list[ReminderTaskPayload] = Field(default_factory=list)
    observed_by_me: list[ReminderTaskPayload] = Field(default_factory=list)
    waiting_my_response: list[ReminderTaskPayload] = Field(default_factory=list)
    waiting_my_acceptance: list[ReminderTaskPayload] = Field(default_factory=list)
    overdue: list[ReminderTaskPayload] = Field(default_factory=list)
    today: list[ReminderTaskPayload] = Field(default_factory=list)
