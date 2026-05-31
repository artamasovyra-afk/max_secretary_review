from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, parse_task_number_allowlist
from app.db.base import import_all_models
from app.db.session import get_session_factory
from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN
from app.modules.chats.models import Chat
from app.modules.chats.settings import parse_chat_daily_summary_settings
from app.modules.notifications.max_sender import MaxSender, OutboundPurpose
from app.modules.notifications.max_sender_factory import build_max_sender
from app.modules.notifications.repository import NotificationDeliveryRepository
from app.modules.notifications.service import NotificationDeliveryService
from app.modules.notifications.templates import PersonalNotificationTemplate, build_personal_task_notification
from app.modules.integrations.max.deep_links import build_max_webapp_deep_link
from app.modules.reminders.manager_summary import (
    DailyManagerSummary,
    DailyManagerSummaryRepository,
    DailyManagerSummaryService,
)
from app.modules.reminders.repository import ReminderRepository
from app.modules.reminders.schemas import DailySummaryPayload, ReminderPayload, ReminderTaskPayload, ReminderType
from app.modules.reminders.service import ReminderService
from app.modules.tasks.deadline_parser import DEFAULT_TIMEZONE
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.scheduled_repository import ScheduledTaskRepository
from app.modules.tasks.scheduled_service import ScheduledTaskService
from app.modules.tasks.service import TaskService

logger = logging.getLogger(__name__)

CHAT_DEADLINE_REPLACED_REMINDER_TYPES = frozenset(
    {
        ReminderType.BEFORE_DEADLINE,
        ReminderType.AT_DEADLINE,
        ReminderType.AFTER_DEADLINE,
        ReminderType.NO_RESPONSE_AFTER_DEADLINE,
    }
)


@dataclass
class ReminderJobResult:
    tasks_processed: int = 0
    reminders_sent: int = 0
    tasks_marked_overdue: int = 0
    summaries_sent: int = 0
    summaries_generated: int = 0
    summaries_skipped: int = 0
    scheduled_tasks_processed: int = 0
    scheduled_tasks_created: int = 0
    scheduled_tasks_failed: int = 0
    scheduled_tasks_deactivated: int = 0
    reminders_skipped: int = 0
    reminders_failed: int = 0


class ReminderJobRunner:
    def __init__(
        self,
        *,
        service: ReminderService,
        repository: ReminderRepository,
        sender: MaxSender,
        session: AsyncSession | None = None,
        notification_delivery_service: NotificationDeliveryService | None = None,
        manager_summary_repository: DailyManagerSummaryRepository | None = None,
        scheduled_task_service: ScheduledTaskService | None = None,
        webapp_base_url: str = "https://maxsecretary.ru",
        max_bot_username: str = "",
        task_deadline_chat_reminders_enabled: bool = False,
    ) -> None:
        self.service = service
        self.repository = repository
        self.sender = sender
        self.session = session
        self.notification_delivery_service = notification_delivery_service
        self.manager_summary_repository = manager_summary_repository
        self.scheduled_task_service = scheduled_task_service
        self.webapp_base_url = webapp_base_url.rstrip("/")
        self.max_bot_username = max_bot_username
        self.task_deadline_chat_reminders_enabled = task_deadline_chat_reminders_enabled

    async def run_due_reminders(self, now: datetime | None = None) -> ReminderJobResult:
        now = now or self._now()
        payloads = [
            await self.service.find_tasks_before_deadline(now),
            await self.service.find_tasks_at_deadline(now),
            await self.service.find_tasks_after_deadline(now),
            await self.service.find_tasks_without_response_after_deadline(now),
            await self.service.find_tasks_waiting_acceptance(now),
        ]

        result = ReminderJobResult()
        for payload in payloads:
            if (
                self.notification_delivery_service is not None
                and payload.reminder_type in CHAT_DEADLINE_REPLACED_REMINDER_TYPES
            ):
                continue
            result.tasks_processed += len(payload.tasks)
            result.reminders_sent += await self._send_task_reminders(payload, now=now)
        if self.notification_delivery_service is not None and self.task_deadline_chat_reminders_enabled:
            chat_payloads = [
                await self.service.find_tasks_due_in_one_hour(now),
                await self.service.find_tasks_overdue_for_chat_reminder(now),
            ]
            for payload in chat_payloads:
                result.tasks_processed += len(payload.tasks)
                sent, skipped, failed = await self._send_chat_deadline_reminders(payload)
                result.reminders_sent += sent
                result.reminders_skipped += skipped
                result.reminders_failed += failed
        return result

    async def run_daily_summary(self, summary_date: Date | None = None) -> ReminderJobResult:
        summary_date = summary_date or self._now().date()
        result = ReminderJobResult()
        user_ids = await self.repository.list_daily_summary_user_ids()

        for user_id in user_ids:
            summary = await self.service.build_daily_summary(user_id=user_id, date=summary_date)
            if not self._summary_has_tasks(summary):
                continue
            if await self._send_user_message(
                user_id=user_id,
                text=self._format_daily_summary(summary),
                reminder_type=ReminderType.DAILY_SUMMARY.value,
            ):
                result.summaries_sent += 1
                result.reminders_sent += 1

        return result

    async def run_daily_manager_summaries(
        self,
        summary_date: Date | None = None,
        now: datetime | None = None,
    ) -> ReminderJobResult:
        summary_date = summary_date or self._now().date()
        now = now or self._now()
        result = ReminderJobResult()
        if self.manager_summary_repository is None:
            logger.info("Daily manager summary skipped", extra={"reason": "repository_not_configured"})
            result.summaries_skipped += 1
            return result

        chats = await self.manager_summary_repository.list_chats_for_daily_manager_summary()
        for chat in chats:
            settings = parse_chat_daily_summary_settings(chat.settings)
            if not settings.daily_summary_enabled:
                logger.info("Daily manager summary skipped", extra={"chat_id": str(chat.id), "reason": "disabled"})
                result.summaries_skipped += 1
                continue
            if settings.daily_summary_time != now.strftime("%H:%M"):
                logger.info(
                    "Daily manager summary skipped",
                    extra={
                        "chat_id": str(chat.id),
                        "reason": "time_mismatch",
                        "configured_time": settings.daily_summary_time,
                    },
                )
                result.summaries_skipped += 1
                continue

            recipient_roles = self._daily_manager_summary_recipient_roles(chat)
            recipient_ids = self._daily_manager_summary_recipient_ids(chat)
            if settings.daily_summary_recipients:
                recipient_ids = [
                    user_id for user_id in settings.daily_summary_recipients if user_id in recipient_roles
                ]
            if not recipient_ids:
                logger.info(
                    "Daily manager summary skipped",
                    extra={"chat_id": str(chat.id), "reason": "no_recipients"},
                )
                result.summaries_skipped += 1
                continue

            for recipient_id in recipient_ids:
                summary_service = DailyManagerSummaryService(
                    repository=self.manager_summary_repository,
                    auth_context=AuthContext(
                        user_id=recipient_id,
                        organization_id=chat.organization_id,
                        chat_id=chat.id,
                        roles=[recipient_roles[recipient_id]],
                        is_super_admin=recipient_roles[recipient_id] == ROLE_SUPER_ADMIN,
                    ),
                )
                summary = await summary_service.build_summary_for_chat(chat.id, recipient_id, summary_date)
                result.summaries_generated += 1
                logger.info(
                    "Daily manager summary generated",
                    extra={
                        "chat_id": str(chat.id),
                        "manager_user_id": str(recipient_id),
                        "total_today": summary.total_today,
                        "overdue": summary.overdue,
                        "waiting_response": summary.waiting_response,
                        "waiting_acceptance": summary.waiting_acceptance,
                    },
                )
                if not self._manager_summary_has_items(summary):
                    logger.info(
                        "Daily manager summary skipped",
                        extra={
                            "chat_id": str(chat.id),
                            "manager_user_id": str(recipient_id),
                            "reason": "empty_summary",
                        },
                    )
                    result.summaries_skipped += 1
                    continue
                background_disabled_reason = self._background_disabled_reason()
                if background_disabled_reason is not None:
                    logger.info(
                        "Daily manager summary skipped",
                        extra={
                            "chat_id": str(chat.id),
                            "manager_user_id": str(recipient_id),
                            "reason": background_disabled_reason,
                        },
                    )
                    result.summaries_skipped += 1
                    continue

                if await self._send_user_message(
                    user_id=recipient_id,
                    text=self._format_daily_manager_summary(chat=chat, summary=summary),
                    reminder_type=ReminderType.DAILY_MANAGER_SUMMARY.value,
                ):
                    logger.info(
                        "Daily manager summary sent",
                        extra={"chat_id": str(chat.id), "manager_user_id": str(recipient_id)},
                    )
                    result.summaries_sent += 1
                    result.reminders_sent += 1
                else:
                    logger.info(
                        "Daily manager summary skipped",
                        extra={
                            "chat_id": str(chat.id),
                            "manager_user_id": str(recipient_id),
                            "reason": "send_failed",
                        },
                    )
                    result.summaries_skipped += 1

        return result

    async def mark_overdue_tasks(self, now: datetime | None = None) -> ReminderJobResult:
        now = now or self._now()
        tasks = await self.repository.find_tasks_to_mark_overdue(now=now)

        for task in tasks:
            await self.repository.mark_task_overdue(task)

        if tasks and self.session is not None:
            await self.session.commit()

        return ReminderJobResult(
            tasks_processed=len(tasks),
            tasks_marked_overdue=len(tasks),
        )

    async def run_due_scheduled_tasks(self, now: datetime | None = None) -> ReminderJobResult:
        if self.scheduled_task_service is None:
            logger.info("Scheduled tasks skipped", extra={"reason": "service_not_configured"})
            return ReminderJobResult()
        scheduled_result = await self.scheduled_task_service.run_due_scheduled_tasks(now=now or self._now())
        return ReminderJobResult(
            scheduled_tasks_processed=scheduled_result.schedules_processed,
            scheduled_tasks_created=scheduled_result.tasks_created,
            scheduled_tasks_failed=scheduled_result.schedules_failed,
            scheduled_tasks_deactivated=scheduled_result.schedules_deactivated,
        )

    async def _send_task_reminders(self, payload: ReminderPayload, *, now: datetime) -> int:
        sent_count = 0
        for task in payload.tasks:
            notification = self._build_task_reminder_notification(task=task, reminder_type=payload.reminder_type)
            attachments = self._task_reminder_attachments(notification, reminder_type=payload.reminder_type)
            for user_id in self._recipient_ids_for_reminder(task, payload.reminder_type):
                if await self.service.is_snoozed(task.task_id, user_id, now):
                    continue
                if self.notification_delivery_service is not None:
                    delivery_result = await self.notification_delivery_service.send_personal_task_notification(
                        user_id=user_id,
                        task_id=task.task_id,
                        message=notification.message,
                        reminder_type=payload.reminder_type.value,
                        attachments=attachments,
                    )
                    if self._delivery_was_sent(delivery_result):
                        sent_count += 1
                else:
                    if await self._send_chat_message(
                        chat_id=task.chat_id,
                        user_id=user_id,
                        text=notification.message,
                        reminder_type=payload.reminder_type.value,
                        attachments=attachments,
                    ):
                        sent_count += 1
        return sent_count

    async def _send_chat_deadline_reminders(self, payload: ReminderPayload) -> tuple[int, int, int]:
        sent_count = 0
        skipped_count = 0
        failed_count = 0
        if self.notification_delivery_service is None:
            return sent_count, skipped_count, failed_count

        for task in payload.tasks:
            if not task.assignee_ids:
                skipped_count += 1
                continue
            try:
                message = await self._format_chat_deadline_reminder(
                    task=task,
                    reminder_type=payload.reminder_type,
                    now=payload.generated_at,
                )
                delivery_result = await self.notification_delivery_service.send_chat_task_notification(
                    chat_id=task.chat_id,
                    task_id=task.task_id,
                    message=message,
                    reminder_type=payload.reminder_type.value,
                    attachments=self._chat_deadline_reminder_attachments(task),
                    purpose=OutboundPurpose.REMINDER,
                )
            except Exception:
                failed_count += 1
                logger.exception(
                    "Chat deadline reminder failed",
                    extra={
                        "task_id": _mask_id(task.task_id),
                        "chat_id": _mask_id(task.chat_id),
                        "reminder_type": payload.reminder_type.value,
                    },
                )
                continue

            delivery_status = self._delivery_status_value(delivery_result)
            if delivery_status == "sent":
                sent_count += 1
            elif delivery_status == "failed":
                failed_count += 1
            else:
                skipped_count += 1

        logger.info(
            "Chat deadline reminders processed",
            extra={
                "reminder_type": payload.reminder_type.value,
                "checked": len(payload.tasks),
                "sent": sent_count,
                "skipped": skipped_count,
                "failed": failed_count,
            },
        )
        return sent_count, skipped_count, failed_count

    def _delivery_was_sent(self, delivery_result: object) -> bool:
        return self._delivery_status_value(delivery_result) == "sent"

    def _delivery_status_value(self, delivery_result: object) -> str:
        status = getattr(delivery_result, "status", None)
        return str(getattr(status, "value", status))

    def _recipient_ids(self, task: ReminderTaskPayload) -> list[UUID]:
        ordered_ids = [
            task.created_by_user_id,
            *task.assignee_ids,
            *task.observer_ids,
        ]
        seen: set[UUID] = set()
        recipients = []
        for user_id in ordered_ids:
            if user_id in seen:
                continue
            seen.add(user_id)
            recipients.append(user_id)
        return recipients

    def _recipient_ids_for_reminder(self, task: ReminderTaskPayload, reminder_type: ReminderType) -> list[UUID]:
        if reminder_type == ReminderType.WAITING_ACCEPTANCE:
            return [task.created_by_user_id]
        return self._recipient_ids(task)

    def _build_task_reminder_notification(
        self,
        *,
        task: ReminderTaskPayload,
        reminder_type: ReminderType,
    ):
        return build_personal_task_notification(
            template=self._notification_template_for_reminder(reminder_type),
            task_id=task.task_id,
            task_number=task.task_number,
            task_title=task.title,
            deadline_at=task.deadline_at,
            creator_display_name=self._format_user_fallback(task.created_by_user_id),
            group_title=self._format_chat_fallback(task.chat_id),
            response_id=task.response_id,
            assignee_display_name=task.response_user_display_name,
            timezone_name=DEFAULT_TIMEZONE,
        )

    def _format_task_reminder(
        self,
        *,
        task: ReminderTaskPayload,
        reminder_type: ReminderType,
    ) -> str:
        return self._build_task_reminder_notification(task=task, reminder_type=reminder_type).message

    def _task_reminder_attachments(
        self,
        notification,
        *,
        reminder_type: ReminderType,
    ) -> list[dict[str, object]] | None:
        if reminder_type != ReminderType.WAITING_ACCEPTANCE:
            return None
        return [
            {
                "type": "inline_keyboard",
                "payload": {
                    "buttons": [
                        [
                            {
                                "type": "callback",
                                "text": button.label,
                                "payload": button.payload,
                                "intent": "default",
                            }
                            for button in notification.buttons
                        ]
                    ]
                },
            }
        ]

    async def _format_chat_deadline_reminder(
        self,
        *,
        task: ReminderTaskPayload,
        reminder_type: ReminderType,
        now: datetime,
    ) -> str:
        assignee_text = await self._format_assignee_mentions(task.assignee_ids)
        assignee_label = "Исполнители" if len(task.assignee_ids) != 1 else "Исполнитель"
        deadline_label = self._format_deadline(task.deadline_at, now=now)
        task_ref = self._task_ref(task)
        if reminder_type == ReminderType.TASK_DUE_IN_1H:
            return "\n".join(
                [
                    f"⏰ До срока по задаче {task_ref} остался 1 час",
                    "",
                    f"Текст: {task.title}",
                    f"{assignee_label}: {assignee_text}",
                    f"Срок: {deadline_label}",
                ]
            )
        return "\n".join(
            [
                f"🔴 Срок по задаче {task_ref} истек",
                "",
                f"Текст: {task.title}",
                f"{assignee_label}: {assignee_text}",
                f"Срок: {deadline_label}",
            ]
        )

    async def _format_assignee_mentions(self, assignee_ids: list[UUID]) -> str:
        mentions = []
        for user_id in assignee_ids:
            user = await self.repository.get_user(user_id)
            display_name = self._display_name(user)
            max_user_id = getattr(user, "max_user_id", None)
            if isinstance(max_user_id, str) and max_user_id.strip():
                mentions.append(f"[@{display_name}](max://user/{max_user_id.strip()})")
            else:
                mentions.append(display_name)
        return ", ".join(mentions) if mentions else "@исполнитель"

    def _display_name(self, user: object | None) -> str:
        for field_name in ("display_name", "username"):
            value = getattr(user, field_name, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "исполнитель"

    def _format_deadline(self, deadline_at: datetime | None, *, now: datetime | None = None) -> str:
        if deadline_at is None:
            return "не указан"
        zone = ZoneInfo(DEFAULT_TIMEZONE)
        local_deadline = deadline_at.astimezone(zone)
        local_now = (now or self._now()).astimezone(zone)
        if local_deadline.date() == local_now.date():
            return f"сегодня {local_deadline:%H:%M}"
        if local_deadline.date() == (local_now.date() + Date.resolution):
            return f"завтра {local_deadline:%H:%M}"
        if local_deadline.year == local_now.year:
            return f"{local_deadline:%d.%m %H:%M}"
        return f"{local_deadline:%d.%m.%Y %H:%M}"

    def _task_ref(self, task: ReminderTaskPayload) -> str:
        if task.task_number is not None:
            return f"#{task.task_number}"
        return "#?"

    def _chat_deadline_reminder_attachments(self, task: ReminderTaskPayload) -> list[dict[str, object]]:
        return [
            {
                "type": "inline_keyboard",
                "payload": {
                    "buttons": [
                        [
                            {
                                "type": "link",
                                "text": "Открыть задачу",
                                "url": build_max_webapp_deep_link(
                                    bot_username=self.max_bot_username,
                                    webapp_base_url=self.webapp_base_url,
                                    startapp=f"task_{task.task_number}" if task.task_number is not None else "my_tasks",
                                    fallback_path="tasks",
                                ),
                            }
                        ]
                    ]
                },
            }
        ]

    def _notification_template_for_reminder(self, reminder_type: ReminderType) -> PersonalNotificationTemplate:
        if reminder_type in {ReminderType.BEFORE_DEADLINE, ReminderType.AT_DEADLINE}:
            return PersonalNotificationTemplate.DEADLINE_SOON
        if reminder_type == ReminderType.NO_RESPONSE_AFTER_DEADLINE:
            return PersonalNotificationTemplate.REPORT_EXPECTED
        if reminder_type == ReminderType.WAITING_ACCEPTANCE:
            return PersonalNotificationTemplate.RESPONSE_WAITING_ACCEPTANCE
        return PersonalNotificationTemplate.DEADLINE_EXPIRED

    def _format_user_fallback(self, user_id: UUID) -> str:
        return f"Пользователь #{str(user_id)[-8:]}"

    def _format_chat_fallback(self, chat_id: UUID) -> str:
        return f"Группа #{str(chat_id)[-8:]}"

    async def _send_user_message(self, *, user_id: UUID, text: str, reminder_type: str) -> bool:
        background_disabled_reason = self._background_disabled_reason()
        if background_disabled_reason is not None:
            logger.info(
                "MAX user notification skipped",
                extra={"user_id": str(user_id), "reason": background_disabled_reason},
            )
            return False
        max_user_id = await self._resolve_max_user_id(user_id)
        if max_user_id is None:
            logger.info(
                "MAX user notification skipped",
                extra={"user_id": str(user_id), "reason": "missing_max_user_id"},
            )
            return False
        outbound = self.sender.send_message(
            chat_id=None,
            user_id=max_user_id,
            text=text,
            purpose=OutboundPurpose.REMINDER,
            reminder_type=reminder_type,
        )
        return bool(getattr(outbound, "sent", False))

    async def _send_chat_message(
        self,
        *,
        chat_id: UUID,
        user_id: UUID,
        text: str,
        reminder_type: str,
        attachments: list[dict[str, object]] | None = None,
    ) -> bool:
        background_disabled_reason = self._background_disabled_reason()
        if background_disabled_reason is not None:
            logger.info(
                "MAX chat notification skipped",
                extra={"chat_id": str(chat_id), "user_id": str(user_id), "reason": background_disabled_reason},
            )
            return False
        max_user_id = await self._resolve_max_user_id(user_id)
        max_chat_id = await self._resolve_max_chat_id(chat_id)
        if max_user_id is None or max_chat_id is None:
            logger.info(
                "MAX chat notification skipped",
                extra={
                    "chat_id": str(chat_id),
                    "user_id": str(user_id),
                    "reason": "missing_max_recipient_id",
                    "missing_user": max_user_id is None,
                    "missing_chat": max_chat_id is None,
                },
            )
            return False
        outbound = self.sender.send_message(
            chat_id=max_chat_id,
            user_id=max_user_id,
            text=text,
            attachments=attachments,
            purpose=OutboundPurpose.REMINDER,
            reminder_type=reminder_type,
        )
        return bool(getattr(outbound, "sent", False))

    async def _resolve_max_user_id(self, user_id: UUID) -> str | None:
        get_user = getattr(self.repository, "get_user", None)
        if get_user is None:
            return None
        user = await get_user(user_id)
        max_user_id = getattr(user, "max_user_id", None)
        if isinstance(max_user_id, str) and max_user_id.strip():
            return max_user_id.strip()
        return None

    async def _resolve_max_chat_id(self, chat_id: UUID) -> str | None:
        get_chat = getattr(self.repository, "get_chat", None)
        if get_chat is None:
            return None
        chat = await get_chat(chat_id)
        max_chat_id = getattr(chat, "max_chat_id", None)
        if isinstance(max_chat_id, str) and max_chat_id.strip():
            return max_chat_id.strip()
        return None

    def _background_disabled_reason(self) -> str | None:
        if not getattr(self.sender, "enabled", False):
            return "sender_disabled"
        if not getattr(self.sender, "background_enabled", True):
            return "background_disabled"
        return None

    def _format_daily_summary(self, summary: DailySummaryPayload) -> str:
        return "\n".join(
            [
                f"daily_summary: {summary.date.isoformat()}",
                f"my_tasks: {len(summary.my_tasks)}",
                f"created_by_me: {len(summary.created_by_me)}",
                f"observed_by_me: {len(summary.observed_by_me)}",
                f"waiting_my_response: {len(summary.waiting_my_response)}",
                f"waiting_my_acceptance: {len(summary.waiting_my_acceptance)}",
                f"overdue: {len(summary.overdue)}",
                f"today: {len(summary.today)}",
            ]
        )

    def _summary_has_tasks(self, summary: DailySummaryPayload) -> bool:
        return any(
            (
                summary.my_tasks,
                summary.created_by_me,
                summary.observed_by_me,
                summary.waiting_my_response,
                summary.waiting_my_acceptance,
                summary.overdue,
                summary.today,
            )
        )

    def _daily_manager_summary_recipient_roles(self, chat: Chat) -> dict[UUID, str]:
        roles: dict[UUID, str] = {}
        for member in chat.members:
            if not member.is_active or member.role not in {ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN}:
                continue
            roles[member.user_id] = member.role
        return roles

    def _daily_manager_summary_recipient_ids(self, chat: Chat) -> list[UUID]:
        return sorted(self._daily_manager_summary_recipient_roles(chat), key=str)

    def _manager_summary_has_items(self, summary: DailyManagerSummary) -> bool:
        return any(
            (
                summary.total_today,
                summary.overdue,
                summary.waiting_response,
                summary.waiting_acceptance,
            )
        )

    def _format_daily_manager_summary(self, *, chat: Chat, summary: DailyManagerSummary) -> str:
        return "\n".join(
            [
                f"daily_manager_summary: {summary.date.isoformat()}",
                f"chat: {chat.title}",
                f"total_today: {summary.total_today}",
                f"overdue: {summary.overdue}",
                f"waiting_response: {summary.waiting_response}",
                f"waiting_acceptance: {summary.waiting_acceptance}",
                f"top_overdue: {len(summary.top_overdue_items)}",
                f"pending_acceptance: {len(summary.pending_acceptance_items)}",
            ]
        )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)


def _mask_id(value: object) -> str:
    text = str(value)
    if len(text) <= 8:
        return text
    return f"...{text[-8:]}"


async def run_due_reminders() -> ReminderJobResult:
    async with get_session_factory()() as session:
        runner = _build_runner(session)
        return await runner.run_due_reminders()


async def run_daily_summary() -> ReminderJobResult:
    async with get_session_factory()() as session:
        runner = _build_runner(session)
        return await runner.run_daily_summary()


async def run_daily_manager_summaries() -> ReminderJobResult:
    async with get_session_factory()() as session:
        runner = _build_runner(session)
        return await runner.run_daily_manager_summaries()


async def mark_overdue_tasks() -> ReminderJobResult:
    async with get_session_factory()() as session:
        runner = _build_runner(session)
        return await runner.mark_overdue_tasks()


async def run_due_scheduled_tasks() -> ReminderJobResult:
    async with get_session_factory()() as session:
        runner = _build_runner(session)
        return await runner.run_due_scheduled_tasks()


def _build_runner(session: AsyncSession) -> ReminderJobRunner:
    import_all_models()
    settings = get_settings()
    repository = ReminderRepository(session)
    service = ReminderService(
        repository=repository,
        session=session,
        overdue_notification_lookback=timedelta(hours=settings.task_overdue_notification_lookback_hours),
        task_deadline_reminder_allowed_task_numbers=parse_task_number_allowlist(
            settings.task_deadline_reminder_allowed_task_numbers
        ),
    )
    sender = build_max_sender()
    notification_repository = NotificationDeliveryRepository(session)
    notification_delivery_service = NotificationDeliveryService(
        repository=notification_repository,
        sender=sender,
        session=session,
    )
    manager_summary_repository = DailyManagerSummaryRepository(session)
    scheduled_task_service = ScheduledTaskService(
        repository=ScheduledTaskRepository(session),
        session=session,
        task_service=TaskService(repository=TaskRepository(session), session=session),
    )
    return ReminderJobRunner(
        service=service,
        repository=repository,
        sender=sender,
        session=session,
        notification_delivery_service=notification_delivery_service,
        manager_summary_repository=manager_summary_repository,
        scheduled_task_service=scheduled_task_service,
        webapp_base_url=settings.webapp_base_url,
        max_bot_username=settings.max_bot_username,
        task_deadline_chat_reminders_enabled=settings.task_deadline_chat_reminders_enabled,
    )
