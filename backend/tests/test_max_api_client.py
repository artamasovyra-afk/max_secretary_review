from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.modules.integrations.max.client import (
    MaxApiClient,
    build_callback_button_attachment,
    build_inline_keyboard_attachment,
    build_link_button_attachment,
)
from app.modules.integrations.max.exceptions import (
    MaxApiConfigurationError,
    MaxApiHTTPError,
    MaxApiRequestError,
    MaxApiResponseError,
    MaxApiTemporaryError,
    MaxApiTimeoutError,
)


def test_send_message_posts_to_max_api_without_leaking_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": {"id": "max-message-1"}})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        bot_token=SecretStr("secret-token"),
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    result = client.send_message(chat_id="123", text="hello")

    assert result == {"message": {"id": "max-message-1"}}
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/messages"
    assert requests[0].url.params["chat_id"] == "123"
    assert requests[0].headers["Authorization"] == "secret-token"
    assert json.loads(requests[0].read()) == {"text": "hello", "notify": True}


def test_send_message_requires_recipient() -> None:
    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        bot_token="secret-token",
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )

    with pytest.raises(MaxApiRequestError, match="Either chat_id or user_id is required"):
        client.send_message(chat_id=None, user_id=None, text="hello")


def test_edit_message_puts_to_max_api() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": {"id": "max-message-1"}})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
        **{"bot_" + "token": "fixture-value"},
    )

    result = client.edit_message(
        message_id="max-message-1",
        text="Задача создана",
        attachments=[{"type": "inline_keyboard", "payload": {"buttons": []}}],
    )

    assert result == {"message": {"id": "max-message-1"}}
    assert requests[0].method == "PUT"
    assert requests[0].url.path == "/messages"
    assert requests[0].url.params["message_id"] == "max-message-1"
    assert json.loads(requests[0].read()) == {
        "text": "Задача создана",
        "attachments": [{"type": "inline_keyboard", "payload": {"buttons": []}}],
        "notify": True,
    }


def test_edit_message_requires_message_id() -> None:
    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        **{"bot_" + "token": "fixture-value"},
    )

    with pytest.raises(MaxApiRequestError, match="message_id is required"):
        client.edit_message(message_id="", text="hello")


def test_delete_message_deletes_from_max_api() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
        **{"bot_" + "token": "fixture-value"},
    )

    result = client.delete_message(message_id="max-message-1")

    assert result == {"success": True}
    assert requests[0].method == "DELETE"
    assert requests[0].url.path == "/messages"
    assert requests[0].url.params["message_id"] == "max-message-1"
    assert not requests[0].content


def test_delete_message_requires_message_id() -> None:
    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        **{"bot_" + "token": "fixture-value"},
    )

    with pytest.raises(MaxApiRequestError, match="message_id is required"):
        client.delete_message(message_id="")


def test_send_webapp_button_message_posts_inline_keyboard_attachment() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": {"id": "max-message-webapp"}})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
        **{"bot_token": "secret-token"},
    )

    result = client.send_webapp_button_message(
        user_id="max-user-001",
        chat_id=None,
        text="Тест кнопки мини-приложения Дьяк",
        button_text="Открыть Дьяк",
        url="https://maxsecretary.ru",
    )

    body = json.loads(requests[0].read())
    assert result == {"message": {"id": "max-message-webapp"}}
    assert requests[0].url.params["user_id"] == "max-user-001"
    assert body == {
        "text": "Тест кнопки мини-приложения Дьяк",
        "attachments": build_link_button_attachment(
            button_text="Открыть Дьяк",
            url="https://maxsecretary.ru",
        ),
        "notify": True,
    }


def test_send_callback_button_message_posts_active_inline_keyboard_attachment() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": {"id": "max-message-callback"}})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
        **{"bot_token": "secret-token"},
    )

    result = client.send_callback_button_message(
        chat_id="max-chat-001",
        user_id=None,
        text="Тест callback-кнопки Дьяк",
        button_text="Проверить callback",
        payload="test:callback:ping",
    )

    body = json.loads(requests[0].read())
    assert result == {"message": {"id": "max-message-callback"}}
    assert requests[0].url.params["chat_id"] == "max-chat-001"
    assert body == {
        "text": "Тест callback-кнопки Дьяк",
        "attachments": build_callback_button_attachment(
            button_text="Проверить callback",
            payload="test:callback:ping",
        ),
        "notify": True,
    }
    assert body["attachments"][0]["payload"]["buttons"][0][0] == {
        "type": "callback",
        "text": "Проверить callback",
        "payload": "test:callback:ping",
        "intent": "default",
    }


def test_send_inline_keyboard_message_posts_button_rows() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": {"id": "max-message-picker"}})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
        **{"bot_token": "secret-token"},
    )
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

    result = client.send_inline_keyboard_message(
        chat_id="max-chat-001",
        user_id=None,
        text="Выберите исполнителя",
        button_rows=button_rows,
    )

    body = json.loads(requests[0].read())
    assert result == {"message": {"id": "max-message-picker"}}
    assert requests[0].url.params["chat_id"] == "max-chat-001"
    assert body == {
        "text": "Выберите исполнителя",
        "attachments": build_inline_keyboard_attachment(button_rows=button_rows),
        "notify": True,
    }


def test_answer_callback_posts_to_answers_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
        **{"bot_token": "credential-placeholder"},
    )

    result = client.answer_callback(
        callback_id="mock-callback-001",
        notification="Задача взята в работу.",
    )

    assert result == {"success": True}
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/answers"
    assert requests[0].url.params["callback_id"] == "mock-callback-001"
    assert json.loads(requests[0].read()) == {"notification": "Задача взята в работу."}


def test_answer_callback_can_update_message_and_remove_keyboard() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
        **{"bot_token": "credential-placeholder"},
    )

    result = client.answer_callback(
        callback_id="mock-callback-001",
        notification="Исполнитель назначен.",
        message={"text": "Задача создана.", "attachments": []},
    )

    assert result == {"success": True}
    assert json.loads(requests[0].read()) == {
        "notification": "Исполнитель назначен.",
        "message": {"text": "Задача создана.", "attachments": []},
    }


def test_send_task_card_uses_text_payload_adapter() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": {"id": "max-message-2"}})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        bot_token="secret-token",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    result = client.send_task_card(
        chat_id="123",
        task={"id": "task-1", "task_ref": "#1042", "title": "Подготовить отчет", "status": "new"},
    )

    body = json.loads(requests[0].read())
    assert result == {"message": {"id": "max-message-2"}}
    assert "Задача #1042 создана" in body["text"]
    assert "Подготовить отчет" in body["text"]
    assert "Статус: Новая" in body["text"]
    assert "task-1" not in body["text"]
    assert "Статус: new" not in body["text"]


def test_ping_uses_me_endpoint_and_retries_temporary_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"message": "temporary"})
        return httpx.Response(200, json={"user_id": 1, "name": "Bot", "is_bot": True})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        bot_token="secret-token",
        timeout_seconds=3,
        backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    result = client.ping()

    assert calls == 2
    assert result["user_id"] == 1
    assert result["is_bot"] is True


def test_get_chat_admins_normalizes_admin_members() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "members": [
                    {"user_id": "max-user-1", "username": "ivan", "name": "Иван"},
                    {"id": 2, "display_name": "Мария"},
                    {"user": {"user_id": "max-user-3", "username": "petr"}},
                    {"user_id": "max-user-1", "username": "duplicate"},
                    {"name": "Без id"},
                ]
            },
        )

    client = MaxApiClient(
        **{
            "base_url": "https://max-api.example.invalid",
            "bot_" + "token": "fixture-value",
            "timeout_seconds": 3,
            "transport": httpx.MockTransport(handler),
        }
    )

    result = client.get_chat_admins("max-chat-1")

    assert requests[0].method == "GET"
    assert requests[0].url.path == "/chats/max-chat-1/members/admins"
    assert result == [
        {"max_user_id": "max-user-1", "username": "ivan", "display_name": "Иван"},
        {"max_user_id": "2", "username": None, "display_name": "Мария"},
        {"max_user_id": "max-user-3", "username": "petr", "display_name": None},
    ]


def test_get_chat_info_normalizes_chat_title() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"chat": {"title": "Тестовый MAX чат", "type": "chat"}})

    client = MaxApiClient(
        **{
            "base_url": "https://max-api.example.invalid",
            "bot_" + "token": "fixture-value",
            "timeout_seconds": 3,
            "transport": httpx.MockTransport(handler),
        }
    )

    result = client.get_chat_info("max-chat-1")

    assert requests[0].method == "GET"
    assert requests[0].url.path == "/chats/max-chat-1"
    assert result == {"title": "Тестовый MAX чат", "type": "chat"}


def test_get_chat_info_uses_alternate_name_fields() -> None:
    client = MaxApiClient(
        **{
            "base_url": "https://max-api.example.invalid",
            "bot_" + "token": "fixture-value",
            "timeout_seconds": 3,
            "transport": httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"result": {"name": "Название из MAX"}})
            ),
        }
    )

    result = client.get_chat_info("max-chat-1")

    assert result == {"title": "Название из MAX", "type": None}


def test_get_chat_info_requires_chat_id() -> None:
    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        **{"bot_" + "token": "fixture-value"},
    )

    with pytest.raises(MaxApiRequestError, match="chat_id is required"):
        client.get_chat_info("")


def test_send_message_does_not_retry_non_idempotent_post() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"message": "temporary"})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        bot_token="secret-token",
        timeout_seconds=3,
        backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MaxApiTemporaryError, match="HTTP 503"):
        client.send_message(chat_id="123", text="hello")

    assert calls == 1


def test_http_error_is_wrapped_without_token() -> None:
    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        bot_token="secret-token",
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: httpx.Response(401, text="unauthorized")),
    )

    with pytest.raises(MaxApiHTTPError) as exc_info:
        client.ping()

    assert exc_info.value.status_code == 401
    assert "secret-token" not in str(exc_info.value)


def test_timeout_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        bot_token="secret-token",
        timeout_seconds=3,
        backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MaxApiTimeoutError, match="timed out"):
        client.ping()


def test_invalid_json_is_wrapped() -> None:
    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        bot_token="secret-token",
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="not-json")),
    )

    with pytest.raises(MaxApiResponseError, match="invalid JSON"):
        client.ping()


def test_token_is_required() -> None:
    with pytest.raises(MaxApiConfigurationError, match="MAX_BOT_TOKEN is required"):
        MaxApiClient(base_url="https://max-api.example.invalid", bot_token="", timeout_seconds=3)
