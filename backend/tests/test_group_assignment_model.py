from __future__ import annotations

from pathlib import Path

from app.db.base import Base, import_all_models
from app.modules.tasks.enums import TaskType


def test_group_assignment_task_columns() -> None:
    import_all_models()
    table = Base.metadata.tables["tasks"]

    assert table.columns["task_type"].nullable is False
    assert table.columns["task_type"].default.arg == TaskType.PERSONAL.value
    assert table.columns["task_type"].server_default.arg == TaskType.PERSONAL.value
    assert table.columns["requires_individual_report"].nullable is False
    assert table.columns["requires_individual_report"].default.arg is False
    assert table.columns["requires_individual_report"].server_default.arg == "false"
    assert table.columns["audience_snapshot"].nullable is True
    assert table.columns["creator_display_name_snapshot"].nullable is True
    assert table.columns["creator_role_snapshot"].nullable is True
    assert table.columns["source_chat_title_snapshot"].nullable is True


def test_group_assignment_task_type_index_exists() -> None:
    import_all_models()
    table = Base.metadata.tables["tasks"]

    indexes = {index.name: index for index in table.indexes}
    index = indexes["ix_tasks_task_type"]

    assert [column.name for column in index.columns] == ["task_type"]


def test_task_number_indexes_and_constraints_exist() -> None:
    import_all_models()
    table = Base.metadata.tables["tasks"]

    indexes = {index.name: index for index in table.indexes}
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert [column.name for column in indexes["ix_tasks_task_number"].columns] == ["task_number"]
    assert [column.name for column in constraints["uq_tasks_organization_task_number"].columns] == [
        "organization_id",
        "task_number",
    ]


def test_group_assignment_migration_backfills_old_tasks_as_personal() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260521_013000_add_group_assignment_task_fields.py"
    )
    migration = migration_path.read_text()

    assert 'down_revision: Union[str, None] = "a4c8e1d2f930"' in migration
    assert 'sa.Column("task_type", sa.String(length=50), server_default="personal", nullable=False)' in migration
    assert 'sa.Column("requires_individual_report", sa.Boolean(), server_default=sa.text("false"), nullable=False)' in migration
