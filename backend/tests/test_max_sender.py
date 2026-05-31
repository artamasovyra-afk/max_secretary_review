from __future__ import annotations

import logging

import pytest

from app.core.config import Settings
from app.modules.integrations.max.exceptions import MaxApiError
from app.modules.notifications.max_sender import MaxSender, OutboundPurpose
from app.modules.notifications.max_sender_factory import build_max_sender


class FakeMaxApiClient:
    def __init__(self, *, send_message_response: dict[str, object] | None = None) -> None:
        self.send_message_response = send_message_response
        self.messages: list[dict[str, object]] = []
        self.task_cards: list[dict[str, object]] = []
        self.webapp_buttons: list[dict[str, str | None]] = []
        self.callback_buttons: list[dict[str, str | None]] = []
        self.inline_keyboards: list[dict[str, object]] = []
        self.callback_answers: list[dict[str, str | None]] = []
        self.edits: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []

    def send_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        attachments=None,
    ) -> dict[str, object]:
        self.messages.append({"chat_id": chat_id, "user_id": user_id, "text": text, "attachments": attachments})
        return self.send_message_response or {"message": {"id": "max-message-1"}}

    def send_task_card(self, *, chat_id: str, task: dict[str, object]) -> dict[str, object]:
        self.task_cards.append({"chat_id": chat_id, "task": task})
        return {"message": {"id": "max-message-2"}}

    def send_webapp_button_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_text: str,
        url: str,
    ) -> dict[str, object]:
        self.webapp_buttons.append(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "text": text,
                "button_text": button_text,
                "url": url,
            }
        )
        return {"message": {"id": "max-message-3"}}

    def send_callback_button_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_text: str,
        payload: str,
        intent: str = "default",
    ) -> dict[str, object]:
        self.callback_buttons.append(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "text": text,
                "button_text": button_text,
                "payload": payload,
                "intent": intent,
            }
        )
        return {"message": {"id": "max-message-callback"}}

    def answer_callback(
        self,
        *,
        callback_id: str,
        notification: str | None = None,
        message: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.callback_answers.append(
            {
                "callback_id": callback_id,
                "notification": notification,
                "message": str(message) if message is not None else None,
            }
        )
        return {"success": True}

    def send_inline_keyboard_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_rows: list[list[dict[str, object]]],
    ) -> dict[str, object]:
        self.inline_keyboards.append(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "text": text,
                "button_rows": button_rows,
            }
        )
        return {"message": {"id": "max-message-inline-keyboard"}}

    def edit_message(
        self,
        *,
        message_id: str,
        text: str,
        attachments=None,
    ) -> dict[str, object]:
        self.edits.append({"message_id": message_id, "text": text, "attachments": attachments})
        return {"message": {"id": message_id}}

    def delete_message(self, *, message_id: str) -> dict[str, object]:
        self.deletes.append({"message_id": message_id})
        return {"success": True}


class FailingMaxApiClient:
    def send_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        attachments=None,
    ) -> dict[str, object]:
        raise MaxApiError("MAX API returned HTTP 401.")

    def send_task_card(self, *, chat_id: str, task: dict[str, object]) -> dict[str, object]:
        raise MaxApiError("MAX API returned HTTP 503.")

    def send_webapp_button_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_text: str,
        url: str,
    ) -> dict[str, object]:
        raise MaxApiError("MAX API returned HTTP 400.")

    def send_callback_button_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_text: str,
        payload: str,
        intent: str = "default",
    ) -> dict[str, object]:
        raise MaxApiError("MAX API returned HTTP 400.")

    def answer_callback(
        self,
        *,
        callback_id: str,
        notification: str | None = None,
        message: dict[str, object] | None = None,
    ) -> dict[str, object]:
        raise MaxApiError("MAX API returned HTTP 500.")

    def send_inline_keyboard_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_rows: list[list[dict[str, object]]],
    ) -> dict[str, object]:
        raise MaxApiError("MAX API returned HTTP 400.")

    def edit_message(
        self,
        *,
        message_id: str,
        text: str,
        attachments=None,
    ) -> dict[str, object]:
        raise MaxApiError("MAX API returned HTTP 400.")

    def delete_message(self, *, message_id: str) -> dict[str, object]:
        raise MaxApiError("MAX API returned HTTP 403.")


def test_build_max_sender_uses_placeholder_by_default(caplog: pytest.LogCaptureFixture) -> None:
    sender = build_max_sender(Settings(max_sender_enabled=False))

    caplog.set_level(logging.INFO, logger="app.modules.notifications.max_sender")
    outbound = sender.send_message(chat_id="chat-1", text="hello")

    assert sender.enabled is False
    assert sender.interactive_enabled is True
    assert sender.background_enabled is False
    assert outbound.sent is False
    assert outbound.reason == "stub: real MAX API sending is disabled"
    assert outbound.purpose == OutboundPurpose.INTERACTIVE.value
    assert "MAX sender stub message" in caplog.text


def test_build_max_sender_carries_split_send_flags() -> None:
    sender = build_max_sender(
        Settings(
            max_sender_enabled=False,
            max_interactive_responses_enabled=False,
            max_background_notifications_enabled=True,
        )
    )

    assert sender.enabled is False
    assert sender.interactive_enabled is False
    assert sender.background_enabled is True


def test_max_sender_disabled_task_card_logs_without_client(caplog: pytest.LogCaptureFixture) -> None:
    sender = MaxSender(enabled=False)

    caplog.set_level(logging.INFO, logger="app.modules.notifications.max_sender")
    outbound = sender.send_task_card(
        chat_id="chat-1",
        task={"id": "task-1", "title": "Подготовить отчет", "status": "new"},
    )

    assert outbound.sent is False
    assert outbound.reason == "stub: real MAX API sending is disabled"
    assert "MAX sender stub task card" in caplog.text


def test_build_max_sender_requires_token_when_enabled() -> None:
    settings = Settings(max_sender_enabled=True, max_bot_token="")

    with pytest.raises(ValueError, match="MAX_BOT_TOKEN is required"):
        build_max_sender(settings)


def test_max_sender_uses_real_client_when_enabled() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True, background_enabled=False)  # type: ignore[arg-type]

    outbound = sender.send_message(chat_id="chat-1", text="hello")

    assert outbound.sent is True
    assert outbound.reason == "sent via MAX API"
    assert outbound.purpose == OutboundPurpose.INTERACTIVE.value
    assert outbound.message_id == "max-message-1"
    assert client.messages == [{"chat_id": "chat-1", "user_id": None, "text": "hello", "attachments": None}]


@pytest.mark.parametrize(
    ("response", "expected_message_id"),
    [
        ({"message": {"body": {"mid": "max-nested-mid-1"}}}, "max-nested-mid-1"),
        ({"body": {"message_id": "max-body-message-1"}}, "max-body-message-1"),
        ({"result": {"messageId": "max-result-message-1"}}, "max-result-message-1"),
    ],
)
def test_max_sender_extracts_nested_message_id_shapes(
    response: dict[str, object],
    expected_message_id: str,
) -> None:
    client = FakeMaxApiClient(send_message_response=response)
    sender = MaxSender(client=client, enabled=True, background_enabled=False)  # type: ignore[arg-type]

    outbound = sender.send_message(chat_id="chat-1", text="hello")

    assert outbound.sent is True
    assert outbound.message_id == expected_message_id


def test_max_sender_edits_real_message_when_enabled() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True)  # type: ignore[arg-type]

    outbound = sender.edit_message(
        message_id="max-message-1",
        text="Задача создана",
        attachments=[{"type": "inline_keyboard", "payload": {"buttons": []}}],
    )

    assert outbound.sent is True
    assert outbound.method == "edit_message"
    assert outbound.message_id == "max-message-1"
    assert client.edits == [
        {
            "message_id": "max-message-1",
            "text": "Задача создана",
            "attachments": [{"type": "inline_keyboard", "payload": {"buttons": []}}],
        }
    ]


def test_max_sender_deletes_real_message_when_enabled() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True)  # type: ignore[arg-type]

    outbound = sender.delete_message(message_id="max-message-1", chat_id="chat-1")

    assert outbound.sent is True
    assert outbound.method == "delete_message"
    assert outbound.message_id == "max-message-1"
    assert client.deletes == [{"message_id": "max-message-1"}]


def test_max_sender_delete_message_error_is_handled_gracefully(caplog: pytest.LogCaptureFixture) -> None:
    sender = MaxSender(client=FailingMaxApiClient(), enabled=True)  # type: ignore[arg-type]

    caplog.set_level(logging.WARNING, logger="app.modules.notifications.max_sender")
    outbound = sender.delete_message(message_id="max-message-1", chat_id="chat-1")

    assert outbound.sent is False
    assert outbound.reason == "MAX API returned HTTP 403."
    assert "MAX sender real message delete failed" in caplog.text


def test_max_sender_blocks_interactive_when_interactive_flag_is_disabled() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True, interactive_enabled=False)  # type: ignore[arg-type]

    outbound = sender.send_inline_keyboard_message(
        chat_id="chat-1",
        text="Дьяк",
        button_rows=[[{"type": "link", "text": "Открыть", "url": "https://maxsecretary.ru"}]],
    )

    assert outbound.sent is False
    assert outbound.reason == "interactive_disabled: MAX interactive responses are disabled"
    assert outbound.purpose == OutboundPurpose.INTERACTIVE.value
    assert client.inline_keyboards == []


def test_max_sender_allows_interactive_but_blocks_background_when_background_flag_is_disabled() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(
        client=client,
        enabled=True,
        interactive_enabled=True,
        background_enabled=False,
    )  # type: ignore[arg-type]

    interactive = sender.send_message(chat_id="chat-1", text="hello")
    reminder = sender.send_message(
        chat_id=None,
        user_id="max-user-001",
        text="Reminder",
        purpose=OutboundPurpose.REMINDER,
        reminder_type="after_deadline",
    )

    assert interactive.sent is True
    assert reminder.sent is False
    assert reminder.reason == "background_disabled: MAX background notifications are disabled"
    assert reminder.purpose == OutboundPurpose.REMINDER.value
    assert client.messages == [{"chat_id": "chat-1", "user_id": None, "text": "hello", "attachments": None}]


def test_max_sender_allows_background_when_background_flag_is_enabled() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True, background_enabled=True)  # type: ignore[arg-type]

    outbound = sender.send_message(
        chat_id=None,
        user_id="max-user-001",
        text="Reminder",
        purpose=OutboundPurpose.REMINDER,
        reminder_type="after_deadline",
    )

    assert outbound.sent is True
    assert outbound.purpose == OutboundPurpose.REMINDER.value
    assert client.messages == [
        {"chat_id": None, "user_id": "max-user-001", "text": "Reminder", "attachments": None}
    ]


def test_max_sender_task_card_uses_real_client_when_enabled() -> None:
    client = FakeMaxApiClient()
    task = {"id": "task-1", "title": "Подготовить отчет", "status": "new"}
    sender = MaxSender(client=client, enabled=True)  # type: ignore[arg-type]

    outbound = sender.send_task_card(chat_id="chat-1", task=task)

    assert outbound.sent is True
    assert outbound.reason == "sent via MAX API"
    assert client.task_cards == [{"chat_id": "chat-1", "task": task}]


def test_max_sender_webapp_button_uses_real_client_when_enabled() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True)  # type: ignore[arg-type]

    outbound = sender.send_webapp_button_message(
        chat_id=None,
        user_id="max-user-001",
        text="Тест кнопки мини-приложения Дьяк",
        button_text="Открыть Дьяк",
        url="https://maxsecretary.ru",
    )

    assert outbound.sent is True
    assert outbound.method == "send_webapp_button_message"
    assert outbound.reason == "sent via MAX API"
    assert client.webapp_buttons == [
        {
            "chat_id": None,
            "user_id": "max-user-001",
            "text": "Тест кнопки мини-приложения Дьяк",
            "button_text": "Открыть Дьяк",
            "url": "https://maxsecretary.ru",
        }
    ]


def test_max_sender_callback_button_uses_real_client_when_enabled() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True)  # type: ignore[arg-type]

    outbound = sender.send_callback_button_message(
        chat_id="max-chat-001",
        user_id=None,
        text="Тест callback-кнопки Дьяк",
        button_text="Проверить callback",
        payload="test:callback:ping",
    )

    assert outbound.sent is True
    assert outbound.method == "send_callback_button_message"
    assert outbound.reason == "sent via MAX API"
    assert client.callback_buttons == [
        {
            "chat_id": "max-chat-001",
            "user_id": None,
            "text": "Тест callback-кнопки Дьяк",
            "button_text": "Проверить callback",
            "payload": "test:callback:ping",
            "intent": "default",
        }
    ]


def test_max_sender_inline_keyboard_uses_real_client_when_enabled() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True)  # type: ignore[arg-type]
    button_rows = [
        [
            {
                "type": "callback",
                "text": "Иван",
                "payload": "task:assign:11111111-1111-4111-8111-111111111111:self",
                "intent": "default",
            }
        ],
        [{"type": "link", "text": "Открыть в WebApp", "url": "https://maxsecretary.ru"}],
    ]

    outbound = sender.send_inline_keyboard_message(
        chat_id="max-chat-001",
        text="Выберите исполнителя",
        button_rows=button_rows,
    )

    assert outbound.sent is True
    assert outbound.method == "send_inline_keyboard_message"
    assert outbound.attachments == [{"type": "inline_keyboard", "payload": {"buttons": button_rows}}]
    assert client.inline_keyboards == [
        {
            "chat_id": "max-chat-001",
            "user_id": None,
            "text": "Выберите исполнителя",
            "button_rows": button_rows,
        }
    ]


def test_max_sender_answer_callback_uses_real_client_when_enabled() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True)  # type: ignore[arg-type]

    outbound = sender.answer_callback(
        callback_id="mock-callback-001",
        notification="Задача взята в работу.",
    )

    assert outbound.sent is True
    assert outbound.method == "answer_callback"
    assert outbound.purpose == OutboundPurpose.CALLBACK_ANSWER.value
    assert outbound.reason == "sent via MAX API"
    assert client.callback_answers == [
        {
            "callback_id": "mock-callback-001",
            "notification": "Задача взята в работу.",
            "message": None,
        }
    ]


def test_max_sender_answer_callback_uses_interactive_guard() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True, interactive_enabled=False)  # type: ignore[arg-type]

    outbound = sender.answer_callback(
        callback_id="mock-callback-001",
        notification="Готово.",
    )

    assert outbound.sent is False
    assert outbound.purpose == OutboundPurpose.CALLBACK_ANSWER.value
    assert outbound.reason == "interactive_disabled: MAX interactive responses are disabled"
    assert client.callback_answers == []


def test_max_sender_answer_callback_can_update_message() -> None:
    client = FakeMaxApiClient()
    sender = MaxSender(client=client, enabled=True)  # type: ignore[arg-type]

    outbound = sender.answer_callback(
        callback_id="mock-callback-001",
        notification="Исполнитель назначен.",
        message={"text": "Задача создана.", "attachments": []},
    )

    assert outbound.sent is True
    assert client.callback_answers == [
        {
            "callback_id": "mock-callback-001",
            "notification": "Исполнитель назначен.",
            "message": "{'text': 'Задача создана.', 'attachments': []}",
        }
    ]


def test_max_sender_returns_failure_without_leaking_token(caplog: pytest.LogCaptureFixture) -> None:
    sender = MaxSender(client=FailingMaxApiClient(), enabled=True)  # type: ignore[arg-type]

    caplog.set_level(logging.WARNING, logger="app.modules.notifications.max_sender")
    outbound = sender.send_message(chat_id="chat-1", text="hello")

    assert outbound.sent is False
    assert outbound.reason == "MAX API returned HTTP 401."
    assert "MAX sender real message failed" in caplog.text


def test_max_sender_task_card_error_is_handled_gracefully(caplog: pytest.LogCaptureFixture) -> None:
    sender = MaxSender(client=FailingMaxApiClient(), enabled=True)  # type: ignore[arg-type]

    caplog.set_level(logging.WARNING, logger="app.modules.notifications.max_sender")
    outbound = sender.send_task_card(chat_id="chat-1", task={"id": "task-1", "title": "Title"})

    assert outbound.sent is False
    assert outbound.reason == "MAX API returned HTTP 503."
    assert "MAX sender real task card failed" in caplog.text


def test_max_sender_webapp_button_error_is_handled_gracefully(caplog: pytest.LogCaptureFixture) -> None:
    sender = MaxSender(client=FailingMaxApiClient(), enabled=True)  # type: ignore[arg-type]

    caplog.set_level(logging.WARNING, logger="app.modules.notifications.max_sender")
    outbound = sender.send_webapp_button_message(
        chat_id=None,
        user_id="max-user-001",
        text="Тест кнопки",
        button_text="Открыть",
        url="https://maxsecretary.ru",
    )

    assert outbound.sent is False
    assert outbound.reason == "MAX API returned HTTP 400."
    assert "MAX sender real WebApp button failed" in caplog.text


def test_max_sender_callback_button_error_is_handled_gracefully(caplog: pytest.LogCaptureFixture) -> None:
    sender = MaxSender(client=FailingMaxApiClient(), enabled=True)  # type: ignore[arg-type]

    caplog.set_level(logging.WARNING, logger="app.modules.notifications.max_sender")
    outbound = sender.send_callback_button_message(
        chat_id="max-chat-001",
        text="Тест callback-кнопки",
        button_text="Проверить callback",
        payload="test:callback:ping",
    )

    assert outbound.sent is False
    assert outbound.reason == "MAX API returned HTTP 400."
    assert "MAX sender real callback button failed" in caplog.text


def test_max_sender_inline_keyboard_error_is_handled_gracefully(caplog: pytest.LogCaptureFixture) -> None:
    sender = MaxSender(client=FailingMaxApiClient(), enabled=True)  # type: ignore[arg-type]

    caplog.set_level(logging.WARNING, logger="app.modules.notifications.max_sender")
    outbound = sender.send_inline_keyboard_message(
        chat_id="max-chat-001",
        text="Выберите исполнителя",
        button_rows=[[{"type": "callback", "text": "Иван", "payload": "payload", "intent": "default"}]],
    )

    assert outbound.sent is False
    assert outbound.reason == "MAX API returned HTTP 400."
    assert "MAX sender real inline keyboard failed" in caplog.text


def test_max_sender_answer_callback_error_is_handled_gracefully(caplog: pytest.LogCaptureFixture) -> None:
    sender = MaxSender(client=FailingMaxApiClient(), enabled=True)  # type: ignore[arg-type]

    caplog.set_level(logging.WARNING, logger="app.modules.notifications.max_sender")
    outbound = sender.answer_callback(
        callback_id="mock-callback-001",
        notification="Не удалось обработать callback.",
    )

    assert outbound.sent is False
    assert outbound.reason == "MAX API returned HTTP 500."
    assert "MAX sender real callback answer failed" in caplog.text
