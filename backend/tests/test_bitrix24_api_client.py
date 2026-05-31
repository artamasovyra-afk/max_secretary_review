from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.integrations.bitrix24.client import Bitrix24Client
from app.modules.integrations.bitrix24.exceptions import (
    Bitrix24ConfigurationError,
    Bitrix24HTTPError,
    Bitrix24RequestError,
    Bitrix24ResponseError,
    Bitrix24TemporaryError,
    Bitrix24TimeoutError,
)

WEBHOOK_URL = "https://portal.example.invalid/rest/1/secret-webhook-token/"


def test_call_method_posts_to_bitrix_webhook_method_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"result": {"ok": True}})

    client = Bitrix24Client(
        webhook_url=SecretStr(WEBHOOK_URL),
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    result = client.call_method("tasks.task.get", {"taskId": "42"}, retry_safe=True)

    assert result == {"result": {"ok": True}}
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/rest/1/secret-webhook-token/tasks.task.get.json"
    assert json.loads(requests[0].read()) == {"taskId": "42"}


def test_method_path_accepts_json_suffix() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"result": {"ok": True}})

    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    client.call_method("profile.json", retry_safe=True)

    assert requests[0].url.path == "/rest/1/secret-webhook-token/profile.json"


def test_call_method_requires_method_name() -> None:
    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )

    with pytest.raises(Bitrix24RequestError, match="method name is required"):
        client.call_method(" ")


def test_create_task_uses_tasks_task_add_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"result": {"task": {"id": 101}}})

    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    result = client.create_task({"TITLE": "Prepare report", "RESPONSIBLE_ID": "123"})

    assert result == {"result": {"task": {"id": 101}}}
    assert requests[0].url.path == "/rest/1/secret-webhook-token/tasks.task.add.json"
    assert json.loads(requests[0].read()) == {
        "fields": {"TITLE": "Prepare report", "RESPONSIBLE_ID": "123"}
    }


def test_update_task_uses_tasks_task_update_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"result": True})

    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    result = client.update_task(101, {"STATUS": "5"})

    assert result == {"result": True}
    assert requests[0].url.path == "/rest/1/secret-webhook-token/tasks.task.update.json"
    assert json.loads(requests[0].read()) == {"taskId": "101", "fields": {"STATUS": "5"}}


def test_get_task_uses_task_id_string() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"result": {"task": {"id": 101}}})

    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    client.get_task(101)

    assert json.loads(requests[0].read()) == {"taskId": "101"}


def test_ping_uses_profile_and_retries_temporary_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json={"result": {"ID": "1", "NAME": "Portal user"}})

    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    result = client.ping()

    assert calls == 2
    assert result["result"]["ID"] == "1"


def test_create_task_does_not_retry_non_idempotent_post() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "temporary"})

    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(Bitrix24TemporaryError, match="HTTP 503"):
        client.create_task({"TITLE": "Prepare report"})

    assert calls == 1


def test_http_error_is_wrapped_without_webhook_url() -> None:
    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: httpx.Response(401, text=WEBHOOK_URL)),
    )

    with pytest.raises(Bitrix24HTTPError) as exc_info:
        client.ping()

    assert exc_info.value.status_code == 401
    assert WEBHOOK_URL not in str(exc_info.value)
    assert WEBHOOK_URL not in (exc_info.value.response_text or "")


def test_timeout_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(Bitrix24TimeoutError, match="timed out"):
        client.ping()


def test_invalid_json_is_wrapped() -> None:
    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="not-json")),
    )

    with pytest.raises(Bitrix24ResponseError, match="invalid JSON"):
        client.ping()


def test_bitrix_api_error_payload_is_wrapped_without_webhook_url() -> None:
    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "error": "ERROR_METHOD_NOT_FOUND",
                    "error_description": f"method not found for {WEBHOOK_URL}",
                },
            )
        ),
    )

    with pytest.raises(Bitrix24ResponseError) as exc_info:
        client.ping()

    assert "ERROR_METHOD_NOT_FOUND" in str(exc_info.value)
    assert WEBHOOK_URL not in str(exc_info.value)


def test_webhook_url_is_required() -> None:
    with pytest.raises(Bitrix24ConfigurationError, match="BITRIX24_WEBHOOK_URL is required"):
        Bitrix24Client(webhook_url="", timeout_seconds=3)


def test_client_requires_enabled_settings_without_explicit_webhook_url() -> None:
    settings = Settings(
        bitrix24_enabled=False,
        bitrix24_webhook_url=SecretStr(WEBHOOK_URL),
    )

    with pytest.raises(Bitrix24ConfigurationError, match="BITRIX24_ENABLED must be true"):
        Bitrix24Client(settings=settings, timeout_seconds=3)


def test_client_can_use_enabled_settings_webhook_url() -> None:
    requests: list[httpx.Request] = []
    settings = Settings(
        bitrix24_enabled=True,
        bitrix24_webhook_url=SecretStr(WEBHOOK_URL),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"result": {"ok": True}})

    client = Bitrix24Client(
        settings=settings,
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    client.ping()

    assert requests[0].url.path == "/rest/1/secret-webhook-token/profile.json"


def test_repr_does_not_expose_webhook_url() -> None:
    client = Bitrix24Client(
        webhook_url=WEBHOOK_URL,
        timeout_seconds=3,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )

    assert WEBHOOK_URL not in repr(client)
    assert "[redacted-bitrix24-webhook-url]" in repr(client)
