from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.tasks.enums import (
    ScheduledTaskScheduleType,
    ScheduledTaskRunStatus,
    TaskAcceptanceDecision,
    TaskAssigneeStatus,
    TaskCompletionRule,
    TaskPriority,
    TaskResponseStatus,
    TaskStatus,
    TaskType,
)

if TYPE_CHECKING:
    from app.modules.chats.models import Chat
    from app.modules.integrations.models import BitrixTaskLink
    from app.modules.organizations.models import Organization
    from app.modules.users.models import User


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("organization_id", "task_number", name="uq_tasks_organization_task_number"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chat_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    task_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=TaskType.PERSONAL.value,
        server_default=TaskType.PERSONAL.value,
        index=True,
    )
    requires_individual_report: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    audience_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    creator_display_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    creator_role_snapshot: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_chat_title_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=TaskStatus.NEW.value, index=True)
    priority: Mapped[str] = mapped_column(String(50), nullable=False, default=TaskPriority.NORMAL.value)
    completion_rule: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=TaskCompletionRule.ANY_ASSIGNEE_RESPONSE.value,
    )
    external_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="tasks")
    chat: Mapped["Chat"] = relationship(back_populates="tasks")
    created_by_user: Mapped["User"] = relationship(back_populates="created_tasks", foreign_keys=[created_by_user_id])
    assignees: Mapped[list["TaskAssignee"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    observers: Mapped[list["TaskObserver"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    comments: Mapped[list["TaskComment"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    files: Mapped[list["TaskFile"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    responses: Mapped[list["TaskResponse"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    acceptances: Mapped[list["TaskAcceptance"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    reminder_rules: Mapped[list["TaskReminderRule"]] = relationship(back_populates="task")
    reminder_snoozes: Mapped[list["TaskReminderSnooze"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    status_history: Mapped[list["TaskStatusHistory"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    bitrix_task_links: Mapped[list["BitrixTaskLink"]] = relationship(back_populates="task")


class TaskTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_templates"

    organization_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chat_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=TaskType.GROUP_ASSIGNMENT.value,
        server_default=TaskType.GROUP_ASSIGNMENT.value,
        index=True,
    )
    response_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    default_deadline_rule: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    audience_type: Mapped[str] = mapped_column(String(50), nullable=False)
    exclude_creator: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )

    organization: Mapped["Organization"] = relationship(back_populates="task_templates")
    chat: Mapped["Chat"] = relationship(back_populates="task_templates")
    created_by_user: Mapped["User"] = relationship(back_populates="task_templates")
    scheduled_tasks: Mapped[list["ScheduledTask"]] = relationship(back_populates="template")


class ScheduledTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scheduled_tasks"

    template_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("task_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chat_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    schedule_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ScheduledTaskScheduleType.ONE_TIME.value,
        server_default=ScheduledTaskScheduleType.ONE_TIME.value,
        index=True,
    )
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    repeat_rule: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC", server_default="UTC")
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    template: Mapped["TaskTemplate"] = relationship(back_populates="scheduled_tasks")
    organization: Mapped["Organization"] = relationship(back_populates="scheduled_tasks")
    chat: Mapped["Chat"] = relationship(back_populates="scheduled_tasks")
    created_by_user: Mapped["User"] = relationship(back_populates="scheduled_tasks")
    runs: Mapped[list["ScheduledTaskRun"]] = relationship(
        back_populates="scheduled_task",
        cascade="all, delete-orphan",
    )


class ScheduledTaskRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scheduled_task_runs"
    __table_args__ = (
        UniqueConstraint(
            "scheduled_task_id",
            "planned_run_at",
            name="uq_scheduled_task_runs_task_planned_run",
        ),
    )

    scheduled_task_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("scheduled_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    planned_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ScheduledTaskRunStatus.STARTED.value,
        server_default=ScheduledTaskRunStatus.STARTED.value,
        index=True,
    )
    created_task_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scheduled_task: Mapped["ScheduledTask"] = relationship(back_populates="runs")
    created_task: Mapped[Optional["Task"]] = relationship()


class TaskAssignee(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_assignees"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_assignees_task_user"),)

    task_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=TaskAssigneeStatus.ASSIGNED.value,
    )
    response_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="assignees")
    user: Mapped["User"] = relationship(back_populates="task_assignments")


class TaskObserver(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_observers"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_observers_task_user"),)

    task_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task: Mapped["Task"] = relationship(back_populates="observers")
    user: Mapped["User"] = relationship(back_populates="task_observers")


class TaskComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_comments"

    task_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reply_to_comment_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("task_comments.id", ondelete="SET NULL"),
        nullable=True,
    )

    task: Mapped["Task"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship(back_populates="task_comments")
    reply_to_comment: Mapped[Optional["TaskComment"]] = relationship(remote_side="TaskComment.id")
    files: Mapped[list["TaskFile"]] = relationship(back_populates="comment")


class TaskFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_files"

    task_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    comment_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("task_comments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_storage_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    task: Mapped["Task"] = relationship(back_populates="files")
    comment: Mapped[Optional["TaskComment"]] = relationship(back_populates="files")
    uploaded_by_user: Mapped["User"] = relationship(back_populates="uploaded_files")


class TaskResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_responses"

    task_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=TaskResponseStatus.SUBMITTED.value,
    )

    task: Mapped["Task"] = relationship(back_populates="responses")
    user: Mapped["User"] = relationship(back_populates="task_responses")
    acceptances: Mapped[list["TaskAcceptance"]] = relationship(back_populates="response")


class TaskAcceptance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_acceptances"

    task_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    response_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("task_responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    accepted_by_user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=TaskAcceptanceDecision.ACCEPTED.value,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    task: Mapped["Task"] = relationship(back_populates="acceptances")
    response: Mapped["TaskResponse"] = relationship(back_populates="acceptances")
    accepted_by_user: Mapped["User"] = relationship(back_populates="task_acceptances")


class TaskReminderRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_reminder_rules"

    organization_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chat_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    task_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    reminder_type: Mapped[str] = mapped_column(String(50), nullable=False)
    offset_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    repeat_interval_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_repeats: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    organization: Mapped["Organization"] = relationship(back_populates="reminder_rules")
    chat: Mapped[Optional["Chat"]] = relationship(back_populates="reminder_rules")
    task: Mapped[Optional["Task"]] = relationship(back_populates="reminder_rules")


class TaskReminderSnooze(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "task_reminder_snoozes"

    task_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snoozed_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    task: Mapped["Task"] = relationship(back_populates="reminder_snoozes")
    user: Mapped["User"] = relationship()


class TaskStatusHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_status_history"

    task_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_user_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    task: Mapped["Task"] = relationship(back_populates="status_history")
    changed_by_user: Mapped[Optional["User"]] = relationship(back_populates="status_changes")


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    organization_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[Optional[UUID]] = mapped_column(PostgresUUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="audit_logs")
    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")
