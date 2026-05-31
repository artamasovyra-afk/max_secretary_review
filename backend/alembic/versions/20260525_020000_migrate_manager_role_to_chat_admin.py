"""migrate manager chat members to chat admin

Revision ID: e8f901234567
Revises: d7e8f9012345
Create Date: 2026-05-25 02:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e8f901234567"
down_revision: Union[str, None] = "d7e8f9012345"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE chat_members SET role = 'chat_admin' WHERE role = 'manager'")


def downgrade() -> None:
    # The upgrade intentionally preserves existing privileges. A safe downgrade
    # cannot distinguish migrated legacy managers from native chat admins.
    pass
