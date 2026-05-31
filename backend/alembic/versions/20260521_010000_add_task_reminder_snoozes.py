"""add task reminder snoozes

Revision ID: f3d7c2a9b810
Revises: c91e7a42b851
Create Date: 2026-05-21 01:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3d7c2a9b810"
down_revision: Union[str, None] = "c91e7a42b851"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_reminder_snoozes",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_reminder_snoozes_snoozed_until"), "task_reminder_snoozes", ["snoozed_until"])
    op.create_index(op.f("ix_task_reminder_snoozes_task_id"), "task_reminder_snoozes", ["task_id"])
    op.create_index(op.f("ix_task_reminder_snoozes_user_id"), "task_reminder_snoozes", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_task_reminder_snoozes_user_id"), table_name="task_reminder_snoozes")
    op.drop_index(op.f("ix_task_reminder_snoozes_task_id"), table_name="task_reminder_snoozes")
    op.drop_index(op.f("ix_task_reminder_snoozes_snoozed_until"), table_name="task_reminder_snoozes")
    op.drop_table("task_reminder_snoozes")
