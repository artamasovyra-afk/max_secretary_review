from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class BotCallbackReceipt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bot_callback_receipts"

    callback_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    payload: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="max", server_default="max", index=True)
    actor_user_id: Mapped[Optional[UUID]] = mapped_column(PostgresUUID(as_uuid=True), nullable=True, index=True)
    task_id: Mapped[Optional[UUID]] = mapped_column(PostgresUUID(as_uuid=True), nullable=True, index=True)
    action_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    payload_normalized: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    logical_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, index=True)
    logical_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    logical_window_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="processing",
        server_default="processing",
        index=True,
    )
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class BotPendingAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bot_pending_actions"

    action_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chat_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )
    completed_task_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    selected_assignee_user_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    picker_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cleanup_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    cleanup_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
