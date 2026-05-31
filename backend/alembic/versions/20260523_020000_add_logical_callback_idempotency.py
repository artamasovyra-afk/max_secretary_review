"""add logical callback idempotency metadata

Revision ID: f3a4b5c6d7e8
Revises: f2a3b4c5d6e7
Create Date: 2026-05-23 02:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bot_callback_receipts",
        sa.Column("provider", sa.String(length=50), server_default="max", nullable=False),
    )
    op.add_column(
        "bot_callback_receipts",
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "bot_callback_receipts",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "bot_callback_receipts",
        sa.Column("action_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "bot_callback_receipts",
        sa.Column("payload_normalized", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "bot_callback_receipts",
        sa.Column("logical_key", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "bot_callback_receipts",
        sa.Column("logical_status", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "bot_callback_receipts",
        sa.Column("logical_window_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_bot_callback_receipts_provider"),
        "bot_callback_receipts",
        ["provider"],
    )
    op.create_index(
        op.f("ix_bot_callback_receipts_actor_user_id"),
        "bot_callback_receipts",
        ["actor_user_id"],
    )
    op.create_index(
        op.f("ix_bot_callback_receipts_task_id"),
        "bot_callback_receipts",
        ["task_id"],
    )
    op.create_index(
        op.f("ix_bot_callback_receipts_action_type"),
        "bot_callback_receipts",
        ["action_type"],
    )
    op.create_index(
        op.f("ix_bot_callback_receipts_logical_key"),
        "bot_callback_receipts",
        ["logical_key"],
    )
    op.create_index(
        op.f("ix_bot_callback_receipts_logical_status"),
        "bot_callback_receipts",
        ["logical_status"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_callback_receipts_logical_status"), table_name="bot_callback_receipts")
    op.drop_index(op.f("ix_bot_callback_receipts_logical_key"), table_name="bot_callback_receipts")
    op.drop_index(op.f("ix_bot_callback_receipts_action_type"), table_name="bot_callback_receipts")
    op.drop_index(op.f("ix_bot_callback_receipts_task_id"), table_name="bot_callback_receipts")
    op.drop_index(op.f("ix_bot_callback_receipts_actor_user_id"), table_name="bot_callback_receipts")
    op.drop_index(op.f("ix_bot_callback_receipts_provider"), table_name="bot_callback_receipts")
    op.drop_column("bot_callback_receipts", "logical_window_started_at")
    op.drop_column("bot_callback_receipts", "logical_status")
    op.drop_column("bot_callback_receipts", "logical_key")
    op.drop_column("bot_callback_receipts", "payload_normalized")
    op.drop_column("bot_callback_receipts", "action_type")
    op.drop_column("bot_callback_receipts", "task_id")
    op.drop_column("bot_callback_receipts", "actor_user_id")
    op.drop_column("bot_callback_receipts", "provider")
