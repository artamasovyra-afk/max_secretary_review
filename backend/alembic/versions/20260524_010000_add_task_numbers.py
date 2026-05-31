"""add task numbers

Revision ID: c6d7e8f90123
Revises: b5c6d7e8f901
Create Date: 2026-05-24 01:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6d7e8f90123"
down_revision: Union[str, None] = "b5c6d7e8f901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("task_number", sa.Integer(), nullable=True))
    _backfill_task_numbers()
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.alter_column("task_number", existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_tasks_organization_task_number",
            ["organization_id", "task_number"],
        )
    op.create_index(op.f("ix_tasks_task_number"), "tasks", ["task_number"])


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_task_number"), table_name="tasks")
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("uq_tasks_organization_task_number", type_="unique")
        batch_op.drop_column("task_number")


def _backfill_task_numbers() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, organization_id
            FROM tasks
            ORDER BY organization_id ASC, created_at ASC, id ASC
            """
        )
    ).mappings()
    counters: dict[str, int] = {}
    for row in rows:
        organization_key = str(row["organization_id"])
        next_number = counters.get(organization_key, 0) + 1
        counters[organization_key] = next_number
        connection.execute(
            sa.text("UPDATE tasks SET task_number = :task_number WHERE id = :task_id"),
            {"task_number": next_number, "task_id": row["id"]},
        )
