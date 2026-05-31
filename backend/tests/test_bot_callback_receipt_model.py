from __future__ import annotations

from app.modules.bot.models import BotCallbackReceipt, BotPendingAction
from app.modules.bot.repository import BotCallbackReceiptRepository, BotPendingActionRepository


def test_bot_callback_receipt_model_shape() -> None:
    table = BotCallbackReceipt.__table__

    assert table.name == "bot_callback_receipts"
    assert "callback_id" in table.columns
    assert "payload" in table.columns
    assert "provider" in table.columns
    assert "actor_user_id" in table.columns
    assert "task_id" in table.columns
    assert "action_type" in table.columns
    assert "payload_normalized" in table.columns
    assert "logical_key" in table.columns
    assert "logical_status" in table.columns
    assert "logical_window_started_at" in table.columns
    assert "status" in table.columns
    assert "response_text" in table.columns
    assert "last_error" in table.columns
    assert table.columns["callback_id"].unique is True


def test_bot_pending_action_model_shape() -> None:
    table = BotPendingAction.__table__

    assert table.name == "bot_pending_actions"
    assert "action_type" in table.columns
    assert "actor_user_id" in table.columns
    assert "chat_id" in table.columns
    assert "source_message_id" in table.columns
    assert "title" in table.columns
    assert "source_text" in table.columns
    assert "description" in table.columns
    assert "deadline_at" in table.columns
    assert "reply_context" in table.columns
    assert "expires_at" in table.columns
    assert "status" in table.columns
    assert "completed_task_id" in table.columns
    assert "selected_assignee_user_id" in table.columns
    assert "picker_message_id" in table.columns
    assert "cleanup_status" in table.columns
    assert "cleanup_error" in table.columns


def test_callback_receipt_repository_exposes_receipt_methods() -> None:
    assert hasattr(BotCallbackReceiptRepository, "mark_succeeded")
    assert hasattr(BotCallbackReceiptRepository, "mark_failed")
    assert hasattr(BotCallbackReceiptRepository, "find_recent_logical_duplicate")
    assert not hasattr(BotPendingActionRepository, "mark_succeeded")
