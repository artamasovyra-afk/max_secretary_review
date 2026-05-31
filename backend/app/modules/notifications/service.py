from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bot.schemas import BotOutboundMessage
from app.modules.notifications.enums import DeliveryStatus
from app.modules.notifications.max_sender import MaxSender, OutboundPurpose
from app.modules.notifications.models import NotificationDelivery
from app.modules.notifications.repository import NotificationDeliveryRepository

MAX_DM_CHANNEL = "max_dm"
MAX_GROUP_FALLBACK_CHANNEL = "max_group"
MAX_CHAT_CHANNEL = "max_chat"
SENSITIVE_ERROR_PATTERNS = (
    re.compile(r"(token=)[^&\s]+", flags=re.IGNORECASE),
    re.compile(r"(password=)[^&\s]+", flags=re.IGNORECASE),
    re.compile(r"(webhook/)[A-Za-z0-9_-]+", flags=re.IGNORECASE),
)


@dataclass
class NotificationDeliveryResult:
    task_id: UUID
    user_id: UUID | None
    status: DeliveryStatus
    primary_delivery: NotificationDelivery
    chat_id: UUID | None = None
    fallback_delivery: NotificationDelivery | None = None


MISSING_MAX_USER_ID_ERROR = "missing_max_user_id"
MISSING_MAX_CHAT_ID_ERROR = "missing_max_chat_id"
BACKGROUND_DISABLED_ERROR = "background_disabled"
CHAT_NOT_ACTIVE_ERROR = "chat_not_active"
CHAT_DEADLINE_REMINDERS_DISABLED_ERROR = "chat_deadline_reminders_disabled"
CHAT_DEADLINE_REMINDER_TYPES = frozenset({"task_due_in_1h", "task_overdue"})
DEADLINE_REMINDERS_ENABLED_KEY = "deadline_reminders_enabled"


class NotificationDeliveryService:
    def __init__(
        self,
        *,
        repository: NotificationDeliveryRepository,
        sender: MaxSender,
        session: AsyncSession | None = None,
        dedup_window: timedelta | None = None,
    ) -> None:
        self.repository = repository
        self.sender = sender
        self.session = session
        self.dedup_window = dedup_window or timedelta(hours=1)

    async def send_personal_task_notification(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        message: str,
        reminder_type: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        purpose: OutboundPurpose | str = OutboundPurpose.REMINDER,
        allow_group_fallback: bool = True,
    ) -> NotificationDeliveryResult:
        task = await self.repository.get_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        recent_delivery = await self.repository.find_recent_delivery(
            task_id=task_id,
            user_id=user_id,
            channel=MAX_DM_CHANNEL,
            reminder_type=reminder_type,
            since=self._now() - self.dedup_window,
        )
        if recent_delivery is not None:
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=user_id,
                status=DeliveryStatus.SKIPPED,
                primary_delivery=recent_delivery,
            )

        primary_delivery = await self.repository.create_delivery(
            task_id=task_id,
            user_id=user_id,
            channel=MAX_DM_CHANNEL,
            reminder_type=reminder_type,
        )

        disabled = self._background_disabled()
        if disabled is not None:
            error_code, error_message = disabled
            await self.repository.update_delivery(
                primary_delivery,
                status=DeliveryStatus.SKIPPED,
                error_code=error_code,
                error_message=error_message,
            )
            await self._commit()
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=user_id,
                status=DeliveryStatus.SKIPPED,
                primary_delivery=primary_delivery,
            )

        max_user_id = await self._resolve_max_user_id(user_id)
        if max_user_id is None:
            await self.repository.update_delivery(
                primary_delivery,
                status=DeliveryStatus.DM_UNAVAILABLE,
                error_code=MISSING_MAX_USER_ID_ERROR,
                error_message="MAX external user id is not available for this user.",
            )
            await self._commit()
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=user_id,
                status=DeliveryStatus.DM_UNAVAILABLE,
                primary_delivery=primary_delivery,
            )

        outbound = self.sender.send_message(
            chat_id=None,
            user_id=max_user_id,
            text=message,
            attachments=attachments,
            purpose=purpose,
            reminder_type=reminder_type,
        )

        if outbound.sent:
            await self.repository.update_delivery(
                primary_delivery,
                status=DeliveryStatus.SENT,
                sent_at=self._now(),
            )
            await self._commit()
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=user_id,
                status=DeliveryStatus.SENT,
                primary_delivery=primary_delivery,
            )

        if self._is_dm_unavailable(outbound):
            await self.repository.update_delivery(
                primary_delivery,
                status=DeliveryStatus.DM_UNAVAILABLE,
                error_code=self._error_code(outbound, default="dm_unavailable"),
                error_message=self._safe_error_message(outbound),
            )
            if not allow_group_fallback:
                await self._commit()
                return NotificationDeliveryResult(
                    task_id=task_id,
                    user_id=user_id,
                    status=DeliveryStatus.DM_UNAVAILABLE,
                    primary_delivery=primary_delivery,
                )
            fallback_delivery = await self._send_group_fallback(
                task_id=task_id,
                user_id=user_id,
                chat_id=task.chat_id,
                message=message,
                reminder_type=reminder_type,
                attachments=attachments,
                purpose=purpose,
            )
            await self._commit()
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=user_id,
                status=DeliveryStatus(fallback_delivery.status),
                primary_delivery=primary_delivery,
                fallback_delivery=fallback_delivery,
            )

        await self.repository.update_delivery(
            primary_delivery,
            status=DeliveryStatus.FAILED,
            error_code=self._error_code(outbound, default="send_failed"),
            error_message=self._safe_error_message(outbound),
        )
        await self._commit()
        return NotificationDeliveryResult(
            task_id=task_id,
            user_id=user_id,
            status=DeliveryStatus.FAILED,
            primary_delivery=primary_delivery,
        )

    async def send_chat_task_notification(
        self,
        *,
        chat_id: UUID,
        task_id: UUID,
        message: str,
        reminder_type: str,
        attachments: list[dict[str, Any]] | None = None,
        purpose: OutboundPurpose | str = OutboundPurpose.REMINDER,
        dedup_since: datetime | None = None,
    ) -> NotificationDeliveryResult:
        task = await self.repository.get_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        existing_delivery = await self.repository.find_recent_delivery(
            task_id=task_id,
            chat_id=chat_id,
            channel=MAX_CHAT_CHANNEL,
            reminder_type=reminder_type,
            since=dedup_since,
        )
        if existing_delivery is not None:
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=None,
                chat_id=chat_id,
                status=DeliveryStatus.SKIPPED,
                primary_delivery=existing_delivery,
            )

        delivery = await self.repository.create_delivery(
            task_id=task_id,
            chat_id=chat_id,
            channel=MAX_CHAT_CHANNEL,
            reminder_type=reminder_type,
        )

        disabled = self._background_disabled()
        if disabled is not None:
            error_code, error_message = disabled
            await self.repository.update_delivery(
                delivery,
                status=DeliveryStatus.SKIPPED,
                error_code=error_code,
                error_message=error_message,
            )
            await self._commit()
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=None,
                chat_id=chat_id,
                status=DeliveryStatus.SKIPPED,
                primary_delivery=delivery,
            )

        chat = await self.repository.get_chat(chat_id)
        max_chat_id = self._max_chat_id_from_chat(chat)
        if max_chat_id is None:
            await self.repository.update_delivery(
                delivery,
                status=DeliveryStatus.SKIPPED,
                error_code=MISSING_MAX_CHAT_ID_ERROR,
                error_message="MAX external chat id is not available for this chat.",
            )
            await self._commit()
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=None,
                chat_id=chat_id,
                status=DeliveryStatus.SKIPPED,
                primary_delivery=delivery,
            )
        chat_status = str(getattr(chat, "status", "active") or "active") if chat is not None else "active"
        if chat_status != "active":
            await self.repository.update_delivery(
                delivery,
                status=DeliveryStatus.SKIPPED,
                error_code=CHAT_NOT_ACTIVE_ERROR,
                error_message="Chat is not active for MAX chat notifications.",
            )
            await self._commit()
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=None,
                chat_id=chat_id,
                status=DeliveryStatus.SKIPPED,
                primary_delivery=delivery,
            )

        if (
            reminder_type in CHAT_DEADLINE_REMINDER_TYPES
            and not self._chat_deadline_reminders_enabled(chat)
        ):
            await self.repository.update_delivery(
                delivery,
                status=DeliveryStatus.SKIPPED,
                error_code=CHAT_DEADLINE_REMINDERS_DISABLED_ERROR,
                error_message="Chat deadline reminders are disabled for this chat.",
            )
            await self._commit()
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=None,
                chat_id=chat_id,
                status=DeliveryStatus.SKIPPED,
                primary_delivery=delivery,
            )

        outbound = self.sender.send_message(
            chat_id=max_chat_id,
            user_id=None,
            text=message,
            attachments=attachments,
            purpose=purpose,
            reminder_type=reminder_type,
        )
        if outbound.sent:
            await self.repository.update_delivery(
                delivery,
                status=DeliveryStatus.SENT,
                sent_at=self._now(),
            )
            await self._commit()
            return NotificationDeliveryResult(
                task_id=task_id,
                user_id=None,
                chat_id=chat_id,
                status=DeliveryStatus.SENT,
                primary_delivery=delivery,
            )

        await self.repository.update_delivery(
            delivery,
            status=DeliveryStatus.FAILED,
            error_code=self._error_code(outbound, default="send_failed"),
            error_message=self._safe_error_message(outbound),
        )
        await self._commit()
        return NotificationDeliveryResult(
            task_id=task_id,
            user_id=None,
            chat_id=chat_id,
            status=DeliveryStatus.FAILED,
            primary_delivery=delivery,
        )

    async def _send_group_fallback(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        chat_id: UUID,
        message: str,
        reminder_type: str | None,
        attachments: list[dict[str, Any]] | None = None,
        purpose: OutboundPurpose | str = OutboundPurpose.REMINDER,
    ) -> NotificationDelivery:
        fallback_delivery = await self.repository.create_delivery(
            task_id=task_id,
            user_id=user_id,
            channel=MAX_GROUP_FALLBACK_CHANNEL,
            reminder_type=reminder_type,
        )
        max_chat_id = await self._resolve_max_chat_id(chat_id)
        if max_chat_id is None:
            return await self.repository.update_delivery(
                fallback_delivery,
                status=DeliveryStatus.FAILED,
                error_code=MISSING_MAX_CHAT_ID_ERROR,
                error_message="MAX external chat id is not available for this chat.",
            )

        outbound = self.sender.send_message(
            chat_id=max_chat_id,
            user_id=None,
            text=message,
            attachments=attachments,
            purpose=purpose,
            reminder_type=reminder_type,
        )
        if outbound.sent:
            return await self.repository.update_delivery(
                fallback_delivery,
                status=DeliveryStatus.SENT,
                sent_at=self._now(),
            )

        return await self.repository.update_delivery(
            fallback_delivery,
            status=DeliveryStatus.FAILED,
            error_code=self._error_code(outbound, default="fallback_failed"),
            error_message=self._safe_error_message(outbound),
        )

    def _is_dm_unavailable(self, outbound: BotOutboundMessage) -> bool:
        reason = outbound.reason.lower()
        return (
            "dm_unavailable" in reason
            or "dm unavailable" in reason
            or "direct message unavailable" in reason
        )

    def _error_code(self, outbound: BotOutboundMessage, *, default: str) -> str:
        raw_code = self._extract_optional_string(outbound, "error_code")
        return raw_code or default

    def _safe_error_message(self, outbound: BotOutboundMessage) -> str:
        message = outbound.reason
        for pattern in SENSITIVE_ERROR_PATTERNS:
            message = pattern.sub(r"\1<redacted>", message)
        return message[:500]

    def _extract_optional_string(self, value: Any, field_name: str) -> str | None:
        raw_value = getattr(value, field_name, None)
        return raw_value if isinstance(raw_value, str) and raw_value else None

    async def _resolve_max_user_id(self, user_id: UUID) -> str | None:
        user = await self.repository.get_user(user_id)
        max_user_id = getattr(user, "max_user_id", None)
        if isinstance(max_user_id, str) and max_user_id.strip():
            return max_user_id.strip()
        return None

    async def _resolve_max_chat_id(self, chat_id: UUID) -> str | None:
        chat = await self.repository.get_chat(chat_id)
        return self._max_chat_id_from_chat(chat)

    def _max_chat_id_from_chat(self, chat: object | None) -> str | None:
        max_chat_id = getattr(chat, "max_chat_id", None)
        if isinstance(max_chat_id, str) and max_chat_id.strip():
            return max_chat_id.strip()
        return None

    def _chat_deadline_reminders_enabled(self, chat: object | None) -> bool:
        settings = getattr(chat, "settings", None)
        if not isinstance(settings, dict):
            return False
        return settings.get(DEADLINE_REMINDERS_ENABLED_KEY) is True

    def _background_disabled(self) -> tuple[str, str] | None:
        if not getattr(self.sender, "enabled", False):
            return "sender_disabled", "MAX sender is disabled."
        if not getattr(self.sender, "background_enabled", True):
            return BACKGROUND_DISABLED_ERROR, "MAX background notifications are disabled."
        return None

    async def _commit(self) -> None:
        if self.session is not None:
            await self.session.commit()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
