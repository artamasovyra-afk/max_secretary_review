from __future__ import annotations

from pathlib import Path

from app.db.base import Base, import_all_models
from app.modules.tasks.enums import ScheduledTaskRunStatus, ScheduledTaskScheduleType


def test_scheduled_task_columns() -> None:
    import_all_models()
    table = Base.metadata.tables["scheduled_tasks"]

    assert table.columns["template_id"].nullable is False
    assert table.columns["organization_id"].nullable is False
    assert table.columns["chat_id"].nullable is False
    assert table.columns["created_by_user_id"].nullable is False
    assert table.columns["schedule_type"].nullable is False
    assert table.columns["schedule_type"].default.arg == ScheduledTaskScheduleType.ONE_TIME.value
    assert table.columns["schedule_type"].server_default.arg == ScheduledTaskScheduleType.ONE_TIME.value
    assert table.columns["scheduled_for"].nullable is True
    assert table.columns["repeat_rule"].nullable is True
    assert table.columns["timezone"].nullable is False
    assert table.columns["timezone"].default.arg == "UTC"
    assert table.columns["timezone"].server_default.arg == "UTC"
    assert table.columns["next_run_at"].nullable is False
    assert table.columns["last_run_at"].nullable is True
    assert table.columns["is_active"].nullable is False
    assert table.columns["last_error"].nullable is True


def test_scheduled_task_indexes_exist() -> None:
    import_all_models()
    indexes = {index.name: index for index in Base.metadata.tables["scheduled_tasks"].indexes}

    assert [column.name for column in indexes["ix_scheduled_tasks_template_id"].columns] == ["template_id"]
    assert [column.name for column in indexes["ix_scheduled_tasks_organization_id"].columns] == ["organization_id"]
    assert [column.name for column in indexes["ix_scheduled_tasks_chat_id"].columns] == ["chat_id"]
    assert [column.name for column in indexes["ix_scheduled_tasks_created_by_user_id"].columns] == [
        "created_by_user_id"
    ]
    assert [column.name for column in indexes["ix_scheduled_tasks_schedule_type"].columns] == ["schedule_type"]
    assert [column.name for column in indexes["ix_scheduled_tasks_next_run_at"].columns] == ["next_run_at"]
    assert [column.name for column in indexes["ix_scheduled_tasks_is_active"].columns] == ["is_active"]


def test_scheduled_task_migration_creates_table() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260521_015000_add_scheduled_tasks.py"
    )
    migration = migration_path.read_text()

    assert 'down_revision: Union[str, None] = "c3f2a4d9e810"' in migration
    assert '"scheduled_tasks"' in migration
    assert 'sa.Column("schedule_type", sa.String(length=50), server_default="one_time", nullable=False)' in migration
    assert 'sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False)' in migration


def test_scheduled_task_run_columns_and_constraints() -> None:
    import_all_models()
    table = Base.metadata.tables["scheduled_task_runs"]

    assert table.columns["scheduled_task_id"].nullable is False
    assert table.columns["planned_run_at"].nullable is False
    assert table.columns["status"].nullable is False
    assert table.columns["status"].default.arg == ScheduledTaskRunStatus.STARTED.value
    assert table.columns["status"].server_default.arg == ScheduledTaskRunStatus.STARTED.value
    assert table.columns["created_task_id"].nullable is True
    assert table.columns["started_at"].nullable is True
    assert table.columns["finished_at"].nullable is True
    assert table.columns["last_error"].nullable is True

    unique_constraints = {constraint.name: constraint for constraint in table.constraints}
    assert [column.name for column in unique_constraints["uq_scheduled_task_runs_task_planned_run"].columns] == [
        "scheduled_task_id",
        "planned_run_at",
    ]


def test_scheduled_task_run_indexes_exist() -> None:
    import_all_models()
    indexes = {index.name: index for index in Base.metadata.tables["scheduled_task_runs"].indexes}

    assert [column.name for column in indexes["ix_scheduled_task_runs_scheduled_task_id"].columns] == [
        "scheduled_task_id"
    ]
    assert [column.name for column in indexes["ix_scheduled_task_runs_planned_run_at"].columns] == ["planned_run_at"]
    assert [column.name for column in indexes["ix_scheduled_task_runs_status"].columns] == ["status"]
    assert [column.name for column in indexes["ix_scheduled_task_runs_created_task_id"].columns] == [
        "created_task_id"
    ]


def test_scheduled_task_run_migration_creates_table() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260521_020000_add_scheduled_task_runs.py"
    )
    migration = migration_path.read_text()

    assert 'down_revision: Union[str, None] = "d9e8c7b6a540"' in migration
    assert '"scheduled_task_runs"' in migration
    assert 'sa.Column("status", sa.String(length=50), server_default="started", nullable=False)' in migration
    assert 'name="uq_scheduled_task_runs_task_planned_run"' in migration
