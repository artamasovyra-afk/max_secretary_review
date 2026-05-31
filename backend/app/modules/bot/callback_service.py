from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN
from app.modules.bot.callbacks import (
    CallbackAction,
    ParsedCallbackPayload,
    ParsedTaskAssignmentPayload,
    ParsedTaskReportPayload,
    SnoozeValue,
    parse_callback_payload,
    parse_task_assignment_callback_payload,
    parse_task_report_callback_payload,
)
from app.modules.bot.repository import (
    CALLBACK_RECEIPT_FAILED,
    CALLBACK_RECEIPT_PROCESSING,
    PENDING_ACTION_COMPLETED,
    PENDING_ACTION_PENDING,
    PENDING_ACTION_TASK_CREATE_SELECT_ASSIGNEE,
    PENDING_ACTION_CLEANUP_EDITED,
    PENDING_ACTION_CLEANUP_FAILED,
    CallbackReceiptLike,
)
from app.modules.integrations.max.deep_links import build_max_webapp_deep_link
from app.modules.reminders.service import ReminderService, SnoozeDuration
from app.modules.tasks.enums import TaskAssigneeStatus, TaskResponseStatus, TaskStatus
from app.modules.tasks.deadline_parser import DEFAULT_TIMEZONE, as_aware_utc
from app.modules.tasks.schemas import TaskAcceptanceCreate, TaskCreate, TaskResponseCreate
from app.modules.tasks.service import TaskService


class BotCallbackError(Exception):
    """Base callback service error."""


class BotCallbackForbidden(BotCallbackError):
    """Raised when callback actor cannot perform the requested action."""


@dataclass(frozen=True)
class NormalizedCallbackEvent:
    payload: str
    user_id: UUID
    chat_id: UUID | None = None
    message_id: str | None = None
    callback_id: str | None = None


@dataclass(frozen=True)
class BotCallbackResult:
    action: CallbackAction
    task_id: UUID | None
    response_text: str
    webapp_url: str | None = None
    snooze: SnoozeValue | None = None
    pending_action_id: UUID | None = None
    answer_message_text: str | None = None
    answer_message_attachments: list[dict[str, Any]] | None = None


class BotCallbackService:
    LOGICAL_IDEMPOTENCY_WINDOW_SECONDS = 60
    _LOGICAL_IDEMPOTENT_ACTIONS: set[CallbackAction] = {"start", "confirm", "accept", "reject", "snooze"}

    def __init__(
        self,
        *,
        task_service: TaskService,
        reminder_service: ReminderService,
        webapp_base_url: str,
        max_bot_username: str = "",
        receipt_repository: Any | None = None,
        pending_action_repository: Any | None = None,
        chat_repository: Any | None = None,
    ) -> None:
        self.task_service = task_service
        self.reminder_service = reminder_service
        self.webapp_base_url = webapp_base_url.rstrip("/")
        self.max_bot_username = max_bot_username
        self.receipt_repository = receipt_repository
        self.pending_action_repository = pending_action_repository
        self.chat_repository = chat_repository

    async def handle_event(self, event: NormalizedCallbackEvent) -> BotCallbackResult:
        assignment = parse_task_assignment_callback_payload(event.payload)
        if assignment is not None:
            return await self._handle_assignment_event(event, assignment)

        report = parse_task_report_callback_payload(event.payload)
        if report is not None:
            return await self._handle_report_start_event(event, report)

        parsed = parse_callback_payload(event.payload)

        receipt: CallbackReceiptLike | None = None
        if self.receipt_repository is not None and event.callback_id:
            receipt, should_process = await self.receipt_repository.start(
                callback_id=event.callback_id,
                payload=event.payload,
            )
            if not should_process:
                return BotCallbackResult(
                    action=parsed.action,
                    task_id=parsed.task_id,
                    response_text=self._duplicate_response_text(receipt),
                    snooze=parsed.snooze,
                )

        try:
            task = await self.task_service.get(parsed.task_id)
            duplicate_result = await self._logical_duplicate_result(event, parsed, task, receipt)
            if duplicate_result is not None:
                return duplicate_result
            result = await self._handle_parsed_event(event, parsed, task)
        except Exception as exc:
            if self.receipt_repository is not None and receipt is not None:
                await self.receipt_repository.mark_failed(receipt, error=self._safe_error(exc))
            raise

        if self.receipt_repository is not None and receipt is not None:
            await self.receipt_repository.mark_succeeded(receipt, response_text=result.response_text)
        return result

    async def _handle_report_start_event(
        self,
        event: NormalizedCallbackEvent,
        report: ParsedTaskReportPayload,
    ) -> BotCallbackResult:
        receipt: CallbackReceiptLike | None = None
        if self.receipt_repository is not None and event.callback_id:
            receipt, should_process = await self.receipt_repository.start(
                callback_id=event.callback_id,
                payload=event.payload,
            )
            if not should_process:
                return BotCallbackResult(
                    action="report",
                    task_id=report.task_id,
                    response_text=self._duplicate_response_text(receipt),
                )

        try:
            result = await self._process_report_start_event(event, report)
        except Exception as exc:
            if self.receipt_repository is not None and receipt is not None:
                await self.receipt_repository.mark_failed(receipt, error=self._safe_error(exc))
            raise

        if self.receipt_repository is not None and receipt is not None:
            await self.receipt_repository.mark_succeeded(receipt, response_text=result.response_text)
        return result

    async def _process_report_start_event(
        self,
        event: NormalizedCallbackEvent,
        report: ParsedTaskReportPayload,
    ) -> BotCallbackResult:
        if self.pending_action_repository is None:
            raise BotCallbackError("Pending action handler is not configured.")
        if event.chat_id is None:
            raise BotCallbackError("Callback chat id is required for report flow.")
        task = await self.task_service.get(report.task_id)
        self._ensure_assignee(task, event.user_id)
        self._ensure_report_task_status(task)
        create_task_report_submit = getattr(self.pending_action_repository, "create_task_report_submit", None)
        if create_task_report_submit is None:
            raise BotCallbackError("Pending report handler is not configured.")
        pending = await create_task_report_submit(
            actor_user_id=event.user_id,
            chat_id=event.chat_id,
            task_id=task.id,
            task_ref=self._task_ref(task),
            title=getattr(task, "title", "Задача"),
            source_message_id=event.message_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        return BotCallbackResult(
            action="report",
            task_id=task.id,
            response_text=f"Напишите отчет по задаче {self._task_ref(task)} одним сообщением.",
            pending_action_id=getattr(pending, "id", None),
            answer_message_text=self._report_wizard_prompt_text(self._task_ref(task)),
        )

    async def _handle_assignment_event(
        self,
        event: NormalizedCallbackEvent,
        assignment: ParsedTaskAssignmentPayload,
    ) -> BotCallbackResult:
        receipt: CallbackReceiptLike | None = None
        if self.receipt_repository is not None and event.callback_id:
            receipt, should_process = await self.receipt_repository.start(
                callback_id=event.callback_id,
                payload=event.payload,
            )
            if not should_process:
                return BotCallbackResult(
                    action="assign",
                    task_id=None,
                    response_text=self._duplicate_response_text(receipt),
                )

        try:
            result = await self._process_assignment_event(event, assignment)
        except Exception as exc:
            if self.receipt_repository is not None and receipt is not None:
                await self.receipt_repository.mark_failed(receipt, error=self._safe_error(exc))
            raise

        if self.receipt_repository is not None and receipt is not None:
            await self.receipt_repository.mark_succeeded(receipt, response_text=result.response_text)
        return result

    async def _process_assignment_event(
        self,
        event: NormalizedCallbackEvent,
        assignment: ParsedTaskAssignmentPayload,
    ) -> BotCallbackResult:
        if self.pending_action_repository is None or self.chat_repository is None:
            raise BotCallbackError("Pending action handler is not configured.")

        pending = await self.pending_action_repository.get(assignment.pending_action_id)
        if pending is None:
            return BotCallbackResult(
                action="assign",
                task_id=None,
                response_text="Выбор исполнителя устарел. Создайте задачу заново.",
            )
        if pending.action_type != PENDING_ACTION_TASK_CREATE_SELECT_ASSIGNEE:
            raise BotCallbackError("Unsupported pending action type.")
        if pending.status == PENDING_ACTION_COMPLETED:
            return BotCallbackResult(
                action="assign",
                task_id=getattr(pending, "completed_task_id", None),
                response_text="Исполнитель уже назначен.",
                pending_action_id=pending.id,
            )
        if pending.status != PENDING_ACTION_PENDING:
            return BotCallbackResult(
                action="assign",
                task_id=None,
                response_text="Выбор исполнителя уже недоступен. Создайте задачу заново.",
                pending_action_id=pending.id,
            )
        now = datetime.now(timezone.utc)
        if pending.expires_at <= now:
            await self.pending_action_repository.mark_expired(pending)
            return BotCallbackResult(
                action="assign",
                task_id=None,
                response_text="Выбор исполнителя устарел. Создайте задачу заново.",
                pending_action_id=pending.id,
            )
        if pending.actor_user_id != event.user_id:
            raise BotCallbackForbidden("Only pending action creator can choose assignee.")

        assignee_id = event.user_id if assignment.assign_self else assignment.assignee_id
        if assignee_id is None:
            raise BotCallbackError("Assignee id is required.")
        if assignee_id != event.user_id and not await self._pending_actor_can_assign_others(pending, event.user_id):
            raise BotCallbackForbidden("Only chat admin can assign tasks to other users.")

        member = await self.chat_repository.get_member(chat_id=pending.chat_id, user_id=assignee_id)
        if member is None or not getattr(member, "is_active", False):
            raise BotCallbackForbidden("Selected assignee is not an active chat member.")
        chat = await self.chat_repository.get_chat(pending.chat_id)
        if chat is None:
            raise BotCallbackError("Chat for pending action was not found.")

        task = await self.task_service.create(
            TaskCreate(
                organization_id=chat.organization_id,
                chat_id=chat.id,
                title=pending.title,
                description=pending.description,
                source_message_id=pending.source_message_id,
                created_by_user_id=pending.actor_user_id,
                deadline_at=as_aware_utc(pending.deadline_at),
                assignee_ids=[assignee_id],
                observer_ids=[],
            )
        )
        await self.pending_action_repository.mark_completed(
            pending,
            task_id=task.id,
            selected_assignee_user_id=assignee_id,
            picker_message_id=event.message_id,
        )
        display_name = self._member_display_name(member, assignee_id)
        summary_text = self._assignment_summary_text(
            task=task,
            title=pending.title,
            display_name=display_name,
            deadline_at=pending.deadline_at,
        )
        return BotCallbackResult(
            action="assign",
            task_id=task.id,
            response_text=f"Исполнитель назначен: {display_name}.",
            pending_action_id=pending.id,
            answer_message_text=summary_text,
            answer_message_attachments=self._open_task_attachments(task),
        )

    async def mark_assignment_cleanup(
        self,
        pending_action_id: UUID,
        *,
        succeeded: bool,
        error: str | None = None,
    ) -> None:
        if self.pending_action_repository is None:
            return
        mark_cleanup_result = getattr(self.pending_action_repository, "mark_cleanup_result", None)
        if mark_cleanup_result is None:
            return
        await mark_cleanup_result(
            pending_action_id,
            status=PENDING_ACTION_CLEANUP_EDITED if succeeded else PENDING_ACTION_CLEANUP_FAILED,
            error=error,
        )

    def _assignment_summary_text(
        self,
        *,
        task: object | None = None,
        title: str,
        display_name: str,
        deadline_at: datetime | None,
    ) -> str:
        task_ref = self._task_ref(task)
        lines = [
            f"Задача {task_ref or '#?'} создана ✅",
            "",
            f"Текст: {title}",
            f"Исполнитель: {display_name}",
        ]
        deadline = self._format_deadline(deadline_at) if deadline_at is not None else "не указан"
        lines.append(f"Срок: {deadline}")
        return "\n".join(lines)

    def _open_task_attachments(self, task: object) -> list[dict[str, Any]]:
        task_number = getattr(task, "task_number", None)
        startapp = f"task_{task_number}" if task_number is not None else "my_tasks"
        url = build_max_webapp_deep_link(
            bot_username=self.max_bot_username,
            webapp_base_url=self.webapp_base_url,
            startapp=startapp,
            fallback_path="tasks",
        )
        return [
            {
                "type": "inline_keyboard",
                "payload": {
                    "buttons": [
                        [
                            {
                                "type": "link",
                                "text": "Открыть задачу",
                                "url": url,
                            }
                        ]
                    ]
                },
            }
        ]

    def _report_wizard_prompt_text(self, task_ref: str) -> str:
        return f"/отчет {task_ref}\n\nНапишите отчет по задаче {task_ref} одним сообщением."

    def _task_ref(self, task: object | None) -> str:
        if task is None:
            return ""
        task_number = getattr(task, "task_number", None)
        return f"#{task_number}" if task_number is not None else ""

    def _format_deadline(self, deadline_at: datetime) -> str:
        value = as_aware_utc(deadline_at)
        if value is None:
            return "не указан"
        return value.astimezone(ZoneInfo(DEFAULT_TIMEZONE)).strftime("%d.%m.%Y %H:%M")

    def _member_display_name(self, member: Any, user_id: UUID) -> str:
        user = getattr(member, "user", None)
        if user is not None:
            display_name = getattr(user, "display_name", None)
            if isinstance(display_name, str) and display_name.strip():
                return display_name.strip()
            username = getattr(user, "username", None)
            if isinstance(username, str) and username.strip():
                return username.strip()
        return str(user_id)

    async def _handle_parsed_event(
        self,
        event: NormalizedCallbackEvent,
        parsed: ParsedCallbackPayload,
        task: Any,
    ) -> BotCallbackResult:
        if parsed.action == "start":
            return await self._start_task(event, parsed, task)
        if parsed.action == "reply":
            self._ensure_assignee(task, event.user_id)
            return BotCallbackResult(
                action=parsed.action,
                task_id=parsed.task_id,
                response_text="Напишите ответ на задачу сообщением в чат.",
            )
        if parsed.action == "confirm":
            return await self._confirm_completion(event, parsed, task)
        if parsed.action == "accept":
            return await self._accept_response(event, parsed, task)
        if parsed.action == "reject":
            return await self._reject_response(event, parsed, task)
        if parsed.action == "snooze":
            return await self._snooze(event, parsed, task)
        if parsed.action == "open":
            return self._open_task(event, parsed, task)

        raise BotCallbackError(f"Unsupported callback action: {parsed.action}.")

    async def _logical_duplicate_result(
        self,
        event: NormalizedCallbackEvent,
        parsed: ParsedCallbackPayload,
        task: Any,
        receipt: CallbackReceiptLike | None,
    ) -> BotCallbackResult | None:
        if (
            self.receipt_repository is None
            or receipt is None
            or event.callback_id is None
            or parsed.action not in self._LOGICAL_IDEMPOTENT_ACTIONS
        ):
            return None

        await self._ensure_action_allowed(parsed, task, event)
        now = datetime.now(timezone.utc)
        logical_key = self._logical_key(event, parsed)
        await self.receipt_repository.set_logical_context(
            receipt,
            provider="max",
            actor_user_id=event.user_id,
            task_id=parsed.task_id,
            action_type=parsed.action,
            payload_normalized=event.payload,
            logical_key=logical_key,
            logical_window_started_at=now,
        )
        duplicate = await self.receipt_repository.find_recent_logical_duplicate(
            logical_key=logical_key,
            since=now - timedelta(seconds=self.LOGICAL_IDEMPOTENCY_WINDOW_SECONDS),
            exclude_callback_id=event.callback_id,
        )
        if duplicate is None:
            return None

        response_text = self._logical_duplicate_response_text(parsed, duplicate)
        await self.receipt_repository.mark_logical_duplicate(receipt, response_text=response_text)
        return BotCallbackResult(
            action=parsed.action,
            task_id=parsed.task_id,
            response_text=response_text,
            snooze=parsed.snooze,
        )

    def _logical_key(self, event: NormalizedCallbackEvent, parsed: ParsedCallbackPayload) -> str:
        return f"max:{event.user_id}:{parsed.task_id}:{parsed.action}:{event.payload}"

    def _logical_duplicate_response_text(
        self,
        parsed: ParsedCallbackPayload,
        receipt: CallbackReceiptLike,
    ) -> str:
        if receipt.status == CALLBACK_RECEIPT_PROCESSING:
            return "Действие уже обрабатывается."
        if parsed.action == "snooze":
            return "Напоминание уже отложено."
        if parsed.action == "confirm":
            return "Отчет уже отправлен постановщику."
        if parsed.action == "accept":
            return "Результат уже принят."
        if parsed.action == "reject":
            return "Причина отклонения уже ожидается."
        if parsed.action == "start":
            return "Задача уже взята в работу."
        return "Действие уже обработано."

    def _duplicate_response_text(self, receipt: CallbackReceiptLike) -> str:
        if receipt.response_text:
            return receipt.response_text
        if receipt.status == CALLBACK_RECEIPT_PROCESSING:
            return "Действие уже обрабатывается."
        if receipt.status == CALLBACK_RECEIPT_FAILED:
            return "Действие уже было обработано с ошибкой."
        return "Действие уже обработано."

    def _safe_error(self, exc: Exception) -> str:
        message = str(exc) or exc.__class__.__name__
        return message[:1000]

    async def _start_task(
        self,
        event: NormalizedCallbackEvent,
        parsed: ParsedCallbackPayload,
        task: Any,
    ) -> BotCallbackResult:
        self._ensure_assignee(task, event.user_id)
        if self._assignee_has_status(task, event.user_id, TaskAssigneeStatus.IN_PROGRESS.value):
            return BotCallbackResult(
                action=parsed.action,
                task_id=parsed.task_id,
                response_text="Задача уже взята в работу.",
            )
        await self.task_service.start_assignee_task(parsed.task_id, event.user_id)
        return BotCallbackResult(
            action=parsed.action,
            task_id=parsed.task_id,
            response_text="Задача взята в работу.",
        )

    async def _confirm_completion(
        self,
        event: NormalizedCallbackEvent,
        parsed: ParsedCallbackPayload,
        task: Any,
    ) -> BotCallbackResult:
        self._ensure_assignee(task, event.user_id)
        if self._assignee_has_status(task, event.user_id, TaskAssigneeStatus.RESPONDED.value):
            return BotCallbackResult(
                action=parsed.action,
                task_id=parsed.task_id,
                response_text="Отчет уже отправлен постановщику.",
            )
        await self.task_service.submit_response(
            parsed.task_id,
            TaskResponseCreate(
                user_id=event.user_id,
                text="Выполнено",
                source_message_id=event.message_id,
            ),
        )
        return BotCallbackResult(
            action=parsed.action,
            task_id=parsed.task_id,
            response_text="Отчет о выполнении отправлен постановщику.",
        )

    async def _accept_response(
        self,
        event: NormalizedCallbackEvent,
        parsed: ParsedCallbackPayload,
        task: Any,
    ) -> BotCallbackResult:
        await self._ensure_accept_allowed(task, event)
        if parsed.response_id is None:
            raise BotCallbackError("Response id is required for accept callback.")
        if self._response_has_status(task, parsed.response_id, TaskResponseStatus.ACCEPTED.value):
            response_text = "Результат уже принят."
            return BotCallbackResult(
                action=parsed.action,
                task_id=parsed.task_id,
                response_text=response_text,
                answer_message_text=response_text,
            )
        if self._response_has_status(task, parsed.response_id, TaskResponseStatus.REJECTED.value):
            response_text = "Результат уже отклонен."
            return BotCallbackResult(
                action=parsed.action,
                task_id=parsed.task_id,
                response_text=response_text,
                answer_message_text=response_text,
            )
        await self.task_service.accept_response(
            parsed.task_id,
            parsed.response_id,
            TaskAcceptanceCreate(accepted_by_user_id=event.user_id),
            auth_context=await self._acceptance_auth_context(task, event),
        )
        response_text = f"Ответ по задаче {self._task_ref(task)} принят ✅"
        return BotCallbackResult(
            action=parsed.action,
            task_id=parsed.task_id,
            response_text=response_text,
            answer_message_text=response_text,
        )

    async def _reject_response(
        self,
        event: NormalizedCallbackEvent,
        parsed: ParsedCallbackPayload,
        task: Any,
    ) -> BotCallbackResult:
        await self._ensure_accept_allowed(task, event)
        if parsed.response_id is None:
            raise BotCallbackError("Response id is required for reject callback.")
        if self._response_has_status(task, parsed.response_id, TaskResponseStatus.REJECTED.value):
            response_text = "Результат уже отклонен."
            return BotCallbackResult(
                action=parsed.action,
                task_id=parsed.task_id,
                response_text=response_text,
                answer_message_text=response_text,
            )
        if self._response_has_status(task, parsed.response_id, TaskResponseStatus.ACCEPTED.value):
            response_text = "Результат уже принят."
            return BotCallbackResult(
                action=parsed.action,
                task_id=parsed.task_id,
                response_text=response_text,
                answer_message_text=response_text,
            )
        if self.pending_action_repository is None:
            raise BotCallbackError("Pending action handler is not configured.")
        if event.chat_id is None:
            raise BotCallbackError("Callback chat id is required for reject reason flow.")
        create_reject_reason = getattr(self.pending_action_repository, "create_task_acceptance_reject_reason", None)
        if create_reject_reason is None:
            raise BotCallbackError("Pending reject reason handler is not configured.")
        prompt = self._reject_reason_prompt(task)
        pending = await create_reject_reason(
            actor_user_id=event.user_id,
            chat_id=event.chat_id,
            task_id=parsed.task_id,
            response_id=parsed.response_id,
            task_ref=self._task_ref(task),
            title=getattr(task, "title", "Задача"),
            source_message_id=event.message_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        return BotCallbackResult(
            action=parsed.action,
            task_id=parsed.task_id,
            response_text=prompt,
            pending_action_id=getattr(pending, "id", None),
            answer_message_text=prompt,
        )

    async def _snooze(
        self,
        event: NormalizedCallbackEvent,
        parsed: ParsedCallbackPayload,
        task: Any,
    ) -> BotCallbackResult:
        self._ensure_assignee(task, event.user_id)
        if parsed.snooze is None:
            raise BotCallbackError("Snooze value is required for snooze callback.")
        labels = {
            "1h": "на 1 час",
            "tomorrow": "до завтра",
        }
        await self.reminder_service.create_snooze(
            parsed.task_id,
            event.user_id,
            self._snooze_duration(parsed.snooze),
            reason=f"callback/snooze:{parsed.snooze}",
        )
        return BotCallbackResult(
            action=parsed.action,
            task_id=parsed.task_id,
            response_text=f"Напоминание отложено {labels[parsed.snooze]}.",
            snooze=parsed.snooze,
        )

    def _snooze_duration(self, snooze: SnoozeValue) -> SnoozeDuration:
        if snooze == "1h":
            return "1h"
        if snooze == "tomorrow":
            return "tomorrow_09"
        raise BotCallbackError(f"Unsupported snooze value: {snooze}.")

    def _open_task(
        self,
        event: NormalizedCallbackEvent,
        parsed: ParsedCallbackPayload,
        task: Any,
    ) -> BotCallbackResult:
        self._ensure_can_view(task, event.user_id)
        webapp_url = build_max_webapp_deep_link(
            bot_username=self.max_bot_username,
            webapp_base_url=self.webapp_base_url,
            startapp=f"task_{parsed.task_id}",
            fallback_path=f"tasks/{parsed.task_id}",
        )
        return BotCallbackResult(
            action=parsed.action,
            task_id=parsed.task_id,
            response_text="Откройте карточку задачи в WebApp.",
            webapp_url=webapp_url,
        )

    def _ensure_assignee(self, task: Any, user_id: UUID) -> None:
        if not self._is_assignee(task, user_id):
            raise BotCallbackForbidden("Only task assignee can perform this callback action.")

    def _ensure_creator(self, task: Any, user_id: UUID) -> None:
        if getattr(task, "created_by_user_id", None) != user_id:
            raise BotCallbackForbidden("Only task creator can perform this callback action.")

    def _ensure_can_view(self, task: Any, user_id: UUID) -> None:
        if (
            getattr(task, "created_by_user_id", None) == user_id
            or self._is_assignee(task, user_id)
            or self._is_observer(task, user_id)
        ):
            return
        raise BotCallbackForbidden("User cannot view this task.")

    def _ensure_report_task_status(self, task: Any) -> None:
        if getattr(task, "status", None) in {
            TaskStatus.DONE.value,
            TaskStatus.CANCELLED.value,
            TaskStatus.REJECTED.value,
        }:
            raise BotCallbackError("Task already has a final status.")

    def _is_assignee(self, task: Any, user_id: UUID) -> bool:
        return any(getattr(assignee, "user_id", None) == user_id for assignee in getattr(task, "assignees", []))

    def _is_observer(self, task: Any, user_id: UUID) -> bool:
        return any(getattr(observer, "user_id", None) == user_id for observer in getattr(task, "observers", []))

    async def _ensure_action_allowed(
        self,
        parsed: ParsedCallbackPayload,
        task: Any,
        event: NormalizedCallbackEvent,
    ) -> None:
        if parsed.action in {"start", "reply", "confirm", "snooze"}:
            self._ensure_assignee(task, event.user_id)
            return
        if parsed.action in {"accept", "reject"}:
            await self._ensure_accept_allowed(task, event)
            return
        if parsed.action == "open":
            self._ensure_can_view(task, event.user_id)

    async def _ensure_accept_allowed(self, task: Any, event: NormalizedCallbackEvent) -> None:
        if getattr(task, "created_by_user_id", None) == event.user_id:
            return
        auth_context = await self._acceptance_auth_context(task, event)
        if auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN):
            return
        if auth_context.has_any_role(frozenset({ROLE_CHAT_ADMIN})) and self._same_scope(
            auth_context.chat_id,
            getattr(task, "chat_id", None),
        ):
            return
        raise BotCallbackForbidden("Недостаточно прав для этого действия.")

    def _reject_reason_prompt(self, task: object) -> str:
        return f"Напишите причину отклонения приемки по задаче {self._task_ref(task)} одним сообщением."

    async def _pending_actor_can_assign_others(self, pending: Any, user_id: UUID) -> bool:
        if self.chat_repository is None:
            return False
        member = await self.chat_repository.get_member(chat_id=pending.chat_id, user_id=user_id)
        if member is None or not getattr(member, "is_active", False):
            return False
        role = str(getattr(member, "role", "") or "")
        return role in {ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN}

    async def _acceptance_auth_context(
        self,
        task: Any,
        event: NormalizedCallbackEvent,
    ) -> AuthContext:
        chat_id = getattr(task, "chat_id", None) or event.chat_id
        role: str | None = None
        if self.chat_repository is not None and chat_id is not None:
            member = await self.chat_repository.get_member(chat_id=chat_id, user_id=event.user_id)
            if member is not None and getattr(member, "is_active", False):
                role = getattr(member, "role", None)
        return AuthContext(
            user_id=event.user_id,
            organization_id=getattr(task, "organization_id", None),
            chat_id=chat_id,
            roles=[role] if role else [],
            is_super_admin=role == ROLE_SUPER_ADMIN,
        )

    def _same_scope(self, left: Any, right: Any) -> bool:
        if left is None or right is None:
            return False
        return str(left) == str(right)

    def _assignee_has_status(self, task: Any, user_id: UUID, status: str) -> bool:
        return any(
            getattr(assignee, "user_id", None) == user_id and getattr(assignee, "status", None) == status
            for assignee in getattr(task, "assignees", [])
        )

    def _response_has_status(self, task: Any, response_id: UUID, status: str) -> bool:
        return any(
            getattr(response, "id", None) == response_id and getattr(response, "status", None) == status
            for response in getattr(task, "responses", [])
        )
