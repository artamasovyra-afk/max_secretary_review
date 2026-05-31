from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Optional

from app.modules.bot.schemas import BotOutboundMessage
from app.modules.integrations.max.client import MaxApiClient
from app.modules.integrations.max.exceptions import MaxApiError

logger = logging.getLogger(__name__)


class OutboundPurpose(str, Enum):
    INTERACTIVE = "interactive"
    CALLBACK_ANSWER = "callback_answer"
    BACKGROUND_NOTIFICATION = "background_notification"
    REMINDER = "reminder"
    PING = "ping"
    GROUP_BROADCAST = "group_broadcast"


BACKGROUND_PURPOSES = frozenset(
    {
        OutboundPurpose.BACKGROUND_NOTIFICATION.value,
        OutboundPurpose.REMINDER.value,
        OutboundPurpose.PING.value,
        OutboundPurpose.GROUP_BROADCAST.value,
    }
)


class MaxSender:
    def __init__(
        self,
        *,
        client: MaxApiClient | None = None,
        enabled: bool = False,
        interactive_enabled: bool = True,
        background_enabled: bool = False,
    ) -> None:
        self.client = client
        self.enabled = enabled
        self.interactive_enabled = interactive_enabled
        self.background_enabled = background_enabled

    def send_message(
        self,
        chat_id: Optional[str],
        text: str,
        *,
        user_id: Optional[str] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
        reminder_type: Optional[str] = None,
        purpose: OutboundPurpose | str = OutboundPurpose.INTERACTIVE,
    ) -> BotOutboundMessage:
        purpose_value = _purpose_value(purpose)
        skip_reason = self._skip_reason(purpose_value)
        if skip_reason is None and self.client is not None:
            try:
                response = self.client.send_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text=text,
                    attachments=attachments,
                )
            except MaxApiError as exc:
                logger.warning(
                    "MAX sender real message failed",
                    extra={
                        "chat_id": _mask_recipient_id(chat_id),
                        "user_id": _mask_recipient_id(user_id),
                        "reminder_type": reminder_type,
                    },
                )
                return BotOutboundMessage(
                    adapter="max",
                    method="send_message",
                    chat_id=chat_id,
                    user_id=user_id,
                    text=text,
                    attachments=attachments,
                    reminder_type=reminder_type,
                    purpose=purpose_value,
                    sent=False,
                    reason=str(exc),
                )
            return BotOutboundMessage(
                adapter="max",
                method="send_message",
                chat_id=chat_id,
                user_id=user_id,
                message_id=_message_id_from_response(response),
                text=text,
                attachments=attachments,
                reminder_type=reminder_type,
                purpose=purpose_value,
                sent=True,
                reason="sent via MAX API",
            )

        logger.info(
            "MAX sender stub message",
            extra={
                "chat_id": _mask_recipient_id(chat_id),
                "user_id": _mask_recipient_id(user_id),
                "message_text": _sanitize_message_text(text),
                "reminder_type": reminder_type,
                "purpose": purpose_value,
                "reason": skip_reason,
            },
        )
        return BotOutboundMessage(
            adapter="max",
            method="send_message",
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            attachments=attachments,
            reminder_type=reminder_type,
            purpose=purpose_value,
            sent=False,
            reason=skip_reason or "stub: real MAX API sending is disabled",
        )

    def send_webapp_button_message(
        self,
        *,
        chat_id: Optional[str],
        user_id: Optional[str] = None,
        text: str,
        button_text: str,
        url: str,
        purpose: OutboundPurpose | str = OutboundPurpose.INTERACTIVE,
    ) -> BotOutboundMessage:
        purpose_value = _purpose_value(purpose)
        skip_reason = self._skip_reason(purpose_value)
        if skip_reason is None and self.client is not None:
            try:
                response = self.client.send_webapp_button_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text=text,
                    button_text=button_text,
                    url=url,
                )
            except MaxApiError as exc:
                logger.warning(
                    "MAX sender real WebApp button failed",
                    extra={
                        "chat_id": _mask_recipient_id(chat_id),
                        "user_id": _mask_recipient_id(user_id),
                    },
                )
                return BotOutboundMessage(
                    adapter="max",
                    method="send_webapp_button_message",
                    chat_id=chat_id,
                    user_id=user_id,
                    text=text,
                    purpose=purpose_value,
                    sent=False,
                    reason=str(exc),
                )
            return BotOutboundMessage(
                adapter="max",
                method="send_webapp_button_message",
                chat_id=chat_id,
                user_id=user_id,
                message_id=_message_id_from_response(response),
                text=text,
                purpose=purpose_value,
                sent=True,
                reason="sent via MAX API",
            )

        logger.info(
            "MAX sender stub WebApp button",
            extra={
                "chat_id": _mask_recipient_id(chat_id),
                "user_id": _mask_recipient_id(user_id),
                "button_text": button_text,
                "url": url,
                "purpose": purpose_value,
                "reason": skip_reason,
            },
        )
        return BotOutboundMessage(
            adapter="max",
            method="send_webapp_button_message",
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            purpose=purpose_value,
            sent=False,
            reason=skip_reason or "stub: real MAX API sending is disabled",
        )

    def send_callback_button_message(
        self,
        *,
        chat_id: Optional[str],
        user_id: Optional[str] = None,
        text: str,
        button_text: str,
        payload: str,
        intent: str = "default",
        purpose: OutboundPurpose | str = OutboundPurpose.INTERACTIVE,
    ) -> BotOutboundMessage:
        purpose_value = _purpose_value(purpose)
        skip_reason = self._skip_reason(purpose_value)
        if skip_reason is None and self.client is not None:
            try:
                response = self.client.send_callback_button_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text=text,
                    button_text=button_text,
                    payload=payload,
                    intent=intent,
                )
            except MaxApiError as exc:
                logger.warning(
                    "MAX sender real callback button failed",
                    extra={
                        "chat_id": _mask_recipient_id(chat_id),
                        "user_id": _mask_recipient_id(user_id),
                    },
                )
                return BotOutboundMessage(
                    adapter="max",
                    method="send_callback_button_message",
                    chat_id=chat_id,
                    user_id=user_id,
                    text=text,
                    purpose=purpose_value,
                    sent=False,
                    reason=str(exc),
                )
            return BotOutboundMessage(
                adapter="max",
                method="send_callback_button_message",
                chat_id=chat_id,
                user_id=user_id,
                message_id=_message_id_from_response(response),
                text=text,
                purpose=purpose_value,
                sent=True,
                reason="sent via MAX API",
            )

        logger.info(
            "MAX sender stub callback button",
            extra={
                "chat_id": _mask_recipient_id(chat_id),
                "user_id": _mask_recipient_id(user_id),
                "button_text": button_text,
                "purpose": purpose_value,
                "reason": skip_reason,
            },
        )
        return BotOutboundMessage(
            adapter="max",
            method="send_callback_button_message",
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            purpose=purpose_value,
            sent=False,
            reason=skip_reason or "stub: real MAX API sending is disabled",
        )

    def send_inline_keyboard_message(
        self,
        *,
        chat_id: Optional[str],
        user_id: Optional[str] = None,
        text: str,
        button_rows: list[list[dict[str, Any]]],
        purpose: OutboundPurpose | str = OutboundPurpose.INTERACTIVE,
    ) -> BotOutboundMessage:
        purpose_value = _purpose_value(purpose)
        skip_reason = self._skip_reason(purpose_value)
        if skip_reason is None and self.client is not None:
            try:
                response = self.client.send_inline_keyboard_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text=text,
                    button_rows=button_rows,
                )
            except MaxApiError as exc:
                logger.warning(
                    "MAX sender real inline keyboard failed",
                    extra={
                        "chat_id": _mask_recipient_id(chat_id),
                        "user_id": _mask_recipient_id(user_id),
                    },
                )
                return BotOutboundMessage(
                    adapter="max",
                    method="send_inline_keyboard_message",
                    chat_id=chat_id,
                    user_id=user_id,
                    text=text,
                    attachments=[{"type": "inline_keyboard", "payload": {"buttons": button_rows}}],
                    purpose=purpose_value,
                    sent=False,
                    reason=str(exc),
                )
            return BotOutboundMessage(
                adapter="max",
                method="send_inline_keyboard_message",
                chat_id=chat_id,
                user_id=user_id,
                message_id=_message_id_from_response(response),
                text=text,
                attachments=[{"type": "inline_keyboard", "payload": {"buttons": button_rows}}],
                purpose=purpose_value,
                sent=True,
                reason="sent via MAX API",
            )

        logger.info(
            "MAX sender stub inline keyboard",
            extra={
                "chat_id": _mask_recipient_id(chat_id),
                "user_id": _mask_recipient_id(user_id),
                "button_count": sum(len(row) for row in button_rows),
                "purpose": purpose_value,
                "reason": skip_reason,
            },
        )
        return BotOutboundMessage(
            adapter="max",
            method="send_inline_keyboard_message",
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            attachments=[{"type": "inline_keyboard", "payload": {"buttons": button_rows}}],
            purpose=purpose_value,
            sent=False,
            reason=skip_reason or "stub: real MAX API sending is disabled",
        )

    def answer_callback(
        self,
        *,
        callback_id: str | None,
        notification: str,
        message: dict[str, Any] | None = None,
        purpose: OutboundPurpose | str = OutboundPurpose.CALLBACK_ANSWER,
    ) -> BotOutboundMessage:
        purpose_value = _purpose_value(purpose)
        if not callback_id:
            return BotOutboundMessage(
                adapter="max",
                method="answer_callback",
                chat_id=None,
                text=notification,
                purpose=purpose_value,
                sent=False,
                reason="callback_id is missing",
            )

        skip_reason = self._skip_reason(purpose_value)
        if skip_reason is None and self.client is not None:
            try:
                response = self.client.answer_callback(callback_id=callback_id, notification=notification, message=message)
            except MaxApiError as exc:
                logger.warning(
                    "MAX sender real callback answer failed",
                    extra={"callback_id": _mask_recipient_id(callback_id)},
                )
                return BotOutboundMessage(
                    adapter="max",
                    method="answer_callback",
                    chat_id=None,
                    text=notification,
                    purpose=purpose_value,
                    sent=False,
                    reason=str(exc),
                )
            return BotOutboundMessage(
                adapter="max",
                method="answer_callback",
                chat_id=None,
                message_id=_message_id_from_response(response),
                text=notification,
                purpose=purpose_value,
                sent=True,
                reason="sent via MAX API",
            )

        logger.info(
            "MAX sender stub callback answer",
            extra={
                "callback_id": _mask_recipient_id(callback_id),
                "purpose": purpose_value,
                "reason": skip_reason,
            },
        )
        return BotOutboundMessage(
            adapter="max",
            method="answer_callback",
            chat_id=None,
            text=notification,
            attachments=message.get("attachments") if message else None,
            purpose=purpose_value,
            sent=False,
            reason=skip_reason or "stub: real MAX API sending is disabled",
        )

    def send_task_card(
        self,
        chat_id: str,
        task: dict[str, Any],
        *,
        purpose: OutboundPurpose | str = OutboundPurpose.INTERACTIVE,
    ) -> BotOutboundMessage:
        purpose_value = _purpose_value(purpose)
        skip_reason = self._skip_reason(purpose_value)
        if skip_reason is None and self.client is not None:
            try:
                response = self.client.send_task_card(chat_id=chat_id, task=task)
            except MaxApiError as exc:
                logger.warning("MAX sender real task card failed", extra={"chat_id": _mask_recipient_id(chat_id)})
                return BotOutboundMessage(
                    adapter="max",
                    method="send_task_card",
                    chat_id=chat_id,
                    task=task,
                    purpose=purpose_value,
                    sent=False,
                    reason=str(exc),
                )
            return BotOutboundMessage(
                adapter="max",
                method="send_task_card",
                chat_id=chat_id,
                message_id=_message_id_from_response(response),
                task=task,
                purpose=purpose_value,
                sent=True,
                reason="sent via MAX API",
            )

        logger.info(
            "MAX sender stub task card",
            extra={
                "chat_id": _mask_recipient_id(chat_id),
                "task_id": task.get("id"),
                "task_title": task.get("title"),
                "purpose": purpose_value,
                "reason": skip_reason,
            },
        )
        return BotOutboundMessage(
            adapter="max",
            method="send_task_card",
            chat_id=chat_id,
            task=task,
            purpose=purpose_value,
            sent=False,
            reason=skip_reason or "stub: real MAX API sending is disabled",
        )

    def edit_message(
        self,
        *,
        message_id: str | None,
        text: str,
        attachments: Optional[list[dict[str, Any]]] = None,
        purpose: OutboundPurpose | str = OutboundPurpose.INTERACTIVE,
    ) -> BotOutboundMessage:
        purpose_value = _purpose_value(purpose)
        if not message_id:
            return BotOutboundMessage(
                adapter="max",
                method="edit_message",
                chat_id=None,
                message_id=None,
                text=text,
                attachments=attachments,
                purpose=purpose_value,
                sent=False,
                reason="message_id is missing",
            )

        skip_reason = self._skip_reason(purpose_value)
        if skip_reason is None and self.client is not None:
            try:
                response = self.client.edit_message(message_id=message_id, text=text, attachments=attachments)
            except MaxApiError as exc:
                logger.warning(
                    "MAX sender real message edit failed",
                    extra={"message_id": _mask_recipient_id(message_id)},
                )
                return BotOutboundMessage(
                    adapter="max",
                    method="edit_message",
                    chat_id=None,
                    message_id=message_id,
                    text=text,
                    attachments=attachments,
                    purpose=purpose_value,
                    sent=False,
                    reason=str(exc),
                )
            return BotOutboundMessage(
                adapter="max",
                method="edit_message",
                chat_id=None,
                message_id=_message_id_from_response(response) or message_id,
                text=text,
                attachments=attachments,
                purpose=purpose_value,
                sent=True,
                reason="edited via MAX API",
            )

        logger.info(
            "MAX sender stub message edit",
            extra={
                "message_id": _mask_recipient_id(message_id),
                "message_text": _sanitize_message_text(text),
                "purpose": purpose_value,
                "reason": skip_reason,
            },
        )
        return BotOutboundMessage(
            adapter="max",
            method="edit_message",
            chat_id=None,
            message_id=message_id,
            text=text,
            attachments=attachments,
            purpose=purpose_value,
            sent=False,
            reason=skip_reason or "stub: real MAX API sending is disabled",
        )

    def delete_message(
        self,
        *,
        message_id: str | None,
        chat_id: str | None = None,
        purpose: OutboundPurpose | str = OutboundPurpose.INTERACTIVE,
    ) -> BotOutboundMessage:
        purpose_value = _purpose_value(purpose)
        if not message_id:
            return BotOutboundMessage(
                adapter="max",
                method="delete_message",
                chat_id=chat_id,
                message_id=None,
                purpose=purpose_value,
                sent=False,
                reason="message_id is missing",
            )

        skip_reason = self._skip_reason(purpose_value)
        if skip_reason is None and self.client is not None:
            try:
                self.client.delete_message(message_id=message_id)
            except MaxApiError as exc:
                logger.warning(
                    "MAX sender real message delete failed",
                    extra={
                        "chat_id": _mask_recipient_id(chat_id),
                        "message_id": _mask_recipient_id(message_id),
                    },
                )
                return BotOutboundMessage(
                    adapter="max",
                    method="delete_message",
                    chat_id=chat_id,
                    message_id=message_id,
                    purpose=purpose_value,
                    sent=False,
                    reason=str(exc),
                )
            return BotOutboundMessage(
                adapter="max",
                method="delete_message",
                chat_id=chat_id,
                message_id=message_id,
                purpose=purpose_value,
                sent=True,
                reason="deleted via MAX API",
            )

        logger.info(
            "MAX sender stub message delete",
            extra={
                "chat_id": _mask_recipient_id(chat_id),
                "message_id": _mask_recipient_id(message_id),
                "purpose": purpose_value,
                "reason": skip_reason,
            },
        )
        return BotOutboundMessage(
            adapter="max",
            method="delete_message",
            chat_id=chat_id,
            message_id=message_id,
            purpose=purpose_value,
            sent=False,
            reason=skip_reason or "stub: real MAX API sending is disabled",
        )

    def _skip_reason(self, purpose: str) -> str | None:
        if not self.enabled:
            return "stub: real MAX API sending is disabled"
        if self.client is None:
            return "stub: MAX API client is not configured"
        if purpose in BACKGROUND_PURPOSES:
            if not self.background_enabled:
                return "background_disabled: MAX background notifications are disabled"
            return None
        if not self.interactive_enabled:
            return "interactive_disabled: MAX interactive responses are disabled"
        return None


def _mask_recipient_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if len(value) <= 8:
        return value
    return f"...{value[-8:]}"


def _sanitize_message_text(value: str) -> str:
    return re.sub(r"max://user/[A-Za-z0-9_.:-]+", "max://user/<redacted>", value)


def _purpose_value(purpose: OutboundPurpose | str) -> str:
    if isinstance(purpose, OutboundPurpose):
        return purpose.value
    return str(purpose)


def _message_id_from_response(response: object) -> str | None:
    if not isinstance(response, dict):
        return None
    for path in (
        ("message", "id"),
        ("message", "message_id"),
        ("message", "messageId"),
        ("message", "mid"),
        ("message", "body", "id"),
        ("message", "body", "message_id"),
        ("message", "body", "messageId"),
        ("message", "body", "mid"),
        ("body", "id"),
        ("body", "message_id"),
        ("body", "messageId"),
        ("body", "mid"),
        ("result", "id"),
        ("result", "message_id"),
        ("result", "messageId"),
        ("result", "mid"),
        ("id",),
        ("message_id",),
        ("messageId",),
        ("mid",),
    ):
        value = _nested_response_value(response, path)
        if value:
            return str(value)
    return None


def _nested_response_value(response: dict[str, Any], path: tuple[str, ...]) -> object | None:
    current: object = response
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
