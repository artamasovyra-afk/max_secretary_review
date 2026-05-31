"""add reminder delivery type and picker cleanup

Revision ID: b5c6d7e8f901
Revises: a4b5c6d7e8f9
Create Date: 2026-05-23 04:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5c6d7e8f901"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notification_deliveries", sa.Column("reminder_type", sa.String(length=80), nullable=True))
    op.create_index(
        op.f("ix_notification_deliveries_reminder_type"),
        "notification_deliveries",
        ["reminder_type"],
    )
    op.add_column("bot_pending_actions", sa.Column("picker_message_id", sa.String(length=255), nullable=True))
    op.add_column("bot_pending_actions", sa.Column("cleanup_status", sa.String(length=50), nullable=True))
    op.add_column("bot_pending_actions", sa.Column("cleanup_error", sa.Text(), nullable=True))
    op.create_index(op.f("ix_bot_pending_actions_cleanup_status"), "bot_pending_actions", ["cleanup_status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_pending_actions_cleanup_status"), table_name="bot_pending_actions")
    op.drop_column("bot_pending_actions", "cleanup_error")
    op.drop_column("bot_pending_actions", "cleanup_status")
    op.drop_column("bot_pending_actions", "picker_message_id")
    op.drop_index(op.f("ix_notification_deliveries_reminder_type"), table_name="notification_deliveries")
    op.drop_column("notification_deliveries", "reminder_type")
