from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.organizations.models import Organization
    from app.modules.tasks.models import ScheduledTask, Task, TaskReminderRule, TaskTemplate
    from app.modules.users.models import User


class Chat(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chats"
    __table_args__ = (UniqueConstraint("organization_id", "max_chat_id", name="uq_chats_organization_max_chat"),)

    organization_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    max_chat_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="chats")
    members: Mapped[list["ChatMember"]] = relationship(back_populates="chat", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="chat")
    task_templates: Mapped[list["TaskTemplate"]] = relationship(back_populates="chat")
    scheduled_tasks: Mapped[list["ScheduledTask"]] = relationship(back_populates="chat")
    reminder_rules: Mapped[list["TaskReminderRule"]] = relationship(back_populates="chat")

    @property
    def display_title(self) -> str | None:
        if not self.settings:
            return None
        value = self.settings.get("display_title")
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None


class ChatMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_members"
    __table_args__ = (UniqueConstraint("chat_id", "user_id", name="uq_chat_members_chat_user"),)

    chat_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    chat: Mapped["Chat"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="chat_memberships")
