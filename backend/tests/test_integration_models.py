from app.db.base import Base, import_all_models
from app.modules.integrations.enums import BitrixSyncStatus, BitrixUserMatchSource


def get_table(table_name: str):
    import_all_models()
    return Base.metadata.tables[table_name]


def test_integration_account_columns() -> None:
    table = get_table("integration_accounts")

    assert set(table.columns.keys()) >= {
        "id",
        "organization_id",
        "provider",
        "auth_type",
        "credentials_encrypted",
        "settings",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert "webhook_url_secret_ref" not in table.columns
    assert "base_url" not in table.columns
    assert table.columns["credentials_encrypted"].nullable is True
    assert table.columns["settings"].nullable is True
    assert table.columns["is_active"].default.arg is True


def test_bitrix_task_link_columns() -> None:
    table = get_table("bitrix_task_links")

    assert set(table.columns.keys()) >= {
        "id",
        "task_id",
        "organization_id",
        "bitrix_portal_url",
        "bitrix_task_id",
        "sync_status",
        "last_sync_at",
        "last_error",
        "created_at",
        "updated_at",
    }
    assert "integration_account_id" not in table.columns
    assert "bitrix_task_url" not in table.columns
    assert "last_sync_error" not in table.columns
    assert "last_synced_at" not in table.columns
    assert table.columns["bitrix_task_id"].nullable is True
    assert table.columns["sync_status"].default.arg == BitrixSyncStatus.PENDING.value


def test_bitrix_task_link_foreign_keys() -> None:
    table = get_table("bitrix_task_links")

    foreign_key_targets = {foreign_key.target_fullname for foreign_key in table.foreign_keys}

    assert "tasks.id" in foreign_key_targets
    assert "organizations.id" in foreign_key_targets


def test_bitrix_task_link_has_single_active_link_index() -> None:
    table = get_table("bitrix_task_links")
    indexes = {index.name: index for index in table.indexes}
    index = indexes["uq_bitrix_task_links_active_task_id"]

    assert index.unique is True
    assert [column.name for column in index.columns] == ["task_id"]
    assert str(index.dialect_options["postgresql"]["where"]) == "sync_status != 'disabled'"


def test_bitrix_user_mapping_columns() -> None:
    table = get_table("bitrix_user_mappings")

    assert set(table.columns.keys()) >= {
        "id",
        "organization_id",
        "user_id",
        "bitrix_user_id",
        "match_source",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert table.columns["bitrix_user_id"].nullable is False
    assert table.columns["bitrix_user_id"].type.length == 255
    assert table.columns["match_source"].default.arg == BitrixUserMatchSource.MANUAL.value
    assert table.columns["is_active"].default.arg is True


def test_bitrix_user_mapping_foreign_keys() -> None:
    table = get_table("bitrix_user_mappings")

    foreign_key_targets = {foreign_key.target_fullname for foreign_key in table.foreign_keys}

    assert "organizations.id" in foreign_key_targets
    assert "users.id" in foreign_key_targets


def test_bitrix_user_mapping_has_single_active_mapping_index() -> None:
    table = get_table("bitrix_user_mappings")
    indexes = {index.name: index for index in table.indexes}
    index = indexes["uq_bitrix_user_mappings_active_org_user"]

    assert index.unique is True
    assert [column.name for column in index.columns] == ["organization_id", "user_id"]
    assert str(index.dialect_options["postgresql"]["where"]) == "is_active"
