from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.chats.models import Chat
from app.modules.tasks.enums import TaskAssigneeStatus, TaskStatus
from app.modules.tasks.models import (
    Task,
    TaskAssignee,
    TaskObserver,
    TaskReminderRule,
    TaskReminderSnooze,
    TaskResponse,
    TaskStatusHistory,
)
from app.modules.users.models import User


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_task(self, task_id: UUID) -> Task | None:
        return await self.session.get(Task, task_id)

    async def get_chat(self, chat_id: UUID) -> Chat | None:
        return await self.session.get(Chat, chat_id)

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def create_rule(
        self,
        *,
        organization_id: UUID,
        reminder_type: str,
        chat_id: UUID | None = None,
        task_id: UUID | None = None,
        offset_minutes: int | None = None,
        repeat_interval_minutes: int | None = None,
        max_repeats: int | None = None,
        is_active: bool = True,
    ) -> TaskReminderRule:
        rule = TaskReminderRule(
            organization_id=organization_id,
            chat_id=chat_id,
            task_id=task_id,
            reminder_type=reminder_type,
            offset_minutes=offset_minutes,
            repeat_interval_minutes=repeat_interval_minutes,
            max_repeats=max_repeats,
            is_active=is_active,
        )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def list_task_rules(self, task_id: UUID) -> list[TaskReminderRule]:
        result = await self.session.scalars(
            select(TaskReminderRule)
            .where(TaskReminderRule.task_id == task_id)
            .order_by(TaskReminderRule.created_at.desc())
        )
        return list(result)

    async def list_chat_rules(self, chat_id: UUID) -> list[TaskReminderRule]:
        result = await self.session.scalars(
            select(TaskReminderRule)
            .where(
                TaskReminderRule.chat_id == chat_id,
                TaskReminderRule.task_id.is_(None),
            )
            .order_by(TaskReminderRule.created_at.desc())
        )
        return list(result)

    async def get_rule(self, rule_id: UUID) -> TaskReminderRule | None:
        return await self.session.get(TaskReminderRule, rule_id)

    async def update_rule(
        self,
        rule: TaskReminderRule,
        *,
        values: dict[str, object],
    ) -> TaskReminderRule:
        for field_name in (
            "reminder_type",
            "offset_minutes",
            "repeat_interval_minutes",
            "max_repeats",
            "is_active",
        ):
            if field_name in values:
                setattr(rule, field_name, values[field_name])
        await self.session.flush()
        return rule

    async def delete_rule(self, rule: TaskReminderRule) -> None:
        await self.session.delete(rule)
        await self.session.flush()

    async def create_snooze(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        snoozed_until: datetime,
        reason: str | None = None,
    ) -> TaskReminderSnooze:
        snooze = TaskReminderSnooze(
            task_id=task_id,
            user_id=user_id,
            snoozed_until=snoozed_until,
            reason=reason,
        )
        self.session.add(snooze)
        await self.session.flush()
        return snooze

    async def get_active_snooze(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> TaskReminderSnooze | None:
        result = await self.session.scalars(
            select(TaskReminderSnooze)
            .where(
                TaskReminderSnooze.task_id == task_id,
                TaskReminderSnooze.user_id == user_id,
                TaskReminderSnooze.snoozed_until > now,
            )
            .order_by(TaskReminderSnooze.snoozed_until.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def find_tasks_to_mark_overdue(self, *, now: datetime) -> list[Task]:
        result = await self.session.scalars(
            self._active_task_query()
            .where(
                Task.deadline_at.is_not(None),
                Task.deadline_at < now,
                Task.status.notin_(
                    [
                        TaskStatus.WAITING_ACCEPTANCE.value,
                        TaskStatus.OVERDUE.value,
                    ]
                ),
            )
            .order_by(Task.deadline_at.asc(), Task.created_at.desc())
        )
        return list(result.unique())

    async def mark_task_overdue(self, task: Task) -> Task:
        old_status = task.status
        task.status = TaskStatus.OVERDUE.value
        self.session.add(
            TaskStatusHistory(
                task_id=task.id,
                old_status=old_status,
                new_status=TaskStatus.OVERDUE.value,
                changed_by_user_id=None,
            )
        )
        await self.session.flush()
        return task

    async def list_daily_summary_user_ids(self) -> list[UUID]:
        user_ids: set[UUID] = set()

        created_by_result = await self.session.scalars(
            select(Task.created_by_user_id).where(self._active_task_status_condition())
        )
        user_ids.update(created_by_result)

        assignee_result = await self.session.scalars(
            select(TaskAssignee.user_id)
            .join(Task, Task.id == TaskAssignee.task_id)
            .where(self._active_task_status_condition())
        )
        user_ids.update(assignee_result)

        observer_result = await self.session.scalars(
            select(TaskObserver.user_id)
            .join(Task, Task.id == TaskObserver.task_id)
            .where(self._active_task_status_condition())
        )
        user_ids.update(observer_result)

        return sorted(user_ids, key=str)

    async def find_tasks_before_deadline(
        self,
        *,
        now: datetime,
        window_end: datetime,
    ) -> list[Task]:
        result = await self.session.scalars(
            self._active_task_query()
            .where(
                Task.deadline_at.is_not(None),
                Task.deadline_at > now,
                Task.deadline_at <= window_end,
            )
            .order_by(Task.deadline_at.asc(), Task.created_at.desc())
        )
        return list(result.unique())

    async def find_tasks_at_deadline(
        self,
        *,
        window_start: datetime,
        now: datetime,
    ) -> list[Task]:
        result = await self.session.scalars(
            self._active_task_query()
            .where(
                Task.deadline_at.is_not(None),
                Task.deadline_at >= window_start,
                Task.deadline_at <= now,
            )
            .order_by(Task.deadline_at.asc(), Task.created_at.desc())
        )
        return list(result.unique())

    async def find_tasks_after_deadline(self, *, now: datetime) -> list[Task]:
        result = await self.session.scalars(
            self._active_task_query()
            .where(
                Task.deadline_at.is_not(None),
                Task.deadline_at < now,
            )
            .order_by(Task.deadline_at.asc(), Task.created_at.desc())
        )
        return list(result.unique())

    async def find_tasks_without_response_after_deadline(self, *, now: datetime) -> list[Task]:
        result = await self.session.scalars(
            self._active_task_query()
            .where(
                Task.deadline_at.is_not(None),
                Task.deadline_at < now,
                Task.assignees.any(
                    and_(
                        TaskAssignee.response_required.is_(True),
                        TaskAssignee.status.notin_(
                            [
                                TaskAssigneeStatus.RESPONDED.value,
                                TaskAssigneeStatus.COMPLETED.value,
                            ]
                        ),
                    )
                ),
            )
            .order_by(Task.deadline_at.asc(), Task.created_at.desc())
        )
        return list(result.unique())

    async def find_tasks_due_in_one_hour(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> list[Task]:
        result = await self.session.scalars(
            self._chat_deadline_reminder_query()
            .where(
                Task.deadline_at.is_not(None),
                Task.deadline_at >= window_start,
                Task.deadline_at <= window_end,
            )
            .order_by(Task.deadline_at.asc(), Task.created_at.desc())
        )
        return list(result.unique())

    async def find_tasks_overdue_for_chat_reminder(self, *, now: datetime) -> list[Task]:
        result = await self.session.scalars(
            self._chat_deadline_reminder_query()
            .where(
                Task.deadline_at.is_not(None),
                Task.deadline_at < now,
            )
            .order_by(Task.deadline_at.asc(), Task.created_at.desc())
        )
        return list(result.unique())

    async def find_tasks_overdue_for_chat_reminder_window(
        self,
        *,
        now: datetime,
        window_start: datetime,
    ) -> list[Task]:
        result = await self.session.scalars(
            self._chat_deadline_reminder_query()
            .where(
                Task.deadline_at.is_not(None),
                Task.deadline_at >= window_start,
                Task.deadline_at <= now,
            )
            .order_by(Task.deadline_at.asc(), Task.created_at.desc())
        )
        return list(result.unique())

    async def find_tasks_waiting_acceptance(self, *, now: datetime) -> list[Task]:
        result = await self.session.scalars(
            self._active_task_query()
            .where(Task.status == TaskStatus.WAITING_ACCEPTANCE.value)
            .order_by(Task.deadline_at.asc().nulls_last(), Task.created_at.desc())
        )
        return list(result.unique())

    async def list_tasks_for_daily_summary(self, *, user_id: UUID) -> list[Task]:
        result = await self.session.scalars(
            self._active_task_query()
            .where(self._user_related_condition(user_id))
            .order_by(Task.deadline_at.asc().nulls_last(), Task.created_at.desc())
        )
        return list(result.unique())

    def _active_task_query(self):
        return (
            select(Task)
            .where(self._active_task_status_condition())
            .options(
                selectinload(Task.assignees),
                selectinload(Task.assignees).selectinload(TaskAssignee.user),
                selectinload(Task.observers),
                selectinload(Task.responses).selectinload(TaskResponse.user),
                selectinload(Task.created_by_user),
                selectinload(Task.chat),
            )
        )

    def _chat_deadline_reminder_query(self):
        return (
            self._active_task_query()
            .join(Chat, Chat.id == Task.chat_id)
            .where(
                Chat.status == "active",
                Task.assignees.any(
                    and_(
                        TaskAssignee.response_required.is_(True),
                        TaskAssignee.status.notin_(
                            [
                                TaskAssigneeStatus.RESPONDED.value,
                                TaskAssigneeStatus.COMPLETED.value,
                            ]
                        ),
                    )
                )
            )
        )

    def _active_task_status_condition(self):
        return Task.status.notin_(
            [
                TaskStatus.DONE.value,
                TaskStatus.CANCELLED.value,
                TaskStatus.REJECTED.value,
            ]
        )

    def _user_related_condition(self, user_id: UUID):
        return or_(
            Task.created_by_user_id == user_id,
            Task.assignees.any(TaskAssignee.user_id == user_id),
            Task.observers.any(TaskObserver.user_id == user_id),
        )
