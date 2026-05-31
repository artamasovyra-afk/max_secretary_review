"""add task templates

Revision ID: c3f2a4d9e810
Revises: b6e4d9a1c720
Create Date: 2026-05-21 01:40:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3f2a4d9e810"
down_revision: Union[str, None] = "b6e4d9a1c720"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_templates",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_type", sa.String(length=50), server_default="group_assignment", nullable=False),
        sa.Column("response_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("default_deadline_rule", sa.String(length=255), nullable=True),
        sa.Column("audience_type", sa.String(length=50), nullable=False),
        sa.Column("exclude_creator", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_templates_chat_id"), "task_templates", ["chat_id"])
    op.create_index(op.f("ix_task_templates_created_by_user_id"), "task_templates", ["created_by_user_id"])
    op.create_index(op.f("ix_task_templates_is_active"), "task_templates", ["is_active"])
    op.create_index(op.f("ix_task_templates_organization_id"), "task_templates", ["organization_id"])
    op.create_index(op.f("ix_task_templates_task_type"), "task_templates", ["task_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_task_templates_task_type"), table_name="task_templates")
    op.drop_index(op.f("ix_task_templates_organization_id"), table_name="task_templates")
    op.drop_index(op.f("ix_task_templates_is_active"), table_name="task_templates")
    op.drop_index(op.f("ix_task_templates_created_by_user_id"), table_name="task_templates")
    op.drop_index(op.f("ix_task_templates_chat_id"), table_name="task_templates")
    op.drop_table("task_templates")
