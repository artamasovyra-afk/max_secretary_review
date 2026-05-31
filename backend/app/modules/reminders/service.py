from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reminders.repository import ReminderRepository
from app.modules.reminders.schemas import (
    DailySummaryPayload,
    ReminderPayload,
    ReminderRuleCreate,
    ReminderRuleUpdate,
    ReminderTaskPayload,
    ReminderType,
)
from app.modules.tasks.enums import TaskAssigneeStatus, TaskResponseStatus, TaskStatus
from app.modules.tasks.models import Task, TaskReminderRule, TaskReminderSnooze

SnoozeDuration = Literal["1h", "3h", "tomorrow_09"]
DEADLINE_REMINDERS_ENABLED_KEY = "deadline_reminders_enabled"


class ReminderService:
    def __init__(
        self,
        repository: ReminderRepository,
        session: AsyncSession | None = None,
        *,
        before_deadline_window: timedelta = timedelta(hours=1),
        at_deadline_window: timedelta = timedelta(minutes=5),
        overdue_notification_lookback: timedelta = timedelta(hours=6),
        task_deadline_reminder_allowed_task_numbers: frozenset[int] | None = None,
    ) -> None:
        self.repository = repository
        self.session = session
        self.before_deadline_window = before_deadline_window
        self.at_deadline_window = at_deadline_window
        self.overdue_notification_lookback = overdue_notification_lookback
        self.task_deadline_reminder_allowed_task_numbers = task_deadline_reminder_allowed_task_numbers

    async def create_task_rule(self, task_id: UUID, payload: ReminderRuleCreate) -> TaskReminderRule:
        task = await self._get_task_or_404(task_id)
        rule = await self.repository.create_rule(
            organization_id=task.organization_id,
            task_id=task.id,
            chat_id=None,
            **self._rule_create_values(payload),
        )
        await self._commit_and_refresh(rule)
        return rule

    async def list_task_rules(self, task_id: UUID) -> list[TaskReminderRule]:
        await self._get_task_or_404(task_id)
        return await self.repository.list_task_rules(task_id)

    async def update_task_rule(
        self,
        *,
        task_id: UUID,
        rule_id: UUID,
        payload: ReminderRuleUpdate,
    ) -> TaskReminderRule:
        rule = await self._get_task_rule_or_404(task_id=task_id, rule_id=rule_id)
        values = self._rule_update_values(payload)
        rule = await self.repository.update_rule(rule, values=values)
        await self._commit_and_refresh(rule)
        return rule

    async def delete_task_rule(self, *, task_id: UUID, rule_id: UUID) -> None:
        rule = await self._get_task_rule_or_404(task_id=task_id, rule_id=rule_id)
        await self.repository.delete_rule(rule)
        await self._commit()

    async def create_chat_rule(self, chat_id: UUID, payload: ReminderRuleCreate) -> TaskReminderRule:
        chat = await self._get_chat_or_404(chat_id)
        rule = await self.repository.create_rule(
            organization_id=chat.organization_id,
            chat_id=chat.id,
            task_id=None,
            **self._rule_create_values(payload),
        )
        await self._commit_and_refresh(rule)
        return rule

    async def list_chat_rules(self, chat_id: UUID) -> list[TaskReminderRule]:
        await self._get_chat_or_404(chat_id)
        return await self.repository.list_chat_rules(chat_id)

    async def create_snooze(
        self,
        task_id: UUID,
        user_id: UUID,
        duration: SnoozeDuration,
        *,
        now: datetime | None = None,
        reason: str | None = None,
    ) -> TaskReminderSnooze:
        task = await self._get_task_or_404(task_id)
        current_time = self._as_aware_utc(now or self._now())
        snooze = await self.repository.create_snooze(
            task_id=task.id,
            user_id=user_id,
            snoozed_until=self._snoozed_until(duration, current_time),
            reason=reason or duration,
        )
        await self._commit_and_refresh(snooze)
        return snooze

    async def get_active_snooze(
        self,
        task_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> TaskReminderSnooze | None:
        await self._get_task_or_404(task_id)
        return await self.repository.get_active_snooze(
            task_id=task_id,
            user_id=user_id,
            now=self._as_aware_utc(now),
        )

    async def is_snoozed(self, task_id: UUID, user_id: UUID, now: datetime) -> bool:
        return await self.get_active_snooze(task_id, user_id, now) is not None

    async def find_tasks_before_deadline(self, now: datetime) -> ReminderPayload:
        tasks = await self.repository.find_tasks_before_deadline(
            now=now,
            window_end=now + self.before_deadline_window,
        )
        return self._build_payload(
            reminder_type=ReminderType.BEFORE_DEADLINE,
            generated_at=now,
            tasks=tasks,
        )

    async def find_tasks_due_in_one_hour(self, now: datetime) -> ReminderPayload:
        target_time = now + timedelta(hours=1)
        tasks = await self.repository.find_tasks_due_in_one_hour(
            window_start=target_time - self.at_deadline_window,
            window_end=target_time + self.at_deadline_window,
        )
        return self._build_payload(
            reminder_type=ReminderType.TASK_DUE_IN_1H,
            generated_at=now,
            tasks=tasks,
        )

    async def find_tasks_overdue_for_chat_reminder(self, now: datetime) -> ReminderPayload:
        find_window = getattr(self.repository, "find_tasks_overdue_for_chat_reminder_window", None)
        if find_window is not None:
            tasks = await find_window(
                now=now,
                window_start=now - self.overdue_notification_lookback,
            )
        else:
            tasks = [
                task
                for task in await self.repository.find_tasks_overdue_for_chat_reminder(now=now)
                if task.deadline_at is not None
                and self._as_aware_utc(task.deadline_at) >= now - self.overdue_notification_lookback
            ]
        return self._build_payload(
            reminder_type=ReminderType.TASK_OVERDUE,
            generated_at=now,
            tasks=tasks,
        )

    async def find_tasks_at_deadline(self, now: datetime) -> ReminderPayload:
        tasks = await self.repository.find_tasks_at_deadline(
            window_start=now - self.at_deadline_window,
            now=now,
        )
        return self._build_payload(
            reminder_type=ReminderType.AT_DEADLINE,
            generated_at=now,
            tasks=tasks,
        )

    async def find_tasks_after_deadline(self, now: datetime) -> ReminderPayload:
        tasks = await self.repository.find_tasks_after_deadline(now=now)
        return self._build_payload(
            reminder_type=ReminderType.AFTER_DEADLINE,
            generated_at=now,
            tasks=tasks,
        )

    async def find_tasks_without_response_after_deadline(self, now: datetime) -> ReminderPayload:
        tasks = await self.repository.find_tasks_without_response_after_deadline(now=now)
        filtered_tasks = [task for task in tasks if self._has_pending_required_assignee(task)]
        return self._build_payload(
            reminder_type=ReminderType.NO_RESPONSE_AFTER_DEADLINE,
            generated_at=now,
            tasks=filtered_tasks,
        )

    async def find_tasks_waiting_acceptance(self, now: datetime) -> ReminderPayload:
        tasks = await self.repository.find_tasks_waiting_acceptance(now=now)
        filtered_tasks = [
            task
            for task in tasks
            if self._status_value(task.status) == TaskStatus.WAITING_ACCEPTANCE.value
        ]
        return self._build_payload(
            reminder_type=ReminderType.WAITING_ACCEPTANCE,
            generated_at=now,
            tasks=filtered_tasks,
        )

    async def build_daily_summary(self, user_id: UUID, date: date) -> DailySummaryPayload:
        now = self._now()
        day_start = datetime.combine(date, time.min, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        tasks = self._active_tasks(await self.repository.list_tasks_for_daily_summary(user_id=user_id))

        return DailySummaryPayload(
            user_id=user_id,
            date=date,
            generated_at=now,
            my_tasks=[
                self._task_to_payload(task)
                for task in tasks
                if self._has_assignee(task, user_id)
            ],
            created_by_me=[
                self._task_to_payload(task)
                for task in tasks
                if task.created_by_user_id == user_id
            ],
            observed_by_me=[
                self._task_to_payload(task)
                for task in tasks
                if self._has_observer(task, user_id)
            ],
            waiting_my_response=[
                self._task_to_payload(task)
                for task in tasks
                if self._has_pending_required_assignee(task, user_id=user_id)
            ],
            waiting_my_acceptance=[
                self._task_to_payload(task)
                for task in tasks
                if task.created_by_user_id == user_id
                and self._status_value(task.status) == TaskStatus.WAITING_ACCEPTANCE.value
            ],
            overdue=[
                self._task_to_payload(task)
                for task in tasks
                if task.deadline_at is not None and self._as_aware_utc(task.deadline_at) < now
            ],
            today=[
                self._task_to_payload(task)
                for task in tasks
                if task.deadline_at is not None
                and day_start <= self._as_aware_utc(task.deadline_at) < day_end
            ],
        )

    def _build_payload(
        self,
        *,
        reminder_type: ReminderType,
        generated_at: datetime,
        tasks: list[Task],
    ) -> ReminderPayload:
        active_tasks = self._active_tasks(tasks)
        if reminder_type in {ReminderType.TASK_DUE_IN_1H, ReminderType.TASK_OVERDUE}:
            active_tasks = self._deadline_reminder_chat_enabled_tasks(active_tasks)
            active_tasks = self._deadline_reminder_allowlisted_tasks(active_tasks)
        return ReminderPayload(
            reminder_type=reminder_type,
            generated_at=generated_at,
            tasks=[self._task_to_payload(task) for task in active_tasks],
        )

    def _active_tasks(self, tasks: list[Task]) -> list[Task]:
        return [
            task
            for task in tasks
            if self._status_value(task.status)
            not in {TaskStatus.DONE.value, TaskStatus.CANCELLED.value, TaskStatus.REJECTED.value}
        ]

    def _deadline_reminder_allowlisted_tasks(self, tasks: list[Task]) -> list[Task]:
        allowed = self.task_deadline_reminder_allowed_task_numbers
        if not allowed:
            return tasks
        return [task for task in tasks if getattr(task, "task_number", None) in allowed]

    def _deadline_reminder_chat_enabled_tasks(self, tasks: list[Task]) -> list[Task]:
        return [task for task in tasks if self._task_chat_deadline_reminders_enabled(task)]

    def _task_chat_deadline_reminders_enabled(self, task: Task) -> bool:
        chat = getattr(task, "chat", None)
        if chat is None:
            return False
        chat_status = str(getattr(chat, "status", "active") or "active")
        if chat_status != "active":
            return False
        settings = getattr(chat, "settings", None)
        if not isinstance(settings, dict):
            return False
        return settings.get(DEADLINE_REMINDERS_ENABLED_KEY) is True

    def _task_to_payload(self, task: Task) -> ReminderTaskPayload:
        submitted_response = self._latest_submitted_response(task)
        return ReminderTaskPayload(
            task_id=task.id,
            organization_id=task.organization_id,
            chat_id=task.chat_id,
            task_number=getattr(task, "task_number", None),
            title=task.title,
            status=self._status_value(task.status),
            deadline_at=task.deadline_at,
            created_by_user_id=task.created_by_user_id,
            assignee_ids=[assignee.user_id for assignee in getattr(task, "assignees", [])],
            observer_ids=[observer.user_id for observer in getattr(task, "observers", [])],
            response_id=getattr(submitted_response, "id", None),
            response_user_id=getattr(submitted_response, "user_id", None),
            response_user_display_name=self._response_user_display_name(submitted_response),
        )

    def _latest_submitted_response(self, task: Task):
        submitted = [
            response
            for response in getattr(task, "responses", [])
            if self._status_value(getattr(response, "status", "")) == TaskResponseStatus.SUBMITTED.value
        ]
        if not submitted:
            return None
        return max(
            submitted,
            key=lambda response: self._as_aware_utc(getattr(response, "created_at", None) or datetime.min),
        )

    def _response_user_display_name(self, response: object | None) -> str | None:
        if response is None:
            return None
        user = getattr(response, "user", None)
        if user is None:
            return None
        display_name = getattr(user, "display_name", None)
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
        username = getattr(user, "username", None)
        if isinstance(username, str) and username.strip():
            return username.strip()
        return None

    def _has_assignee(self, task: Task, user_id: UUID) -> bool:
        return any(assignee.user_id == user_id for assignee in getattr(task, "assignees", []))

    def _has_observer(self, task: Task, user_id: UUID) -> bool:
        return any(observer.user_id == user_id for observer in getattr(task, "observers", []))

    def _has_pending_required_assignee(self, task: Task, user_id: UUID | None = None) -> bool:
        pending_statuses = {
            TaskAssigneeStatus.RESPONDED.value,
            TaskAssigneeStatus.COMPLETED.value,
        }
        for assignee in getattr(task, "assignees", []):
            if user_id is not None and assignee.user_id != user_id:
                continue
            if not getattr(assignee, "response_required", True):
                continue
            if self._status_value(assignee.status) not in pending_statuses:
                return True
        return False

    async def _get_task_or_404(self, task_id: UUID) -> Task:
        task = await self.repository.get_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )
        return task

    async def _get_chat_or_404(self, chat_id: UUID):
        chat = await self.repository.get_chat(chat_id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found",
            )
        return chat

    async def _get_task_rule_or_404(self, *, task_id: UUID, rule_id: UUID) -> TaskReminderRule:
        await self._get_task_or_404(task_id)
        rule = await self.repository.get_rule(rule_id)
        if rule is None or rule.task_id != task_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reminder rule not found",
            )
        return rule

    def _rule_create_values(self, payload: ReminderRuleCreate) -> dict[str, object]:
        return {
            "reminder_type": payload.reminder_type.value,
            "offset_minutes": payload.offset_minutes,
            "repeat_interval_minutes": payload.repeat_interval_minutes,
            "max_repeats": payload.max_repeats,
            "is_active": payload.is_active,
        }

    def _rule_update_values(self, payload: ReminderRuleUpdate) -> dict[str, object]:
        values = payload.model_dump(exclude_unset=True)
        if "reminder_type" in values and values["reminder_type"] is not None:
            values["reminder_type"] = values["reminder_type"].value
        return values

    def _snoozed_until(self, duration: SnoozeDuration, now: datetime) -> datetime:
        if duration == "1h":
            return now + timedelta(hours=1)
        if duration == "3h":
            return now + timedelta(hours=3)
        if duration == "tomorrow_09":
            tomorrow = (now + timedelta(days=1)).date()
            return datetime.combine(tomorrow, time(hour=9), tzinfo=timezone.utc)
        raise ValueError(f"Unsupported snooze duration: {duration}")

    async def _commit_and_refresh(self, instance: object) -> None:
        await self._commit()
        if self.session is None:
            return
        await self.session.refresh(instance)

    async def _commit(self) -> None:
        if self.session is None:
            raise RuntimeError("ReminderService write methods require a database session")
        await self.session.commit()

    def _status_value(self, status: object) -> str:
        if hasattr(status, "value"):
            return str(status.value)
        return str(status)

    def _as_aware_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
