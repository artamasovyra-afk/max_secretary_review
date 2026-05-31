from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bot.models import BotCallbackReceipt, BotPendingAction

CALLBACK_RECEIPT_PROCESSING = "processing"
CALLBACK_RECEIPT_SUCCEEDED = "succeeded"
CALLBACK_RECEIPT_FAILED = "failed"
CALLBACK_RECEIPT_SKIPPED = "skipped"
CALLBACK_LOGICAL_PROCESSING = "processing"
CALLBACK_LOGICAL_PROCESSED = "processed"
CALLBACK_LOGICAL_DUPLICATE = "duplicate_logical"
CALLBACK_LOGICAL_FAILED = "failed"
PENDING_ACTION_TASK_CREATE_SELECT_ASSIGNEE = "task_create_select_assignee"
PENDING_ACTION_TASK_CREATE_SET_DEADLINE = "task_create_set_deadline"
PENDING_ACTION_TASK_CREATE_SET_TEXT = "task_create_set_text"
PENDING_ACTION_TASK_REPORT_SUBMIT = "task_report_submit"
PENDING_ACTION_TASK_ACCEPTANCE_REJECT_REASON = "task_acceptance_reject_reason"
PENDING_ACTION_PENDING = "pending"
PENDING_ACTION_COMPLETED = "completed"
PENDING_ACTION_EXPIRED = "expired"
PENDING_ACTION_CANCELLED = "cancelled"
PENDING_ACTION_CLEANUP_PENDING = "pending"
PENDING_ACTION_CLEANUP_EDITED = "edited"
PENDING_ACTION_CLEANUP_PARTIAL = "partial"
PENDING_ACTION_CLEANUP_FAILED = "failed"
PENDING_ACTION_CLEANUP_UNSUPPORTED = "unsupported"


class CallbackReceiptLike(Protocol):
    callback_id: str
    payload: str
    status: str
    response_text: str | None
    last_error: str | None


class BotCallbackReceiptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_callback_id(self, callback_id: str) -> BotCallbackReceipt | None:
        result = await self.session.execute(
            select(BotCallbackReceipt).where(BotCallbackReceipt.callback_id == callback_id)
        )
        return result.scalar_one_or_none()

    async def start(self, *, callback_id: str, payload: str) -> tuple[BotCallbackReceipt, bool]:
        existing = await self.get_by_callback_id(callback_id)
        if existing is not None:
            return existing, False

        receipt = BotCallbackReceipt(
            callback_id=callback_id,
            payload=payload,
            status=CALLBACK_RECEIPT_PROCESSING,
        )
        self.session.add(receipt)
        try:
            await self.session.commit()
            await self.session.refresh(receipt)
        except IntegrityError:
            await self.session.rollback()
            existing_after_race = await self.get_by_callback_id(callback_id)
            if existing_after_race is None:
                raise
            return existing_after_race, False
        return receipt, True

    async def set_logical_context(
        self,
        receipt: BotCallbackReceipt,
        *,
        provider: str,
        actor_user_id: UUID,
        task_id: UUID,
        action_type: str,
        payload_normalized: str,
        logical_key: str,
        logical_window_started_at: datetime,
    ) -> BotCallbackReceipt:
        receipt.provider = provider
        receipt.actor_user_id = actor_user_id
        receipt.task_id = task_id
        receipt.action_type = action_type
        receipt.payload_normalized = payload_normalized
        receipt.logical_key = logical_key
        receipt.logical_window_started_at = logical_window_started_at
        receipt.logical_status = CALLBACK_LOGICAL_PROCESSING
        await self.session.commit()
        await self.session.refresh(receipt)
        return receipt

    async def find_recent_logical_duplicate(
        self,
        *,
        logical_key: str,
        since: datetime,
        exclude_callback_id: str,
    ) -> BotCallbackReceipt | None:
        result = await self.session.execute(
            select(BotCallbackReceipt)
            .where(BotCallbackReceipt.logical_key == logical_key)
            .where(BotCallbackReceipt.callback_id != exclude_callback_id)
            .where(BotCallbackReceipt.created_at >= since)
            .where(BotCallbackReceipt.status.in_([CALLBACK_RECEIPT_PROCESSING, CALLBACK_RECEIPT_SUCCEEDED]))
            .where(
                BotCallbackReceipt.logical_status.in_(
                    [CALLBACK_LOGICAL_PROCESSING, CALLBACK_LOGICAL_PROCESSED]
                )
            )
            .order_by(BotCallbackReceipt.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_succeeded(self, receipt: BotCallbackReceipt, *, response_text: str) -> BotCallbackReceipt:
        receipt.status = CALLBACK_RECEIPT_SUCCEEDED
        if receipt.logical_key is not None:
            receipt.logical_status = CALLBACK_LOGICAL_PROCESSED
        receipt.response_text = response_text
        receipt.last_error = None
        await self.session.commit()
        await self.session.refresh(receipt)
        return receipt

    async def mark_logical_duplicate(
        self,
        receipt: BotCallbackReceipt,
        *,
        response_text: str,
    ) -> BotCallbackReceipt:
        receipt.status = CALLBACK_RECEIPT_SKIPPED
        receipt.logical_status = CALLBACK_LOGICAL_DUPLICATE
        receipt.response_text = response_text
        receipt.last_error = None
        await self.session.commit()
        await self.session.refresh(receipt)
        return receipt

    async def mark_failed(self, receipt: BotCallbackReceipt, *, error: str) -> BotCallbackReceipt:
        receipt.status = CALLBACK_RECEIPT_FAILED
        if receipt.logical_key is not None:
            receipt.logical_status = CALLBACK_LOGICAL_FAILED
        receipt.last_error = error[:1000]
        await self.session.commit()
        await self.session.refresh(receipt)
        return receipt


class BotPendingActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
    ) -> BotPendingAction:
        action = BotPendingAction(
            action_type=PENDING_ACTION_TASK_CREATE_SELECT_ASSIGNEE,
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            title=title,
            source_text=source_text,
            description=description,
            source_message_id=source_message_id,
            deadline_at=deadline_at,
            reply_context=reply_context,
            expires_at=expires_at,
            status=PENDING_ACTION_PENDING,
            picker_message_id=wizard_message_id,
        )
        self.session.add(action)
        await self.session.commit()
        await self.session.refresh(action)
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
    ) -> BotPendingAction:
        action = BotPendingAction(
            action_type=PENDING_ACTION_TASK_CREATE_SET_DEADLINE,
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            title=title,
            source_text=source_text,
            description=description,
            source_message_id=source_message_id,
            deadline_at=None,
            reply_context=reply_context,
            expires_at=expires_at,
            status=PENDING_ACTION_PENDING,
            picker_message_id=wizard_message_id,
        )
        self.session.add(action)
        await self.session.commit()
        await self.session.refresh(action)
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
    ) -> BotPendingAction:
        action = BotPendingAction(
            action_type=PENDING_ACTION_TASK_CREATE_SET_TEXT,
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            title="",
            source_text=None,
            description=None,
            source_message_id=source_message_id,
            deadline_at=None,
            reply_context=reply_context,
            expires_at=expires_at,
            status=PENDING_ACTION_PENDING,
            picker_message_id=wizard_message_id,
        )
        self.session.add(action)
        await self.session.commit()
        await self.session.refresh(action)
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
    ) -> BotPendingAction:
        context = dict(reply_context or {})
        context["task_id"] = str(task_id)
        context["task_ref"] = task_ref
        action = BotPendingAction(
            action_type=PENDING_ACTION_TASK_REPORT_SUBMIT,
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            title=title,
            source_text=None,
            description=None,
            source_message_id=source_message_id,
            deadline_at=None,
            reply_context=context,
            expires_at=expires_at,
            status=PENDING_ACTION_PENDING,
            picker_message_id=wizard_message_id,
        )
        self.session.add(action)
        await self.session.commit()
        await self.session.refresh(action)
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
    ) -> BotPendingAction:
        action = BotPendingAction(
            action_type=PENDING_ACTION_TASK_ACCEPTANCE_REJECT_REASON,
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            title=title,
            source_text=None,
            description=None,
            source_message_id=source_message_id,
            deadline_at=None,
            reply_context={
                "task_id": str(task_id),
                "response_id": str(response_id),
                "task_ref": task_ref,
            },
            expires_at=expires_at,
            status=PENDING_ACTION_PENDING,
        )
        self.session.add(action)
        await self.session.commit()
        await self.session.refresh(action)
        return action

    async def get(self, action_id: UUID) -> BotPendingAction | None:
        return await self.session.get(BotPendingAction, action_id)

    async def get_latest_pending_task_assignee_picker(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        now: datetime,
    ) -> BotPendingAction | None:
        result = await self.session.scalars(
            select(BotPendingAction)
            .where(BotPendingAction.action_type == PENDING_ACTION_TASK_CREATE_SELECT_ASSIGNEE)
            .where(BotPendingAction.actor_user_id == actor_user_id)
            .where(BotPendingAction.chat_id == chat_id)
            .where(BotPendingAction.status == PENDING_ACTION_PENDING)
            .where(BotPendingAction.expires_at > now)
            .order_by(BotPendingAction.created_at.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def get_latest_pending_task_deadline_clarification(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        now: datetime,
    ) -> BotPendingAction | None:
        result = await self.session.scalars(
            select(BotPendingAction)
            .where(BotPendingAction.action_type == PENDING_ACTION_TASK_CREATE_SET_DEADLINE)
            .where(BotPendingAction.actor_user_id == actor_user_id)
            .where(BotPendingAction.chat_id == chat_id)
            .where(BotPendingAction.status == PENDING_ACTION_PENDING)
            .where(BotPendingAction.expires_at > now)
            .order_by(BotPendingAction.created_at.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def get_latest_pending_task_text_clarification(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
    ) -> BotPendingAction | None:
        result = await self.session.scalars(
            select(BotPendingAction)
            .where(BotPendingAction.action_type == PENDING_ACTION_TASK_CREATE_SET_TEXT)
            .where(BotPendingAction.actor_user_id == actor_user_id)
            .where(BotPendingAction.chat_id == chat_id)
            .where(BotPendingAction.status == PENDING_ACTION_PENDING)
            .order_by(BotPendingAction.created_at.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def get_latest_pending_task_report_submit(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
    ) -> BotPendingAction | None:
        result = await self.session.scalars(
            select(BotPendingAction)
            .where(BotPendingAction.action_type == PENDING_ACTION_TASK_REPORT_SUBMIT)
            .where(BotPendingAction.actor_user_id == actor_user_id)
            .where(BotPendingAction.chat_id == chat_id)
            .where(BotPendingAction.status == PENDING_ACTION_PENDING)
            .order_by(BotPendingAction.created_at.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def get_latest_pending_task_acceptance_reject_reason(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
    ) -> BotPendingAction | None:
        result = await self.session.scalars(
            select(BotPendingAction)
            .where(BotPendingAction.action_type == PENDING_ACTION_TASK_ACCEPTANCE_REJECT_REASON)
            .where(BotPendingAction.actor_user_id == actor_user_id)
            .where(BotPendingAction.chat_id == chat_id)
            .where(BotPendingAction.status == PENDING_ACTION_PENDING)
            .order_by(BotPendingAction.created_at.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def cancel_pending_task_reports(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
    ) -> int:
        result = await self.session.scalars(
            select(BotPendingAction)
            .where(BotPendingAction.action_type == PENDING_ACTION_TASK_REPORT_SUBMIT)
            .where(BotPendingAction.actor_user_id == actor_user_id)
            .where(BotPendingAction.chat_id == chat_id)
            .where(BotPendingAction.status == PENDING_ACTION_PENDING)
        )
        actions = list(result.all())
        for action in actions:
            action.status = PENDING_ACTION_CANCELLED
        if actions:
            await self.session.commit()
        return len(actions)

    async def cancel_pending_task_creation(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
    ) -> int:
        result = await self.session.scalars(
            select(BotPendingAction)
            .where(
                BotPendingAction.action_type.in_(
                    [
                        PENDING_ACTION_TASK_CREATE_SET_TEXT,
                        PENDING_ACTION_TASK_CREATE_SET_DEADLINE,
                        PENDING_ACTION_TASK_CREATE_SELECT_ASSIGNEE,
                    ]
                )
            )
            .where(BotPendingAction.actor_user_id == actor_user_id)
            .where(BotPendingAction.chat_id == chat_id)
            .where(BotPendingAction.status == PENDING_ACTION_PENDING)
        )
        actions = list(result.all())
        for action in actions:
            action.status = PENDING_ACTION_CANCELLED
        if actions:
            await self.session.commit()
        return len(actions)

    async def mark_text_completed(self, action: BotPendingAction) -> BotPendingAction:
        action.status = PENDING_ACTION_COMPLETED
        action.cleanup_status = PENDING_ACTION_CLEANUP_UNSUPPORTED
        await self.session.commit()
        await self.session.refresh(action)
        return action

    async def mark_wizard_message_sent(
        self,
        action_id: UUID,
        *,
        message_id: str,
    ) -> BotPendingAction | None:
        action = await self.get(action_id)
        if action is None:
            return None
        action.picker_message_id = message_id
        await self.session.commit()
        await self.session.refresh(action)
        return action

    async def mark_task_creation_completed(
        self,
        action: BotPendingAction,
        *,
        task_id: UUID,
    ) -> BotPendingAction:
        action.status = PENDING_ACTION_COMPLETED
        action.completed_task_id = task_id
        action.cleanup_status = PENDING_ACTION_CLEANUP_PENDING
        await self.session.commit()
        await self.session.refresh(action)
        return action

    async def mark_cancelled(self, action: BotPendingAction) -> BotPendingAction:
        action.status = PENDING_ACTION_CANCELLED
        await self.session.commit()
        await self.session.refresh(action)
        return action

    async def mark_completed(
        self,
        action: BotPendingAction,
        *,
        task_id: UUID,
        selected_assignee_user_id: UUID,
        picker_message_id: str | None = None,
    ) -> BotPendingAction:
        action.status = PENDING_ACTION_COMPLETED
        action.completed_task_id = task_id
        action.selected_assignee_user_id = selected_assignee_user_id
        if picker_message_id:
            action.picker_message_id = picker_message_id
        action.cleanup_status = PENDING_ACTION_CLEANUP_PENDING
        await self.session.commit()
        await self.session.refresh(action)
        return action

    async def mark_report_completed(
        self,
        action: BotPendingAction,
        *,
        task_id: UUID,
    ) -> BotPendingAction:
        action.status = PENDING_ACTION_COMPLETED
        action.completed_task_id = task_id
        action.cleanup_status = PENDING_ACTION_CLEANUP_PENDING
        await self.session.commit()
        await self.session.refresh(action)
        return action

    async def mark_acceptance_reject_reason_completed(
        self,
        action: BotPendingAction,
        *,
        task_id: UUID,
    ) -> BotPendingAction:
        action.status = PENDING_ACTION_COMPLETED
        action.completed_task_id = task_id
        action.cleanup_status = PENDING_ACTION_CLEANUP_UNSUPPORTED
        await self.session.commit()
        await self.session.refresh(action)
        return action

    async def mark_expired(self, action: BotPendingAction) -> BotPendingAction:
        action.status = PENDING_ACTION_EXPIRED
        await self.session.commit()
        await self.session.refresh(action)
        return action

    async def mark_cleanup_result(
        self,
        action_id: UUID,
        *,
        status: str,
        error: str | None = None,
    ) -> BotPendingAction | None:
        action = await self.get(action_id)
        if action is None:
            return None
        action.cleanup_status = status
        action.cleanup_error = error[:1000] if error else None
        await self.session.commit()
        await self.session.refresh(action)
        return action
