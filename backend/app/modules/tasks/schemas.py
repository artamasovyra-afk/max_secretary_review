from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.modules.tasks.enums import (
    TaskAcceptanceDecision,
    TaskAssigneeStatus,
    TaskCompletionRule,
    TaskPriority,
    TaskResponseStatus,
    TaskStatus as TaskLifecycleStatus,
    TaskType,
)
from app.modules.tasks.task_numbering import format_task_ref, normalize_task_ref


class TaskStatus(BaseModel):
    status: str
    module: str


class TaskCreate(BaseModel):
    organization_id: UUID
    chat_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    source_message_id: Optional[str] = Field(default=None, max_length=255)
    created_by_user_id: UUID
    deadline_at: Optional[datetime] = None
    priority: TaskPriority = TaskPriority.NORMAL
    completion_rule: TaskCompletionRule = TaskCompletionRule.ANY_ASSIGNEE_RESPONSE
    assignee_ids: list[UUID] = Field(default_factory=list)
    observer_ids: list[UUID] = Field(default_factory=list)

    @field_validator("assignee_ids", "observer_ids")
    @classmethod
    def validate_unique_user_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("user ids must be unique")
        return value


class TaskGroupAssignmentCreate(BaseModel):
    organization_id: UUID
    chat_id: UUID
    created_by_user_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    deadline_at: Optional[datetime] = None
    assignee_ids: Optional[list[UUID]] = None
    exclude_creator: bool = True
    response_required: bool = True

    @field_validator("assignee_ids")
    @classmethod
    def deduplicate_assignee_ids(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is None:
            return None
        return list(dict.fromkeys(value))


class TaskGroupAssignmentCreateRead(BaseModel):
    task_id: UUID
    task_number: int
    task_ref: str
    total_assignees: int
    creator_display_name: Optional[str] = None
    creator_role: Optional[str] = None


class TaskGroupReportUserRead(BaseModel):
    user_id: UUID
    display_name: str


class TaskGroupReportCreatorRead(BaseModel):
    user_id: UUID
    display_name: str
    role: Optional[str] = None


class TaskGroupReportChatRead(BaseModel):
    chat_id: UUID
    title: str


class TaskGroupReportItemRead(BaseModel):
    user: TaskGroupReportUserRead
    status: TaskAssigneeStatus
    responded_at: Optional[datetime] = None
    response_text: Optional[str] = None


class TaskGroupReportRead(BaseModel):
    task_id: UUID
    task_number: int
    task_ref: str
    title: str
    creator: TaskGroupReportCreatorRead
    chat: TaskGroupReportChatRead
    total: int
    responded: int
    pending: int
    overdue: int
    items: list[TaskGroupReportItemRead]


class TaskListScope(str, Enum):
    ALL = "all"
    ASSIGNED_TO_ME = "assigned_to_me"
    CREATED_BY_ME = "created_by_me"
    OBSERVED_BY_ME = "observed_by_me"
    AWAITING_REPORT = "awaiting_report"
    AWAITING_ACCEPTANCE = "awaiting_acceptance"


class TaskParticipantRole(str, Enum):
    ASSIGNEE = "assignee"
    CREATOR = "creator"


class TaskQuickStatus(str, Enum):
    NEW = "new"
    AWAITING_REPORT = "awaiting_report"
    AWAITING_ACCEPTANCE = "awaiting_acceptance"
    OVERDUE = "overdue"


class TaskListFilters(BaseModel):
    organization_id: Optional[UUID] = None
    chat_id: Optional[UUID] = None
    status: Optional[TaskLifecycleStatus] = None
    task_type: Optional[TaskType] = None
    scope: TaskListScope = TaskListScope.ALL
    quick_status: Optional[TaskQuickStatus] = None
    viewer_user_id: Optional[UUID] = None
    search: Optional[str] = None
    task_number: Optional[int] = None
    participant_role: Optional[TaskParticipantRole] = None
    participant_user_id: Optional[UUID] = None
    created_by_user_id: Optional[UUID] = None
    assignee_id: Optional[UUID] = None
    observer_id: Optional[UUID] = None
    overdue: Optional[bool] = None
    due_today: Optional[bool] = None
    now: Optional[datetime] = None
    today_from: Optional[datetime] = None
    today_to: Optional[datetime] = None
    deadline_from: Optional[datetime] = None
    deadline_to: Optional[datetime] = None

    @computed_field
    @property
    def search_task_number(self) -> int | None:
        return normalize_task_ref(self.search)


class TaskInboxSummaryFilters(BaseModel):
    user_id: UUID
    organization_id: Optional[UUID] = None
    chat_id: Optional[UUID] = None
    status: Optional[TaskLifecycleStatus] = None
    deadline_from: Optional[datetime] = None
    deadline_to: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    deadline_at: Optional[datetime] = None
    priority: Optional[TaskPriority] = None
    completion_rule: Optional[TaskCompletionRule] = None
    status: Optional[TaskLifecycleStatus] = None

    @field_validator("title", "priority", "completion_rule", "status")
    @classmethod
    def reject_required_field_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class TaskParticipantCreate(BaseModel):
    user_id: UUID


class TaskCommentCreate(BaseModel):
    user_id: UUID
    text: str = Field(min_length=1)
    reply_to_comment_id: Optional[UUID] = None


class TaskFileCreate(BaseModel):
    uploaded_by_user_id: UUID
    comment_id: Optional[UUID] = None
    file_name: str = Field(min_length=1, max_length=255)
    file_url: Optional[str] = None
    file_storage_key: Optional[str] = Field(default=None, max_length=500)
    mime_type: Optional[str] = Field(default=None, max_length=255)
    size_bytes: Optional[int] = Field(default=None, ge=0)


class TaskResponseCreate(BaseModel):
    user_id: UUID
    text: Optional[str] = None
    source_message_id: Optional[str] = Field(default=None, max_length=255)


class TaskAcceptanceCreate(BaseModel):
    accepted_by_user_id: UUID
    comment: Optional[str] = None


class TaskAssigneeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    user_id: UUID
    status: TaskAssigneeStatus
    response_required: bool
    responded_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class TaskObserverRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class TaskCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    user_id: UUID
    text: str
    reply_to_comment_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


class TaskFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    comment_id: Optional[UUID]
    uploaded_by_user_id: UUID
    file_name: str
    file_url: Optional[str]
    file_storage_key: Optional[str]
    mime_type: Optional[str]
    size_bytes: Optional[int]
    created_at: datetime


class TaskResponseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    user_id: UUID
    text: Optional[str]
    source_message_id: Optional[str]
    status: TaskResponseStatus
    created_at: datetime
    updated_at: datetime


class TaskAcceptanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    response_id: UUID
    accepted_by_user_id: UUID
    decision: TaskAcceptanceDecision
    comment: Optional[str]
    created_at: datetime


class TaskStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    old_status: Optional[TaskLifecycleStatus]
    new_status: TaskLifecycleStatus
    changed_by_user_id: Optional[UUID]
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    chat_id: UUID
    task_number: int
    task_type: TaskType = TaskType.PERSONAL
    requires_individual_report: bool = False
    audience_snapshot: Optional[dict[str, Any]] = None
    title: str
    description: Optional[str]
    created_by_user_id: UUID
    creator_display_name_snapshot: Optional[str] = None
    creator_role_snapshot: Optional[str] = None
    source_chat_title_snapshot: Optional[str] = None
    deadline_at: Optional[datetime]
    status: TaskLifecycleStatus
    priority: TaskPriority
    completion_rule: TaskCompletionRule
    submitted_at: Optional[datetime]
    completed_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    assignees: list[TaskAssigneeRead]
    observers: list[TaskObserverRead]

    @computed_field
    @property
    def task_ref(self) -> str:
        return format_task_ref(self.task_number)


class TaskInboxSummaryRead(BaseModel):
    my_tasks: list[TaskRead] = Field(default_factory=list)
    created_by_me: list[TaskRead] = Field(default_factory=list)
    observed_by_me: list[TaskRead] = Field(default_factory=list)
    new: list[TaskRead] = Field(default_factory=list)
    waiting_my_response: list[TaskRead] = Field(default_factory=list)
    waiting_my_acceptance: list[TaskRead] = Field(default_factory=list)
    overdue: list[TaskRead] = Field(default_factory=list)
    today: list[TaskRead] = Field(default_factory=list)

    @computed_field
    @property
    def today_count(self) -> int:
        return len(self.today)

    @computed_field
    @property
    def new_count(self) -> int:
        return len(self.new)

    @computed_field
    @property
    def overdue_count(self) -> int:
        return len(self.overdue)

    @computed_field
    @property
    def awaiting_report_count(self) -> int:
        return len(self.waiting_my_response)

    @computed_field
    @property
    def awaiting_acceptance_count(self) -> int:
        return len(self.waiting_my_acceptance)


class TaskDetailRead(TaskRead):
    comments: list[TaskCommentRead]
    files: list[TaskFileRead]
    responses: list[TaskResponseRead]
    status_history: list[TaskStatusHistoryRead]
