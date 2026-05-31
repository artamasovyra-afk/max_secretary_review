"""add chat notification deliveries

Revision ID: d7e8f9012345
Revises: c6d7e8f90123
Create Date: 2026-05-25 01:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f9012345"
down_revision: Union[str, None] = "c6d7e8f90123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notification_deliveries", sa.Column("chat_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_notification_deliveries_chat_id_chats",
        "notification_deliveries",
        "chats",
        ["chat_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_notification_deliveries_chat_id"), "notification_deliveries", ["chat_id"])
    op.alter_column("notification_deliveries", "user_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column("notification_deliveries", "user_id", existing_type=sa.UUID(), nullable=False)
    op.drop_index(op.f("ix_notification_deliveries_chat_id"), table_name="notification_deliveries")
    op.drop_constraint("fk_notification_deliveries_chat_id_chats", "notification_deliveries", type_="foreignkey")
    op.drop_column("notification_deliveries", "chat_id")
