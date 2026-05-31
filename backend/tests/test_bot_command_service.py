from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.modules.bot.command_parser import BotCommandParser
from app.modules.bot.callback_service import BotCallbackResult, NormalizedCallbackEvent
from app.modules.bot.identity_resolver import ResolvedMaxIdentity
from app.modules.bot.service import MaxBotWebhookService, normalize_max_event
from app.modules.bot.schemas import MaxBotWebhookEvent, NormalizedBotEvent, NormalizedMaxCallbackEvent, NormalizedMention
from app.modules.notifications.enums import DeliveryStatus
from app.modules.notifications.max_sender import MaxSender
from app.modules.notifications.service import (
    BACKGROUND_DISABLED_ERROR,
    MISSING_MAX_CHAT_ID_ERROR,
    NotificationDeliveryResult,
)
from app.modules.tasks.enums import TaskResponseStatus, TaskStatus


class FakeUserRepository:
    def __init__(self, users: list[SimpleNamespace]) -> None:
        self.users = users

    async def get(self, user_id: UUID) -> SimpleNamespace | None:
        return next((user for user in self.users if user.id == user_id), None)

    async def get_by_max_user_id(self, max_user_id: str) -> SimpleNamespace | None:
        return next((user for user in self.users if getattr(user, "max_user_id", None) == max_user_id), None)

    async def create(
        self,
        *,
        display_name: str,
        max_user_id: str | None = None,
        username: str | None = None,
        phone: str | None = None,
        email: str | None = None,
    ) -> SimpleNamespace:
        user = SimpleNamespace(
            id=uuid4(),
            max_user_id=max_user_id,
            display_name=display_name,
            username=username,
            phone=phone,
            email=email,
        )
        self.users.append(user)
        return user

    async def find_by_display_name(self, display_name: str) -> list[SimpleNamespace]:
        normalized = display_name.strip().lower()
        return [user for user in self.users if user.display_name.lower() == normalized]

    async def find_by_mention(self, mention: str) -> list[SimpleNamespace]:
        normalized = mention.strip().removeprefix("@").lower()
        return [
            user
            for user in self.users
            if (getattr(user, "username", None) or "").lower() == normalized
            or user.display_name.lower() == normalized
        ]


class FakeChatRepository:
    def __init__(self, chat: SimpleNamespace, members: list[SimpleNamespace] | None = None) -> None:
        self.chat = chat
        self.members = members or []

    async def get_chat(self, chat_id: UUID) -> SimpleNamespace | None:
        if chat_id == self.chat.id:
            return self.chat
        return None

    async def list_members(self, chat_id: UUID) -> list[SimpleNamespace]:
        if chat_id != self.chat.id:
            return []
        return self.members

    async def get_member(self, *, chat_id: UUID, user_id: UUID) -> SimpleNamespace | None:
        if chat_id != self.chat.id:
            return None
        return next((member for member in self.members if member.user_id == user_id), None)

    async def create_member(
        self,
        *,
        chat_id: UUID,
        user_id: UUID,
        role: str,
        is_active: bool,
    ) -> SimpleNamespace:
        user = next(
            (member.user for member in self.members if getattr(member.user, "id", None) == user_id),
            None,
        )
        member = SimpleNamespace(chat_id=chat_id, user_id=user_id, user=user, role=role, is_active=is_active)
        self.members.append(member)
        return member

    async def update_member(self, member: SimpleNamespace, *, values: dict[str, object]) -> SimpleNamespace:
        for key, value in values.items():
            setattr(member, key, value)
        return member


class FakePendingActionRepository:
    def __init__(self) -> None:
        self.created: list[SimpleNamespace] = []
        self.cancelled_reports: int = 0
        self.cancelled_task_creation: int = 0

    async def create_task_assignee_picker(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        title: str,
        source_text: str | None,
        description: str | None,
        source_message_id: str | None,
        deadline_at: datetime | None,
        reply_context: dict | None,
        expires_at: datetime,
        wizard_message_id: str | None = None,
    ) -> SimpleNamespace:
        action = SimpleNamespace(
            id=uuid4(),
            action_type="task_create_select_assignee",
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            title=title,
            source_text=source_text,
            description=description,
            source_message_id=source_message_id,
            deadline_at=deadline_at,
            reply_context=reply_context,
            expires_at=expires_at,
            status="pending",
            picker_message_id=wizard_message_id,
            cleanup_status=None,
            cleanup_error=None,
        )
        self.created.append(action)
        return action

    async def create_task_deadline_clarification(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        title: str,
        source_text: str | None,
        description: str | None,
        source_message_id: str | None,
        reply_context: dict | None,
        expires_at: datetime,
        wizard_message_id: str | None = None,
    ) -> SimpleNamespace:
        action = SimpleNamespace(
            id=uuid4(),
            action_type="task_create_set_deadline",
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            title=title,
            source_text=source_text,
            description=description,
            source_message_id=source_message_id,
            deadline_at=None,
            reply_context=reply_context,
            expires_at=expires_at,
            status="pending",
            picker_message_id=wizard_message_id,
            cleanup_status=None,
            cleanup_error=None,
        )
        self.created.append(action)
        return action

    async def create_task_text_clarification(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        source_message_id: str | None,
        reply_context: dict | None,
        expires_at: datetime,
        wizard_message_id: str | None = None,
    ) -> SimpleNamespace:
        action = SimpleNamespace(
            id=uuid4(),
            action_type="task_create_set_text",
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            title="",
            source_text=None,
            description=None,
            source_message_id=source_message_id,
            deadline_at=None,
            reply_context=reply_context,
            expires_at=expires_at,
            status="pending",
            picker_message_id=wizard_message_id,
            cleanup_status=None,
            cleanup_error=None,
        )
        self.created.append(action)
        return action

    async def create_task_report_submit(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        task_id: UUID,
        task_ref: str,
        title: str,
        source_message_id: str | None,
        expires_at: datetime,
        reply_context: dict | None = None,
        wizard_message_id: str | None = None,
    ) -> SimpleNamespace:
        context = dict(reply_context or {})
        context["task_id"] = str(task_id)
        context["task_ref"] = task_ref
        action = SimpleNamespace(
            id=uuid4(),
            action_type="task_report_submit",
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            title=title,
            source_message_id=source_message_id,
            reply_context=context,
            expires_at=expires_at,
            status="pending",
            picker_message_id=wizard_message_id,
            completed_task_id=None,
            cleanup_status=None,
            cleanup_error=None,
        )
        self.created.append(action)
        return action

    async def create_task_acceptance_reject_reason(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        task_id: UUID,
        response_id: UUID,
        task_ref: str,
        title: str,
        source_message_id: str | None,
        expires_at: datetime,
    ) -> SimpleNamespace:
        action = SimpleNamespace(
            id=uuid4(),
            action_type="task_acceptance_reject_reason",
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            title=title,
            source_message_id=source_message_id,
            reply_context={
                "task_id": str(task_id),
                "response_id": str(response_id),
                "task_ref": task_ref,
            },
            expires_at=expires_at,
            status="pending",
            completed_task_id=None,
            cleanup_status=None,
            cleanup_error=None,
        )
        self.created.append(action)
        return action

    async def get_latest_pending_task_assignee_picker(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        now: datetime,
    ) -> SimpleNamespace | None:
        for action in reversed(self.created):
            if (
                getattr(action, "action_type", None) == "task_create_select_assignee"
                and action.actor_user_id == actor_user_id
                and action.chat_id == chat_id
                and action.status == "pending"
                and action.expires_at > now
            ):
                return action
        return None

    async def get_latest_pending_task_text_clarification(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
    ) -> SimpleNamespace | None:
        for action in reversed(self.created):
            if (
                getattr(action, "action_type", None) == "task_create_set_text"
                and action.actor_user_id == actor_user_id
                and action.chat_id == chat_id
                and action.status == "pending"
            ):
                return action
        return None

    async def get_latest_pending_task_deadline_clarification(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        now: datetime,
    ) -> SimpleNamespace | None:
        for action in reversed(self.created):
            if (
                getattr(action, "action_type", None) == "task_create_set_deadline"
                and action.actor_user_id == actor_user_id
                and action.chat_id == chat_id
                and action.status == "pending"
                and action.expires_at > now
            ):
                return action
        return None

    async def get_latest_pending_task_report_submit(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
    ) -> SimpleNamespace | None:
        for action in reversed(self.created):
            if (
                getattr(action, "action_type", None) == "task_report_submit"
                and action.actor_user_id == actor_user_id
                and action.chat_id == chat_id
                and action.status == "pending"
            ):
                return action
        return None

    async def get_latest_pending_task_acceptance_reject_reason(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
    ) -> SimpleNamespace | None:
        for action in reversed(self.created):
            if (
                getattr(action, "action_type", None) == "task_acceptance_reject_reason"
                and action.actor_user_id == actor_user_id
                and action.chat_id == chat_id
                and action.status == "pending"
            ):
                return action
        return None

    async def mark_completed(
        self,
        action: SimpleNamespace,
        *,
        task_id: UUID,
        selected_assignee_user_id: UUID,
        picker_message_id: str | None = None,
    ) -> SimpleNamespace:
        action.status = "completed"
        action.completed_task_id = task_id
        action.selected_assignee_user_id = selected_assignee_user_id
        action.picker_message_id = picker_message_id
        action.cleanup_status = "pending"
        return action

    async def mark_report_completed(self, action: SimpleNamespace, *, task_id: UUID) -> SimpleNamespace:
        action.status = "completed"
        action.completed_task_id = task_id
        action.cleanup_status = "pending"
        return action

    async def mark_acceptance_reject_reason_completed(
        self,
        action: SimpleNamespace,
        *,
        task_id: UUID,
    ) -> SimpleNamespace:
        action.status = "completed"
        action.completed_task_id = task_id
        action.cleanup_status = "unsupported"
        return action

    async def mark_text_completed(self, action: SimpleNamespace) -> SimpleNamespace:
        action.status = "completed"
        action.cleanup_status = "unsupported"
        return action

    async def mark_wizard_message_sent(self, action_id: UUID, *, message_id: str) -> SimpleNamespace | None:
        action = next((item for item in self.created if item.id == action_id), None)
        if action is None:
            return None
        action.picker_message_id = message_id
        return action

    async def mark_task_creation_completed(self, action: SimpleNamespace, *, task_id: UUID) -> SimpleNamespace:
        action.status = "completed"
        action.completed_task_id = task_id
        action.cleanup_status = "pending"
        return action

    async def cancel_pending_task_reports(self, *, actor_user_id: UUID, chat_id: UUID) -> int:
        count = 0
        for action in self.created:
            if (
                getattr(action, "action_type", None) == "task_report_submit"
                and action.actor_user_id == actor_user_id
                and action.chat_id == chat_id
                and action.status == "pending"
            ):
                action.status = "cancelled"
                count += 1
        self.cancelled_reports += count
        return count

    async def cancel_pending_task_creation(self, *, actor_user_id: UUID, chat_id: UUID) -> int:
        count = 0
        for action in self.created:
            if (
                getattr(action, "action_type", None)
                in {
                    "task_create_set_text",
                    "task_create_set_deadline",
                    "task_create_select_assignee",
                }
                and action.actor_user_id == actor_user_id
                and action.chat_id == chat_id
                and action.status == "pending"
            ):
                action.status = "cancelled"
                count += 1
        self.cancelled_task_creation += count
        return count

    async def mark_cancelled(self, action: SimpleNamespace) -> SimpleNamespace:
        action.status = "cancelled"
        return action

    async def mark_expired(self, action: SimpleNamespace) -> SimpleNamespace:
        action.status = "expired"
        return action

    async def mark_cleanup_result(
        self,
        action_id: UUID,
        *,
        status: str,
        error: str | None = None,
    ) -> SimpleNamespace | None:
        action = next((item for item in self.created if item.id == action_id), None)
        if action is None:
            return None
        action.cleanup_status = status
        action.cleanup_error = error
        return action


class FakeNotificationDeliveryService:
    def __init__(
        self,
        *,
        results_by_user_id: dict[UUID, NotificationDeliveryResult] | None = None,
        results_by_chat_id: dict[UUID, NotificationDeliveryResult] | None = None,
        default_status: DeliveryStatus = DeliveryStatus.SENT,
    ) -> None:
        self.results_by_user_id = results_by_user_id or {}
        self.results_by_chat_id = results_by_chat_id or {}
        self.default_status = default_status
        self.calls: list[dict[str, object]] = []

    async def send_personal_task_notification(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        message: str,
        reminder_type: str | None = None,
        attachments: list[dict[str, object]] | None = None,
        purpose: object | None = None,
        allow_group_fallback: bool = True,
    ) -> NotificationDeliveryResult:
        self.calls.append(
            {
                "user_id": user_id,
                "task_id": task_id,
                "message": message,
                "reminder_type": reminder_type,
                "attachments": attachments,
                "purpose": getattr(purpose, "value", purpose),
                "allow_group_fallback": allow_group_fallback,
            }
        )
        if user_id in self.results_by_user_id:
            return self.results_by_user_id[user_id]
        return make_delivery_result(
            task_id=task_id,
            user_id=user_id,
            status=self.default_status,
        )

    async def send_chat_task_notification(
        self,
        *,
        chat_id: UUID,
        task_id: UUID,
        message: str,
        reminder_type: str,
        attachments: list[dict[str, object]] | None = None,
        purpose: object | None = None,
        dedup_since: datetime | None = None,
    ) -> NotificationDeliveryResult:
        self.calls.append(
            {
                "chat_id": chat_id,
                "task_id": task_id,
                "message": message,
                "reminder_type": reminder_type,
                "attachments": attachments,
                "purpose": getattr(purpose, "value", purpose),
                "dedup_since": dedup_since,
            }
        )
        if chat_id in self.results_by_chat_id:
            return self.results_by_chat_id[chat_id]
        return make_chat_delivery_result(
            task_id=task_id,
            chat_id=chat_id,
            status=self.default_status,
        )


class FakeInlineKeyboardMaxClient:
    def __init__(self) -> None:
        self.inline_keyboards: list[dict[str, object]] = []
        self.messages: list[dict[str, object]] = []

    def send_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        attachments=None,
    ) -> dict[str, object]:
        self.messages.append(
            {"chat_id": chat_id, "user_id": user_id, "text": text, "attachments": attachments}
        )
        return {"message": {"id": "max-message-text"}}

    def send_inline_keyboard_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_rows: list[list[dict[str, object]]],
    ) -> dict[str, object]:
        self.inline_keyboards.append(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "text": text,
                "button_rows": button_rows,
            }
        )
        return {"message": {"id": "max-message-inline"}}


class FakeTaskService:
    def __init__(self) -> None:
        self.created_payload = None
        self.next_task_number = 1
        self.list_filters = None
        self.inbox_filters = None
        self.response_calls: list[tuple[UUID, object]] = []
        self.accept_calls: list[tuple[UUID, UUID, object]] = []
        self.reject_calls: list[tuple[UUID, UUID, object]] = []
        self.list_tasks = [
            self._task(title="Active chat task", status=TaskStatus.NEW.value),
            self._task(title="Done chat task", status=TaskStatus.DONE.value),
        ]
        self.my_tasks = [self._task(title="My assigned task", status=TaskStatus.IN_PROGRESS.value)]

    async def create(self, payload):
        self.created_payload = payload
        task_id = uuid4()
        task_number = self._next_task_number()
        return SimpleNamespace(
            id=task_id,
            task_number=task_number,
            title=payload.title,
            status=TaskStatus.NEW.value,
            assignees=[SimpleNamespace(user_id=user_id) for user_id in payload.assignee_ids],
            observers=[SimpleNamespace(user_id=user_id) for user_id in payload.observer_ids],
        )

    async def list(self, *, filters, limit: int, offset: int):
        self.list_filters = filters
        tasks = self.list_tasks
        if getattr(filters, "organization_id", None) is not None:
            tasks = [task for task in tasks if task.organization_id == filters.organization_id]
        if getattr(filters, "chat_id", None) is not None:
            tasks = [task for task in tasks if task.chat_id == filters.chat_id]
        if getattr(filters, "task_number", None) is not None:
            tasks = [task for task in tasks if task.task_number == filters.task_number]
        if getattr(filters, "assignee_id", None) is not None:
            tasks = [
                task
                for task in tasks
                if any(assignee.user_id == filters.assignee_id for assignee in task.assignees)
            ]
        return tasks[offset : offset + limit]

    async def get(self, task_id: UUID) -> SimpleNamespace:
        for task in self.list_tasks:
            if task.id == task_id:
                return task
        raise AssertionError(f"Task not found in fake service: {task_id}")

    async def inbox_summary(self, filters):
        self.inbox_filters = filters
        return SimpleNamespace(my_tasks=self.my_tasks)

    async def submit_response(self, task_id: UUID, payload):
        self.response_calls.append((task_id, payload))
        for task in self.list_tasks:
            if task.id == task_id:
                task.status = TaskStatus.WAITING_ACCEPTANCE.value
        return SimpleNamespace(id=uuid4())

    async def accept_response(self, task_id: UUID, response_id: UUID, payload, *, auth_context=None):
        self.accept_calls.append((task_id, response_id, payload))
        return SimpleNamespace(response_id=response_id)

    async def reject_response(self, task_id: UUID, response_id: UUID, payload, *, auth_context=None):
        self.reject_calls.append((task_id, response_id, payload))
        return SimpleNamespace(response_id=response_id)

    def _task(
        self,
        *,
        title: str,
        status: str,
        organization_id: UUID | None = None,
        chat_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
        assignee_ids: list[UUID] | None = None,
        observer_ids: list[UUID] | None = None,
        deadline_at: datetime | None = None,
        created_at: datetime | None = None,
        task_number: int | None = None,
        creator_display_name: str | None = None,
        assignee_users: list[SimpleNamespace] | None = None,
        responses: list[SimpleNamespace] | None = None,
    ) -> SimpleNamespace:
        assignee_users_by_id = {user.id: user for user in (assignee_users or [])}
        return SimpleNamespace(
            id=uuid4(),
            task_number=task_number or self._next_task_number(),
            organization_id=organization_id or uuid4(),
            chat_id=chat_id or uuid4(),
            title=title,
            status=status,
            created_by_user_id=created_by_user_id or uuid4(),
            creator_display_name_snapshot=creator_display_name,
            assignees=[
                SimpleNamespace(user_id=user_id, user=assignee_users_by_id.get(user_id))
                for user_id in (assignee_ids or [])
            ],
            observers=[SimpleNamespace(user_id=user_id) for user_id in (observer_ids or [])],
            responses=responses or [],
            deadline_at=deadline_at,
            created_at=created_at or datetime.now(timezone.utc),
        )

    def _next_task_number(self) -> int:
        task_number = self.next_task_number
        self.next_task_number += 1
        return task_number


class FakeIdentityResolver:
    def __init__(self, *, user: SimpleNamespace, chat: SimpleNamespace, organization_id: UUID) -> None:
        self.calls = 0
        self.identity = ResolvedMaxIdentity(
            user=user,
            chat=chat,
            organization=SimpleNamespace(id=organization_id, name="MAX default organization"),
        )

    async def resolve_event(self, event: NormalizedBotEvent) -> ResolvedMaxIdentity:
        self.calls += 1
        return self.identity


class FakeCallbackService:
    def __init__(
        self,
        *,
        task_id: UUID,
        action: str = "start",
        response_text: str = "Задача взята в работу.",
        pending_action_id: UUID | None = None,
        answer_message_text: str | None = None,
    ) -> None:
        self.task_id = task_id
        self.action = action
        self.response_text = response_text
        self.pending_action_id = pending_action_id
        self.answer_message_text = answer_message_text
        self.events: list[NormalizedCallbackEvent] = []

    async def handle_event(self, event: NormalizedCallbackEvent) -> BotCallbackResult:
        self.events.append(event)
        return BotCallbackResult(
            action=self.action,  # type: ignore[arg-type]
            task_id=self.task_id,
            response_text=self.response_text,
            pending_action_id=self.pending_action_id,
            answer_message_text=self.answer_message_text,
        )


class FakeWizardMaxApiClient:
    def __init__(
        self,
        *,
        fail_edit: bool = False,
        fail_delete: bool = False,
        nested_message_id: bool = False,
    ) -> None:
        self.fail_edit = fail_edit
        self.fail_delete = fail_delete
        self.nested_message_id = nested_message_id
        self.next_message_number = 1
        self.messages: list[dict[str, object]] = []
        self.inline_keyboards: list[dict[str, object]] = []
        self.edits: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []
        self.callback_answers: list[dict[str, object]] = []

    def send_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        attachments=None,
    ) -> dict[str, object]:
        message_id = self._next_message_id()
        self.messages.append(
            {"message_id": message_id, "chat_id": chat_id, "user_id": user_id, "text": text, "attachments": attachments}
        )
        return self._response(message_id)

    def send_inline_keyboard_message(
        self,
        *,
        chat_id: str | None,
        user_id: str | None,
        text: str,
        button_rows: list[list[dict[str, object]]],
    ) -> dict[str, object]:
        message_id = self._next_message_id()
        self.inline_keyboards.append(
            {"message_id": message_id, "chat_id": chat_id, "user_id": user_id, "text": text, "button_rows": button_rows}
        )
        return self._response(message_id)

    def edit_message(
        self,
        *,
        message_id: str,
        text: str,
        attachments=None,
    ) -> dict[str, object]:
        if self.fail_edit:
            from app.modules.integrations.max.exceptions import MaxApiError

            raise MaxApiError("MAX API returned HTTP 400.")
        self.edits.append({"message_id": message_id, "text": text, "attachments": attachments})
        return self._response(message_id)

    def delete_message(self, *, message_id: str) -> dict[str, object]:
        if self.fail_delete:
            from app.modules.integrations.max.exceptions import MaxApiError

            raise MaxApiError("MAX API returned HTTP 403.")
        self.deletes.append({"message_id": message_id})
        return {"success": True}

    def answer_callback(
        self,
        *,
        callback_id: str,
        notification: str | None = None,
        message: dict[str, object] | None = None,
    ) -> dict[str, object]:
        message_id = self._next_message_id()
        self.callback_answers.append(
            {
                "message_id": message_id,
                "callback_id": callback_id,
                "notification": notification,
                "message": message,
            }
        )
        return self._response(message_id)

    def _next_message_id(self) -> str:
        message_id = f"wizard-message-{self.next_message_number}"
        self.next_message_number += 1
        return message_id

    def _response(self, message_id: str) -> dict[str, object]:
        if self.nested_message_id:
            return {"message": {"body": {"mid": message_id}}}
        return {"message": {"id": message_id}}


@pytest.fixture()
def bot_context() -> dict[str, object]:
    organization_id = uuid4()
    chat = SimpleNamespace(id=uuid4(), organization_id=organization_id, status="active")
    requester = SimpleNamespace(
        id=uuid4(), max_user_id="max-user-admin", display_name="Постановщик", username="admin"
    )
    assignee_1 = SimpleNamespace(id=uuid4(), max_user_id="max-user-ivan", display_name="Иван", username="ivan")
    assignee_2 = SimpleNamespace(id=uuid4(), max_user_id="max-user-maria", display_name="Мария", username="maria")
    observer = SimpleNamespace(id=uuid4(), max_user_id="max-user-sergey", display_name="Сергей", username="sergey")
    out_of_chat_user = SimpleNamespace(
        id=uuid4(), max_user_id="max-user-outside", display_name="Внешний пользователь", username="ivan"
    )
    members = [
        SimpleNamespace(user=requester, user_id=requester.id, role="chat_admin", is_active=True),
        SimpleNamespace(user=assignee_1, user_id=assignee_1.id, role="member", is_active=True),
        SimpleNamespace(user=assignee_2, user_id=assignee_2.id, role="member", is_active=True),
        SimpleNamespace(user=observer, user_id=observer.id, role="member", is_active=True),
    ]
    task_service = FakeTaskService()
    pending_action_repository = FakePendingActionRepository()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat, members),
        user_repository=FakeUserRepository([requester, assignee_1, assignee_2, observer, out_of_chat_user]),
        task_service=task_service,
        pending_action_repository=pending_action_repository,
    )
    return {
        "service": service,
        "task_service": task_service,
        "pending_action_repository": pending_action_repository,
        "organization_id": organization_id,
        "chat": chat,
        "requester": requester,
        "assignee_1": assignee_1,
        "assignee_2": assignee_2,
        "observer": observer,
        "out_of_chat_user": out_of_chat_user,
        "members": members,
    }


@pytest.mark.anyio
async def test_pending_chat_blocks_task_command(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    chat.status = "pending_approval"

    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="/задача проверить завтра 18:00")
    )

    assert response.response_text == "Этот чат еще не подключен к Дьяку. Ожидается подтверждение супер-администратора."
    assert task_service.created_payload is None


@pytest.mark.anyio
async def test_pending_chat_secretary_command_returns_connection_notice(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    chat.status = "pending_approval"

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/дьяк"))

    assert response.response_text == "Этот чат еще не подключен к Дьяку. Ожидается подтверждение супер-администратора."
    assert response.outbound.method == "send_message"
    assert response.outbound.purpose == "interactive"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "expected_text"),
    [
        ("rejected", "Этот чат не подключен к Дьяку: подключение отклонено супер-администратором."),
        ("suspended", "Этот чат временно отключен в Дьяке. Обратитесь к супер-администратору."),
    ],
)
async def test_inactive_chat_statuses_return_user_facing_notice(
    bot_context: dict[str, object],
    status: str,
    expected_text: str,
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    chat.status = status

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача тест"))

    assert response.response_text == expected_text
    assert response.outbound.method == "send_message"
    assert response.outbound.purpose == "interactive"
    assert task_service.created_payload is None


@pytest.mark.anyio
async def test_active_chat_allows_task_command(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    chat.status = "active"

    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="/задача проверить завтра 18:00")
    )

    assert "Укажите исполнителя или исполнителей через @упоминание." in response.response_text
    assert pending_action_repository.created[-1].action_type == "task_create_select_assignee"


@pytest.mark.anyio
async def test_create_task_command_rejects_past_deadline_and_keeps_deadline_pending(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="/задача Проверить сегодня 10:00")
    )

    assert "Срок уже прошел. Укажите будущий срок задачи." in response.response_text
    assert task_service.created_payload is None
    assert len(pending_action_repository.created) == 1
    pending = pending_action_repository.created[0]
    assert pending.action_type == "task_create_set_deadline"
    assert pending.status == "pending"


@pytest.mark.anyio
async def test_admin_deadline_followup_rejects_past_deadline_until_valid(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет"))
    deadline_pending = pending_action_repository.created[-1]

    invalid = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="сегодня 10:00"))

    assert "Срок уже прошел. Укажите будущий срок задачи." in invalid.response_text
    assert task_service.created_payload is None
    assert deadline_pending.status == "pending"
    assert pending_action_repository.created[-1] is deadline_pending

    valid = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="завтра до 18:00"))

    assert "Укажите исполнителя или исполнителей через @упоминание." in valid.response_text
    assert task_service.created_payload is None
    assert deadline_pending.status == "cancelled"
    assert pending_action_repository.created[-1].action_type == "task_create_select_assignee"


@pytest.mark.anyio
async def test_chat_admin_deadline_followup_today_in_one_hour_opens_assignee_picker(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет"))
    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="сегодня через час")
    )

    assert response.ok is True
    assert "Укажите исполнителя или исполнителей через @упоминание." in response.response_text
    assert task_service.created_payload is None
    pending = pending_action_repository.created[-1]
    assert pending.action_type == "task_create_select_assignee"
    assert pending.deadline_at == datetime(2026, 5, 20, 11, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_member_deadline_followup_today_in_one_hour_creates_self_task(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    bot_context["members"][0].role = "member"

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет"))
    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="сегодня через час")
    )

    assert response.ok is True
    assert "Задача #" in response.response_text
    assert "создана ✅" in response.response_text
    assert "Исполнитель: Постановщик" in response.response_text
    assert "20.05 16:00" in response.response_text
    assert "20.05 18:00" not in response.response_text
    assert task_service.created_payload is not None
    assert task_service.created_payload.assignee_ids == [requester.id]
    assert task_service.created_payload.deadline_at == datetime(2026, 5, 20, 11, 0, tzinfo=timezone.utc)
    assert pending_action_repository.created[-1].status == "completed"


@pytest.mark.anyio
async def test_deadline_followup_conflicting_future_day_and_relative_delta_keeps_pending(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет"))
    deadline_pending = pending_action_repository.created[-1]
    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="завтра через час")
    )

    assert "Не понял срок задачи." in response.response_text
    assert task_service.created_payload is None
    assert deadline_pending.status == "pending"
    assert pending_action_repository.created[-1] is deadline_pending


def make_event(*, chat_id: UUID, user_id: UUID, text: str, reply_to_text: str | None = None) -> MaxBotWebhookEvent:
    return MaxBotWebhookEvent(
        chat_id=str(chat_id),
        user_id=str(user_id),
        message_id=str(uuid4()),
        text=text,
        reply_to_text=reply_to_text,
    )


def make_normalized_event(
    *,
    chat_id: UUID,
    user_id: UUID,
    text: str,
    message_id: str = "mock-command-message",
    reply_to_message_id: str | None = None,
    reply_to_text: str | None = None,
    reply_to_author_id: str | None = None,
) -> NormalizedBotEvent:
    return NormalizedBotEvent(
        chat_id=str(chat_id),
        user_id=str(user_id),
        message_id=message_id,
        text=text,
        reply_to_message_id=reply_to_message_id,
        reply_to_text=reply_to_text,
        reply_to_author_id=reply_to_author_id,
    )


def assert_compact_task_creation_response(
    response,
    *,
    title: str,
    assignee_line: str,
    deadline_text: str | None = None,
) -> None:
    assert response.outbound.method == "send_inline_keyboard_message"
    assert re.search(r"Задача #\d+ создана ✅", response.response_text)
    assert f"Текст: {title}" in response.response_text
    assert assignee_line in response.response_text
    assert "Срок: " in response.response_text
    if deadline_text is not None:
        assert deadline_text in response.response_text
    assert "ID:" not in response.response_text
    assert "Статус: new" not in response.response_text
    assert "Название:" not in response.response_text
    forbidden_buttons = {
        "Написать отчет",
        "Отложить",
        "Принять",
        "Отклонить",
        "Сменить исполнителя",
        "Изменить срок",
        "История",
        "Вложения",
    }
    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons[0][0]["text"] == "Открыть задачу"
    rendered_buttons = str(buttons)
    for button_text in forbidden_buttons:
        assert button_text not in rendered_buttons


def make_delivery_result(
    *,
    task_id: UUID,
    user_id: UUID,
    status: DeliveryStatus,
    error_code: str | None = None,
    primary_status: DeliveryStatus | None = None,
) -> NotificationDeliveryResult:
    delivery_status = primary_status or status
    return NotificationDeliveryResult(
        task_id=task_id,
        user_id=user_id,
        status=status,
        primary_delivery=SimpleNamespace(
            id=uuid4(),
            task_id=task_id,
            user_id=user_id,
            channel="max_dm",
            reminder_type="task_ping",
            status=delivery_status.value,
            error_code=error_code,
            error_message=None,
            sent_at=None,
        ),
    )


def make_chat_delivery_result(
    *,
    task_id: UUID,
    chat_id: UUID,
    status: DeliveryStatus,
    error_code: str | None = None,
    primary_status: DeliveryStatus | None = None,
) -> NotificationDeliveryResult:
    delivery_status = primary_status or status
    return NotificationDeliveryResult(
        task_id=task_id,
        user_id=None,
        chat_id=chat_id,
        status=status,
        primary_delivery=SimpleNamespace(
            id=uuid4(),
            task_id=task_id,
            user_id=None,
            chat_id=chat_id,
            channel="max_chat",
            reminder_type="task_ping",
            status=delivery_status.value,
            error_code=error_code,
            error_message=None,
            sent_at=None,
        ),
    )


@pytest.mark.anyio
async def test_empty_create_task_command_starts_text_wizard(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))

    assert response.ok is True
    assert response.is_command is True
    assert response.response_text == "/задача\n\nНапишите текст задачи одним сообщением."
    assert response.outbound.method == "send_message"
    assert len(pending_action_repository.created) == 1
    pending = pending_action_repository.created[0]
    assert pending.action_type == "task_create_set_text"
    assert pending.actor_user_id == requester.id
    assert pending.chat_id == chat.id
    assert pending.status == "pending"


@pytest.mark.anyio
async def test_empty_create_task_text_followup_asks_for_deadline(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет")
    )

    assert response.ok is True
    assert response.is_command is False
    assert response.response_text == "/задача\n\nУкажите срок задачи.\nНапример: завтра до 18:00."
    assert task_service.created_payload is None
    text_pending = pending_action_repository.created[0]
    deadline_pending = pending_action_repository.created[1]
    assert text_pending.status == "completed"
    assert deadline_pending.action_type == "task_create_set_deadline"
    assert deadline_pending.title == "Подготовить отчет"
    assert deadline_pending.source_text == "Подготовить отчет"


@pytest.mark.anyio
async def test_member_empty_task_wizard_creates_self_task_after_deadline(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_action_repository = FakePendingActionRepository()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(
            chat,
            [SimpleNamespace(user=requester, user_id=requester.id, role="member", is_active=True)],
        ),
        user_repository=FakeUserRepository([requester]),
        task_service=task_service,
        pending_action_repository=pending_action_repository,
    )

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет"))
    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="завтра до 18:00")
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="Подготовить отчет",
        assignee_line="Исполнитель: Постановщик",
        deadline_text="21.05 18:00",
    )
    assert task_service.created_payload is not None
    assert task_service.created_payload.title == "Подготовить отчет"
    assert task_service.created_payload.assignee_ids == [requester.id]


@pytest.mark.anyio
async def test_admin_empty_task_wizard_opens_assignee_picker_after_deadline(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет"))
    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="завтра до 18:00")
    )

    assert response.ok is True
    assert response.outbound.method == "send_message"
    assert "Срок понял" not in response.response_text
    assert "Укажите исполнителя или исполнителей через @упоминание." in response.response_text
    assert "@Иван Иванов @Мария Петрова" in response.response_text
    assert response.outbound.attachments is None
    assert task_service.created_payload is None
    assert pending_action_repository.created[-1].action_type == "task_create_select_assignee"
    assert pending_action_repository.created[-1].title == "Подготовить отчет"


@pytest.mark.anyio
async def test_admin_task_wizard_collapses_prompts_into_single_message(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient()
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]

    start = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    assert start.outbound.method == "send_message"
    assert start.outbound.message_id == "wizard-message-1"
    assert pending_action_repository.created[0].picker_message_id == "wizard-message-1"

    text_followup = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет")
    )
    assert text_followup.outbound.method == "edit_message"
    assert text_followup.outbound.message_id == "wizard-message-1"
    assert client.edits[-1]["text"] == "/задача\n\nУкажите срок задачи.\nНапример: завтра до 18:00."
    assert pending_action_repository.created[1].picker_message_id == "wizard-message-1"

    deadline_followup = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="завтра до 18:00")
    )
    assert deadline_followup.outbound.method == "edit_message"
    assert deadline_followup.outbound.message_id == "wizard-message-1"
    assert "Срок понял" not in deadline_followup.response_text
    assert "Укажите исполнителя или исполнителей через @упоминание." in deadline_followup.response_text
    assert pending_action_repository.created[-1].action_type == "task_create_select_assignee"
    assert pending_action_repository.created[-1].picker_message_id == "wizard-message-1"

    final = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="assignee-message",
            text="@ivan",
            mentions=[NormalizedMention(raw_text="@ivan", username="ivan")],
        )
    )

    assert final.outbound.method == "edit_message"
    assert final.outbound.message_id == "wizard-message-1"
    assert re.search(r"Задача #\d+ создана ✅", final.response_text)
    assert "Текст: Подготовить отчет" in final.response_text
    assert "Исполнитель: Иван" in final.response_text
    assert "ID:" not in final.response_text
    assert "Статус: new" not in final.response_text
    assert len(client.messages) == 1
    assert client.inline_keyboards == []
    assert len(client.edits) == 3
    assert client.edits[-1]["message_id"] == "wizard-message-1"
    assert client.edits[-1]["attachments"][0]["payload"]["buttons"][0][0]["text"] == "Открыть задачу"
    assert task_service.created_payload is not None
    assert task_service.created_payload.assignee_ids == [bot_context["assignee_1"].id]
    assert pending_action_repository.created[-1].cleanup_status == "edited"


@pytest.mark.anyio
async def test_admin_task_wizard_tracks_nested_max_message_mid(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient(nested_message_id=True)
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]

    start = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    assert start.outbound.message_id == "wizard-message-1"
    assert pending_action_repository.created[0].picker_message_id == "wizard-message-1"

    text_followup = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет")
    )

    assert text_followup.outbound.method == "edit_message"
    assert text_followup.outbound.message_id == "wizard-message-1"
    assert client.edits[-1]["message_id"] == "wizard-message-1"


@pytest.mark.anyio
async def test_task_wizard_deletes_user_input_messages_after_success(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient()
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]
    service.task_wizard_delete_user_inputs = True

    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="/задача", message_id="command-message")
    )
    assert pending_action_repository.created[-1].reply_context["user_input_message_ids"] == ["command-message"]

    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="Подготовить отчет",
            message_id="text-message",
        )
    )
    assert pending_action_repository.created[-1].reply_context["user_input_message_ids"] == [
        "command-message",
        "text-message",
    ]

    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="завтра до 18:00",
            message_id="deadline-message",
        )
    )
    assert pending_action_repository.created[-1].reply_context["user_input_message_ids"] == [
        "command-message",
        "text-message",
        "deadline-message",
    ]

    final = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="assignee-message",
            text="@ivan",
            mentions=[NormalizedMention(raw_text="@ivan", username="ivan")],
        )
    )

    assert re.search(r"Задача #\d+ создана ✅", final.response_text)
    assert client.deletes == [
        {"message_id": "command-message"},
        {"message_id": "text-message"},
        {"message_id": "deadline-message"},
        {"message_id": "assignee-message"},
    ]
    assert pending_action_repository.created[-1].cleanup_status == "edited"


@pytest.mark.anyio
async def test_task_wizard_invalid_deadline_edits_and_deletes_user_input(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient()
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]
    service.task_wizard_delete_user_inputs = True

    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="/задача", message_id="command-message")
    )
    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет", message_id="text-message")
    )
    invalid = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="сегодня 10:00",
            message_id="invalid-deadline-message",
        )
    )

    assert "Срок уже прошел. Укажите будущий срок задачи." in invalid.response_text
    assert invalid.outbound.method == "edit_message"
    assert invalid.outbound.message_id == "wizard-message-1"
    assert task_service.created_payload is None
    assert client.deletes == [{"message_id": "invalid-deadline-message"}]
    assert pending_action_repository.created[-1].status == "pending"
    assert pending_action_repository.created[-1].cleanup_status == "edited"


@pytest.mark.anyio
async def test_task_wizard_invalid_deadline_cleanup_flag_disables_error_input_delete(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient()
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]
    service.task_wizard_delete_user_inputs = False

    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="/задача", message_id="command-message")
    )
    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет", message_id="text-message")
    )
    invalid = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="сегодня 10:00",
            message_id="invalid-deadline-message",
        )
    )

    assert "Срок уже прошел. Укажите будущий срок задачи." in invalid.response_text
    assert invalid.outbound.method == "edit_message"
    assert client.deletes == []
    assert pending_action_repository.created[-1].status == "pending"


@pytest.mark.anyio
async def test_task_wizard_multiple_invalid_deadlines_edit_same_message_and_keep_pending(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient()
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]
    service.task_wizard_delete_user_inputs = True

    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="/задача", message_id="command-message")
    )
    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет", message_id="text-message")
    )
    first_invalid = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="завтра через час",
            message_id="invalid-deadline-1",
        )
    )
    second_invalid = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="сегодня 10:00",
            message_id="invalid-deadline-2",
        )
    )

    assert "Не понял срок задачи." in first_invalid.response_text
    assert "Срок уже прошел. Укажите будущий срок задачи." in second_invalid.response_text
    assert first_invalid.outbound.method == "edit_message"
    assert second_invalid.outbound.method == "edit_message"
    assert len(client.messages) == 1
    assert [item["message_id"] for item in client.deletes] == ["invalid-deadline-1", "invalid-deadline-2"]
    assert task_service.created_payload is None
    assert pending_action_repository.created[-1].status == "pending"

    valid = await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="завтра до 18:00", message_id="deadline-message")
    )

    assert "Укажите исполнителя или исполнителей через @упоминание." in valid.response_text
    assert pending_action_repository.created[-1].action_type == "task_create_select_assignee"


@pytest.mark.anyio
async def test_task_wizard_missing_mention_edits_and_deletes_only_actor_input(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    client = FakeWizardMaxApiClient()
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]
    service.task_wizard_delete_user_inputs = True

    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="/задача", message_id="command-message")
    )
    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет", message_id="text-message")
    )
    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="завтра до 18:00", message_id="deadline-message")
    )
    other_user_message = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=assignee_1.id,
            text="обычное обсуждение между шагами",
            message_id="other-user-message",
        )
    )
    invalid = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="иван",
            message_id="invalid-assignee-message",
        )
    )

    assert other_user_message.outbound is None
    assert "Не вижу @упоминаний." in invalid.response_text
    assert invalid.outbound.method == "edit_message"
    assert task_service.created_payload is None
    assert pending_action_repository.created[-1].status == "pending"
    assert [item["message_id"] for item in client.deletes] == ["invalid-assignee-message"]
    assert "other-user-message" not in [item["message_id"] for item in client.deletes]


@pytest.mark.anyio
async def test_task_wizard_preserves_replied_source_message_during_cleanup(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient()
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]
    service.task_wizard_delete_user_inputs = True

    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача",
            message_id="command-message",
            reply_to_message_id="source-message",
            reply_to_text="Исходное поручение",
        )
    )
    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="завтра до 18:00",
            message_id="deadline-message",
        )
    )
    await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="assignee-message",
            text="@ivan",
            mentions=[NormalizedMention(raw_text="@ivan", username="ivan")],
        )
    )

    deleted_ids = [str(item["message_id"]) for item in client.deletes]
    assert deleted_ids == ["command-message", "deadline-message", "assignee-message"]
    assert "source-message" not in deleted_ids
    assert "wizard-message-1" not in deleted_ids


@pytest.mark.anyio
async def test_task_wizard_user_input_cleanup_flag_disables_deletion(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient()
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]
    service.task_wizard_delete_user_inputs = False

    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="/задача", message_id="command-message")
    )
    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет", message_id="text-message")
    )
    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="завтра до 18:00",
            message_id="deadline-message",
        )
    )
    await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="assignee-message",
            text="@ivan",
            mentions=[NormalizedMention(raw_text="@ivan", username="ivan")],
        )
    )

    assert client.deletes == []


@pytest.mark.anyio
async def test_task_wizard_delete_failure_does_not_rollback_task(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient(fail_delete=True)
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]
    service.task_wizard_delete_user_inputs = True

    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="/задача", message_id="command-message")
    )
    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет", message_id="text-message")
    )
    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="завтра до 18:00",
            message_id="deadline-message",
        )
    )
    final = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="assignee-message",
            text="@ivan",
            mentions=[NormalizedMention(raw_text="@ivan", username="ivan")],
        )
    )

    assert re.search(r"Задача #\d+ создана ✅", final.response_text)
    assert task_service.created_payload is not None
    assert client.deletes == []
    assert pending_action_repository.created[-1].cleanup_status == "failed"
    assert "user input cleanup deleted 0/4" in pending_action_repository.created[-1].cleanup_error


@pytest.mark.anyio
async def test_member_task_wizard_deletes_user_inputs_after_self_task(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_action_repository = FakePendingActionRepository()
    client = FakeWizardMaxApiClient()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(client=client, enabled=True),  # type: ignore[arg-type]
        chat_repository=FakeChatRepository(
            chat,
            [SimpleNamespace(user=requester, user_id=requester.id, role="member", is_active=True)],
        ),
        user_repository=FakeUserRepository([requester]),
        task_service=task_service,
        pending_action_repository=pending_action_repository,
        task_wizard_delete_user_inputs=True,
    )

    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача проверить",
            message_id="command-message",
        )
    )
    final = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="завтра до 18:00",
            message_id="deadline-message",
        )
    )

    assert re.search(r"Задача #\d+ создана ✅", final.response_text)
    assert client.deletes == [{"message_id": "command-message"}, {"message_id": "deadline-message"}]
    assert pending_action_repository.created[-1].cleanup_status == "edited"


@pytest.mark.anyio
async def test_task_wizard_final_edit_failure_falls_back_to_new_card(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient()
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет"))
    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="завтра до 18:00"))
    client.fail_edit = True

    final = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="assignee-message",
            text="@ivan",
            mentions=[NormalizedMention(raw_text="@ivan", username="ivan")],
        )
    )

    assert final.outbound.method == "send_inline_keyboard_message"
    assert re.search(r"Задача #\d+ создана ✅", final.response_text)
    assert len(client.inline_keyboards) == 1
    assert pending_action_repository.created[-1].cleanup_status == "failed"
    assert "MAX API returned HTTP 400." in pending_action_repository.created[-1].cleanup_error


@pytest.mark.anyio
async def test_member_deadline_clarification_creates_self_task_for_ambiguous_time(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_action_repository = FakePendingActionRepository()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(
            chat,
            [SimpleNamespace(user=requester, user_id=requester.id, role="member", is_active=True)],
        ),
        user_repository=FakeUserRepository([requester]),
        task_service=task_service,
        pending_action_repository=pending_action_repository,
    )

    prompt = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="/задача проверить")
    )
    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="завтра до 01:00")
    )

    assert prompt.response_text == "/задача\n\nУкажите срок задачи.\nНапример: завтра до 18:00."
    assert response.ok is True
    assert "Задача #" in response.response_text
    assert "создана ✅" in response.response_text
    assert "Исполнитель: Постановщик" in response.response_text
    assert task_service.created_payload is not None
    assert task_service.created_payload.assignee_ids == [requester.id]
    assert pending_action_repository.created[-1].status == "completed"


@pytest.mark.anyio
async def test_chat_admin_deadline_clarification_opens_assignee_picker_for_ambiguous_time(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    prompt = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="/задача проверить")
    )
    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="завтра до 01:00")
    )

    assert prompt.response_text == "/задача\n\nУкажите срок задачи.\nНапример: завтра до 18:00."
    assert response.ok is True
    assert response.outbound.method == "send_message"
    assert "Срок понял" not in response.response_text
    assert "Укажите исполнителя или исполнителей через @упоминание." in response.response_text
    assert "@Иван Иванов @Мария Петрова" in response.response_text
    assert response.outbound.attachments is None
    assert task_service.created_payload is None
    assert pending_action_repository.created[-1].action_type == "task_create_select_assignee"
    assert pending_action_repository.created[-1].deadline_at is not None


@pytest.mark.anyio
async def test_super_admin_deadline_clarification_opens_assignee_picker_for_ambiguous_time(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_action_repository = FakePendingActionRepository()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(
            chat,
            [SimpleNamespace(user=requester, user_id=requester.id, role="super_admin", is_active=True)],
        ),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_action_repository,
    )

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача проверить"))
    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="завтра до 01:00")
    )

    assert response.ok is True
    assert response.outbound.method == "send_message"
    assert "Укажите исполнителя или исполнителей через @упоминание." in response.response_text
    assert response.outbound.attachments is None
    assert task_service.created_payload is None
    assert pending_action_repository.created[-1].action_type == "task_create_select_assignee"


@pytest.mark.anyio
async def test_slash_command_during_task_text_pending_supersedes_wizard(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача"))
    pending = pending_action_repository.created[0]
    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/дьяк"))

    assert response.is_command is True
    assert "Дьяк" in response.response_text
    assert pending.status == "cancelled"


@pytest.mark.anyio
async def test_expired_task_text_pending_does_not_create_task(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    pending_action_repository = bot_context["pending_action_repository"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    pending = await pending_action_repository.create_task_text_clarification(
        actor_user_id=requester.id,
        chat_id=chat.id,
        source_message_id="expired-task-text",
        reply_context=None,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="Новая задача"))

    assert response.response_text == "Время создания задачи истекло. Напишите /задача еще раз."
    assert pending.status == "expired"
    assert task_service.created_payload is None


@pytest.mark.anyio
async def test_create_task_without_assignee_creates_pending_mention_prompt(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert response.outbound.method == "send_message"
    assert response.outbound.attachments is None
    assert "Укажите исполнителя или исполнителей через @упоминание." in response.response_text
    assert "@Иван Иванов @Мария Петрова" in response.response_text
    assert "Выберите исполнителя для задачи:" not in response.response_text
    assert "Назначить себе" not in response.response_text
    assert "Открыть в WebApp" not in response.response_text
    assert task_service.created_payload is None

    assert len(pending_action_repository.created) == 1
    pending = pending_action_repository.created[0]
    assert pending.actor_user_id == requester.id
    assert pending.chat_id == chat.id
    assert pending.title == "Подготовить отчет"
    assert pending.source_text == "Подготовить отчет до пятницы"
    assert pending.deadline_at == datetime(2026, 5, 22, 13, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_create_task_without_assignee_prompt_has_no_buttons_when_username_configured(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_action_repository = FakePendingActionRepository()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_action_repository,
        max_bot_username="@secretary_oren_bot",
    )

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )

    assert pending_action_repository.created[0].action_type == "task_create_select_assignee"
    assert response.outbound.method == "send_message"
    assert response.outbound.attachments is None
    assert "Укажите исполнителя или исполнителей через @упоминание." in response.response_text
    assert "secretary_oren_bot" not in response.response_text


@pytest.mark.anyio
async def test_member_create_task_without_assignee_creates_self_task(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(
            chat,
            [SimpleNamespace(user=requester, user_id=requester.id, is_active=True)],
        ),
        user_repository=FakeUserRepository([requester]),
        task_service=task_service,
        pending_action_repository=FakePendingActionRepository(),
    )

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )

    assert response.ok is True
    assert response.outbound.method == "send_inline_keyboard_message"
    assert "Задача #" in response.response_text
    assert "создана ✅" in response.response_text
    assert "Исполнитель: Постановщик" in response.response_text
    assert task_service.created_payload is not None
    assert task_service.created_payload.created_by_user_id == requester.id
    assert task_service.created_payload.assignee_ids == [requester.id]
    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert [button["text"] for row in buttons for button in row] == ["Открыть задачу"]


@pytest.mark.anyio
async def test_member_create_task_with_other_assignee_is_rejected(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    task_service = bot_context["task_service"]
    members = [
        SimpleNamespace(user=requester, user_id=requester.id, role="member", is_active=True),
        SimpleNamespace(user=assignee_1, user_id=assignee_1.id, role="member", is_active=True),
    ]
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat, members),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=FakePendingActionRepository(),
    )

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Проверить доступы | Иван | 2026-05-22",
        )
    )

    assert response.ok is True
    assert response.response_text == "Назначать задачи другим может только админ чата."
    assert task_service.created_payload is None


@pytest.mark.anyio
async def test_pending_assignee_picker_can_be_completed_by_structured_mention(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]

    pending_response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )

    assert pending_response.ok is True
    assert pending_response.outbound.method == "send_message"
    assert pending_response.outbound.attachments is None
    assert "Укажите исполнителя или исполнителей через @упоминание." in pending_response.response_text
    assert task_service.created_payload is None
    pending = pending_action_repository.created[0]

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-mention-message",
            text="@Иван тест выбора исполнителя",
            reply_to_message_id="mock-picker-message",
            mentions=[
                NormalizedMention(
                    raw_text="@Иван",
                    external_user_id=assignee_1.max_user_id,
                    display_name=assignee_1.display_name,
                    start=0,
                    length=5,
                )
            ],
        )
    )

    assert response.ok is True
    assert response.is_command is False
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="Подготовить отчет",
        assignee_line="Исполнитель: Иван",
        deadline_text="22.05 18:00",
    )

    payload = task_service.created_payload
    assert payload is not None
    assert payload.title == "Подготовить отчет"
    assert payload.assignee_ids == [assignee_1.id]
    assert payload.created_by_user_id == requester.id
    assert payload.deadline_at == datetime(2026, 5, 22, 13, 0, tzinfo=timezone.utc)
    assert pending.status == "completed"
    assert pending.selected_assignee_user_id == assignee_1.id
    assert pending.picker_message_id == "mock-picker-message"
    assert pending.cleanup_status == "failed"


@pytest.mark.anyio
async def test_pending_assignee_picker_can_be_completed_by_multiple_structured_mentions(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    assignee_2 = bot_context["assignee_2"]

    await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )
    pending = pending_action_repository.created[0]

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-multiple-mentions-message",
            text="@Иван @Мария тест выбора исполнителей",
            reply_to_message_id="mock-picker-message",
            mentions=[
                NormalizedMention(
                    raw_text="@Иван",
                    external_user_id=assignee_1.max_user_id,
                    display_name=assignee_1.display_name,
                    start=0,
                    length=5,
                ),
                NormalizedMention(
                    raw_text="@Мария",
                    external_user_id=assignee_2.max_user_id,
                    display_name=assignee_2.display_name,
                    start=6,
                    length=6,
                ),
            ],
        )
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="Подготовить отчет",
        assignee_line="Исполнители: Иван, Мария",
        deadline_text="22.05 18:00",
    )
    assert "В сообщении найдено несколько @упоминаний" not in response.response_text

    payload = task_service.created_payload
    assert payload is not None
    assert payload.assignee_ids == [assignee_1.id, assignee_2.id]
    assert pending.status == "completed"


@pytest.mark.anyio
async def test_pending_assignee_picker_bot_mention_assigns_actor(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    service.max_bot_username = "@secretary_oren_bot"
    task_service = bot_context["task_service"]
    user_repository = service.user_repository
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    initial_users_count = len(user_repository.users)

    await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-bot-mention-message",
            text="@secretary_oren_bot",
            mentions=[
                NormalizedMention(
                    raw_text="@secretary_oren_bot",
                    external_user_id="max-user-bot",
                    username="secretary_oren_bot",
                    display_name="secretary_oren_bot",
                    start=0,
                    length=19,
                )
            ],
        )
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="Подготовить отчет",
        assignee_line="Исполнитель: Постановщик",
        deadline_text="22.05 18:00",
    )
    assert "Не удалось определить исполнителей" not in response.response_text

    payload = task_service.created_payload
    assert payload is not None
    assert payload.assignee_ids == [requester.id]
    assert len(user_repository.users) == initial_users_count
    assert all(user.max_user_id != "max-user-bot" for user in user_repository.users)


@pytest.mark.anyio
async def test_pending_assignee_picker_bot_mention_priority_over_help_and_cleanup(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    service.command_parser.bot_username = "secretary_oren_bot"
    service.max_bot_username = "@secretary_oren_bot"
    service.task_wizard_delete_user_inputs = True
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    client = FakeWizardMaxApiClient()
    service.sender = MaxSender(client=client, enabled=True)  # type: ignore[assignment,arg-type]

    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="/задача", message_id="command-message")
    )
    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="Подготовить отчет", message_id="text-message")
    )
    await service.handle_event(
        make_normalized_event(chat_id=chat.id, user_id=requester.id, text="завтра до 18:00", message_id="deadline-message")
    )
    response = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="@secretary_oren_bot /",
            message_id="bot-mention-message",
        )
    )

    assert response.ok is True
    assert response.is_command is False
    assert "Команды Дьяка" not in response.response_text
    assert response.outbound.method == "edit_message"
    assert re.search(r"Задача #\d+ создана ✅", response.response_text)
    assert "Текст: Подготовить отчет" in response.response_text
    assert "Исполнитель: Постановщик" in response.response_text
    assert "Срок: 21.05 18:00" in response.response_text
    payload = task_service.created_payload
    assert payload is not None
    assert payload.assignee_ids == [requester.id]
    assert pending_action_repository.created[-1].status == "completed"
    assert [item["message_id"] for item in client.deletes] == [
        "command-message",
        "text-message",
        "deadline-message",
        "bot-mention-message",
    ]


@pytest.mark.anyio
async def test_pending_assignee_picker_brand_bot_mention_assigns_actor(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-brand-bot-mention-message",
            text="@Дьяк",
            mentions=[
                NormalizedMention(
                    raw_text="@Дьяк",
                    external_user_id="max-user-bot",
                    display_name="Дьяк",
                    start=0,
                    length=5,
                )
            ],
        )
    )

    assert response.ok is True
    assert "Команды Дьяка" not in response.response_text
    assert_compact_task_creation_response(
        response,
        title="Подготовить отчет",
        assignee_line="Исполнитель: Постановщик",
        deadline_text="22.05 18:00",
    )
    payload = task_service.created_payload
    assert payload is not None
    assert payload.assignee_ids == [requester.id]


@pytest.mark.anyio
async def test_pending_assignee_picker_plain_bot_mention_assigns_actor(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    service.max_bot_username = "@secretary_oren_bot"
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-plain-bot-mention-message",
            text="@secretary_oren_bot",
        )
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="Подготовить отчет",
        assignee_line="Исполнитель: Постановщик",
        deadline_text="22.05 18:00",
    )

    payload = task_service.created_payload
    assert payload is not None
    assert payload.assignee_ids == [requester.id]


@pytest.mark.anyio
async def test_pending_assignee_picker_bot_mention_with_user_mentions_assigns_both(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    service.max_bot_username = "@secretary_oren_bot"
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]

    await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-bot-and-user-mention-message",
            text="@secretary_oren_bot @Иван",
            mentions=[
                NormalizedMention(
                    raw_text="@Иван",
                    external_user_id=assignee_1.max_user_id,
                    display_name=assignee_1.display_name,
                    start=20,
                    length=5,
                ),
            ],
        )
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="Подготовить отчет",
        assignee_line="Исполнители: Постановщик, Иван",
        deadline_text="22.05 18:00",
    )

    payload = task_service.created_payload
    assert payload is not None
    assert payload.assignee_ids == [requester.id, assignee_1.id]


@pytest.mark.anyio
async def test_pending_assignee_picker_deduplicates_bot_and_actor_mentions(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    service.max_bot_username = "@secretary_oren_bot"
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-bot-and-actor-mention-message",
            text="@secretary_oren_bot @Постановщик",
            mentions=[
                NormalizedMention(
                    raw_text="@secretary_oren_bot",
                    username="secretary_oren_bot",
                    display_name="secretary_oren_bot",
                    start=0,
                    length=19,
                ),
                NormalizedMention(
                    raw_text="@Постановщик",
                    external_user_id=requester.max_user_id,
                    display_name=requester.display_name,
                    start=20,
                    length=12,
                ),
            ],
        )
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="Подготовить отчет",
        assignee_line="Исполнитель: Постановщик",
        deadline_text="22.05 18:00",
    )
    assert "Некоторые @упоминания" not in response.response_text

    payload = task_service.created_payload
    assert payload is not None
    assert payload.assignee_ids == [requester.id]


@pytest.mark.anyio
async def test_pending_assignee_picker_deduplicates_structured_mentions(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]

    await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-duplicate-mentions-message",
            text="@Иван @Иван",
            mentions=[
                NormalizedMention(
                    raw_text="@Иван",
                    external_user_id=assignee_1.max_user_id,
                    display_name=assignee_1.display_name,
                    start=0,
                    length=5,
                ),
                NormalizedMention(
                    raw_text="@Иван",
                    external_user_id=assignee_1.max_user_id,
                    display_name=assignee_1.display_name,
                    start=6,
                    length=5,
                ),
            ],
        )
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="Подготовить отчет",
        assignee_line="Исполнитель: Иван",
        deadline_text="22.05 18:00",
    )
    assert "Некоторые @упоминания" not in response.response_text

    payload = task_service.created_payload
    assert payload is not None
    assert payload.assignee_ids == [assignee_1.id]


@pytest.mark.anyio
async def test_pending_assignee_picker_returns_friendly_text_without_structured_mentions(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )
    pending = pending_action_repository.created[0]

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-plain-mention-message",
            text="@unknown тест выбора исполнителя",
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert "Не вижу @упоминаний." in response.response_text
    assert "Укажите исполнителя или исполнителей через @." in response.response_text
    assert task_service.created_payload is None
    assert pending.status == "pending"


@pytest.mark.anyio
async def test_pending_assignee_picker_does_not_guess_unresolved_structured_mention(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )
    pending = pending_action_repository.created[0]

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-unresolved-mention-message",
            text="@unknown тест выбора исполнителя",
            mentions=[NormalizedMention(raw_text="@unknown")],
        )
    )

    assert response.ok is True
    assert response.is_command is False
    assert response.action == "reply_prepared"
    assert "Не удалось определить исполнителя." in response.response_text
    assert "Укажите исполнителя или исполнителей через @." in response.response_text
    assert task_service.created_payload is None
    assert pending.status == "pending"


@pytest.mark.anyio
async def test_member_pending_assignee_picker_cannot_assign_others_by_mentions(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    task_service = bot_context["task_service"]
    pending_action_repository = FakePendingActionRepository()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(
            chat,
            [
                SimpleNamespace(user=requester, user_id=requester.id, role="member", is_active=True),
                SimpleNamespace(user=assignee_1, user_id=assignee_1.id, role="member", is_active=True),
            ],
        ),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_action_repository,
    )
    pending = await pending_action_repository.create_task_assignee_picker(
        actor_user_id=requester.id,
        chat_id=chat.id,
        title="Подготовить отчет",
        source_text="Подготовить отчет до пятницы",
        description=None,
        source_message_id="mock-source-message",
        deadline_at=datetime(2026, 5, 22, 13, 0, tzinfo=timezone.utc),
        reply_context=None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-member-mention-message",
            text="@Иван",
            mentions=[
                NormalizedMention(
                    raw_text="@Иван",
                    external_user_id=assignee_1.max_user_id,
                    display_name=assignee_1.display_name,
                )
            ],
        )
    )

    assert response.ok is True
    assert response.response_text == (
        "/задача\n\nНазначать задачи другим участникам может только администратор чата."
    )
    assert task_service.created_payload is None
    assert pending.status == "pending"


@pytest.mark.anyio
async def test_member_pending_assignee_picker_cannot_assign_self_by_bot_mention(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_action_repository = FakePendingActionRepository()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(
            chat,
            [
                SimpleNamespace(user=requester, user_id=requester.id, role="member", is_active=True),
            ],
        ),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_action_repository,
        max_bot_username="@secretary_oren_bot",
    )
    pending = await pending_action_repository.create_task_assignee_picker(
        actor_user_id=requester.id,
        chat_id=chat.id,
        title="Подготовить отчет",
        source_text="Подготовить отчет до пятницы",
        description=None,
        source_message_id="mock-source-message",
        deadline_at=datetime(2026, 5, 22, 13, 0, tzinfo=timezone.utc),
        reply_context=None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id=str(requester.id),
            message_id="mock-member-bot-mention-message",
            text="@secretary_oren_bot",
            mentions=[
                NormalizedMention(
                    raw_text="@secretary_oren_bot",
                    username="secretary_oren_bot",
                    display_name="secretary_oren_bot",
                )
            ],
        )
    )

    assert response.ok is True
    assert response.response_text == (
        "/задача\n\nНазначать задачи другим участникам может только администратор чата."
    )
    assert task_service.created_payload is None
    assert pending.status == "pending"


@pytest.mark.anyio
async def test_create_task_command_calls_task_service(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    assignee_2 = bot_context["assignee_2"]
    observer = bot_context["observer"]

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет | Иван, Мария | 2026-05-20 | наблюдатели: Сергей",
        )
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="Подготовить отчет",
        assignee_line="Исполнители: Иван, Мария",
    )
    payload = task_service.created_payload
    assert payload.organization_id == chat.organization_id
    assert payload.chat_id == chat.id
    assert payload.created_by_user_id == requester.id
    assert payload.title == "Подготовить отчет"
    assert payload.source_message_id is not None
    assert payload.assignee_ids == [assignee_1.id, assignee_2.id]
    assert payload.observer_ids == [observer.id]


@pytest.mark.anyio
async def test_create_task_command_assigns_by_username_mention(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача @ivan подготовь отчет до пятницы",
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="подготовь отчет",
        assignee_line="Исполнитель: Иван",
    )
    assert "Назначьте исполнителя." not in response.response_text

    payload = task_service.created_payload
    assert payload is not None
    assert payload.created_by_user_id == requester.id
    assert payload.title == "подготовь отчет"
    assert payload.source_message_id is not None
    assert payload.assignee_ids == [assignee_1.id]


@pytest.mark.anyio
async def test_create_task_command_assigns_by_display_name_mention(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_2 = bot_context["assignee_2"]

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача @Мария проверить список завтра в 15:00",
        )
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="проверить список",
        assignee_line="Исполнитель: Мария",
    )

    payload = task_service.created_payload
    assert payload is not None
    assert payload.title == "проверить список"
    assert payload.assignee_ids == [assignee_2.id]
    assert payload.deadline_at == datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_create_task_command_assigns_by_max_user_id_mention(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача @max-user-ivan подготовь отчет до пятницы",
        )
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="подготовь отчет",
        assignee_line="Исполнитель: Иван",
    )

    payload = task_service.created_payload
    assert payload is not None
    assert payload.assignee_ids == [assignee_1.id]


@pytest.mark.anyio
async def test_create_task_command_assigns_multiple_mentions(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    assignee_2 = bot_context["assignee_2"]

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача @ivan @maria подготовить материалы до пятницы",
        )
    )

    assert response.ok is True
    assert_compact_task_creation_response(
        response,
        title="подготовить материалы",
        assignee_line="Исполнители: Иван, Мария",
    )

    payload = task_service.created_payload
    assert payload is not None
    assert payload.title == "подготовить материалы"
    assert payload.assignee_ids == [assignee_1.id, assignee_2.id]
    assert payload.deadline_at == datetime(2026, 5, 22, 13, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_reply_create_task_command_uses_mention_instead_of_self_assignment(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]

    response = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача @ivan",
            message_id="mock-command-message-mention-reply",
            reply_to_message_id="mock-source-message-mention-reply",
            reply_to_text="Проверить доступ завтра в 15:00",
            reply_to_author_id=str(requester.id),
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="Проверить доступ",
        assignee_line="Исполнитель: Иван",
    )

    payload = task_service.created_payload
    assert payload is not None
    assert payload.title == "Проверить доступ"
    assert payload.assignee_ids == [assignee_1.id]
    assert payload.created_by_user_id == requester.id
    assert payload.source_message_id == "mock-source-message-mention-reply"


@pytest.mark.anyio
async def test_reply_mention_overrides_fallback_for_different_command_and_reply_authors(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    command_author = bot_context["assignee_2"]
    assignee_1 = bot_context["assignee_1"]
    reply_author = bot_context["observer"]
    bot_context["members"][2].role = "chat_admin"

    response = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=command_author.id,
            text="/задача @ivan",
            message_id="mock-command-message-mention-overrides-fallback",
            reply_to_message_id="mock-source-message-mention-overrides-fallback",
            reply_to_text="Проверить доступ завтра в 15:00",
            reply_to_author_id=str(reply_author.id),
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="Проверить доступ",
        assignee_line="Исполнитель: Иван",
    )

    payload = task_service.created_payload
    assert payload is not None
    assert payload.title == "Проверить доступ"
    assert payload.created_by_user_id == command_author.id
    assert payload.assignee_ids == [assignee_1.id]
    assert command_author.id not in payload.assignee_ids
    assert reply_author.id not in payload.assignee_ids
    assert payload.source_message_id == "mock-source-message-mention-overrides-fallback"
    assert payload.deadline_at == datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_create_task_command_with_unknown_mention_offers_assignee_picker(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача @unknown подготовь отчет до пятницы",
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert "Не удалось найти исполнителя @unknown. Уточните исполнителя в WebApp." in response.response_text
    assert "Укажите исполнителя или исполнителей через @упоминание." in response.response_text
    assert "@Иван Иванов @Мария Петрова" in response.response_text
    assert "Выберите исполнителя для задачи:" not in response.response_text
    assert response.outbound.method == "send_message"
    assert response.outbound.attachments is None
    assert task_service.created_payload is None
    assert len(pending_action_repository.created) == 1
    pending = pending_action_repository.created[0]
    assert pending.actor_user_id == requester.id
    assert pending.chat_id == chat.id
    assert pending.title == "подготовь отчет"


@pytest.mark.anyio
async def test_create_task_command_keeps_final_creation_card_compact_with_unresolved_mentions(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача @ivan @unknown подготовь отчет до пятницы",
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="подготовь отчет",
        assignee_line="Исполнитель: Иван",
    )
    assert "Не удалось найти исполнителя @unknown. Уточните исполнителя в WebApp." not in response.response_text

    payload = task_service.created_payload
    assert payload is not None
    assert payload.assignee_ids == [assignee_1.id]


@pytest.mark.anyio
async def test_reply_create_task_with_unresolved_mention_offers_picker_without_fallback(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача @unknown",
            message_id="mock-command-message-unresolved-mention-reply",
            reply_to_message_id="mock-source-message-unresolved-mention-reply",
            reply_to_text="Проверить доступ завтра в 15:00",
            reply_to_author_id=str(requester.id),
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert "Не удалось найти исполнителя @unknown. Уточните исполнителя в WebApp." in response.response_text
    assert "Укажите исполнителя или исполнителей через @упоминание." in response.response_text
    assert "Выберите исполнителя для задачи:" not in response.response_text
    assert response.outbound.method == "send_message"
    assert response.outbound.attachments is None
    assert task_service.created_payload is None
    assert len(pending_action_repository.created) == 1
    pending = pending_action_repository.created[0]
    assert pending.actor_user_id == requester.id
    assert pending.title == "Проверить доступ"
    assert pending.source_message_id == "mock-source-message-unresolved-mention-reply"


@pytest.mark.anyio
async def test_create_task_command_returns_friendly_error_for_ambiguous_chat_mention(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    task_service = bot_context["task_service"]
    duplicate = SimpleNamespace(
        id=uuid4(), max_user_id="max-user-ivan-duplicate", display_name="Другой Иван", username="ivan"
    )
    members = [
        SimpleNamespace(user=requester, user_id=requester.id, role="chat_admin", is_active=True),
        SimpleNamespace(user=assignee_1, user_id=assignee_1.id, is_active=True),
        SimpleNamespace(user=duplicate, user_id=duplicate.id, is_active=True),
    ]
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat, members),
        user_repository=FakeUserRepository([requester, assignee_1, duplicate]),
        task_service=task_service,
    )

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача @ivan подготовь отчет до пятницы",
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert response.response_text == (
        "Нашлось несколько пользователей для @ivan. Уточните исполнителя в WebApp."
    )
    assert task_service.created_payload is None


@pytest.mark.anyio
async def test_create_task_command_returns_clear_error_for_missing_display_name(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет | Неизвестный | 2026-05-20",
        )
    )

    assert response.ok is False
    assert response.action == "error"
    assert response.error == "Пользователь не найден по display_name: Неизвестный"


@pytest.mark.anyio
async def test_reply_create_task_command_assigns_command_author_for_another_users_message(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача",
            message_id="mock-command-message-1",
            reply_to_message_id="mock-source-message-1",
            reply_to_text="Иван, подготовь отчет до пятницы",
            reply_to_author_id="mock-author-1",
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="Иван, подготовь отчет",
        assignee_line="Исполнитель: Постановщик",
        deadline_text="22.05 18:00",
    )
    assert "Назначьте исполнителя." not in response.response_text

    payload = task_service.created_payload
    assert payload is not None
    assert payload.organization_id == chat.organization_id
    assert payload.chat_id == chat.id
    assert payload.created_by_user_id == requester.id
    assert payload.title == "Иван, подготовь отчет"
    assert payload.deadline_at == datetime(2026, 5, 22, 13, 0, tzinfo=timezone.utc)
    assert payload.assignee_ids == [requester.id]
    assert payload.source_message_id == "mock-source-message-1"
    assert payload.description == (
        "Исходный текст: Иван, подготовь отчет до пятницы\n"
        "Исходное сообщение MAX: mock-source-message-1\n"
        "Автор исходного сообщения MAX: mock-author-1\n"
        "Команда MAX: mock-command-message-1"
    )


@pytest.mark.anyio
async def test_reply_create_task_command_assigns_command_author_for_own_message(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача",
            message_id="mock-command-message-2",
            reply_to_message_id="mock-source-message-2",
            reply_to_text="Проверить доступ завтра в 15:00",
            reply_to_author_id=str(requester.id),
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="Проверить доступ",
        assignee_line="Исполнитель: Постановщик",
        deadline_text="21.05 15:00",
    )
    assert "Назначьте исполнителя." not in response.response_text

    payload = task_service.created_payload
    assert payload is not None
    assert payload.created_by_user_id == requester.id
    assert payload.assignee_ids == [requester.id]
    assert payload.source_message_id == "mock-source-message-2"
    assert payload.title == "Проверить доступ"
    assert payload.deadline_at == datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
@pytest.mark.parametrize("reply_text", ["Отпуск2", "Добрый вечер"])
async def test_reply_create_task_inline_deadline_uses_reply_text_and_opens_assignee_picker(
    bot_context: dict[str, object],
    reply_text: str,
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача завтра 15:00",
            message_id="mock-command-message-inline-deadline",
            reply_to_message_id="mock-source-message-inline-deadline",
            reply_to_text=reply_text,
            reply_to_author_id="mock-author-inline-deadline",
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert response.outbound.method == "send_message"
    assert response.outbound.attachments is None
    assert "Укажите исполнителя или исполнителей через @упоминание." in response.response_text
    assert "Выберите исполнителя для задачи:" not in response.response_text
    assert "ID:" not in response.response_text
    assert "Статус: new" not in response.response_text
    assert task_service.created_payload is None
    assert task_service.response_calls == []

    pending = pending_action_repository.created[0]
    assert pending.action_type == "task_create_select_assignee"
    assert pending.title == reply_text
    assert pending.source_text == reply_text
    assert pending.source_message_id == "mock-source-message-inline-deadline"
    assert pending.deadline_at == datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_reply_create_task_inline_mention_and_deadline_uses_reply_text(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]

    response = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача @ivan завтра 15:00",
            message_id="mock-command-message-inline-mention-deadline",
            reply_to_message_id="mock-source-message-inline-mention-deadline",
            reply_to_text="Отпуск2",
            reply_to_author_id="mock-author-inline-mention-deadline",
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="Отпуск2",
        assignee_line="Исполнитель: Иван",
        deadline_text="21.05 15:00",
    )

    payload = task_service.created_payload
    assert payload is not None
    assert payload.title == "Отпуск2"
    assert payload.assignee_ids == [assignee_1.id]
    assert payload.source_message_id == "mock-source-message-inline-mention-deadline"
    assert payload.deadline_at == datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_real_like_reply_link_payload_creates_self_task(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    reply_author_id = uuid4()

    event = normalize_max_event(
        {
            "update_type": "message_created",
            "timestamp": 1779439001000,
            "message": {
                "recipient": {
                    "chat_id": str(chat.id),
                    "chat_type": "dialog",
                    "user_id": str(requester.id),
                },
                "sender": {
                    "user_id": str(requester.id),
                    "name": requester.display_name,
                },
                "body": {
                    "mid": "mock-command-message-real-link",
                    "seq": 101,
                    "text": "/задача",
                },
                "link": {
                    "type": "reply",
                    "chat_id": str(chat.id),
                    "message": {
                        "mid": "mock-source-message-real-link",
                        "seq": 100,
                        "text": "Проверить доступ завтра в 15:00",
                    },
                    "sender": {
                        "user_id": str(reply_author_id),
                        "name": "Другой участник",
                    },
                },
                "timestamp": 1779439001000,
            },
        }
    )

    response = await service.handle_event(event)

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="Проверить доступ",
        assignee_line="Исполнитель: Постановщик",
        deadline_text="21.05 15:00",
    )

    payload = task_service.created_payload
    assert payload is not None
    assert payload.created_by_user_id == requester.id
    assert payload.assignee_ids == [requester.id]
    assert payload.source_message_id == "mock-source-message-real-link"
    assert payload.title == "Проверить доступ"
    assert payload.deadline_at == datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    assert payload.description == (
        "Исходный текст: Проверить доступ завтра в 15:00\n"
        "Исходное сообщение MAX: mock-source-message-real-link\n"
        f"Автор исходного сообщения MAX: {reply_author_id}\n"
        "Команда MAX: mock-command-message-real-link"
    )


@pytest.mark.anyio
async def test_list_chat_tasks_command_returns_active_chat_tasks(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service.list_tasks = [
        task_service._task(title="Active chat task", status=TaskStatus.NEW.value, chat_id=chat.id),
        task_service._task(title="Done chat task", status=TaskStatus.DONE.value, chat_id=chat.id),
    ]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задачи"))

    assert response.ok is True
    assert task_service.list_filters.chat_id == chat.id
    assert "Active chat task" in response.response_text
    assert "Done chat task" not in response.response_text


@pytest.mark.anyio
async def test_my_tasks_command_returns_active_assignee_tasks_sorted_and_limited(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    other_user_id = uuid4()
    now = datetime.now(timezone.utc)
    overdue_deadline = now - timedelta(hours=2)
    future_soon = now + timedelta(hours=2)
    future_later = now + timedelta(days=2)
    task_service.list_tasks = [
        task_service._task(
            title="Cancelled hidden",
            status=TaskStatus.CANCELLED.value,
            organization_id=chat.organization_id,
            assignee_ids=[requester.id],
            deadline_at=overdue_deadline,
            task_number=1,
        ),
        task_service._task(
            title="Done hidden",
            status=TaskStatus.DONE.value,
            organization_id=chat.organization_id,
            assignee_ids=[requester.id],
            deadline_at=overdue_deadline,
            task_number=2,
        ),
        task_service._task(
            title="Rejected hidden",
            status=TaskStatus.REJECTED.value,
            organization_id=chat.organization_id,
            assignee_ids=[requester.id],
            deadline_at=overdue_deadline,
            task_number=3,
        ),
        task_service._task(
            title="Other assignee hidden",
            status=TaskStatus.NEW.value,
            organization_id=chat.organization_id,
            assignee_ids=[other_user_id],
            deadline_at=overdue_deadline,
            task_number=4,
        ),
        task_service._task(
            title="Overdue visible",
            status=TaskStatus.NEW.value,
            organization_id=chat.organization_id,
            assignee_ids=[requester.id],
            deadline_at=overdue_deadline,
            task_number=1042,
            creator_display_name="Иван Иванов",
        ),
        task_service._task(
            title="Soon visible",
            status=TaskStatus.IN_PROGRESS.value,
            organization_id=chat.organization_id,
            assignee_ids=[requester.id],
            deadline_at=future_soon,
            task_number=1047,
            creator_display_name="Мария Петрова",
        ),
        task_service._task(
            title="Later visible",
            status=TaskStatus.WAITING_RESPONSE.value,
            organization_id=chat.organization_id,
            assignee_ids=[requester.id],
            deadline_at=future_later,
            task_number=1048,
        ),
        *[
            task_service._task(
                title=f"No deadline {index}",
                status=TaskStatus.NEW.value,
                organization_id=chat.organization_id,
                assignee_ids=[requester.id],
                deadline_at=None,
                task_number=1050 + index,
                created_at=now - timedelta(minutes=index),
            )
            for index in range(6)
        ],
    ]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/мои задачи"))

    assert response.ok is True
    assert task_service.list_filters.assignee_id == requester.id
    assert task_service.list_filters.organization_id == chat.organization_id
    assert response.outbound.method == "send_inline_keyboard_message"
    assert response.response_text.startswith("Ваши задачи:")
    assert "#1042 · Просрочена" in response.response_text
    assert "#1047 · В работе" in response.response_text
    assert "Постановщик: Иван Иванов" in response.response_text
    assert "Постановщик: Мария Петрова" in response.response_text
    assert "Еще 2 задач — откройте WebApp." in response.response_text
    assert response.response_text.index("Overdue visible") < response.response_text.index("Soon visible")
    assert response.response_text.index("Soon visible") < response.response_text.index("Later visible")
    assert "Cancelled hidden" not in response.response_text
    assert "Done hidden" not in response.response_text
    assert "Rejected hidden" not in response.response_text
    assert "Other assignee hidden" not in response.response_text
    assert str(task_service.list_tasks[4].id) not in response.response_text

    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons == [
        [{"type": "link", "text": "Открыть все в WebApp", "url": "https://maxsecretary.ru"}]
    ]


@pytest.mark.anyio
async def test_my_tasks_command_uses_max_deep_link_button(bot_context: dict[str, object]) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    task_service.list_tasks = [
        task_service._task(
            title="Assigned task",
            status=TaskStatus.NEW.value,
            organization_id=chat.organization_id,
            assignee_ids=[requester.id],
            task_number=2001,
        )
    ]
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        max_bot_username="@secretary_oren_bot",
    )

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/мои_задачи"))

    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons == [
        [
            {
                "type": "link",
                "text": "Открыть все в WebApp",
                "url": "https://max.ru/secretary_oren_bot?startapp=my_tasks",
            }
        ]
    ]


@pytest.mark.anyio
async def test_my_tasks_command_empty_state(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service.list_tasks = [
        task_service._task(
            title="Done hidden",
            status=TaskStatus.DONE.value,
            organization_id=chat.organization_id,
            assignee_ids=[requester.id],
        )
    ]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/мои_задачи"))

    assert response.ok is True
    assert "У вас нет активных задач." in response.response_text
    assert "Создать задачу можно командой /задача в этом чате." in response.response_text
    assert "Done hidden" not in response.response_text
    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons == [
        [{"type": "link", "text": "Открыть Дьяк", "url": "https://maxsecretary.ru"}]
    ]


@pytest.mark.anyio
async def test_task_lookup_by_number_returns_card_for_assignee(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=1)
    task = task_service._task(
        title="Подготовить отчет по заявкам",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=uuid4(),
        assignee_ids=[requester.id],
        assignee_users=[requester],
        deadline_at=deadline,
        task_number=1042,
        creator_display_name="Иван Иванов",
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="#1042"))

    assert response.ok is True
    assert task_service.list_filters.organization_id == chat.organization_id
    assert task_service.list_filters.task_number == 1042
    assert response.response_text.startswith("#1042 · В работе")
    assert "Подготовить отчет по заявкам" in response.response_text
    assert "Постановщик: Иван Иванов" in response.response_text
    assert "Исполнитель: Постановщик" in response.response_text
    assert "Статус: В работе" in response.response_text
    assert str(task.id) not in response.response_text

    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons[0] == [
        {
            "type": "callback",
            "text": "Написать отчет",
            "payload": f"task:report:start:{task.id}",
            "intent": "default",
        }
    ]
    assert buttons[1] == [
        {
            "type": "callback",
            "text": "Отложить на 1 час",
            "payload": f"task:snooze:1h:{task.id}",
            "intent": "default",
        }
    ]
    assert buttons[2] == [
        {"type": "link", "text": "Открыть в WebApp", "url": "https://maxsecretary.ru/tasks"}
    ]


@pytest.mark.anyio
async def test_task_lookup_by_slash_number_returns_card_for_creator(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    task_service.list_tasks = [
        task_service._task(
            title="Проверить доступы",
            status=TaskStatus.NEW.value,
            organization_id=chat.organization_id,
            chat_id=chat.id,
            created_by_user_id=requester.id,
            assignee_ids=[assignee_1.id],
            assignee_users=[assignee_1],
            deadline_at=None,
            task_number=1047,
            creator_display_name="Постановщик",
        )
    ]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/1047"))

    assert response.ok is True
    assert "#1047 · Новая" in response.response_text
    assert "Срок: не указан" in response.response_text
    assert "Исполнитель: Иван" in response.response_text


@pytest.mark.anyio
async def test_task_lookup_missing_and_unauthorized_use_same_response(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    bot_context["members"][0].role = "member"
    unauthorized_task = task_service._task(
        title="Чужая задача",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=uuid4(),
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1042,
    )
    task_service.list_tasks = [unauthorized_task]

    unauthorized = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="#1042"))
    task_service.list_tasks = []
    missing = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="#1042"))

    assert unauthorized.response_text == "Задача #1042 не найдена или у вас нет доступа."
    assert missing.response_text == "Задача #1042 не найдена или у вас нет доступа."
    assert str(unauthorized_task.id) not in unauthorized.response_text


@pytest.mark.anyio
async def test_task_lookup_overdue_and_deep_link(bot_context: dict[str, object]) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    task = task_service._task(
        title="Просроченная задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=requester.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        deadline_at=datetime.now(timezone.utc) - timedelta(hours=1),
        task_number=1042,
        creator_display_name="Постановщик",
    )
    task_service.list_tasks = [task]
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        max_bot_username="@secretary_oren_bot",
    )

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="T-1042"))

    assert response.response_text.startswith("#1042 · Просрочена")
    assert "Статус: Просрочена" in response.response_text
    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons[2] == [
        {
            "type": "link",
            "text": "Открыть в WebApp",
            "url": "https://max.ru/secretary_oren_bot?startapp=task_1042",
        }
    ]


@pytest.mark.anyio
async def test_task_lookup_creator_sees_accept_reject_buttons_for_pending_report(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    response_id = uuid4()
    task = task_service._task(
        title="Проверить отчет",
        status=TaskStatus.WAITING_ACCEPTANCE.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=requester.id,
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1042,
        responses=[
            SimpleNamespace(
                id=response_id,
                user_id=assignee_1.id,
                status=TaskResponseStatus.SUBMITTED.value,
                created_at=datetime.now(timezone.utc),
            )
        ],
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="#1042"))

    assert "Исполнитель отправил отчет." in response.response_text
    assert str(task.id) not in response.response_text
    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons[0] == [
        {
            "type": "callback",
            "text": "Принять",
            "payload": f"task:accept:{task.id}:{response_id}",
            "intent": "default",
        },
        {
            "type": "callback",
            "text": "Отклонить",
            "payload": f"task:reject:{task.id}:{response_id}",
            "intent": "default",
        },
    ]
    assert buttons[1][0]["text"] == "Открыть в WebApp"


@pytest.mark.anyio
async def test_task_lookup_assignee_does_not_see_accept_reject_for_own_report(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    bot_context["members"][0].role = "member"
    response_id = uuid4()
    task = task_service._task(
        title="Мой отчет",
        status=TaskStatus.WAITING_ACCEPTANCE.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=uuid4(),
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
        responses=[
            SimpleNamespace(
                id=response_id,
                user_id=requester.id,
                status=TaskResponseStatus.SUBMITTED.value,
                created_at=datetime.now(timezone.utc),
            )
        ],
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="#1042"))

    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    button_texts = [button["text"] for row in buttons for button in row]
    assert "Принять" not in button_texts
    assert "Отклонить" not in button_texts
    assert "Написать отчет" in button_texts


@pytest.mark.anyio
async def test_task_lookup_chat_admin_sees_accept_reject_buttons_for_pending_report(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    bot_context["members"][0].role = "chat_admin"
    response_id = uuid4()
    task = task_service._task(
        title="Отчет для админа",
        status=TaskStatus.WAITING_ACCEPTANCE.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=uuid4(),
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1042,
        responses=[
            SimpleNamespace(
                id=response_id,
                user_id=assignee_1.id,
                status=TaskResponseStatus.SUBMITTED.value,
                created_at=datetime.now(timezone.utc),
            )
        ],
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="#1042"))

    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons[0][0]["payload"] == f"task:accept:{task.id}:{response_id}"
    assert buttons[0][1]["payload"] == f"task:reject:{task.id}:{response_id}"


@pytest.mark.anyio
async def test_task_report_command_with_text_submits_report(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task = task_service._task(
        title="Отчетная задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="/отчет #1042 сделал, доступы проверены")
    )

    assert response.ok is True
    assert task_service.response_calls == [(task.id, task_service.response_calls[0][1])]
    payload = task_service.response_calls[0][1]
    assert payload.user_id == requester.id
    assert payload.text == "сделал, доступы проверены"
    assert "Отчет по задаче #1042 отправлен" in response.response_text
    assert "Ответ передан постановщику на приемку." in response.response_text
    assert str(task.id) not in response.response_text
    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons == [
        [{"type": "link", "text": "Открыть задачу", "url": "https://maxsecretary.ru/tasks"}]
    ]


@pytest.mark.anyio
async def test_task_report_command_with_text_cleans_command_message_when_enabled(
    bot_context: dict[str, object],
) -> None:
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task = task_service._task(
        title="Отчетная задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]
    max_client = FakeWizardMaxApiClient()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(client=max_client, enabled=True, interactive_enabled=True),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=bot_context["pending_action_repository"],
        task_wizard_delete_user_inputs=True,
    )

    response = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            message_id="inline-report-command",
            text="/отчет #1042 сделал, доступы проверены",
        )
    )

    assert response.outbound.method == "send_inline_keyboard_message"
    assert response.response_text == "Отчет по задаче #1042 отправлен ✅\n\nОтвет передан постановщику на приемку."
    assert task_service.response_calls[0][1].text == "сделал, доступы проверены"
    assert [item["message_id"] for item in max_client.deletes] == ["inline-report-command"]


@pytest.mark.anyio
async def test_pending_acceptance_reject_reason_saves_reason_and_notifies_assignee(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    response_id = uuid4()
    task = task_service._task(
        title="Проверить отчет",
        status=TaskStatus.WAITING_ACCEPTANCE.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=requester.id,
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1042,
        responses=[
            SimpleNamespace(
                id=response_id,
                user_id=assignee_1.id,
                status=TaskResponseStatus.SUBMITTED.value,
                created_at=datetime.now(timezone.utc),
            )
        ],
    )
    task_service.list_tasks = [task]
    await pending_action_repository.create_task_acceptance_reject_reason(
        actor_user_id=requester.id,
        chat_id=chat.id,
        task_id=task.id,
        response_id=response_id,
        task_ref="#1042",
        title=task.title,
        source_message_id="callback-message",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    max_client = FakeInlineKeyboardMaxClient()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(client=max_client, enabled=True, interactive_enabled=True),
        chat_repository=bot_context["service"].chat_repository,
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_action_repository,
    )

    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="Нужно подробнее раскрыть выводы")
    )

    assert response.ok is True
    assert "Причина отправлена исполнителю" in response.response_text
    assert task_service.reject_calls[0][0] == task.id
    assert task_service.reject_calls[0][1] == response_id
    assert task_service.reject_calls[0][2].comment == "Нужно подробнее раскрыть выводы"
    pending = pending_action_repository.created[-1]
    assert pending.action_type == "task_acceptance_reject_reason"
    assert pending.status == "completed"
    assert len(max_client.inline_keyboards) == 1
    notice = max_client.inline_keyboards[0]
    assert notice["user_id"] == assignee_1.max_user_id
    assert "Приемка по задаче #1042 отклонена ❌" in notice["text"]
    assert "Нужно подробнее раскрыть выводы" in notice["text"]
    button_texts = [button["text"] for row in notice["button_rows"] for button in row]
    assert button_texts == ["Написать отчет", "Открыть задачу"]


@pytest.mark.anyio
async def test_task_report_command_without_text_creates_pending_report(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task = task_service._task(
        title="Отчетная задача",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/отчет 1042"))

    assert response.ok is True
    assert response.response_text == "/отчет #1042\n\nНапишите отчет по задаче #1042 одним сообщением."
    pending = pending_repository.created[-1]
    assert pending.action_type == "task_report_submit"
    assert pending.actor_user_id == requester.id
    assert pending.chat_id == chat.id
    assert pending.reply_context["task_id"] == str(task.id)
    assert pending.reply_context["task_ref"] == "#1042"
    assert len(pending.reply_context["user_input_message_ids"]) == 1
    assert task_service.response_calls == []


@pytest.mark.anyio
async def test_task_report_wizard_edits_prompt_to_final_and_cleans_inputs(
    bot_context: dict[str, object],
) -> None:
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task = task_service._task(
        title="Отчетная задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]
    max_client = FakeWizardMaxApiClient()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(client=max_client, enabled=True, interactive_enabled=True),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_repository,
        task_wizard_delete_user_inputs=True,
    )

    prompt = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            message_id="report-command-message",
            text="/отчет #1042",
        )
    )
    pending = pending_repository.created[-1]
    followup = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            message_id="report-text-message",
            text="Готово, доступы проверены",
        )
    )

    assert prompt.outbound.method == "send_message"
    assert max_client.messages[0]["text"] == "/отчет #1042\n\nНапишите отчет по задаче #1042 одним сообщением."
    assert pending.picker_message_id == "wizard-message-1"
    assert followup.outbound.method == "edit_message"
    assert max_client.edits[0]["message_id"] == "wizard-message-1"
    assert max_client.edits[0]["text"] == "Отчет по задаче #1042 отправлен ✅\n\nОтвет передан постановщику на приемку."
    assert task_service.response_calls[0][1].text == "Готово, доступы проверены"
    assert [item["message_id"] for item in max_client.deletes] == [
        "report-command-message",
        "report-text-message",
    ]
    assert pending.status == "completed"
    assert pending.cleanup_status == "edited"


@pytest.mark.anyio
async def test_task_report_wizard_cleanup_disabled_leaves_user_inputs(
    bot_context: dict[str, object],
) -> None:
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task = task_service._task(
        title="Отчетная задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]
    max_client = FakeWizardMaxApiClient()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(client=max_client, enabled=True, interactive_enabled=True),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_repository,
        task_wizard_delete_user_inputs=False,
    )

    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            message_id="report-command-message",
            text="/отчет #1042",
        )
    )
    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            message_id="report-text-message",
            text="Готово, доступы проверены",
        )
    )

    assert max_client.deletes == []
    assert task_service.response_calls[0][1].text == "Готово, доступы проверены"


@pytest.mark.anyio
async def test_task_report_wizard_preserves_other_user_messages_between_steps(
    bot_context: dict[str, object],
) -> None:
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    task = task_service._task(
        title="Отчетная задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]
    max_client = FakeWizardMaxApiClient()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(client=max_client, enabled=True, interactive_enabled=True),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_repository,
        task_wizard_delete_user_inputs=True,
    )

    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            message_id="report-command-message",
            text="/отчет #1042",
        )
    )
    other = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=assignee_1.id,
            message_id="other-user-message",
            text="Обычное сообщение между шагами",
        )
    )
    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            message_id="report-text-message",
            text="Готово, доступы проверены",
        )
    )

    assert other.action == "ignored"
    assert [item["message_id"] for item in max_client.deletes] == [
        "report-command-message",
        "report-text-message",
    ]


@pytest.mark.anyio
async def test_task_report_wizard_empty_report_edits_error_and_keeps_pending(
    bot_context: dict[str, object],
) -> None:
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task = task_service._task(
        title="Отчетная задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]
    max_client = FakeWizardMaxApiClient()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(client=max_client, enabled=True, interactive_enabled=True),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_repository,
        task_wizard_delete_user_inputs=True,
    )

    await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            message_id="report-command-message",
            text="/отчет #1042",
        )
    )
    pending = pending_repository.created[-1]
    response = await service.handle_event(
        make_normalized_event(
            chat_id=chat.id,
            user_id=requester.id,
            message_id="empty-report-message",
            text=" ",
        )
    )

    assert response.outbound.method == "edit_message"
    assert max_client.edits[0]["text"] == "/отчет #1042\n\nОтчет не может быть пустым. Напишите отчет одним сообщением."
    assert pending.status == "pending"
    assert task_service.response_calls == []
    assert [item["message_id"] for item in max_client.deletes] == ["empty-report-message"]


@pytest.mark.anyio
async def test_next_message_completes_pending_task_report(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task = task_service._task(
        title="Отчетная задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]
    pending = await pending_repository.create_task_report_submit(
        actor_user_id=requester.id,
        chat_id=chat.id,
        task_id=task.id,
        task_ref="#1042",
        title=task.title,
        source_message_id="command-message",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )

    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="Готово, доступы проверены")
    )

    assert response.ok is True
    assert "Отчет по задаче #1042 отправлен" in response.response_text
    payload = task_service.response_calls[0][1]
    assert payload.text == "Готово, доступы проверены"
    assert pending.status == "completed"
    assert pending.completed_task_id == task.id
    second = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="Еще раз"))
    assert second.action == "ignored"
    assert len(task_service.response_calls) == 1


@pytest.mark.anyio
async def test_expired_pending_task_report_returns_friendly_response(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task = task_service._task(
        title="Отчетная задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]
    pending = await pending_repository.create_task_report_submit(
        actor_user_id=requester.id,
        chat_id=chat.id,
        task_id=task.id,
        task_ref="#1042",
        title=task.title,
        source_message_id="command-message",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="Отчет"))

    assert response.response_text == "/отчет #1042\n\nВремя отправки отчета истекло. Используйте /отчет #1042 еще раз."
    assert pending.status == "expired"
    assert task_service.response_calls == []


@pytest.mark.anyio
@pytest.mark.parametrize("reply_text", ["Отпуск..", "Добрый вечер"])
async def test_reply_task_deadline_followup_takes_priority_over_stale_report_pending(
    bot_context: dict[str, object],
    reply_text: str,
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    report_task = task_service._task(
        title="Старый отчет",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=uuid4(),
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=9,
    )
    task_service.list_tasks = [report_task]
    old_report_pending = await pending_repository.create_task_report_submit(
        actor_user_id=requester.id,
        chat_id=chat.id,
        task_id=report_task.id,
        task_ref="#9",
        title=report_task.title,
        source_message_id="old-report-source",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )

    prompt = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача",
            reply_to_text=reply_text,
        )
    )

    assert prompt.response_text == "/задача\n\nУкажите срок задачи.\nНапример: завтра до 18:00."
    assert old_report_pending.status == "cancelled"
    deadline_pending = pending_repository.created[-1]
    assert deadline_pending.action_type == "task_create_set_deadline"
    assert deadline_pending.title == reply_text

    followup = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="завтра до 18:00",
        )
    )

    assert followup.ok is True
    assert followup.is_command is False
    assert followup.action == "reply_prepared"
    assert "Срок понял" not in followup.response_text
    assert "Укажите исполнителя или исполнителей через @упоминание." in followup.response_text
    assert followup.outbound.method == "send_message"
    assert followup.outbound.attachments is None
    assert "Отчет по задаче #9 отправлен" not in followup.response_text
    assert task_service.response_calls == []
    assert task_service.created_payload is None
    assert deadline_pending.status == "cancelled"
    assignee_pending = pending_repository.created[-1]
    assert assignee_pending.action_type == "task_create_select_assignee"
    assert assignee_pending.title == reply_text
    assert assignee_pending.deadline_at is not None


@pytest.mark.anyio
async def test_member_reply_task_deadline_followup_creates_self_task(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_repository = FakePendingActionRepository()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(
            chat,
            [SimpleNamespace(user=requester, user_id=requester.id, role="member", is_active=True)],
        ),
        user_repository=FakeUserRepository([requester]),
        task_service=task_service,
        pending_action_repository=pending_repository,
    )

    await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/задача", reply_to_text="Отпуск"))
    followup = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="завтра до 18:00"))

    assert followup.ok is True
    assert "Задача #" in followup.response_text
    assert "создана ✅" in followup.response_text
    assert "Исполнитель: Постановщик" in followup.response_text
    assert task_service.created_payload is not None
    assert task_service.created_payload.title == "Отпуск"
    assert task_service.created_payload.assignee_ids == [requester.id]


@pytest.mark.anyio
async def test_slash_task_command_is_not_intercepted_by_pending_report(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    report_task = task_service._task(
        title="Отчетная задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=uuid4(),
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=9,
    )
    old_report_pending = await pending_repository.create_task_report_submit(
        actor_user_id=requester.id,
        chat_id=chat.id,
        task_id=report_task.id,
        task_ref="#9",
        title=report_task.title,
        source_message_id="old-report-source",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )

    response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача",
            reply_to_text="Отпуск..",
        )
    )

    assert response.is_command is True
    assert response.response_text == "/задача\n\nУкажите срок задачи.\nНапример: завтра до 18:00."
    assert old_report_pending.status == "cancelled"
    assert task_service.response_calls == []


@pytest.mark.anyio
async def test_task_report_denies_non_assignee_and_final_task(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    inaccessible_task = task_service._task(
        title="Чужая задача",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1042,
    )
    completed_task = task_service._task(
        title="Завершенная задача",
        status=TaskStatus.DONE.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1043,
    )
    task_service.list_tasks = [inaccessible_task, completed_task]

    denied = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/отчет #1042 текст"))
    final = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/отчет #1043 текст"))

    assert denied.response_text == "Задача #1042 не найдена или у вас нет доступа."
    assert final.response_text == "Задача #1043 уже завершена."
    assert task_service.response_calls == []


@pytest.mark.anyio
async def test_task_ping_creator_sends_chat_notification_to_source_chat(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    bot_context["members"][0].role = "chat_admin"
    notification_service = FakeNotificationDeliveryService()
    service.notification_delivery_service = notification_service
    task = task_service._task(
        title="Подготовить отчет",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=requester.id,
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        deadline_at=datetime(2026, 5, 28, 18, 0, tzinfo=timezone.utc),
        task_number=1042,
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг #1042"))

    assert response.ok is True
    assert response.response_text == "Напоминание по задаче #1042 отправлено в чат задачи."
    assert len(notification_service.calls) == 1
    call = notification_service.calls[0]
    assert call["chat_id"] == chat.id
    assert call["task_id"] == task.id
    assert call["reminder_type"] == "task_ping"
    assert call["purpose"] == "ping"
    assert call["dedup_since"] is not None
    assert "По задаче #1042 требуется отчет." in call["message"]
    assert "[@Иван](max://user/max-user-ivan), нужен отчет." in call["message"]
    assert "Срок:" in call["message"]
    assert str(task.id) not in call["message"]
    buttons = call["attachments"][0]["payload"]["buttons"]
    assert buttons == [
        [
            {"type": "link", "text": "Открыть задачу", "url": "https://maxsecretary.ru/tasks"}
        ],
    ]
    assert "Написать отчет" not in str(buttons)


@pytest.mark.anyio
async def test_task_ping_mentions_multiple_assignees_with_plain_fallback(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    assignee_2 = bot_context["assignee_2"]
    assignee_without_max = SimpleNamespace(
        id=assignee_2.id,
        max_user_id=None,
        display_name="Мария",
        username="maria",
    )
    notification_service = FakeNotificationDeliveryService()
    service.notification_delivery_service = notification_service
    task = task_service._task(
        title="Проверить список",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=requester.id,
        assignee_ids=[assignee_1.id, assignee_2.id],
        assignee_users=[assignee_1, assignee_without_max],
        task_number=1042,
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг #1042"))

    assert response.response_text == "Напоминание по задаче #1042 отправлено в чат задачи."
    message = notification_service.calls[0]["message"]
    assert "[@Иван](max://user/max-user-ivan), @Мария, нужен отчет." in message
    assert str(task.id) not in message


@pytest.mark.anyio
async def test_task_ping_member_self_assigned_task_is_forbidden_without_delivery(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    bot_context["members"][0].role = "member"
    notification_service = FakeNotificationDeliveryService()
    service.notification_delivery_service = notification_service
    task = task_service._task(
        title="Моя задача",
        status=TaskStatus.IN_PROGRESS.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=requester.id,
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг #1042"))

    assert response.response_text == "Пинг по задаче доступен только администратору чата."
    assert notification_service.calls == []
    assert pending_repository.created == []
    assert task_service.response_calls == []


@pytest.mark.anyio
async def test_task_ping_assignee_without_creator_role_does_not_background_ping_self(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    bot_context["members"][0].role = "member"
    notification_service = FakeNotificationDeliveryService()
    service.notification_delivery_service = notification_service
    task = task_service._task(
        title="Назначено мне",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=uuid4(),
        assignee_ids=[requester.id],
        assignee_users=[requester],
        task_number=1042,
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг #1042"))

    assert response.response_text == "Пинг по задаче доступен только администратору чата."
    assert notification_service.calls == []
    assert pending_repository.created == []


@pytest.mark.anyio
async def test_task_ping_chat_admin_can_ping_assignee(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    bot_context["members"][0].role = "chat_admin"
    notification_service = FakeNotificationDeliveryService()
    service.notification_delivery_service = notification_service
    task = task_service._task(
        title="Проверить доступы",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=uuid4(),
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1042,
    )
    task_service.list_tasks = [task]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг 1042"))

    assert response.response_text == "Напоминание по задаче #1042 отправлено в чат задачи."
    assert notification_service.calls[0]["chat_id"] == chat.id


@pytest.mark.anyio
async def test_task_ping_member_is_forbidden_before_task_lookup(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    bot_context["members"][0].role = "member"
    notification_service = FakeNotificationDeliveryService()
    service.notification_delivery_service = notification_service
    inaccessible = task_service._task(
        title="Чужая задача",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=uuid4(),
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1042,
    )
    completed = task_service._task(
        title="Завершенная задача",
        status=TaskStatus.DONE.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=requester.id,
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1043,
    )
    task_service.list_tasks = [inaccessible, completed]

    denied = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг T-1042"))
    final = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг #1043"))

    assert denied.response_text == "Пинг по задаче доступен только администратору чата."
    assert final.response_text == "Пинг по задаче доступен только администратору чата."
    assert notification_service.calls == []


@pytest.mark.anyio
async def test_task_ping_chat_admin_gets_final_task_response(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    bot_context["members"][0].role = "chat_admin"
    notification_service = FakeNotificationDeliveryService()
    service.notification_delivery_service = notification_service
    completed = task_service._task(
        title="Завершенная задача",
        status=TaskStatus.DONE.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=requester.id,
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1043,
    )
    task_service.list_tasks = [completed]

    final = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг #1043"))

    assert final.response_text == "Задача #1043 уже завершена."
    assert notification_service.calls == []


@pytest.mark.anyio
async def test_task_ping_background_disabled_returns_interactive_response(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    task = task_service._task(
        title="Фоновая отправка отключена",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=requester.id,
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1042,
    )
    task_service.list_tasks = [task]
    notification_service = FakeNotificationDeliveryService(
        results_by_chat_id={
            chat.id: make_chat_delivery_result(
                task_id=task.id,
                chat_id=chat.id,
                status=DeliveryStatus.SKIPPED,
                error_code=BACKGROUND_DISABLED_ERROR,
            )
        }
    )
    service.notification_delivery_service = notification_service

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг #1042"))

    assert response.response_text == "Фоновые уведомления сейчас отключены. Напоминание в чат задачи не отправлено."
    assert response.outbound.method == "send_message"
    assert len(notification_service.calls) == 1


@pytest.mark.anyio
async def test_task_ping_missing_max_chat_and_cooldown(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    assignee_1 = bot_context["assignee_1"]
    task = task_service._task(
        title="Проверить пинг",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=requester.id,
        assignee_ids=[assignee_1.id],
        assignee_users=[assignee_1],
        task_number=1042,
    )
    task_service.list_tasks = [task]
    service.notification_delivery_service = FakeNotificationDeliveryService(
        results_by_chat_id={
            chat.id: make_chat_delivery_result(
                task_id=task.id,
                chat_id=chat.id,
                status=DeliveryStatus.SKIPPED,
                error_code=MISSING_MAX_CHAT_ID_ERROR,
            )
        }
    )

    missing = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг #1042"))

    assert missing.response_text == "Не удалось отправить напоминание: чат задачи недоступен для отправки."

    service.notification_delivery_service = FakeNotificationDeliveryService(
        results_by_chat_id={
            chat.id: make_chat_delivery_result(
                task_id=task.id,
                chat_id=chat.id,
                status=DeliveryStatus.SKIPPED,
                primary_status=DeliveryStatus.SENT,
            )
        }
    )

    cooldown = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/пинг #1042"))

    assert cooldown.response_text == "Напоминание уже отправлялось недавно. Попробуйте позже."


@pytest.mark.anyio
async def test_secretary_command_returns_scoped_summary_and_buttons(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    bot_context["members"][0].role = "member"
    other_user_id = uuid4()
    other_chat_id = uuid4()
    overdue_deadline = datetime.now(timezone.utc) - timedelta(hours=1)
    future_deadline = datetime.now(timezone.utc) + timedelta(days=1)
    accessible_assigned = task_service._task(
        title="Assigned task",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        deadline_at=future_deadline,
    )
    accessible_created = task_service._task(
        title="Waiting acceptance",
        status=TaskStatus.WAITING_ACCEPTANCE.value,
        organization_id=chat.organization_id,
        chat_id=other_chat_id,
        created_by_user_id=requester.id,
    )
    accessible_overdue = task_service._task(
        title="Overdue task",
        status=TaskStatus.OVERDUE.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        deadline_at=overdue_deadline,
    )
    done_task = task_service._task(
        title="Done task",
        status=TaskStatus.DONE.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        assignee_ids=[requester.id],
        deadline_at=overdue_deadline,
    )
    inaccessible_task = task_service._task(
        title="Other user task",
        status=TaskStatus.NEW.value,
        organization_id=chat.organization_id,
        chat_id=chat.id,
        created_by_user_id=other_user_id,
        assignee_ids=[other_user_id],
    )
    task_service.list_tasks = [
        accessible_assigned,
        accessible_created,
        accessible_overdue,
        done_task,
        inaccessible_task,
    ]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/дьяк"))

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert response.outbound.method == "send_inline_keyboard_message"
    assert "Дьяк" in response.response_text
    assert "Всего задач: 3" in response.response_text
    assert "В этом чате: 2" in response.response_text
    assert "Просрочено: 1" in response.response_text
    assert "Ждут вашего ответа: 2" in response.response_text
    assert "Ждут приемки: 1" in response.response_text
    assert str(accessible_assigned.id) not in response.response_text
    assert str(accessible_created.id) not in response.response_text
    assert str(accessible_overdue.id) not in response.response_text

    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons == [
        [{"type": "link", "text": "Открыть Дьяк", "url": "https://maxsecretary.ru"}],
    ]
    button_texts = [button["text"] for row in buttons for button in row]
    assert "Мои задачи" not in button_texts
    assert "Групповая задача" not in button_texts


@pytest.mark.anyio
async def test_secretary_deprecated_alias_uses_dyak_brand(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service.list_tasks = []

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/секретарь"))

    assert "Дьяк" in response.response_text
    assert "ЦИТ секретарь" not in response.response_text
    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons == [[{"type": "link", "text": "Открыть Дьяк", "url": "https://maxsecretary.ru"}]]


@pytest.mark.anyio
async def test_secretary_command_uses_max_deep_link_buttons(bot_context: dict[str, object]) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    task_service.list_tasks = []
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        max_bot_username="@secretary_oren_bot",
    )

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/дьяк"))

    assert "Активных задач пока нет." in response.response_text
    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons == [
        [
            {
                "type": "link",
                "text": "Открыть Дьяк",
                "url": "https://max.ru/secretary_oren_bot?startapp=home",
            }
        ],
    ]


@pytest.mark.anyio
async def test_slash_command_help_returns_fallback_menu(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/"))

    assert response.ok is True
    assert response.is_command is True
    assert response.response_text.startswith("Команды Дьяка")
    assert "/дьяк — сводка и вход в WebApp" in response.response_text
    assert "/задача — создать задачу" in response.response_text
    assert "/мои_задачи — посмотреть мои задачи" in response.response_text
    assert "/отчет #номер — отправить отчет по задаче" in response.response_text
    assert "/пинг #номер — напомнить исполнителю" in response.response_text
    assert "отправьте /помощь или /команды" in response.response_text
    assert "/секретарь" not in response.response_text
    assert response.outbound.method == "send_inline_keyboard_message"
    assert response.outbound.purpose == "interactive"
    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons == [[{"type": "link", "text": "Открыть Дьяк", "url": "https://maxsecretary.ru"}]]
    assert task_service.created_payload is None
    assert pending_action_repository.created == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "text",
    ["/помощь", "/help", "/команды", "помощь", "help", "команды", "дьяк помощь", "/дьяк помощь"],
)
async def test_reliable_help_aliases_return_fallback_menu(bot_context: dict[str, object], text: str) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text=text))

    assert response.ok is True
    assert response.is_command is True
    assert response.response_text.startswith("Команды Дьяка")
    assert "отправьте /помощь или /команды" in response.response_text
    assert response.outbound.method == "send_inline_keyboard_message"
    assert response.outbound.purpose == "interactive"
    assert task_service.created_payload is None
    assert pending_action_repository.created == []


@pytest.mark.anyio
async def test_help_alias_bypasses_pending_chat_gate_with_connection_notice(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    chat.status = "pending_approval"

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/помощь"))

    assert response.ok is True
    assert response.response_text.startswith("Команды Дьяка")
    assert "Этот чат еще не подключен к Дьяку." in response.response_text
    assert task_service.created_payload is None
    assert pending_action_repository.created == []


@pytest.mark.anyio
async def test_slash_command_help_accepts_bot_mention_prefix(bot_context: dict[str, object]) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_action_repository = FakePendingActionRepository()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(bot_username="secretary_oren_bot"),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_action_repository,
        max_bot_username="@secretary_oren_bot",
    )

    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="@secretary_oren_bot /")
    )

    assert response.ok is True
    assert response.is_command is True
    assert response.response_text.startswith("Команды Дьяка")
    assert response.outbound.purpose == "interactive"
    buttons = response.outbound.attachments[0]["payload"]["buttons"]
    assert buttons == [
        [
            {
                "type": "link",
                "text": "Открыть Дьяк",
                "url": "https://max.ru/secretary_oren_bot?startapp=home",
            }
        ],
    ]


@pytest.mark.anyio
async def test_slash_command_help_accepts_bot_mention_help_alias(bot_context: dict[str, object]) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_action_repository = FakePendingActionRepository()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(bot_username="secretary_oren_bot"),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        pending_action_repository=pending_action_repository,
        max_bot_username="@secretary_oren_bot",
    )

    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text="@secretary_oren_bot помощь")
    )

    assert response.ok is True
    assert response.is_command is True
    assert response.response_text.startswith("Команды Дьяка")
    assert task_service.created_payload is None
    assert pending_action_repository.created == []


@pytest.mark.anyio
async def test_plain_help_in_assignee_pending_still_returns_help(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    pending_action_repository = bot_context["pending_action_repository"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]

    await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text="/задача Подготовить отчет до пятницы",
        )
    )
    pending = pending_action_repository.created[0]
    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="помощь"))

    assert response.ok is True
    assert response.is_command is True
    assert response.response_text.startswith("Команды Дьяка")
    assert task_service.created_payload is None
    assert pending.status == "cancelled"


@pytest.mark.anyio
async def test_external_max_command_response_uses_resolved_max_chat_id(bot_context: dict[str, object]) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_action_repository = FakePendingActionRepository()
    chat.max_chat_id = "max-chat-real-001"
    max_client = FakeWizardMaxApiClient()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(bot_username="secretary_oren_bot"),
        sender=MaxSender(client=max_client, enabled=True, interactive_enabled=True),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=FakeUserRepository([requester]),
        task_service=task_service,
        pending_action_repository=pending_action_repository,
        identity_resolver=FakeIdentityResolver(
            user=requester,
            chat=chat,
            organization_id=chat.organization_id,
        ),
        max_bot_username="@secretary_oren_bot",
    )

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id=str(chat.id),
            user_id="max-user-admin",
            message_id="command-message",
            text="/помощь",
        )
    )

    assert response.ok is True
    assert response.outbound.sent is True
    assert response.outbound.chat_id == "max-chat-real-001"
    assert max_client.inline_keyboards[-1]["chat_id"] == "max-chat-real-001"
    assert task_service.created_payload is None
    assert pending_action_repository.created == []


@pytest.mark.anyio
async def test_secretary_command_allows_chat_admin_to_see_current_chat_tasks(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    admin_member = SimpleNamespace(user=requester, user_id=requester.id, role="chat_admin", is_active=True)
    task_service.list_tasks = [
        task_service._task(
            title="Managed chat task",
            status=TaskStatus.NEW.value,
            organization_id=chat.organization_id,
            chat_id=chat.id,
            created_by_user_id=uuid4(),
            assignee_ids=[uuid4()],
        ),
        task_service._task(
            title="Other chat task",
            status=TaskStatus.NEW.value,
            organization_id=chat.organization_id,
            chat_id=uuid4(),
            created_by_user_id=uuid4(),
            assignee_ids=[uuid4()],
        ),
    ]
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat, [admin_member]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
    )

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/дьяк"))

    assert "Всего задач: 1" in response.response_text
    assert "В этом чате: 1" in response.response_text


@pytest.mark.anyio
async def test_secretary_command_does_not_crash_when_sender_is_disabled(
    bot_context: dict[str, object],
) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service.list_tasks = []

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/дьяк"))

    assert response.ok is True
    assert response.outbound.sent is False
    assert response.outbound.reason == "stub: real MAX API sending is disabled"


@pytest.mark.anyio
async def test_secretary_command_sends_when_interactive_enabled_and_background_disabled(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    task_service.list_tasks = []
    client = FakeInlineKeyboardMaxClient()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(
            client=client,  # type: ignore[arg-type]
            enabled=True,
            interactive_enabled=True,
            background_enabled=False,
        ),
        chat_repository=FakeChatRepository(chat, bot_context["members"]),
        user_repository=bot_context["service"].user_repository,
        task_service=task_service,
        max_bot_username="@secretary_oren_bot",
    )

    response = await service.handle_event(make_event(chat_id=chat.id, user_id=requester.id, text="/дьяк"))

    assert response.outbound.sent is True
    assert response.outbound.purpose == "interactive"
    assert client.inline_keyboards == [
        {
            "chat_id": str(chat.id),
            "user_id": None,
            "text": response.response_text,
            "button_rows": response.outbound.attachments[0]["payload"]["buttons"],
        }
    ]


@pytest.mark.anyio
async def test_response_and_done_commands_submit_task_response(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    assignee_1 = bot_context["assignee_1"]
    task_id = uuid4()

    response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=assignee_1.id, text=f"/ответ {task_id} Сделал")
    )
    done_response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=assignee_1.id, text=f"/готово {task_id} Готово")
    )

    assert response.ok is True
    assert done_response.ok is True
    assert [call[0] for call in task_service.response_calls] == [task_id, task_id]
    assert task_service.response_calls[0][1].user_id == assignee_1.id
    assert task_service.response_calls[0][1].text == "Сделал"
    assert task_service.response_calls[1][1].text == "Готово"


@pytest.mark.anyio
async def test_accept_and_reject_commands_call_task_service(bot_context: dict[str, object]) -> None:
    service = bot_context["service"]
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_id = task_service.list_tasks[0].id
    response_id = uuid4()

    accept_response = await service.handle_event(
        make_event(chat_id=chat.id, user_id=requester.id, text=f"/принять {task_id} {response_id}")
    )
    reject_response = await service.handle_event(
        make_event(
            chat_id=chat.id,
            user_id=requester.id,
            text=f"/отклонить {task_id} {response_id} Нужно подробнее",
        )
    )

    assert accept_response.ok is True
    assert reject_response.ok is True
    assert task_service.accept_calls[0][0] == task_id
    assert task_service.accept_calls[0][1] == response_id
    assert task_service.accept_calls[0][2].accepted_by_user_id == requester.id
    assert task_service.reject_calls[0][0] == task_id
    assert task_service.reject_calls[0][1] == response_id
    assert task_service.reject_calls[0][2].comment == "Нужно подробнее"


@pytest.mark.anyio
async def test_external_max_reply_command_uses_resolved_internal_identity(bot_context: dict[str, object]) -> None:
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat),
        user_repository=FakeUserRepository([requester]),
        task_service=task_service,
        identity_resolver=FakeIdentityResolver(
            user=requester,
            chat=chat,
            organization_id=chat.organization_id,
        ),
    )

    response = await service.handle_event(
        NormalizedBotEvent(
            chat_id="max-chat-001",
            user_id="max-user-001",
            message_id="mock-command-message-external",
            text="/задача",
            reply_to_message_id="mock-source-message-external",
            reply_to_text="Проверить доступ завтра в 15:00",
            reply_to_author_id="max-user-source",
        )
    )

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="Проверить доступ",
        assignee_line="Исполнитель: Постановщик",
        deadline_text="21.05 15:00",
    )
    payload = task_service.created_payload
    assert payload is not None
    assert payload.organization_id == chat.organization_id
    assert payload.chat_id == chat.id
    assert payload.created_by_user_id == requester.id
    assert payload.assignee_ids == [requester.id]
    assert payload.source_message_id == "mock-source-message-external"
    assert payload.deadline_at == datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_real_like_external_max_reply_fixture_creates_self_task(
    bot_context: dict[str, object],
) -> None:
    task_service = bot_context["task_service"]
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    fixture_path = Path(__file__).parent / "fixtures" / "max" / "message_reply_link_dialog.json"
    event = normalize_max_event(json.loads(fixture_path.read_text()))
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(
            now_provider=lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        ),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat),
        user_repository=FakeUserRepository([requester]),
        task_service=task_service,
        identity_resolver=FakeIdentityResolver(
            user=requester,
            chat=chat,
            organization_id=chat.organization_id,
        ),
    )

    response = await service.handle_event(event)

    assert response.ok is True
    assert response.action == "reply_prepared"
    assert_compact_task_creation_response(
        response,
        title="Проверить доступ",
        assignee_line="Исполнитель: Постановщик",
        deadline_text="21.05 15:00",
    )
    payload = task_service.created_payload
    assert payload is not None
    assert payload.chat_id == chat.id
    assert payload.created_by_user_id == requester.id
    assert payload.assignee_ids == [requester.id]
    assert payload.source_message_id == "mock-message-source-dialog"
    assert payload.title == "Проверить доступ"
    assert payload.deadline_at == datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_real_like_external_max_callback_routes_to_callback_service(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    task_id = uuid4()
    callback_service = FakeCallbackService(task_id=task_id)
    fixture_path = Path(__file__).parent / "fixtures" / "max" / "message_callback_real.json"
    event = normalize_max_event(json.loads(fixture_path.read_text()))
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(),
        chat_repository=FakeChatRepository(chat),
        user_repository=FakeUserRepository([requester]),
        task_service=task_service,
        identity_resolver=FakeIdentityResolver(
            user=requester,
            chat=chat,
            organization_id=chat.organization_id,
        ),
        callback_service=callback_service,  # type: ignore[arg-type]
    )

    response = await service.handle_event(event)

    assert response.ok is True
    assert response.is_command is False
    assert response.action == "callback_processed"
    assert response.response_text == "Задача взята в работу."
    assert response.outbound is not None
    assert response.outbound.method == "answer_callback"
    assert response.outbound.sent is False
    assert callback_service.events == [
        NormalizedCallbackEvent(
            payload="task:start:11111111-1111-4111-8111-111111111111",
            user_id=requester.id,
            chat_id=chat.id,
            message_id="mock-message-callback-source",
            callback_id="mock-callback-real-001",
        )
    ]


@pytest.mark.anyio
async def test_report_callback_answer_tracks_editable_wizard_message(
    bot_context: dict[str, object],
) -> None:
    chat = bot_context["chat"]
    requester = bot_context["requester"]
    task_service = bot_context["task_service"]
    pending_repository = bot_context["pending_action_repository"]
    task_id = uuid4()
    pending = await pending_repository.create_task_report_submit(
        actor_user_id=requester.id,
        chat_id=chat.id,
        task_id=task_id,
        task_ref="#1042",
        title="Отчетная задача",
        source_message_id="callback-source-message",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    callback_service = FakeCallbackService(
        task_id=task_id,
        action="report",
        response_text="Напишите отчет по задаче #1042 одним сообщением.",
        pending_action_id=pending.id,
        answer_message_text="/отчет #1042\n\nНапишите отчет по задаче #1042 одним сообщением.",
    )
    max_client = FakeWizardMaxApiClient()
    service = MaxBotWebhookService(
        command_parser=BotCommandParser(),
        sender=MaxSender(client=max_client, enabled=True, interactive_enabled=True),
        chat_repository=FakeChatRepository(chat),
        user_repository=FakeUserRepository([requester]),
        task_service=task_service,
        pending_action_repository=pending_repository,
        callback_service=callback_service,  # type: ignore[arg-type]
    )

    response = await service.handle_event(
        NormalizedMaxCallbackEvent(
            payload="task:report:start:11111111-1111-4111-8111-111111111111",
            callback_id="report-callback",
            user_id=str(requester.id),
            chat_id=str(chat.id),
            message_id="callback-source-message",
        )
    )

    assert response.ok is True
    assert response.outbound.method == "answer_callback"
    assert pending.picker_message_id == "wizard-message-1"
    assert max_client.callback_answers[0]["message"] == {
        "text": "/отчет #1042\n\nНапишите отчет по задаче #1042 одним сообщением.",
        "attachments": [],
    }
