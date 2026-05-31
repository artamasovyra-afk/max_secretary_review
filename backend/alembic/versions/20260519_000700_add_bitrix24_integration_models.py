"""add bitrix24 integration models

Revision ID: b7c2a9e1d604
Revises: a88b8f143a40
Create Date: 2026-05-19 00:07:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c2a9e1d604"
down_revision: Union[str, None] = "a88b8f143a40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_accounts",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("auth_type", sa.String(length=50), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_integration_accounts_is_active"), "integration_accounts", ["is_active"], unique=False)
    op.create_index(
        op.f("ix_integration_accounts_organization_id"),
        "integration_accounts",
        ["organization_id"],
        unique=False,
    )
    op.create_index(op.f("ix_integration_accounts_provider"), "integration_accounts", ["provider"], unique=False)

    op.create_table(
        "bitrix_task_links",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("bitrix_portal_url", sa.Text(), nullable=True),
        sa.Column("bitrix_task_id", sa.String(length=255), nullable=True),
        sa.Column("sync_status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bitrix_task_links_bitrix_task_id"), "bitrix_task_links", ["bitrix_task_id"], unique=False)
    op.create_index(
        "uq_bitrix_task_links_active_task_id",
        "bitrix_task_links",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("sync_status != 'disabled'"),
    )
    op.create_index(
        op.f("ix_bitrix_task_links_organization_id"),
        "bitrix_task_links",
        ["organization_id"],
        unique=False,
    )
    op.create_index(op.f("ix_bitrix_task_links_sync_status"), "bitrix_task_links", ["sync_status"], unique=False)
    op.create_index(op.f("ix_bitrix_task_links_task_id"), "bitrix_task_links", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bitrix_task_links_task_id"), table_name="bitrix_task_links")
    op.drop_index(op.f("ix_bitrix_task_links_sync_status"), table_name="bitrix_task_links")
    op.drop_index(op.f("ix_bitrix_task_links_organization_id"), table_name="bitrix_task_links")
    op.drop_index("uq_bitrix_task_links_active_task_id", table_name="bitrix_task_links")
    op.drop_index(op.f("ix_bitrix_task_links_bitrix_task_id"), table_name="bitrix_task_links")
    op.drop_table("bitrix_task_links")
    op.drop_index(op.f("ix_integration_accounts_provider"), table_name="integration_accounts")
    op.drop_index(op.f("ix_integration_accounts_organization_id"), table_name="integration_accounts")
    op.drop_index(op.f("ix_integration_accounts_is_active"), table_name="integration_accounts")
    op.drop_table("integration_accounts")
