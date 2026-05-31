from __future__ import annotations

import logging
import secrets
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.bot.callback_service import BotCallbackService
from app.modules.bot.command_parser import BotCommandParser
from app.modules.bot.identity_resolver import MaxIdentityResolver
from app.modules.bot.repository import BotCallbackReceiptRepository, BotPendingActionRepository
from app.modules.bot.schemas import BotWebhookResponse
from app.modules.bot.service import MaxBotWebhookService, normalize_max_event
from app.modules.chats.repository import ChatRepository
from app.modules.notifications.max_sender_factory import build_max_sender
from app.modules.notifications.repository import NotificationDeliveryRepository
from app.modules.notifications.service import NotificationDeliveryService
from app.modules.organizations.repository import OrganizationRepository
from app.modules.reminders.repository import ReminderRepository
from app.modules.reminders.service import ReminderService
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import TaskService
from app.modules.users.repository import UserRepository

router = APIRouter(tags=["bot"])
logger = logging.getLogger(__name__)
MAX_WEBHOOK_DEBUG_SHAPE_DEPTH = 4
MAX_OFFICIAL_WEBHOOK_SECRET_HEADER = "X-Max-Bot-Api-Secret"
MAX_WEBHOOK_SECRET_HEADER = "X-Max-Webhook-Secret"


def verify_max_webhook_access(
    x_max_bot_api_secret: Optional[str] = Header(
        default=None,
        alias=MAX_OFFICIAL_WEBHOOK_SECRET_HEADER,
    ),
    x_max_webhook_secret: Optional[str] = Header(default=None, alias=MAX_WEBHOOK_SECRET_HEADER),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.max_webhook_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )
    expected_secret = settings.max_webhook_secret.get_secret_value()
    if not expected_secret:
        if _is_production(settings):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MAX webhook is not configured",
            )
        return
    provided_secrets = (
        candidate
        for candidate in (x_max_bot_api_secret, x_max_webhook_secret)
        if candidate is not None
    )
    if not any(secrets.compare_digest(candidate, expected_secret) for candidate in provided_secrets):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MAX webhook secret",
        )


def _is_production(settings: Settings) -> bool:
    return settings.app_env.strip().lower() == "production"


def get_max_bot_webhook_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MaxBotWebhookService:
    task_repository = TaskRepository(session)
    chat_repository = ChatRepository(session)
    user_repository = UserRepository(session)
    task_service = TaskService(repository=task_repository, session=session)
    reminder_service = ReminderService(repository=ReminderRepository(session), session=session)
    max_sender = build_max_sender()
    notification_delivery_service = NotificationDeliveryService(
        repository=NotificationDeliveryRepository(session),
        sender=max_sender,
        session=session,
        dedup_window=timedelta(minutes=30),
    )
    return MaxBotWebhookService(
        command_parser=BotCommandParser(bot_username=settings.max_bot_username),
        sender=max_sender,
        chat_repository=chat_repository,
        user_repository=user_repository,
        task_service=task_service,
        identity_resolver=MaxIdentityResolver(
            user_repository=user_repository,
            chat_repository=chat_repository,
            organization_repository=OrganizationRepository(session),
            session=session,
            max_chat_info_client=max_sender.client,
        ),
        callback_service=BotCallbackService(
            task_service=task_service,
            reminder_service=reminder_service,
            webapp_base_url=settings.webapp_base_url,
            max_bot_username=settings.max_bot_username,
            receipt_repository=BotCallbackReceiptRepository(session),
            pending_action_repository=BotPendingActionRepository(session),
            chat_repository=chat_repository,
        ),
        pending_action_repository=BotPendingActionRepository(session),
        notification_delivery_service=notification_delivery_service,
        webapp_base_url=settings.webapp_base_url,
        max_bot_username=settings.max_bot_username,
        task_wizard_delete_user_inputs=settings.task_wizard_delete_user_inputs,
    )


@router.post("/webhook", response_model=BotWebhookResponse)
async def max_bot_webhook(
    payload: dict[str, Any] = Body(...),
    _webhook_access: None = Depends(verify_max_webhook_access),
    service: MaxBotWebhookService = Depends(get_max_bot_webhook_service),
    settings: Settings = Depends(get_settings),
) -> BotWebhookResponse:
    if settings.max_webhook_debug_log:
        logger.info(
            "MAX webhook raw event debug shape: %s",
            _build_raw_event_debug_shape(payload),
        )
        logger.info(
            "MAX webhook chat title candidate debug: %s",
            _build_chat_title_candidate_debug(payload),
        )
    try:
        event = normalize_max_event(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc
    if settings.max_webhook_debug_log:
        logger.info(
            "MAX webhook normalized event debug shape: %s",
            _build_normalized_event_debug_shape(event),
        )
    return await service.handle_event(event)


def _build_raw_event_debug_shape(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "top_level_keys": sorted(str(key) for key in payload.keys()),
        "shape": _shape_without_values(payload),
    }


CHAT_TITLE_DEBUG_PATHS = (
    ("message", "chat", "title"),
    ("message", "chat", "name"),
    ("message", "chat", "display_name"),
    ("message", "chat", "chat_title"),
    ("message", "recipient", "title"),
    ("message", "recipient", "name"),
    ("message", "recipient", "display_name"),
    ("message", "recipient", "chat_title"),
    ("message", "body", "chat", "title"),
    ("message", "body", "chat", "name"),
    ("message", "body", "recipient", "title"),
    ("message", "body", "recipient", "name"),
    ("chat", "title"),
    ("chat", "name"),
    ("recipient", "title"),
    ("recipient", "name"),
    ("recipient", "display_name"),
    ("recipient", "chat_title"),
    ("dialog", "title"),
    ("conversation", "title"),
    ("body", "chat", "title"),
    ("body", "chat", "name"),
    ("body", "recipient", "title"),
    ("body", "recipient", "name"),
    ("message_created", "chat", "title"),
    ("message_created", "chat", "name"),
    ("message_created", "recipient", "title"),
    ("message_created", "recipient", "name"),
)


def _build_chat_title_candidate_debug(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in CHAT_TITLE_DEBUG_PATHS:
        value = _value_at_path(payload, path)
        value_text = value if isinstance(value, str) else None
        candidates.append(
            {
                "path": ".".join(path),
                "value_present": bool(value_text and value_text.strip()),
                "value_length": len(value_text) if value_text else 0,
                "value_preview": _mask_debug_value(value_text) if value_text else None,
            }
        )
    return candidates


def _value_at_path(payload: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _build_normalized_event_debug_shape(event: Any) -> dict[str, Any]:
    callback_payload = getattr(event, "payload", None)
    if callback_payload is not None:
        return {
            "source": getattr(event, "source", None),
            "event_kind": "callback",
            "ignored": getattr(event, "ignored", None),
            "ignore_reason": getattr(event, "ignore_reason", None),
            "raw_update_type": getattr(event, "raw_update_type", None),
            "callback_id": _mask_debug_value(getattr(event, "callback_id", None)),
            "payload_length": len(callback_payload) if isinstance(callback_payload, str) else 0,
            "chat_id": _mask_debug_value(getattr(event, "chat_id", None)),
            "user_id": _mask_debug_value(getattr(event, "user_id", None)),
            "message_id": _mask_debug_value(getattr(event, "message_id", None)),
        }

    text = getattr(event, "text", None)
    reply_to_text = getattr(event, "reply_to_text", None)
    mentions = getattr(event, "mentions", None)
    chat_title = getattr(event, "chat_title", None)
    return {
        "source": getattr(event, "source", None),
        "ignored": getattr(event, "ignored", None),
        "ignore_reason": getattr(event, "ignore_reason", None),
        "chat_id": _mask_debug_value(getattr(event, "chat_id", None)),
        "chat_title_present": bool(chat_title),
        "chat_title_length": len(chat_title) if isinstance(chat_title, str) else 0,
        "chat_title_preview": _mask_debug_value(chat_title),
        "user_id": _mask_debug_value(getattr(event, "user_id", None)),
        "message_id": _mask_debug_value(getattr(event, "message_id", None)),
        "text_length": len(text) if isinstance(text, str) else 0,
        "is_command": text.lstrip().startswith("/") if isinstance(text, str) else False,
        "reply_to_message_id": _mask_debug_value(getattr(event, "reply_to_message_id", None)),
        "reply_to_text_length": len(reply_to_text) if isinstance(reply_to_text, str) else 0,
        "reply_to_author_id": _mask_debug_value(getattr(event, "reply_to_author_id", None)),
        "mention_count": len(mentions) if isinstance(mentions, list) else 0,
    }


def _shape_without_values(value: Any, depth: int = 0) -> Any:
    if depth >= MAX_WEBHOOK_DEBUG_SHAPE_DEPTH:
        return "<max_depth>"
    if isinstance(value, Mapping):
        return {
            str(key): _shape_without_values(child_value, depth + 1)
            for key, child_value in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, str):
        return "str"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if value is None:
        return "null"
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        if not value:
            return []
        return [_shape_without_values(value[0], depth + 1)]
    return type(value).__name__


def _mask_debug_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}...{text[-4:]}"
