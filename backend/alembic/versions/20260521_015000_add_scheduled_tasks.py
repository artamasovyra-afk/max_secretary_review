"""add scheduled tasks

Revision ID: d9e8c7b6a540
Revises: c3f2a4d9e810
Create Date: 2026-05-21 01:50:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d9e8c7b6a540"
down_revision: Union[str, None] = "c3f2a4d9e810"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_type", sa.String(length=50), server_default="one_time", nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repeat_rule", sa.JSON(), nullable=True),
        sa.Column("timezone", sa.String(length=100), server_default="UTC", nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["task_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scheduled_tasks_chat_id"), "scheduled_tasks", ["chat_id"])
    op.create_index(op.f("ix_scheduled_tasks_created_by_user_id"), "scheduled_tasks", ["created_by_user_id"])
    op.create_index(op.f("ix_scheduled_tasks_is_active"), "scheduled_tasks", ["is_active"])
    op.create_index(op.f("ix_scheduled_tasks_next_run_at"), "scheduled_tasks", ["next_run_at"])
    op.create_index(op.f("ix_scheduled_tasks_organization_id"), "scheduled_tasks", ["organization_id"])
    op.create_index(op.f("ix_scheduled_tasks_schedule_type"), "scheduled_tasks", ["schedule_type"])
    op.create_index(op.f("ix_scheduled_tasks_template_id"), "scheduled_tasks", ["template_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_scheduled_tasks_template_id"), table_name="scheduled_tasks")
    op.drop_index(op.f("ix_scheduled_tasks_schedule_type"), table_name="scheduled_tasks")
    op.drop_index(op.f("ix_scheduled_tasks_organization_id"), table_name="scheduled_tasks")
    op.drop_index(op.f("ix_scheduled_tasks_next_run_at"), table_name="scheduled_tasks")
    op.drop_index(op.f("ix_scheduled_tasks_is_active"), table_name="scheduled_tasks")
    op.drop_index(op.f("ix_scheduled_tasks_created_by_user_id"), table_name="scheduled_tasks")
    op.drop_index(op.f("ix_scheduled_tasks_chat_id"), table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
