from __future__ import annotations

from pathlib import Path


def test_manager_role_migration_maps_legacy_rows_to_chat_admin() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260525_020000_migrate_manager_role_to_chat_admin.py"
    )

    migration = migration_path.read_text()

    assert 'down_revision: Union[str, None] = "d7e8f9012345"' in migration
    assert "UPDATE chat_members SET role = 'chat_admin' WHERE role = 'manager'" in migration
