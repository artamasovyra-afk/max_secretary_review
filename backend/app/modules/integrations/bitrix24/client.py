from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import time

import httpx
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.modules.integrations.bitrix24.exceptions import (
    Bitrix24ConfigurationError,
    Bitrix24HTTPError,
    Bitrix24RequestError,
    Bitrix24ResponseError,
    Bitrix24TemporaryError,
    Bitrix24TimeoutError,
)

TEMPORARY_STATUS_CODES = {429, 500, 502, 503, 504}


class Bitrix24Client:
    """HTTP adapter for Bitrix24 incoming webhook REST API.

    Bitrix24 incoming webhook URLs contain credentials in the URL path. Keep
    endpoint construction and error handling isolated here so task sync can be
    added later without leaking the webhook URL into logs or business logic.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        webhook_url: SecretStr | str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = settings or get_settings()
        explicit_webhook_url = webhook_url is not None
        if not explicit_webhook_url and not settings.bitrix24_enabled:
            raise Bitrix24ConfigurationError(
                "BITRIX24_ENABLED must be true before creating Bitrix24 REST client."
            )

        configured_webhook_url = (
            webhook_url if explicit_webhook_url else settings.bitrix24_webhook_url
        )
        url_value = self._extract_webhook_url(configured_webhook_url)
        if not url_value:
            raise Bitrix24ConfigurationError(
                "BITRIX24_WEBHOOK_URL is required for Bitrix24 REST client."
            )

        self._webhook_url = SecretStr(url_value)
        self._base_url = f"{url_value.rstrip('/')}/"
        self.timeout_seconds = timeout_seconds or settings.bitrix24_request_timeout_seconds
        self.max_retries = max(0, max_retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=self.timeout_seconds,
            transport=transport,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Bitrix24Client:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return "Bitrix24Client(webhook_url='[redacted-bitrix24-webhook-url]')"

    def call_method(
        self,
        method_name: str,
        payload: Mapping[str, Any] | None = None,
        *,
        retry_safe: bool = False,
    ) -> dict[str, Any]:
        """Call a Bitrix24 REST method through the configured webhook URL."""

        return self._request(
            "POST",
            self._method_path(method_name),
            json=payload or {},
            retry_safe=retry_safe,
        )

    def ping(self) -> dict[str, Any]:
        # Bitrix24 incoming webhooks commonly support profile as a lightweight connectivity check.
        return self.call_method("profile", retry_safe=True)

    def get_task(self, task_id: str | int) -> dict[str, Any]:
        return self.call_method("tasks.task.get", {"taskId": str(task_id)}, retry_safe=True)

    def create_task(self, fields: Mapping[str, Any]) -> dict[str, Any]:
        return self.call_method("tasks.task.add", {"fields": dict(fields)}, retry_safe=False)

    def update_task(self, task_id: str | int, fields: Mapping[str, Any]) -> dict[str, Any]:
        return self.call_method(
            "tasks.task.update",
            {"taskId": str(task_id), "fields": dict(fields)},
            retry_safe=False,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None,
        retry_safe: bool,
    ) -> dict[str, Any]:
        attempts = self.max_retries + 1 if retry_safe else 1
        last_error: Bitrix24RequestError | Bitrix24HTTPError | None = None

        for attempt in range(attempts):
            try:
                response = self._client.request(method, path, json=json)
            except httpx.TimeoutException as exc:
                last_error = Bitrix24TimeoutError("Bitrix24 API request timed out.")
                if not self._should_retry(retry_safe, attempt, attempts):
                    raise last_error from exc
                self._sleep_before_retry(attempt)
                continue
            except httpx.RequestError as exc:
                last_error = Bitrix24RequestError("Bitrix24 API request failed.")
                if not self._should_retry(retry_safe, attempt, attempts):
                    raise last_error from exc
                self._sleep_before_retry(attempt)
                continue

            if response.status_code in TEMPORARY_STATUS_CODES and self._should_retry(
                retry_safe,
                attempt,
                attempts,
            ):
                last_error = self._build_http_error(response)
                self._sleep_before_retry(attempt)
                continue

            if response.status_code >= 400:
                raise self._build_http_error(response)

            return self._parse_json(response)

        if last_error is not None:
            raise last_error
        raise Bitrix24RequestError("Bitrix24 API request failed.")

    def _build_http_error(self, response: httpx.Response) -> Bitrix24HTTPError:
        message = f"Bitrix24 API returned HTTP {response.status_code}."
        response_text = self._safe_response_text(response)
        if response.status_code in TEMPORARY_STATUS_CODES:
            return Bitrix24TemporaryError(
                message,
                status_code=response.status_code,
                response_text=response_text,
            )
        return Bitrix24HTTPError(
            message,
            status_code=response.status_code,
            response_text=response_text,
        )

    def _parse_json(self, response: httpx.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as exc:
            raise Bitrix24ResponseError("Bitrix24 API returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise Bitrix24ResponseError("Bitrix24 API returned unexpected JSON payload.")

        error_code = data.get("error")
        if error_code:
            description = (
                data.get("error_description")
                or data.get("error_description_raw")
                or "unknown error"
            )
            safe_description = self._sanitize_text(str(description))
            raise Bitrix24ResponseError(
                f"Bitrix24 API returned error {error_code}: {safe_description}"
            )

        return data

    def _method_path(self, method_name: str) -> str:
        method = method_name.strip().strip("/")
        if not method:
            raise Bitrix24RequestError("Bitrix24 method name is required.")
        if not method.endswith(".json"):
            method = f"{method}.json"
        return method

    def _safe_response_text(self, response: httpx.Response) -> str | None:
        if not response.content:
            return None
        return self._sanitize_text(response.text[:500])

    def _should_retry(self, retry_safe: bool, attempt: int, attempts: int) -> bool:
        return retry_safe and attempt < attempts - 1

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.backoff_seconds <= 0:
            return
        time.sleep(self.backoff_seconds * (2**attempt))

    def _extract_webhook_url(self, webhook_url: SecretStr | str | None) -> str:
        if isinstance(webhook_url, SecretStr):
            return webhook_url.get_secret_value()
        return str(webhook_url or "")

    def _sanitize_text(self, text: str) -> str:
        webhook_url = self._webhook_url.get_secret_value()
        return text.replace(webhook_url, "[redacted-bitrix24-webhook-url]")
