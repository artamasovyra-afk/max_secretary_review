from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.chats.models import Chat
    from app.modules.integrations.models import BitrixTaskLink, BitrixUserMapping, IntegrationAccount
    from app.modules.tasks.models import AuditLog, ScheduledTask, Task, TaskReminderRule, TaskTemplate


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    chats: Mapped[list["Chat"]] = relationship(back_populates="organization")
    tasks: Mapped[list["Task"]] = relationship(back_populates="organization")
    task_templates: Mapped[list["TaskTemplate"]] = relationship(back_populates="organization")
    scheduled_tasks: Mapped[list["ScheduledTask"]] = relationship(back_populates="organization")
    reminder_rules: Mapped[list["TaskReminderRule"]] = relationship(back_populates="organization")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="organization")
    integration_accounts: Mapped[list["IntegrationAccount"]] = relationship(back_populates="organization")
    bitrix_task_links: Mapped[list["BitrixTaskLink"]] = relationship(back_populates="organization")
    bitrix_user_mappings: Mapped[list["BitrixUserMapping"]] = relationship(back_populates="organization")
