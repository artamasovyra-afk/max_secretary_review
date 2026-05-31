from __future__ import annotations

from pathlib import Path

from app.db.base import Base, import_all_models
from app.modules.tasks.enums import TaskTemplateAudienceType, TaskType


def test_task_template_columns() -> None:
    import_all_models()
    table = Base.metadata.tables["task_templates"]

    assert table.columns["organization_id"].nullable is False
    assert table.columns["chat_id"].nullable is False
    assert table.columns["created_by_user_id"].nullable is False
    assert table.columns["title"].nullable is False
    assert table.columns["description"].nullable is True
    assert table.columns["task_type"].nullable is False
    assert table.columns["task_type"].default.arg == TaskType.GROUP_ASSIGNMENT.value
    assert table.columns["task_type"].server_default.arg == TaskType.GROUP_ASSIGNMENT.value
    assert table.columns["response_required"].nullable is False
    assert table.columns["response_required"].default.arg is True
    assert table.columns["response_required"].server_default.arg == "true"
    assert table.columns["default_deadline_rule"].nullable is True
    assert table.columns["audience_type"].nullable is False
    assert table.columns["exclude_creator"].nullable is False
    assert table.columns["settings"].nullable is True
    assert table.columns["is_active"].nullable is False


def test_task_template_indexes_exist() -> None:
    import_all_models()
    indexes = {index.name: index for index in Base.metadata.tables["task_templates"].indexes}

    assert [column.name for column in indexes["ix_task_templates_organization_id"].columns] == ["organization_id"]
    assert [column.name for column in indexes["ix_task_templates_chat_id"].columns] == ["chat_id"]
    assert [column.name for column in indexes["ix_task_templates_created_by_user_id"].columns] == [
        "created_by_user_id"
    ]
    assert [column.name for column in indexes["ix_task_templates_task_type"].columns] == ["task_type"]
    assert [column.name for column in indexes["ix_task_templates_is_active"].columns] == ["is_active"]


def test_task_template_migration_creates_table() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260521_014000_add_task_templates.py"
    )
    migration = migration_path.read_text()

    assert 'down_revision: Union[str, None] = "b6e4d9a1c720"' in migration
    assert '"task_templates"' in migration
    assert 'sa.Column("task_type", sa.String(length=50), server_default="group_assignment", nullable=False)' in migration
    assert 'sa.Column("response_required", sa.Boolean(), server_default=sa.text("true"), nullable=False)' in migration
    assert TaskTemplateAudienceType.ALL_CHAT_MEMBERS.value == "all_chat_members"
