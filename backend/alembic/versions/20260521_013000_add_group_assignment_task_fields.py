"""add group assignment task fields

Revision ID: b6e4d9a1c720
Revises: a4c8e1d2f930
Create Date: 2026-05-21 01:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6e4d9a1c720"
down_revision: Union[str, None] = "a4c8e1d2f930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("task_type", sa.String(length=50), server_default="personal", nullable=False),
    )
    op.add_column(
        "tasks",
        sa.Column("requires_individual_report", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("tasks", sa.Column("audience_snapshot", sa.JSON(), nullable=True))
    op.add_column("tasks", sa.Column("creator_display_name_snapshot", sa.String(length=255), nullable=True))
    op.add_column("tasks", sa.Column("creator_role_snapshot", sa.String(length=50), nullable=True))
    op.add_column("tasks", sa.Column("source_chat_title_snapshot", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_tasks_task_type"), "tasks", ["task_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_task_type"), table_name="tasks")
    op.drop_column("tasks", "source_chat_title_snapshot")
    op.drop_column("tasks", "creator_role_snapshot")
    op.drop_column("tasks", "creator_display_name_snapshot")
    op.drop_column("tasks", "audience_snapshot")
    op.drop_column("tasks", "requires_individual_report")
    op.drop_column("tasks", "task_type")
