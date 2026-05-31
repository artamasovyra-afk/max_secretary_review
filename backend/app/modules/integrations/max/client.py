from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import time

import httpx
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.modules.integrations.max.exceptions import (
    MaxApiConfigurationError,
    MaxApiHTTPError,
    MaxApiRequestError,
    MaxApiResponseError,
    MaxApiTemporaryError,
    MaxApiTimeoutError,
)
from app.modules.integrations.max.bot_commands import build_bot_commands_patch_payload
from app.modules.integrations.max.schemas import (
    MaxBotInfo,
    MaxSendMessageRequest,
    MaxSendMessageResponse,
    TextFormat,
)

TEMPORARY_STATUS_CODES = {429, 500, 502, 503, 504}


class MaxApiClient:
    """HTTP adapter for MAX Bot API.

    The concrete message endpoint follows the current MAX Bot API shape:
    POST /messages with chat_id or user_id query parameter and an
    Authorization header. If MAX changes payload details, keep that mapping
    isolated in this client.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        base_url: str | None = None,
        bot_token: SecretStr | str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = settings or get_settings()
        self.base_url = (base_url or settings.max_api_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.max_request_timeout_seconds
        self.max_retries = max(0, max_retries)
        self.backoff_seconds = max(0.0, backoff_seconds)

        token = bot_token if bot_token is not None else settings.max_bot_token
        token_value = token.get_secret_value() if isinstance(token, SecretStr) else str(token or "")
        if not token_value:
            raise MaxApiConfigurationError("MAX_BOT_TOKEN is required when MAX_SENDER_ENABLED=true.")
        if not self.base_url:
            raise MaxApiConfigurationError("MAX_API_BASE_URL is required when MAX_SENDER_ENABLED=true.")

        self._bot_token = SecretStr(token_value)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=transport,
            headers={
                "Authorization": token_value,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MaxApiClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def send_message(
        self,
        *,
        chat_id: str | None,
        text: str,
        user_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        link: dict[str, Any] | None = None,
        notify: bool = True,
        format: TextFormat | None = None,
    ) -> dict[str, Any]:
        if not chat_id and not user_id:
            raise MaxApiRequestError("Either chat_id or user_id is required for MAX message sending.")

        params = {"chat_id": chat_id} if chat_id else {"user_id": user_id}
        payload = MaxSendMessageRequest(
            text=text,
            attachments=attachments,
            link=link,
            notify=notify,
            format=format,
        ).model_dump(exclude_none=True)
        response = self._request("POST", "/messages", params=params, json=payload, retry_safe=False)
        return MaxSendMessageResponse.model_validate(response).model_dump()

    def edit_message(
        self,
        *,
        message_id: str,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
        link: dict[str, Any] | None = None,
        notify: bool = True,
        format: TextFormat | None = None,
    ) -> dict[str, Any]:
        if not message_id:
            raise MaxApiRequestError("message_id is required for MAX message editing.")
        payload = MaxSendMessageRequest(
            text=text,
            attachments=attachments,
            link=link,
            notify=notify,
            format=format,
        ).model_dump(exclude_none=True)
        response = self._request(
            "PUT",
            "/messages",
            params={"message_id": message_id},
            json=payload,
            retry_safe=False,
        )
        return MaxSendMessageResponse.model_validate(response).model_dump()

    def delete_message(self, *, message_id: str) -> dict[str, Any]:
        if not message_id:
            raise MaxApiRequestError("message_id is required for MAX message deletion.")
        return self._request(
            "DELETE",
            "/messages",
            params={"message_id": message_id},
            retry_safe=False,
        )

    def send_task_card(self, chat_id: str, task: Mapping[str, Any]) -> dict[str, Any]:
        # TODO: Replace text-only card with native MAX attachments/buttons after final UX is approved.
        return self.send_message(chat_id=chat_id, text=self._format_task_card(task))

    def send_webapp_button_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_text: str,
        url: str,
    ) -> dict[str, Any]:
        return self.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            attachments=build_link_button_attachment(button_text=button_text, url=url),
        )

    def send_callback_button_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_text: str,
        payload: str,
        intent: str = "default",
    ) -> dict[str, Any]:
        return self.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            attachments=build_callback_button_attachment(button_text=button_text, payload=payload, intent=intent),
        )

    def send_inline_keyboard_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_rows: list[list[dict[str, Any]]],
    ) -> dict[str, Any]:
        return self.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            attachments=build_inline_keyboard_attachment(button_rows=button_rows),
        )

    def answer_callback(
        self,
        *,
        callback_id: str,
        notification: str | None = None,
        message: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not callback_id:
            raise MaxApiRequestError("callback_id is required for MAX callback answers.")
        payload: dict[str, Any] = {}
        if notification:
            payload["notification"] = notification
        if message is not None:
            payload["message"] = message
        return self._request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json=payload,
            retry_safe=False,
        )

    def ping(self) -> dict[str, Any]:
        # TODO: Confirm the final bot health endpoint with MAX API docs before enabling production monitoring.
        response = self._request("GET", "/me", retry_safe=True)
        return MaxBotInfo.model_validate(response).model_dump()

    def patch_bot_commands(self, commands: list[Mapping[str, str]]) -> dict[str, Any]:
        payload = build_bot_commands_patch_payload(commands)
        return self._request("PATCH", "/me", json=payload, retry_safe=False)

    def get_chat_admins(self, chat_id: str) -> list[dict[str, str | None]]:
        if not chat_id:
            raise MaxApiRequestError("chat_id is required for MAX chat admin lookup.")
        response = self._request("GET", f"/chats/{chat_id}/members/admins", retry_safe=True)
        return _normalize_chat_admins(response)

    def get_chat_info(self, chat_id: str) -> dict[str, str | None]:
        if not chat_id:
            raise MaxApiRequestError("chat_id is required for MAX chat info lookup.")
        response = self._request("GET", f"/chats/{chat_id}", retry_safe=True)
        return _normalize_chat_info(response)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | None] | None = None,
        json: Mapping[str, Any] | None = None,
        retry_safe: bool,
    ) -> dict[str, Any]:
        attempts = self.max_retries + 1 if retry_safe else 1
        last_error: MaxApiRequestError | MaxApiHTTPError | None = None

        for attempt in range(attempts):
            try:
                response = self._client.request(method, path, params=self._clean_params(params), json=json)
            except httpx.TimeoutException as exc:
                last_error = MaxApiTimeoutError("MAX API request timed out.")
                if not self._should_retry(retry_safe, attempt, attempts):
                    raise last_error from exc
                self._sleep_before_retry(attempt)
                continue
            except httpx.RequestError as exc:
                last_error = MaxApiRequestError("MAX API request failed.")
                if not self._should_retry(retry_safe, attempt, attempts):
                    raise last_error from exc
                self._sleep_before_retry(attempt)
                continue

            if response.status_code in TEMPORARY_STATUS_CODES and self._should_retry(retry_safe, attempt, attempts):
                last_error = self._build_http_error(response)
                self._sleep_before_retry(attempt)
                continue

            if response.status_code >= 400:
                raise self._build_http_error(response)

            return self._parse_json(response)

        if last_error is not None:
            raise last_error
        raise MaxApiRequestError("MAX API request failed.")

    def _build_http_error(self, response: httpx.Response) -> MaxApiHTTPError:
        message = f"MAX API returned HTTP {response.status_code}."
        response_text = self._safe_response_text(response)
        if response.status_code in TEMPORARY_STATUS_CODES:
            return MaxApiTemporaryError(message, status_code=response.status_code, response_text=response_text)
        return MaxApiHTTPError(message, status_code=response.status_code, response_text=response_text)

    def _parse_json(self, response: httpx.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as exc:
            raise MaxApiResponseError("MAX API returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise MaxApiResponseError("MAX API returned unexpected JSON payload.")
        return data

    def _safe_response_text(self, response: httpx.Response) -> str | None:
        if not response.content:
            return None
        return response.text[:500]

    def _should_retry(self, retry_safe: bool, attempt: int, attempts: int) -> bool:
        return retry_safe and attempt < attempts - 1

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.backoff_seconds <= 0:
            return
        time.sleep(self.backoff_seconds * (2**attempt))

    def _clean_params(self, params: Mapping[str, str | None] | None) -> dict[str, str]:
        if not params:
            return {}
        return {key: value for key, value in params.items() if value is not None}

    def _format_task_card(self, task: Mapping[str, Any]) -> str:
        task_ref = task.get("task_ref") or (f"#{task.get('task_number')}" if task.get("task_number") else "")
        title = task.get("title", "")
        status = task.get("status_label") or _task_status_label(task.get("status"))
        header = f"Задача {task_ref} создана ✅" if task_ref else "Задача создана ✅"
        return f"{header}\n\n{title}\nСтатус: {status}"


def _task_status_label(status: object) -> str:
    labels = {
        "new": "Новая",
        "in_progress": "В работе",
        "waiting_response": "Ждет ответа",
        "waiting_acceptance": "Ждет приемки",
        "done": "Выполнена",
        "overdue": "Просрочена",
        "rejected": "Отклонена",
        "cancelled": "Отменена",
    }
    return labels.get(str(status), "В работе")


def _normalize_chat_admins(response: Mapping[str, Any]) -> list[dict[str, str | None]]:
    raw_items = _extract_admin_items(response)
    admins: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for item in raw_items:
        normalized = _normalize_chat_admin_item(item)
        max_user_id = normalized.get("max_user_id")
        if not max_user_id or max_user_id in seen:
            continue
        seen.add(max_user_id)
        admins.append(normalized)
    return admins


def _normalize_chat_info(response: Mapping[str, Any]) -> dict[str, str | None]:
    source = _first_mapping(response, "chat", "conversation", "dialog", "result", "body") or response
    return {
        "title": _first_string(source, "title", "name", "display_name", "chat_title"),
        "type": _first_string(source, "type", "chat_type"),
    }


def _first_mapping(source: Mapping[str, Any], *keys: str) -> Mapping[str, Any] | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return value
    return None


def _extract_admin_items(response: Mapping[str, Any]) -> list[object]:
    for key in ("members", "users", "admins", "items", "data"):
        value = response.get(key)
        if isinstance(value, list):
            return value
    return []


def _normalize_chat_admin_item(item: object) -> dict[str, str | None]:
    if isinstance(item, (str, int)):
        return {"max_user_id": str(item), "username": None, "display_name": None}
    if not isinstance(item, Mapping):
        return {"max_user_id": None, "username": None, "display_name": None}
    user = item.get("user")
    if isinstance(user, Mapping):
        source = {**item, **user}
    else:
        source = item
    max_user_id = _first_string(source, "user_id", "id", "max_user_id", "maxUserId")
    username = _first_string(source, "username", "login")
    display_name = _first_string(source, "display_name", "name", "first_name", "full_name")
    return {
        "max_user_id": max_user_id,
        "username": username,
        "display_name": display_name,
    }


def _first_string(source: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def build_link_button_attachment(*, button_text: str, url: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {
                            "type": "link",
                            "text": button_text,
                            "url": url,
                        }
                    ]
                ]
            },
        }
    ]


def build_inline_keyboard_attachment(*, button_rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": button_rows,
            },
        }
    ]


def build_callback_button_attachment(
    *,
    button_text: str,
    payload: str,
    intent: str = "default",
) -> list[dict[str, Any]]:
    return build_inline_keyboard_attachment(
        button_rows=[
            [
                {
                    "type": "callback",
                    "text": button_text,
                    "payload": payload,
                    "intent": intent,
                }
            ]
        ]
    )
