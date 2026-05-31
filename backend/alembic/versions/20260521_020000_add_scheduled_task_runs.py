"""add scheduled task runs

Revision ID: e1f2a3b4c5d6
Revises: d9e8c7b6a540
Create Date: 2026-05-21 02:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d9e8c7b6a540"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_task_runs",
        sa.Column("scheduled_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("planned_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="started", nullable=False),
        sa.Column("created_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scheduled_task_id"], ["scheduled_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scheduled_task_id",
            "planned_run_at",
            name="uq_scheduled_task_runs_task_planned_run",
        ),
    )
    op.create_index(op.f("ix_scheduled_task_runs_created_task_id"), "scheduled_task_runs", ["created_task_id"])
    op.create_index(op.f("ix_scheduled_task_runs_planned_run_at"), "scheduled_task_runs", ["planned_run_at"])
    op.create_index(op.f("ix_scheduled_task_runs_scheduled_task_id"), "scheduled_task_runs", ["scheduled_task_id"])
    op.create_index(op.f("ix_scheduled_task_runs_status"), "scheduled_task_runs", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_scheduled_task_runs_status"), table_name="scheduled_task_runs")
    op.drop_index(op.f("ix_scheduled_task_runs_scheduled_task_id"), table_name="scheduled_task_runs")
    op.drop_index(op.f("ix_scheduled_task_runs_planned_run_at"), table_name="scheduled_task_runs")
    op.drop_index(op.f("ix_scheduled_task_runs_created_task_id"), table_name="scheduled_task_runs")
    op.drop_table("scheduled_task_runs")
