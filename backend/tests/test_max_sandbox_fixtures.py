from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.modules.bot.service import normalize_max_event

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "max"


def _load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURES_DIR / name).open(encoding="utf-8") as fixture_file:
        payload = json.load(fixture_file)
    assert isinstance(payload, dict)
    return payload


def test_max_sandbox_fixture_set_is_complete() -> None:
    fixture_names = {path.name for path in FIXTURES_DIR.glob("*.json")}

    assert fixture_names == {
        "message_text.json",
        "message_reply_task.json",
        "message_reply_link_dialog.json",
        "message_reply_link_group.json",
        "callback_task_start.json",
        "callback_task_confirm.json",
        "callback_task_snooze.json",
        "message_callback_real.json",
        "open_app_button_example.json",
    }


@pytest.mark.parametrize(
    "fixture_name",
    [
        "message_text.json",
        "message_reply_task.json",
        "message_reply_link_dialog.json",
        "message_reply_link_group.json",
        "callback_task_start.json",
        "callback_task_confirm.json",
        "callback_task_snooze.json",
        "message_callback_real.json",
        "open_app_button_example.json",
    ],
)
def test_max_sandbox_fixtures_pass_through_normalizer(fixture_name: str) -> None:
    event = normalize_max_event(_load_fixture(fixture_name))

    assert event.source == "max"


def test_message_text_fixture_normalizes_as_text_message() -> None:
    event = normalize_max_event(_load_fixture("message_text.json"))

    assert event.ignored is False
    assert event.chat_id == "mock-chat-001"
    assert event.user_id == "mock-user-001"
    assert event.message_id == "mock-message-001"
    assert event.text == "/задачи"
    assert event.timestamp == "2026-05-21T10:00:00Z"
    assert event.chat_type == "group"
    assert event.chat_title == "Mock MAX Group"
    assert event.sender_display_name == "Mock User"
    assert event.sender_username == "mock_user"


def test_message_reply_task_fixture_preserves_reply_metadata() -> None:
    event = normalize_max_event(_load_fixture("message_reply_task.json"))

    assert event.ignored is False
    assert event.chat_id == "mock-chat-001"
    assert event.user_id == "mock-user-002"
    assert event.message_id == "mock-message-003"
    assert event.text == "/задача"
    assert event.reply_to_message_id == "mock-message-002"
    assert event.reply_to_text == "Иван, подготовь отчет до пятницы"
    assert event.reply_to_author_id == "mock-user-003"
    assert event.reply_to_author_display_name == "Mock Author"


@pytest.mark.parametrize(
    ("fixture_name", "chat_id", "source_message_id", "source_text"),
    [
        (
            "message_reply_link_dialog.json",
            "mock-chat-dialog",
            "mock-message-source-dialog",
            "Проверить доступ завтра в 15:00",
        ),
        (
            "message_reply_link_group.json",
            "mock-chat-group",
            "mock-message-source-group",
            "Иван, подготовь отчет до пятницы",
        ),
    ],
)
def test_real_like_reply_link_fixtures_map_reply_metadata(
    fixture_name: str,
    chat_id: str,
    source_message_id: str,
    source_text: str,
) -> None:
    event = normalize_max_event(_load_fixture(fixture_name))

    assert event.ignored is False
    assert event.chat_id == chat_id
    assert event.user_id == "mock-user-command"
    assert event.text == "/задача"
    assert event.reply_to_message_id == source_message_id
    assert event.reply_to_text == source_text
    assert event.reply_to_author_id == "mock-user-source"
    assert event.reply_to_author_display_name == "Mock Author"


@pytest.mark.parametrize(
    "fixture_name",
    [
        "callback_task_start.json",
        "callback_task_confirm.json",
        "callback_task_snooze.json",
    ],
)
def test_callback_fixtures_are_ignored_until_callback_mapping_exists(fixture_name: str) -> None:
    event = normalize_max_event(_load_fixture(fixture_name))

    assert event.ignored is True
    assert event.raw_update_type == "callback_query"
    assert event.ignore_reason == "Event ignored: unsupported MAX event type or non-text message."


def test_real_callback_fixture_maps_callback_metadata() -> None:
    event = normalize_max_event(_load_fixture("message_callback_real.json"))

    assert event.source == "max"
    assert event.ignored is False
    assert event.raw_update_type == "message_callback"
    assert event.callback_id == "mock-callback-real-001"
    assert event.payload == "task:start:11111111-1111-4111-8111-111111111111"
    assert event.user_id == "mock-user-callback"
    assert event.chat_id == "mock-chat-callback"
    assert event.chat_type == "dialog"
    assert event.message_id == "mock-message-callback-source"
    assert event.message_text == "Тест callback-кнопки Дьяк"
    assert event.sender_display_name == "Mock Actor"


def test_open_app_button_fixture_ignores_unknown_button_payload_safely() -> None:
    event = normalize_max_event(_load_fixture("open_app_button_example.json"))

    assert event.ignored is False
    assert event.chat_id == "mock-chat-001"
    assert event.text == "Открыть задачу"
