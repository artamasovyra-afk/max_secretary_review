from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.chats.models import Chat, ChatMember
from app.modules.organizations.models import Organization
from app.modules.tasks.enums import TaskAssigneeStatus, TaskStatus
from app.modules.tasks.models import (
    AuditLog,
    Task,
    TaskAcceptance,
    TaskAssignee,
    TaskComment,
    TaskFile,
    TaskObserver,
    TaskResponse,
    TaskStatusHistory,
)
from app.modules.tasks.schemas import (
    TaskInboxSummaryFilters,
    TaskListFilters,
    TaskListScope,
    TaskParticipantRole,
    TaskQuickStatus,
)
from app.modules.users.models import User

FINAL_TASK_STATUSES = (
    TaskStatus.DONE.value,
    TaskStatus.CANCELLED.value,
    TaskStatus.REJECTED.value,
)


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def organization_exists(self, organization_id: UUID) -> bool:
        return await self.session.get(Organization, organization_id) is not None

    async def get_chat(self, chat_id: UUID) -> Optional[Chat]:
        return await self.session.get(Chat, chat_id)

    async def get_chat_with_members(self, chat_id: UUID) -> Optional[Chat]:
        result = await self.session.scalars(
            select(Chat)
            .where(Chat.id == chat_id)
            .options(selectinload(Chat.members).selectinload(ChatMember.user))
        )
        return result.one_or_none()

    async def get_user(self, user_id: UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def existing_user_ids(self, user_ids: set[UUID]) -> set[UUID]:
        if not user_ids:
            return set()
        result = await self.session.scalars(select(User.id).where(User.id.in_(user_ids)))
        return set(result)

    async def create_task(
        self,
        *,
        organization_id: UUID,
        chat_id: UUID,
        title: str,
        description: Optional[str],
        source_message_id: Optional[str],
        created_by_user_id: UUID,
        deadline_at: Optional[datetime],
        status: str,
        priority: str,
        completion_rule: str,
        task_type: str = "personal",
        requires_individual_report: bool = False,
        audience_snapshot: Optional[dict[str, Any]] = None,
        creator_display_name_snapshot: Optional[str] = None,
        creator_role_snapshot: Optional[str] = None,
        source_chat_title_snapshot: Optional[str] = None,
    ) -> Task:
        task_number = await self.next_task_number(organization_id)
        task = Task(
            organization_id=organization_id,
            chat_id=chat_id,
            task_number=task_number,
            title=title,
            description=description,
            source_message_id=source_message_id,
            task_type=task_type,
            requires_individual_report=requires_individual_report,
            audience_snapshot=audience_snapshot,
            created_by_user_id=created_by_user_id,
            creator_display_name_snapshot=creator_display_name_snapshot,
            creator_role_snapshot=creator_role_snapshot,
            source_chat_title_snapshot=source_chat_title_snapshot,
            deadline_at=deadline_at,
            status=status,
            priority=priority,
            completion_rule=completion_rule,
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def next_task_number(self, organization_id: UUID) -> int:
        result = await self.session.scalar(
            select(func.coalesce(func.max(Task.task_number), 0) + 1).where(
                Task.organization_id == organization_id
            )
        )
        return int(result or 1)

    async def create_assignees(
        self,
        *,
        task_id: UUID,
        assignee_ids: list[UUID],
        response_required: bool = True,
    ) -> list[TaskAssignee]:
        assignees = [
            TaskAssignee(
                task_id=task_id,
                user_id=user_id,
                status=TaskAssigneeStatus.ASSIGNED.value,
                response_required=response_required,
            )
            for user_id in assignee_ids
        ]
        self.session.add_all(assignees)
        await self.session.flush()
        return assignees

    async def create_assignee(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
    ) -> TaskAssignee:
        assignee = TaskAssignee(
            task_id=task_id,
            user_id=user_id,
            status=TaskAssigneeStatus.ASSIGNED.value,
            response_required=True,
        )
        self.session.add(assignee)
        await self.session.flush()
        return assignee

    async def get_assignee(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
    ) -> Optional[TaskAssignee]:
        result = await self.session.scalars(
            select(TaskAssignee).where(
                TaskAssignee.task_id == task_id,
                TaskAssignee.user_id == user_id,
            )
        )
        return result.one_or_none()

    async def delete_assignee(self, assignee: TaskAssignee) -> None:
        await self.session.delete(assignee)
        await self.session.flush()

    async def create_observers(
        self,
        *,
        task_id: UUID,
        observer_ids: list[UUID],
    ) -> list[TaskObserver]:
        observers = [
            TaskObserver(
                task_id=task_id,
                user_id=user_id,
            )
            for user_id in observer_ids
        ]
        self.session.add_all(observers)
        await self.session.flush()
        return observers

    async def create_observer(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
    ) -> TaskObserver:
        observer = TaskObserver(
            task_id=task_id,
            user_id=user_id,
        )
        self.session.add(observer)
        await self.session.flush()
        return observer

    async def get_observer(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
    ) -> Optional[TaskObserver]:
        result = await self.session.scalars(
            select(TaskObserver).where(
                TaskObserver.task_id == task_id,
                TaskObserver.user_id == user_id,
            )
        )
        return result.one_or_none()

    async def delete_observer(self, observer: TaskObserver) -> None:
        await self.session.delete(observer)
        await self.session.flush()

    async def create_comment(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        text: str,
        reply_to_comment_id: Optional[UUID],
    ) -> TaskComment:
        comment = TaskComment(
            task_id=task_id,
            user_id=user_id,
            text=text,
            reply_to_comment_id=reply_to_comment_id,
        )
        self.session.add(comment)
        await self.session.flush()
        return comment

    async def list_comments(self, task_id: UUID) -> list[TaskComment]:
        result = await self.session.scalars(
            select(TaskComment)
            .where(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at.asc())
        )
        return list(result)

    async def get_comment(self, comment_id: UUID) -> Optional[TaskComment]:
        return await self.session.get(TaskComment, comment_id)

    async def create_file(
        self,
        *,
        task_id: UUID,
        uploaded_by_user_id: UUID,
        file_name: str,
        comment_id: Optional[UUID] = None,
        file_url: Optional[str] = None,
        file_storage_key: Optional[str] = None,
        mime_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
    ) -> TaskFile:
        file = TaskFile(
            task_id=task_id,
            comment_id=comment_id,
            uploaded_by_user_id=uploaded_by_user_id,
            file_name=file_name,
            file_url=file_url,
            file_storage_key=file_storage_key,
            mime_type=mime_type,
            size_bytes=size_bytes,
        )
        self.session.add(file)
        await self.session.flush()
        return file

    async def list_files(self, task_id: UUID) -> list[TaskFile]:
        result = await self.session.scalars(
            select(TaskFile)
            .where(TaskFile.task_id == task_id)
            .order_by(TaskFile.created_at.asc())
        )
        return list(result)

    async def create_response(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        text: Optional[str],
        source_message_id: Optional[str],
        status: str,
    ) -> TaskResponse:
        response = TaskResponse(
            task_id=task_id,
            user_id=user_id,
            text=text,
            source_message_id=source_message_id,
            status=status,
        )
        self.session.add(response)
        await self.session.flush()
        return response

    async def update_assignee_response(
        self,
        assignee: TaskAssignee,
        *,
        responded_at: datetime,
        status: str,
    ) -> TaskAssignee:
        assignee.status = status
        assignee.responded_at = responded_at
        await self.session.flush()
        return assignee

    async def create_status_history(
        self,
        *,
        task_id: UUID,
        old_status: Optional[str],
        new_status: str,
        changed_by_user_id: Optional[UUID],
    ) -> TaskStatusHistory:
        status_history = TaskStatusHistory(
            task_id=task_id,
            old_status=old_status,
            new_status=new_status,
            changed_by_user_id=changed_by_user_id,
        )
        self.session.add(status_history)
        await self.session.flush()
        return status_history

    async def create_audit_log(
        self,
        *,
        organization_id: UUID,
        entity_id: UUID,
        action: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            organization_id=organization_id,
            user_id=None,
            entity_type="task",
            entity_id=entity_id,
            action=action,
            payload=payload,
        )
        self.session.add(audit_log)
        await self.session.flush()
        return audit_log

    async def get_with_participants(self, task_id: UUID) -> Optional[Task]:
        result = await self.session.scalars(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.created_by_user),
                selectinload(Task.assignees),
                selectinload(Task.assignees).selectinload(TaskAssignee.user),
                selectinload(Task.observers),
            )
        )
        return result.one_or_none()

    async def get_group_report_task(self, task_id: UUID) -> Optional[Task]:
        result = await self.session.scalars(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.assignees).selectinload(TaskAssignee.user),
                selectinload(Task.responses).selectinload(TaskResponse.user),
                selectinload(Task.created_by_user),
                selectinload(Task.chat),
            )
        )
        return result.one_or_none()

    async def update_task(
        self,
        task: Task,
        *,
        values: Mapping[str, Any],
    ) -> Task:
        for field_name in (
            "title",
            "description",
            "deadline_at",
            "priority",
            "completion_rule",
            "status",
            "completed_at",
            "cancelled_at",
        ):
            if field_name in values:
                setattr(task, field_name, values[field_name])
        await self.session.flush()
        return task

    async def update_response_status(
        self,
        response: TaskResponse,
        *,
        status: str,
    ) -> TaskResponse:
        response.status = status
        await self.session.flush()
        return response

    async def update_assignee_status(
        self,
        assignee: TaskAssignee,
        *,
        status: str,
    ) -> TaskAssignee:
        assignee.status = status
        await self.session.flush()
        return assignee

    async def create_acceptance(
        self,
        *,
        task_id: UUID,
        response_id: UUID,
        accepted_by_user_id: UUID,
        decision: str,
        comment: Optional[str],
    ) -> TaskAcceptance:
        acceptance = TaskAcceptance(
            task_id=task_id,
            response_id=response_id,
            accepted_by_user_id=accepted_by_user_id,
            decision=decision,
            comment=comment,
        )
        self.session.add(acceptance)
        await self.session.flush()
        return acceptance

    async def list_tasks(
        self,
        *,
        filters: TaskListFilters,
        limit: int,
        offset: int,
    ) -> list[Task]:
        query = (
            select(Task)
            .options(
                selectinload(Task.created_by_user),
                selectinload(Task.assignees),
                selectinload(Task.assignees).selectinload(TaskAssignee.user),
                selectinload(Task.observers),
            )
            .order_by(Task.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if filters.organization_id is not None:
            query = query.where(Task.organization_id == filters.organization_id)
        if filters.chat_id is not None:
            query = query.where(Task.chat_id == filters.chat_id)
        if filters.status is not None:
            query = query.where(Task.status == filters.status.value)
        if filters.task_type is not None:
            query = query.where(Task.task_type == filters.task_type.value)
        if filters.task_number is not None:
            query = query.where(Task.task_number == filters.task_number)
        elif filters.search:
            if filters.search_task_number is not None:
                query = query.where(Task.task_number == filters.search_task_number)
            else:
                pattern = f"%{filters.search.strip()}%"
                query = query.where(
                    or_(
                        Task.title.ilike(pattern),
                        Task.description.ilike(pattern),
                    )
                )
        if filters.created_by_user_id is not None:
            query = query.where(Task.created_by_user_id == filters.created_by_user_id)
        if filters.assignee_id is not None:
            query = query.where(Task.assignees.any(TaskAssignee.user_id == filters.assignee_id))
        if filters.observer_id is not None:
            query = query.where(Task.observers.any(TaskObserver.user_id == filters.observer_id))
        if filters.participant_role == TaskParticipantRole.ASSIGNEE and filters.participant_user_id is not None:
            query = query.where(Task.assignees.any(TaskAssignee.user_id == filters.participant_user_id))
        if filters.participant_role == TaskParticipantRole.CREATOR and filters.participant_user_id is not None:
            query = query.where(Task.created_by_user_id == filters.participant_user_id)
        query = self._apply_task_scope_filters(query, filters)
        query = self._apply_quick_status_filter(query, filters)
        if filters.overdue is True and filters.now is not None:
            query = query.where(
                Task.deadline_at.is_not(None),
                Task.deadline_at < filters.now,
                Task.status.notin_(FINAL_TASK_STATUSES),
            )
        if (
            filters.due_today is True
            and filters.today_from is not None
            and filters.today_to is not None
        ):
            query = query.where(
                Task.deadline_at.is_not(None),
                Task.deadline_at >= filters.today_from,
                Task.deadline_at < filters.today_to,
            )
        if filters.deadline_from is not None:
            query = query.where(Task.deadline_at >= filters.deadline_from)
        if filters.deadline_to is not None:
            query = query.where(Task.deadline_at <= filters.deadline_to)

        result = await self.session.scalars(query)
        return list(result.unique())

    def _apply_task_scope_filters(self, query, filters: TaskListFilters):
        if filters.scope == TaskListScope.ALL:
            return query
        if filters.viewer_user_id is None:
            return query.where(false())
        if filters.scope == TaskListScope.ASSIGNED_TO_ME:
            return query.where(Task.assignees.any(TaskAssignee.user_id == filters.viewer_user_id))
        if filters.scope == TaskListScope.CREATED_BY_ME:
            return query.where(Task.created_by_user_id == filters.viewer_user_id)
        if filters.scope == TaskListScope.OBSERVED_BY_ME:
            return query.where(Task.observers.any(TaskObserver.user_id == filters.viewer_user_id))
        if filters.scope == TaskListScope.AWAITING_REPORT:
            return query.where(
                Task.assignees.any(
                    and_(
                        TaskAssignee.user_id == filters.viewer_user_id,
                        TaskAssignee.response_required.is_(True),
                        TaskAssignee.status.notin_(
                            [
                                TaskAssigneeStatus.RESPONDED.value,
                                TaskAssigneeStatus.COMPLETED.value,
                            ]
                        ),
                    )
                ),
                Task.status.notin_(FINAL_TASK_STATUSES),
            )
        if filters.scope == TaskListScope.AWAITING_ACCEPTANCE:
            return query.where(
                Task.created_by_user_id == filters.viewer_user_id,
                Task.status == TaskStatus.WAITING_ACCEPTANCE.value,
            )
        return query

    def _apply_quick_status_filter(self, query, filters: TaskListFilters):
        if filters.quick_status is None:
            return query
        if filters.quick_status == TaskQuickStatus.NEW:
            return query.where(Task.status == TaskStatus.NEW.value)
        if filters.quick_status == TaskQuickStatus.AWAITING_REPORT:
            return query.where(
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
                Task.status.notin_(FINAL_TASK_STATUSES),
            )
        if filters.quick_status == TaskQuickStatus.AWAITING_ACCEPTANCE:
            return query.where(Task.status == TaskStatus.WAITING_ACCEPTANCE.value)
        if filters.quick_status == TaskQuickStatus.OVERDUE:
            if filters.now is None:
                return query.where(false())
            return query.where(
                Task.deadline_at.is_not(None),
                Task.deadline_at < filters.now,
                Task.status.notin_(FINAL_TASK_STATUSES),
            )
        return query

    async def inbox_summary(
        self,
        *,
        filters: TaskInboxSummaryFilters,
        now: datetime,
        today_start: datetime,
        today_end: datetime,
    ) -> dict[str, list[Task]]:
        return {
            "my_tasks": await self._list_summary_tasks(
                filters,
                Task.assignees.any(TaskAssignee.user_id == filters.user_id),
            ),
            "created_by_me": await self._list_summary_tasks(
                filters,
                Task.created_by_user_id == filters.user_id,
            ),
            "observed_by_me": await self._list_summary_tasks(
                filters,
                Task.observers.any(TaskObserver.user_id == filters.user_id),
            ),
            "new": await self._list_summary_tasks(
                filters,
                self._user_related_condition(filters.user_id),
                Task.status == TaskStatus.NEW.value,
            ),
            "waiting_my_response": await self._list_summary_tasks(
                filters,
                Task.assignees.any(
                    and_(
                        TaskAssignee.user_id == filters.user_id,
                        TaskAssignee.response_required.is_(True),
                        TaskAssignee.status.notin_(
                            [
                                TaskAssigneeStatus.RESPONDED.value,
                                TaskAssigneeStatus.COMPLETED.value,
                            ]
                        ),
                    )
                ),
            ),
            "waiting_my_acceptance": await self._list_summary_tasks(
                filters,
                Task.created_by_user_id == filters.user_id,
                Task.status == TaskStatus.WAITING_ACCEPTANCE.value,
            ),
            "overdue": await self._list_summary_tasks(
                filters,
                self._user_related_condition(filters.user_id),
                Task.deadline_at.is_not(None),
                Task.deadline_at < now,
                Task.status.notin_(FINAL_TASK_STATUSES),
            ),
            "today": await self._list_summary_tasks(
                filters,
                self._user_related_condition(filters.user_id),
                Task.deadline_at.is_not(None),
                Task.deadline_at >= today_start,
                Task.deadline_at < today_end,
            ),
        }

    async def get_detail(self, task_id: UUID) -> Optional[Task]:
        result = await self.session.scalars(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.created_by_user),
                selectinload(Task.chat),
                selectinload(Task.assignees),
                selectinload(Task.assignees).selectinload(TaskAssignee.user),
                selectinload(Task.observers),
                selectinload(Task.observers).selectinload(TaskObserver.user),
                selectinload(Task.comments),
                selectinload(Task.files),
                selectinload(Task.responses),
                selectinload(Task.responses).selectinload(TaskResponse.user),
                selectinload(Task.acceptances),
                selectinload(Task.status_history),
            )
        )
        return result.one_or_none()

    async def _list_summary_tasks(
        self,
        filters: TaskInboxSummaryFilters,
        *conditions,
    ) -> list[Task]:
        query = (
            self._summary_base_query(filters)
            .where(*conditions)
            .order_by(Task.created_at.desc())
        )
        result = await self.session.scalars(query)
        return list(result.unique())

    def _summary_base_query(self, filters: TaskInboxSummaryFilters):
        query = select(Task).options(
            selectinload(Task.assignees),
            selectinload(Task.observers),
        )
        if filters.organization_id is not None:
            query = query.where(Task.organization_id == filters.organization_id)
        if filters.chat_id is not None:
            query = query.where(Task.chat_id == filters.chat_id)
        if filters.status is not None:
            query = query.where(Task.status == filters.status.value)
        if filters.deadline_from is not None:
            query = query.where(Task.deadline_at >= filters.deadline_from)
        if filters.deadline_to is not None:
            query = query.where(Task.deadline_at <= filters.deadline_to)
        return query

    def _user_related_condition(self, user_id: UUID):
        return or_(
            Task.created_by_user_id == user_id,
            Task.assignees.any(TaskAssignee.user_id == user_id),
            Task.observers.any(TaskObserver.user_id == user_id),
        )
