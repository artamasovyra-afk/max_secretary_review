from __future__ import annotations

from collections.abc import Iterator
import inspect
import logging

import pytest
from fastapi.testclient import TestClient

from app.api import bot_max
from app.api.bot_max import (
    MAX_OFFICIAL_WEBHOOK_SECRET_HEADER,
    MAX_WEBHOOK_SECRET_HEADER,
    get_max_bot_webhook_service,
)
from app.core.config import get_settings
from app.main import create_app
from app.modules.bot.command_parser import BotCommandParser
from app.modules.bot.schemas import (
    BotWebhookResponse,
    CommandParseError,
    NormalizedBotEvent,
    UnknownCommand,
)
from app.modules.notifications.max_sender import MaxSender


class FakeEndpointBotService:
    def __init__(self) -> None:
        self.parser = BotCommandParser()
        self.sender = MaxSender()

    async def handle_event(self, event: NormalizedBotEvent) -> BotWebhookResponse:
        if event.ignored:
            return BotWebhookResponse(
                ok=True,
                is_command=False,
                action="ignored",
                response_text=event.ignore_reason,
            )
        if not self.parser.is_command(event.text):
            return BotWebhookResponse(
                ok=True,
                is_command=False,
                action="ignored",
                response_text="Event ignored: message is not a command.",
            )

        command = self.parser.parse(event.text)
        if isinstance(command, CommandParseError):
            response_text = f"Ошибка формата команды: {command.message}"
            return BotWebhookResponse(
                ok=False,
                is_command=True,
                action="error",
                command=command,
                response_text=response_text,
                error=response_text,
                outbound=self.sender.send_message(event.chat_id, response_text),
            )
        if isinstance(command, UnknownCommand):
            response_text = f"Неизвестная команда: /{command.name}"
            return BotWebhookResponse(
                ok=False,
                is_command=True,
                action="error",
                command=command,
                response_text=response_text,
                error=response_text,
                outbound=self.sender.send_message(event.chat_id, response_text),
            )

        response_text = "Команда распознана."
        return BotWebhookResponse(
            ok=True,
            is_command=True,
            action="reply_prepared",
            command=command,
            response_text=response_text,
            outbound=self.sender.send_message(event.chat_id, response_text),
        )


class TrackingEndpointBotService(FakeEndpointBotService):
    def __init__(self) -> None:
        super().__init__()
        self.called = False

    async def handle_event(self, event: NormalizedBotEvent) -> BotWebhookResponse:
        self.called = True
        return await super().handle_event(event)


WEBHOOK_SECRET = "expected-secret"


@pytest.fixture(autouse=True)
def _default_webhook_test_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MAX_WEBHOOK_ENABLED", "true")
    monkeypatch.delenv("MAX_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def bot_client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_max_bot_webhook_service] = lambda: FakeEndpointBotService()
    with TestClient(app) as test_client:
        yield test_client


def make_bot_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_max_bot_webhook_service] = lambda: FakeEndpointBotService()
    return TestClient(app)


def test_max_bot_webhook_ignores_non_command_message(bot_client: TestClient) -> None:
    response = bot_client.post(
        "/api/bot/max/webhook",
        json={
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-1",
            "text": "просто текст без команды",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["is_command"] is False
    assert payload["action"] == "ignored"
    assert payload["command"] is None
    assert payload["outbound"] is None


def test_max_bot_webhook_prepares_command_reply(bot_client: TestClient) -> None:
    response = bot_client.post(
        "/api/bot/max/webhook",
        json={
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-1",
            "text": "/задачи",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["is_command"] is True
    assert payload["action"] == "reply_prepared"
    assert payload["command"] == {"raw_text": "/задачи", "type": "list_tasks"}
    assert payload["response_text"] == "Команда распознана."
    assert payload["outbound"]["adapter"] == "max"
    assert payload["outbound"]["method"] == "send_message"
    assert payload["outbound"]["chat_id"] == "chat-1"
    assert payload["outbound"]["sent"] is False


def test_max_bot_webhook_no_secret_in_local_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("MAX_WEBHOOK_ENABLED", "true")
    monkeypatch.delenv("MAX_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()

    with make_bot_client() as client:
        response = client.post(
            "/api/bot/max/webhook",
            json={
                "chat_id": "chat-1",
                "user_id": "user-1",
                "message_id": "message-1",
                "text": "/задачи",
            },
        )

    assert response.status_code == 200
    assert response.json()["action"] == "reply_prepared"


def test_max_bot_webhook_no_secret_in_test_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MAX_WEBHOOK_ENABLED", "true")
    monkeypatch.delenv("MAX_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()

    with make_bot_client() as client:
        response = client.post(
            "/api/bot/max/webhook",
            json={
                "chat_id": "chat-1",
                "user_id": "user-1",
                "message_id": "message-1",
                "text": "/задачи",
            },
        )

    assert response.status_code == 200
    assert response.json()["action"] == "reply_prepared"


def test_max_bot_webhook_disabled_returns_404_without_handling_or_logging(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_WEBHOOK_ENABLED", "false")
    monkeypatch.delenv("MAX_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("MAX_WEBHOOK_DEBUG_LOG", "true")
    get_settings.cache_clear()
    service = TrackingEndpointBotService()
    app = create_app()
    app.dependency_overrides[get_max_bot_webhook_service] = lambda: service
    caplog.set_level(logging.INFO, logger="app.api.bot_max")

    with TestClient(app) as client:
        response = client.post(
            "/api/bot/max/webhook",
            json={
                "chat_id": "chat-sensitive-123456789",
                "user_id": "user-sensitive-123456789",
                "message_id": "message-sensitive-123456789",
                "text": "/задачи private payload",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"
    assert service.called is False
    assert "MAX webhook raw event debug shape" not in caplog.text
    assert "MAX webhook normalized event debug shape" not in caplog.text
    assert "private payload" not in caplog.text


def test_max_bot_webhook_enabled_without_secret_in_production_returns_503_without_handling_or_logging(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_WEBHOOK_ENABLED", "true")
    monkeypatch.delenv("MAX_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("MAX_WEBHOOK_DEBUG_LOG", "true")
    get_settings.cache_clear()
    service = TrackingEndpointBotService()
    app = create_app()
    app.dependency_overrides[get_max_bot_webhook_service] = lambda: service
    caplog.set_level(logging.INFO, logger="app.api.bot_max")

    with TestClient(app) as client:
        response = client.post(
            "/api/bot/max/webhook",
            json={
                "chat_id": "chat-sensitive-123456789",
                "user_id": "user-sensitive-123456789",
                "message_id": "message-sensitive-123456789",
                "text": "/задачи private payload",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "MAX webhook is not configured"
    assert service.called is False
    assert "MAX webhook raw event debug shape" not in caplog.text
    assert "MAX webhook normalized event debug shape" not in caplog.text
    assert "private payload" not in caplog.text
    assert "secret" not in response.text.casefold()
    assert "token" not in response.text.casefold()


def test_max_bot_webhook_enabled_missing_secret_header_returns_401(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("MAX_WEBHOOK_SECRET", WEBHOOK_SECRET)
    get_settings.cache_clear()
    caplog.set_level(logging.INFO, logger="app.api.bot_max")

    with make_bot_client() as client:
        response = client.post(
            "/api/bot/max/webhook",
            json={
                "chat_id": "chat-1",
                "user_id": "user-1",
                "message_id": "message-1",
                "text": "/задачи",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid MAX webhook secret"
    assert WEBHOOK_SECRET not in response.text
    assert WEBHOOK_SECRET not in caplog.text


def test_max_bot_webhook_correct_official_secret_header_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("MAX_WEBHOOK_SECRET", WEBHOOK_SECRET)
    get_settings.cache_clear()

    with make_bot_client() as client:
        response = client.post(
            "/api/bot/max/webhook",
            headers={MAX_OFFICIAL_WEBHOOK_SECRET_HEADER: WEBHOOK_SECRET},
            json={
                "chat_id": "chat-1",
                "user_id": "user-1",
                "message_id": "message-1",
                "text": "/задачи",
            },
        )

    assert response.status_code == 200
    assert response.json()["action"] == "reply_prepared"


def test_max_bot_webhook_legacy_secret_header_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("MAX_WEBHOOK_SECRET", WEBHOOK_SECRET)
    get_settings.cache_clear()

    with make_bot_client() as client:
        response = client.post(
            "/api/bot/max/webhook",
            headers={MAX_WEBHOOK_SECRET_HEADER: WEBHOOK_SECRET},
            json={
                "chat_id": "chat-1",
                "user_id": "user-1",
                "message_id": "message-1",
                "text": "/задачи",
            },
        )

    assert response.status_code == 200
    assert response.json()["action"] == "reply_prepared"


def test_max_bot_webhook_wrong_official_secret_returns_401(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("MAX_WEBHOOK_SECRET", WEBHOOK_SECRET)
    get_settings.cache_clear()
    caplog.set_level(logging.INFO, logger="app.api.bot_max")

    with make_bot_client() as client:
        response = client.post(
            "/api/bot/max/webhook",
            headers={MAX_OFFICIAL_WEBHOOK_SECRET_HEADER: "wrong-secret"},
            json={
                "chat_id": "chat-1",
                "user_id": "user-1",
                "message_id": "message-1",
                "text": "/задачи",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid MAX webhook secret"
    assert WEBHOOK_SECRET not in response.text
    assert WEBHOOK_SECRET not in caplog.text


def test_max_bot_webhook_secret_validation_uses_constant_time_compare() -> None:
    source = inspect.getsource(bot_max.verify_max_webhook_access)

    assert "compare_digest" in source


def test_max_bot_webhook_debug_logging_is_disabled_by_default(
    bot_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.api.bot_max")

    response = bot_client.post(
        "/api/bot/max/webhook",
        json={
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-1",
            "text": "/задачи",
        },
    )

    assert response.status_code == 200
    assert "MAX webhook raw event debug shape" not in caplog.text
    assert "MAX webhook normalized event debug shape" not in caplog.text


def test_max_bot_webhook_debug_logging_masks_values(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("MAX_WEBHOOK_DEBUG_LOG", "true")
    get_settings.cache_clear()
    caplog.set_level(logging.INFO, logger="app.api.bot_max")

    with make_bot_client() as client:
        response = client.post(
            "/api/bot/max/webhook",
            json={
                "update_type": "message_created",
                "message": {
                    "recipient": {"chat_id": "chat-sensitive-123456789"},
                    "sender": {
                        "user_id": "user-sensitive-123456789",
                        "first_name": "PrivateName",
                    },
                    "body": {
                        "mid": "message-sensitive-123456789",
                        "text": "/задачи private payload",
                    },
                    "access_token": "do-not-log",
                },
            },
        )

    assert response.status_code == 200
    assert "MAX webhook raw event debug shape" in caplog.text
    assert "MAX webhook normalized event debug shape" in caplog.text
    assert "message" in caplog.text
    assert "body" in caplog.text
    assert "chat...6789" in caplog.text
    assert "user...6789" in caplog.text
    assert "mess...6789" in caplog.text
    assert "PrivateName" not in caplog.text
    assert "/задачи private payload" not in caplog.text
    assert "do-not-log" not in caplog.text


def test_max_bot_webhook_chat_title_candidate_debug_masks_values() -> None:
    debug_items = bot_max._build_chat_title_candidate_debug(
        {"body": {"chat": {"title": "Тестовый секретный чат"}}}
    )

    body_chat_title = next(item for item in debug_items if item["path"] == "body.chat.title")

    assert body_chat_title["value_present"] is True
    assert body_chat_title["value_length"] == len("Тестовый секретный чат")
    assert body_chat_title["value_preview"] != "Тестовый секретный чат"


def test_max_bot_webhook_accepts_raw_max_like_event(bot_client: TestClient) -> None:
    response = bot_client.post(
        "/api/bot/max/webhook",
        json={
            "update_type": "message_created",
            "message": {
                "recipient": {"chat_id": "chat-1"},
                "sender": {"user_id": "user-1"},
                "body": {
                    "mid": "message-1",
                    "text": "/задачи",
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["is_command"] is True
    assert payload["action"] == "reply_prepared"
    assert payload["command"] == {"raw_text": "/задачи", "type": "list_tasks"}
    assert payload["outbound"]["chat_id"] == "chat-1"


def test_max_bot_webhook_ignores_unsupported_event(bot_client: TestClient) -> None:
    response = bot_client.post(
        "/api/bot/max/webhook",
        json={
            "update_type": "bot_started",
            "user": {"user_id": "user-1"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["is_command"] is False
    assert payload["action"] == "ignored"
    assert payload["response_text"] == "Event ignored: unsupported MAX event type or non-text message."


def test_max_bot_webhook_ignores_empty_text(bot_client: TestClient) -> None:
    response = bot_client.post(
        "/api/bot/max/webhook",
        json={
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-1",
            "text": "   ",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["is_command"] is False
    assert payload["action"] == "ignored"
    assert payload["response_text"] == "Event ignored: empty text."


def test_max_bot_webhook_normalizes_unknown_command(bot_client: TestClient) -> None:
    response = bot_client.post(
        "/api/bot/max/webhook",
        json={
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-1",
            "text": "/unknown@max_secretary_bot создать отчет",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["action"] == "error"
    assert payload["is_command"] is True
    assert payload["command"] == {
        "type": "unknown",
        "raw_text": "/unknown@max_secretary_bot создать отчет",
        "name": "unknown",
        "args": "создать отчет",
    }
    assert payload["response_text"] == "Неизвестная команда: /unknown"
    assert payload["outbound"]["sent"] is False


def test_max_bot_webhook_validates_normalized_event(bot_client: TestClient) -> None:
    response = bot_client.post(
        "/api/bot/max/webhook",
        json={
            "chat_id": "chat-1",
            "text": "/задачи",
        },
    )

    assert response.status_code == 422


def test_max_bot_webhook_returns_create_task_command_with_deadline_clarification(bot_client: TestClient) -> None:
    response = bot_client.post(
        "/api/bot/max/webhook",
        json={
            "chat_id": "chat-1",
            "user_id": "user-1",
            "message_id": "message-1",
            "text": "/задача только название",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["action"] == "reply_prepared"
    assert payload["command"]["type"] == "create_task"
    assert payload["command"]["title"] == "только название"
    assert payload["command"]["source_text"] == "только название"
    assert payload["command"]["deadline_at"] is None
    assert payload["command"]["deadline_raw"] is None
    assert payload["command"]["needs_deadline_clarification"] is True
    assert payload["outbound"]["sent"] is False
    assert payload["response_text"] == "Команда распознана."
