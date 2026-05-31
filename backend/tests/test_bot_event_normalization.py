from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.bot.service import normalize_max_event


def test_normalize_max_event_keeps_normalized_test_event() -> None:
    event = normalize_max_event(
        {
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-1",
            "text": "/задачи",
        }
    )

    assert event.source == "max"
    assert event.ignored is False
    assert event.chat_id == "chat-1"
    assert event.user_id == "user-1"
    assert event.message_id == "message-1"
    assert event.text == "/задачи"
    assert event.timestamp is None
    assert event.chat_type is None
    assert event.chat_title is None
    assert event.sender_display_name is None
    assert event.sender_username is None
    assert event.reply_to_message_id is None
    assert event.reply_to_text is None
    assert event.reply_to_author_id is None
    assert event.reply_to_author_display_name is None
    assert event.raw_update_type is None


def test_normalize_max_event_keeps_reply_metadata_from_normalized_event() -> None:
    event = normalize_max_event(
        {
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-2",
            "text": "/задача",
            "timestamp": "2026-05-21T10:00:00Z",
            "chat_type": "group",
            "chat_title": "Тестовый чат",
            "sender_display_name": "Иван Петров",
            "sender_username": "ivan",
            "reply_to_message_id": "message-1",
            "reply_to_text": "Иван, подготовь отчет до пятницы",
            "reply_to_author_id": "user-2",
            "reply_to_author_display_name": "Мария",
            "raw_update_type": "message_created",
        }
    )

    assert event.source == "max"
    assert event.ignored is False
    assert event.chat_id == "chat-1"
    assert event.user_id == "user-1"
    assert event.message_id == "message-2"
    assert event.text == "/задача"
    assert event.timestamp == "2026-05-21T10:00:00Z"
    assert event.chat_type == "group"
    assert event.chat_title == "Тестовый чат"
    assert event.sender_display_name == "Иван Петров"
    assert event.sender_username == "ivan"
    assert event.reply_to_message_id == "message-1"
    assert event.reply_to_text == "Иван, подготовь отчет до пятницы"
    assert event.reply_to_author_id == "user-2"
    assert event.reply_to_author_display_name == "Мария"
    assert event.raw_update_type == "message_created"


def test_normalize_max_event_sets_missing_reply_fields_to_none() -> None:
    event = normalize_max_event(
        {
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-1",
            "text": "/задачи",
        }
    )

    assert event.reply_to_message_id is None
    assert event.reply_to_text is None
    assert event.reply_to_author_id is None
    assert event.reply_to_author_display_name is None


def test_normalize_max_event_ignores_unknown_fields_safely() -> None:
    event = normalize_max_event(
        {
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-1",
            "text": "/задачи",
            "unexpected": {"nested": "value"},
        }
    )

    assert event.ignored is False
    assert event.chat_id == "chat-1"
    assert not hasattr(event, "unexpected")


def test_normalize_max_event_maps_raw_max_like_message() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_created",
            "message": {
                "recipient": {"chat_id": "chat-1"},
                "chat": {"id": "chat-1", "type": "group", "title": "Отдел кадров"},
                "sender": {"user_id": "user-1"},
                "body": {
                    "mid": "message-1",
                    "text": "/задачи",
                },
            },
        }
    )

    assert event.source == "max"
    assert event.ignored is False
    assert event.chat_id == "chat-1"
    assert event.user_id == "user-1"
    assert event.message_id == "message-1"
    assert event.text == "/задачи"
    assert event.chat_type == "group"
    assert event.chat_title == "Отдел кадров"
    assert event.raw_update_type == "message_created"


def test_normalize_max_event_maps_chat_title_from_recipient() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_created",
            "message": {
                "recipient": {
                    "chat_id": "chat-1",
                    "chat_type": "chat",
                    "title": "Тест Дьяк",
                },
                "sender": {"user_id": "user-1"},
                "body": {
                    "mid": "message-1",
                    "text": "/задачи",
                },
            },
        }
    )

    assert event.chat_title == "Тест Дьяк"


def test_normalize_max_event_maps_chat_title_from_body_chat() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_created",
            "message": {
                "recipient": {
                    "chat_id": "chat-1",
                    "chat_type": "chat",
                },
                "sender": {"user_id": "user-1"},
                "body": {
                    "mid": "message-1",
                    "text": "/задачи",
                    "chat": {"name": "Тестовые комменты"},
                },
            },
        }
    )

    assert event.chat_title == "Тестовые комменты"


def test_normalize_max_event_maps_chat_title_from_top_level_body_chat() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_created",
            "body": {
                "chat": {"title": "Тест Дьяк"},
            },
            "message": {
                "recipient": {
                    "chat_id": "chat-1",
                    "chat_type": "chat",
                },
                "sender": {"user_id": "user-1"},
                "body": {
                    "mid": "message-1",
                    "text": "/задачи",
                },
            },
        }
    )

    assert event.chat_title == "Тест Дьяк"


def test_normalize_max_event_skips_generated_title_candidate() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_created",
            "message": {
                "recipient": {
                    "chat_id": "chat-1",
                    "chat_type": "chat",
                    "title": "Тест Дьяк",
                },
                "chat": {
                    "id": "chat-1",
                    "type": "chat",
                    "title": "MAX chat #12345678",
                },
                "sender": {"user_id": "user-1"},
                "body": {
                    "mid": "message-1",
                    "text": "/задачи",
                },
            },
        }
    )

    assert event.chat_title == "Тест Дьяк"


def test_normalize_max_event_uses_real_name_when_same_context_title_is_generated() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_created",
            "message": {
                "recipient": {
                    "chat_id": "chat-1",
                    "chat_type": "chat",
                },
                "chat": {
                    "id": "chat-1",
                    "type": "chat",
                    "title": "MAX chat #12345678",
                    "name": "Тест Дьяк",
                },
                "sender": {"user_id": "user-1"},
                "body": {
                    "mid": "message-1",
                    "text": "/задачи",
                },
            },
        }
    )

    assert event.chat_title == "Тест Дьяк"


def test_normalize_max_event_maps_structured_user_mention_markup() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_created",
            "message": {
                "recipient": {"chat_id": "mock-chat-mention", "chat_type": "chat"},
                "sender": {"user_id": "mock-user-author", "name": "Mock Author"},
                "body": {
                    "mid": "mock-message-mention",
                    "text": "@Иван тест выбора исполнителя",
                    "markup": [
                        {
                            "type": "user_mention",
                            "from": 0,
                            "length": 5,
                            "user_id": "mock-user-mentioned",
                            "user": {
                                "user_id": "mock-user-mentioned",
                                "name": "Иван",
                                "username": "ivan",
                            },
                        }
                    ],
                },
            },
        }
    )

    assert event.ignored is False
    assert event.chat_id == "mock-chat-mention"
    assert event.user_id == "mock-user-author"
    assert event.text == "@Иван тест выбора исполнителя"
    assert len(event.mentions) == 1
    mention = event.mentions[0]
    assert mention.raw_text == "@Иван"
    assert mention.external_user_id == "mock-user-mentioned"
    assert mention.username == "ivan"
    assert mention.display_name == "Иван"
    assert mention.start == 0
    assert mention.length == 5


def test_normalize_max_event_maps_real_like_dialog_reply_link() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_created",
            "timestamp": 1779439001000,
            "user_locale": "ru",
            "message": {
                "recipient": {
                    "chat_id": "mock-chat-dialog",
                    "chat_type": "dialog",
                    "user_id": "mock-user-command",
                },
                "sender": {
                    "user_id": "mock-user-command",
                    "name": "Mock Manager",
                },
                "body": {
                    "mid": "mock-message-command-dialog",
                    "seq": 101,
                    "text": "/задача",
                },
                "link": {
                    "type": "reply",
                    "chat_id": "mock-chat-dialog",
                    "message": {
                        "mid": "mock-message-source-dialog",
                        "seq": 100,
                        "text": "Проверить доступ завтра в 15:00",
                    },
                    "sender": {
                        "user_id": "mock-user-source",
                        "name": "Mock Author",
                    },
                },
                "timestamp": 1779439001000,
            },
        }
    )

    assert event.ignored is False
    assert event.chat_id == "mock-chat-dialog"
    assert event.chat_type == "dialog"
    assert event.user_id == "mock-user-command"
    assert event.message_id == "mock-message-command-dialog"
    assert event.text == "/задача"
    assert event.reply_to_message_id == "mock-message-source-dialog"
    assert event.reply_to_text == "Проверить доступ завтра в 15:00"
    assert event.reply_to_author_id == "mock-user-source"
    assert event.reply_to_author_display_name == "Mock Author"
    assert event.raw_update_type == "message_created"


def test_normalize_max_event_maps_real_like_group_reply_link() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_created",
            "timestamp": 1779439101000,
            "message": {
                "recipient": {
                    "chat_id": "mock-chat-group",
                    "chat_type": "chat",
                },
                "sender": {
                    "user_id": "mock-user-command",
                    "first_name": "Mock",
                    "last_name": "Manager",
                },
                "body": {
                    "mid": "mock-message-command-group",
                    "seq": 201,
                    "text": "/задача",
                },
                "link": {
                    "type": "reply",
                    "chat_id": "mock-chat-group",
                    "message": {
                        "mid": "mock-message-source-group",
                        "seq": 200,
                        "text": "Иван, подготовь отчет до пятницы",
                    },
                    "sender": {
                        "user_id": "mock-user-source",
                        "first_name": "Mock",
                        "last_name": "Author",
                    },
                },
                "timestamp": 1779439101000,
            },
        }
    )

    assert event.ignored is False
    assert event.chat_id == "mock-chat-group"
    assert event.chat_type == "chat"
    assert event.user_id == "mock-user-command"
    assert event.message_id == "mock-message-command-group"
    assert event.text == "/задача"
    assert event.reply_to_message_id == "mock-message-source-group"
    assert event.reply_to_text == "Иван, подготовь отчет до пятницы"
    assert event.reply_to_author_id == "mock-user-source"
    assert event.reply_to_author_display_name == "Mock Author"


def test_normalize_max_event_maps_reply_link_without_text_safely() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_created",
            "message": {
                "recipient": {"chat_id": "mock-chat-group", "chat_type": "chat"},
                "sender": {"user_id": "mock-user-command", "name": "Mock Manager"},
                "body": {"mid": "mock-message-command", "text": "/задача"},
                "link": {
                    "type": "reply",
                    "message": {"mid": "mock-message-source"},
                    "sender": {"user_id": "mock-user-source", "name": "Mock Author"},
                },
            },
        }
    )

    assert event.ignored is False
    assert event.reply_to_message_id == "mock-message-source"
    assert event.reply_to_text is None
    assert event.reply_to_author_id == "mock-user-source"
    assert event.reply_to_author_display_name == "Mock Author"


def test_normalize_max_event_maps_real_message_callback_before_message_text() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_callback",
            "timestamp": 1779442213000,
            "user_locale": "ru",
            "callback": {
                "callback_id": "mock-callback-real-001",
                "payload": "task:start:11111111-1111-4111-8111-111111111111",
                "timestamp": 1779442213000,
                "user": {
                    "user_id": "mock-user-callback",
                    "first_name": "Mock",
                    "last_name": "Actor",
                    "name": "Mock Actor",
                },
            },
            "message": {
                "recipient": {
                    "chat_id": "mock-chat-callback",
                    "chat_type": "dialog",
                    "user_id": "mock-user-callback",
                },
                "sender": {
                    "user_id": "mock-bot-001",
                    "name": "Mock Bot",
                    "username": "mock_bot",
                },
                "body": {
                    "mid": "mock-message-callback-source",
                    "seq": 301,
                    "text": "Тест callback-кнопки Дьяк",
                },
            },
        }
    )

    assert event.ignored is False
    assert event.source == "max"
    assert event.raw_update_type == "message_callback"
    assert event.callback_id == "mock-callback-real-001"
    assert event.payload == "task:start:11111111-1111-4111-8111-111111111111"
    assert event.user_id == "mock-user-callback"
    assert event.chat_id == "mock-chat-callback"
    assert event.message_id == "mock-message-callback-source"
    assert event.message_text == "Тест callback-кнопки Дьяк"
    assert event.sender_display_name == "Mock Actor"


def test_normalize_max_event_ignores_callback_without_payload() -> None:
    event = normalize_max_event(
        {
            "update_type": "message_callback",
            "callback": {
                "callback_id": "mock-callback-without-payload",
                "user": {"user_id": "mock-user-callback"},
            },
            "message": {
                "recipient": {"chat_id": "mock-chat-callback"},
                "body": {"mid": "mock-message-callback-source", "text": "Button source text"},
            },
        }
    )

    assert event.ignored is True
    assert event.callback_id == "mock-callback-without-payload"
    assert event.ignore_reason == "Event ignored: callback payload is missing."


def test_normalize_max_event_returns_ignored_for_unsupported_event() -> None:
    event = normalize_max_event({"update_type": "bot_started"})

    assert event.source == "max"
    assert event.ignored is True
    assert event.ignore_reason == "Event ignored: unsupported MAX event type or non-text message."
    assert event.raw_update_type == "bot_started"


def test_normalize_max_event_ignores_real_like_bot_started_shape() -> None:
    event = normalize_max_event(
        {
            "update_type": "bot_started",
            "chat_id": 12345,
            "user_id": 67890,
            "timestamp": 1779438900000,
            "user_locale": "ru",
            "user": {
                "avatar_url": "https://example.invalid/avatar.png",
                "first_name": "Mock",
                "full_avatar_url": "https://example.invalid/full-avatar.png",
                "is_bot": False,
                "last_activity_time": 1779438899000,
                "last_name": "User",
                "name": "Mock User",
                "user_id": 67890,
            },
        }
    )

    assert event.source == "max"
    assert event.ignored is True
    assert event.ignore_reason == "Event ignored: unsupported MAX event type or non-text message."
    assert event.raw_update_type == "bot_started"


def test_normalize_max_event_returns_ignored_for_empty_text() -> None:
    event = normalize_max_event(
        {
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-1",
            "text": "",
        }
    )

    assert event.source == "max"
    assert event.ignored is True
    assert event.ignore_reason == "Event ignored: empty text."


def test_normalize_max_event_preserves_strict_validation_for_partial_normalized_event() -> None:
    with pytest.raises(ValidationError):
        normalize_max_event({"chat_id": "chat-1", "text": "/задачи"})
