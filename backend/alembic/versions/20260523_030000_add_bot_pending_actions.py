"""add bot pending actions

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-05-23 03:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_pending_actions",
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_message_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_context", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("completed_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("selected_assignee_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completed_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selected_assignee_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bot_pending_actions_action_type"), "bot_pending_actions", ["action_type"])
    op.create_index(op.f("ix_bot_pending_actions_actor_user_id"), "bot_pending_actions", ["actor_user_id"])
    op.create_index(op.f("ix_bot_pending_actions_chat_id"), "bot_pending_actions", ["chat_id"])
    op.create_index(op.f("ix_bot_pending_actions_completed_task_id"), "bot_pending_actions", ["completed_task_id"])
    op.create_index(op.f("ix_bot_pending_actions_expires_at"), "bot_pending_actions", ["expires_at"])
    op.create_index(
        op.f("ix_bot_pending_actions_selected_assignee_user_id"),
        "bot_pending_actions",
        ["selected_assignee_user_id"],
    )
    op.create_index(op.f("ix_bot_pending_actions_status"), "bot_pending_actions", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_pending_actions_status"), table_name="bot_pending_actions")
    op.drop_index(op.f("ix_bot_pending_actions_selected_assignee_user_id"), table_name="bot_pending_actions")
    op.drop_index(op.f("ix_bot_pending_actions_expires_at"), table_name="bot_pending_actions")
    op.drop_index(op.f("ix_bot_pending_actions_completed_task_id"), table_name="bot_pending_actions")
    op.drop_index(op.f("ix_bot_pending_actions_chat_id"), table_name="bot_pending_actions")
    op.drop_index(op.f("ix_bot_pending_actions_actor_user_id"), table_name="bot_pending_actions")
    op.drop_index(op.f("ix_bot_pending_actions_action_type"), table_name="bot_pending_actions")
    op.drop_table("bot_pending_actions")
