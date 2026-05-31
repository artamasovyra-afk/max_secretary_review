from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.chats.models import ChatMember
    from app.modules.integrations.models import BitrixUserMapping
    from app.modules.tasks.models import (
        AuditLog,
        ScheduledTask,
        Task,
        TaskAcceptance,
        TaskAssignee,
        TaskComment,
        TaskFile,
        TaskObserver,
        TaskResponse,
        TaskStatusHistory,
        TaskTemplate,
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    max_user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    chat_memberships: Mapped[list["ChatMember"]] = relationship(back_populates="user")
    created_tasks: Mapped[list["Task"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="Task.created_by_user_id",
    )
    task_assignments: Mapped[list["TaskAssignee"]] = relationship(back_populates="user")
    task_observers: Mapped[list["TaskObserver"]] = relationship(back_populates="user")
    task_comments: Mapped[list["TaskComment"]] = relationship(back_populates="user")
    uploaded_files: Mapped[list["TaskFile"]] = relationship(back_populates="uploaded_by_user")
    task_responses: Mapped[list["TaskResponse"]] = relationship(back_populates="user")
    task_templates: Mapped[list["TaskTemplate"]] = relationship(back_populates="created_by_user")
    scheduled_tasks: Mapped[list["ScheduledTask"]] = relationship(back_populates="created_by_user")
    task_acceptances: Mapped[list["TaskAcceptance"]] = relationship(back_populates="accepted_by_user")
    status_changes: Mapped[list["TaskStatusHistory"]] = relationship(back_populates="changed_by_user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    bitrix_user_mappings: Mapped[list["BitrixUserMapping"]] = relationship(back_populates="user")
