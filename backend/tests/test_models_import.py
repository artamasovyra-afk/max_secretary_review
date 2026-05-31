from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import configure_mappers

from app.db.base import Base, import_all_models
from app.modules.bot.models import BotCallbackReceipt, BotPendingAction
from app.modules.chats.models import Chat, ChatMember
from app.modules.integrations.models import BitrixTaskLink, BitrixUserMapping, IntegrationAccount
from app.modules.notifications.models import NotificationDelivery
from app.modules.organizations.models import Organization
from app.modules.tasks.models import (
    AuditLog,
    ScheduledTask,
    Task,
    TaskAcceptance,
    TaskAssignee,
    TaskComment,
    TaskFile,
    TaskObserver,
    TaskReminderRule,
    TaskResponse,
    TaskStatusHistory,
    TaskTemplate,
)
from app.modules.users.models import User


def test_mvp_models_import() -> None:
    assert Organization
    assert User
    assert Chat
    assert ChatMember
    assert Task
    assert TaskAssignee
    assert TaskObserver
    assert TaskComment
    assert TaskFile
    assert TaskResponse
    assert TaskAcceptance
    assert TaskReminderRule
    assert TaskTemplate
    assert ScheduledTask
    assert TaskStatusHistory
    assert AuditLog
    assert IntegrationAccount
    assert BitrixTaskLink
    assert BitrixUserMapping
    assert NotificationDelivery
    assert BotCallbackReceipt
    assert BotPendingAction


def test_mvp_model_tables_are_registered() -> None:
    import_all_models()

    assert set(Base.metadata.tables) >= {
        "organizations",
        "users",
        "chats",
        "chat_members",
        "tasks",
        "task_assignees",
        "task_observers",
        "task_comments",
        "task_files",
        "task_responses",
        "task_acceptances",
        "task_reminder_rules",
        "task_templates",
        "scheduled_tasks",
        "task_status_history",
        "audit_logs",
        "integration_accounts",
        "bitrix_task_links",
        "bitrix_user_mappings",
        "notification_deliveries",
        "bot_callback_receipts",
        "bot_pending_actions",
    }


def test_task_model_uses_expected_relationship_tables() -> None:
    import_all_models()
    task_columns = Base.metadata.tables["tasks"].columns

    assert "organization_id" in task_columns
    assert "chat_id" in task_columns
    assert "task_number" in task_columns
    assert "task_type" in task_columns
    assert "requires_individual_report" in task_columns
    assert "audience_snapshot" in task_columns
    assert "creator_display_name_snapshot" in task_columns
    assert "creator_role_snapshot" in task_columns
    assert "source_chat_title_snapshot" in task_columns
    assert "responsible_user_id" not in task_columns
    assert "user_id" in Base.metadata.tables["task_assignees"].columns
    assert "user_id" in Base.metadata.tables["task_observers"].columns


def test_models_use_uuid_primary_keys() -> None:
    import_all_models()

    for table in Base.metadata.tables.values():
        id_column = table.columns["id"]
        assert id_column.primary_key
        assert isinstance(id_column.type, PostgresUUID)


def test_model_relationships_configure() -> None:
    import_all_models()

    configure_mappers()
