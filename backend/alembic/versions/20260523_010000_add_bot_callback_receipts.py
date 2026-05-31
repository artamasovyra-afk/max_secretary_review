"""add bot callback receipts

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-23 01:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_callback_receipts",
        sa.Column("callback_id", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="processing", nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("callback_id"),
    )
    op.create_index(op.f("ix_bot_callback_receipts_callback_id"), "bot_callback_receipts", ["callback_id"])
    op.create_index(op.f("ix_bot_callback_receipts_status"), "bot_callback_receipts", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_callback_receipts_status"), table_name="bot_callback_receipts")
    op.drop_index(op.f("ix_bot_callback_receipts_callback_id"), table_name="bot_callback_receipts")
    op.drop_table("bot_callback_receipts")
