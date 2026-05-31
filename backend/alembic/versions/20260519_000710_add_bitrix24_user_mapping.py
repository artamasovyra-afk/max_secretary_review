"""add bitrix24 user mapping

Revision ID: c91e7a42b851
Revises: b7c2a9e1d604
Create Date: 2026-05-19 00:07:10.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c91e7a42b851"
down_revision: Union[str, None] = "b7c2a9e1d604"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bitrix_user_mappings",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("bitrix_user_id", sa.String(length=255), nullable=False),
        sa.Column("match_source", sa.String(length=50), server_default="manual", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bitrix_user_mappings_bitrix_user_id"),
        "bitrix_user_mappings",
        ["bitrix_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_bitrix_user_mappings_is_active"), "bitrix_user_mappings", ["is_active"], unique=False)
    op.create_index(
        op.f("ix_bitrix_user_mappings_organization_id"),
        "bitrix_user_mappings",
        ["organization_id"],
        unique=False,
    )
    op.create_index(op.f("ix_bitrix_user_mappings_user_id"), "bitrix_user_mappings", ["user_id"], unique=False)
    op.create_index(
        "uq_bitrix_user_mappings_active_org_user",
        "bitrix_user_mappings",
        ["organization_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_bitrix_user_mappings_active_org_user", table_name="bitrix_user_mappings")
    op.drop_index(op.f("ix_bitrix_user_mappings_user_id"), table_name="bitrix_user_mappings")
    op.drop_index(op.f("ix_bitrix_user_mappings_organization_id"), table_name="bitrix_user_mappings")
    op.drop_index(op.f("ix_bitrix_user_mappings_is_active"), table_name="bitrix_user_mappings")
    op.drop_index(op.f("ix_bitrix_user_mappings_bitrix_user_id"), table_name="bitrix_user_mappings")
    op.drop_table("bitrix_user_mappings")
