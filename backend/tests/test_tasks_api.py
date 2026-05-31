from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.api.tasks import get_task_service
from app.core.config import get_settings
from app.main import create_app
from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_MEMBER, ROLE_SUPER_ADMIN
from app.modules.tasks.enums import (
    TaskAcceptanceDecision,
    TaskAssigneeStatus,
    TaskCompletionRule,
    TaskPriority,
    TaskResponseStatus,
    TaskStatus,
    TaskType,
)
from app.modules.tasks.deadline_parser import local_day_bounds_utc
from app.modules.tasks.schemas import (
    TaskAcceptanceCreate,
    TaskCommentCreate,
    TaskCreate,
    TaskFileCreate,
    TaskGroupAssignmentCreate,
    TaskGroupAssignmentCreateRead,
    TaskGroupReportChatRead,
    TaskGroupReportCreatorRead,
    TaskGroupReportItemRead,
    TaskGroupReportRead,
    TaskGroupReportUserRead,
    TaskInboxSummaryFilters,
    TaskListFilters,
    TaskListScope,
    TaskParticipantRole,
    TaskParticipantCreate,
    TaskQuickStatus,
    TaskResponseCreate,
    TaskUpdate,
)


class TaskAssigneeRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    user_id: UUID
    status: str
    response_required: bool
    responded_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class TaskObserverRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class TaskCommentRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    user_id: UUID
    text: str
    reply_to_comment_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


class TaskFileRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    comment_id: Optional[UUID]
    uploaded_by_user_id: UUID
    file_name: str
    file_url: Optional[str]
    file_storage_key: Optional[str]
    mime_type: Optional[str]
    size_bytes: Optional[int]
    created_at: datetime


class TaskResponseRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    user_id: UUID
    text: Optional[str]
    source_message_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class TaskStatusHistoryRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    old_status: Optional[str]
    new_status: str
    changed_by_user_id: Optional[UUID]
    created_at: datetime


class TaskAcceptanceRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    response_id: UUID
    accepted_by_user_id: UUID
    decision: str
    comment: Optional[str]
    created_at: datetime


class TaskRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    chat_id: UUID
    task_number: int
    task_type: str = TaskType.PERSONAL.value
    requires_individual_report: bool = False
    audience_snapshot: Optional[dict[str, object]] = None
    title: str
    description: Optional[str]
    created_by_user_id: UUID
    deadline_at: Optional[datetime]
    status: str
    priority: str
    completion_rule: str
    submitted_at: Optional[datetime]
    completed_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    assignees: list[TaskAssigneeRecord]
    observers: list[TaskObserverRecord]
    comments: list[TaskCommentRecord]
    files: list[TaskFileRecord]
    responses: list[TaskResponseRecord]
    status_history: list[TaskStatusHistoryRecord]


class FakeTaskService:
    def __init__(self) -> None:
        self.tasks: dict[UUID, TaskRecord] = {}
        self.last_filters: Optional[TaskListFilters] = None
        self.last_inbox_filters: Optional[TaskInboxSummaryFilters] = None
        self.last_limit: Optional[int] = None
        self.last_offset: Optional[int] = None
        self.last_group_assignment_payload: Optional[TaskGroupAssignmentCreate] = None
        self.last_group_assignment_context: Optional[AuthContext] = None
        self.last_group_report_task_id: Optional[UUID] = None
        self.last_group_report_context: Optional[AuthContext] = None
        self.audit_actions: list[str] = []
        self.acceptances: list[TaskAcceptanceRecord] = []
        self.task_number_counters: dict[UUID, int] = {}

    async def create(self, payload: TaskCreate) -> TaskRecord:
        now = datetime.now(timezone.utc)
        task_id = uuid4()
        task_number = self._next_task_number(payload.organization_id)
        task = TaskRecord(
            id=task_id,
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            task_number=task_number,
            task_type=TaskType.PERSONAL.value,
            requires_individual_report=False,
            audience_snapshot=None,
            title=payload.title,
            description=payload.description,
            created_by_user_id=payload.created_by_user_id,
            deadline_at=payload.deadline_at,
            status=TaskStatus.NEW.value,
            priority=payload.priority.value,
            completion_rule=payload.completion_rule.value,
            submitted_at=None,
            completed_at=None,
            cancelled_at=None,
            created_at=now,
            updated_at=now,
            assignees=[
                TaskAssigneeRecord(
                    id=uuid4(),
                    task_id=task_id,
                    user_id=user_id,
                    status=TaskAssigneeStatus.ASSIGNED.value,
                    response_required=True,
                    responded_at=None,
                    created_at=now,
                    updated_at=now,
                )
                for user_id in payload.assignee_ids
            ],
            observers=[
                TaskObserverRecord(
                    id=uuid4(),
                    task_id=task_id,
                    user_id=user_id,
                    created_at=now,
                    updated_at=now,
                )
                for user_id in payload.observer_ids
            ],
            comments=[
                TaskCommentRecord(
                    id=uuid4(),
                    task_id=task_id,
                    user_id=payload.created_by_user_id,
                    text="Initial comment",
                    reply_to_comment_id=None,
                    created_at=now,
                    updated_at=now,
                )
            ],
            files=[
                TaskFileRecord(
                    id=uuid4(),
                    task_id=task_id,
                    comment_id=None,
                    uploaded_by_user_id=payload.created_by_user_id,
                    file_name="brief.pdf",
                    file_url=None,
                    file_storage_key="tasks/brief.pdf",
                    mime_type="application/pdf",
                    size_bytes=1024,
                    created_at=now,
                )
            ],
            responses=[
                TaskResponseRecord(
                    id=uuid4(),
                    task_id=task_id,
                    user_id=payload.assignee_ids[0] if payload.assignee_ids else payload.created_by_user_id,
                    text="Done",
                    source_message_id=None,
                    status=TaskResponseStatus.SUBMITTED.value,
                    created_at=now,
                    updated_at=now,
                )
            ],
            status_history=[
                TaskStatusHistoryRecord(
                    id=uuid4(),
                    task_id=task_id,
                    old_status=None,
                    new_status=TaskStatus.NEW.value,
                    changed_by_user_id=payload.created_by_user_id,
                    created_at=now,
                )
            ],
        )
        self.tasks[task.id] = task
        return task

    def _next_task_number(self, organization_id: UUID) -> int:
        next_number = self.task_number_counters.get(organization_id, 0) + 1
        self.task_number_counters[organization_id] = next_number
        return next_number

    async def create_group_assignment(
        self,
        payload: TaskGroupAssignmentCreate,
        auth_context: AuthContext,
    ) -> TaskGroupAssignmentCreateRead:
        self.last_group_assignment_payload = payload
        self.last_group_assignment_context = auth_context
        task_number = self._next_task_number(payload.organization_id)
        return TaskGroupAssignmentCreateRead(
            task_id=uuid4(),
            task_number=task_number,
            task_ref=f"#{task_number}",
            total_assignees=2,
            creator_display_name="Иван Руководитель",
            creator_role=auth_context.roles[0] if auth_context.roles else None,
        )

    async def get_group_report(
        self,
        task_id: UUID,
        auth_context: AuthContext,
    ) -> TaskGroupReportRead:
        self.last_group_report_task_id = task_id
        self.last_group_report_context = auth_context
        assignee_id = uuid4()
        return TaskGroupReportRead(
            task_id=task_id,
            task_number=42,
            task_ref="#42",
            title="Сдать отчеты",
            creator=TaskGroupReportCreatorRead(
                user_id=auth_context.user_id,
                display_name="Иван Руководитель",
                role=auth_context.roles[0] if auth_context.roles else None,
            ),
            chat=TaskGroupReportChatRead(
                chat_id=auth_context.chat_id or uuid4(),
                title="MAX group",
            ),
            total=1,
            responded=1,
            pending=0,
            overdue=0,
            items=[
                TaskGroupReportItemRead(
                    user=TaskGroupReportUserRead(
                        user_id=assignee_id,
                        display_name="Петр Исполнитель",
                    ),
                    status=TaskAssigneeStatus.RESPONDED,
                    responded_at=datetime.now(timezone.utc),
                    response_text="Готово",
                )
            ],
        )

    async def list(
        self,
        *,
        filters: TaskListFilters,
        limit: int,
        offset: int,
    ) -> list[TaskRecord]:
        self.last_filters = filters
        self.last_limit = limit
        self.last_offset = offset
        tasks = list(self.tasks.values())
        if filters.organization_id is not None:
            tasks = [task for task in tasks if task.organization_id == filters.organization_id]
        if filters.chat_id is not None:
            tasks = [task for task in tasks if task.chat_id == filters.chat_id]
        if filters.status is not None:
            tasks = [task for task in tasks if task.status == filters.status.value]
        if filters.task_type is not None:
            tasks = [task for task in tasks if task.task_type == filters.task_type.value]
        if filters.task_number is not None:
            tasks = [task for task in tasks if task.task_number == filters.task_number]
        elif filters.search_task_number is not None:
            tasks = [task for task in tasks if task.task_number == filters.search_task_number]
        elif filters.search:
            search = filters.search.lower()
            tasks = [
                task
                for task in tasks
                if search in task.title.lower() or (task.description and search in task.description.lower())
            ]
        if filters.created_by_user_id is not None:
            tasks = [task for task in tasks if task.created_by_user_id == filters.created_by_user_id]
        if filters.assignee_id is not None:
            tasks = [
                task
                for task in tasks
                if any(assignee.user_id == filters.assignee_id for assignee in task.assignees)
            ]
        if filters.observer_id is not None:
            tasks = [
                task
                for task in tasks
                if any(observer.user_id == filters.observer_id for observer in task.observers)
            ]
        if filters.participant_role == TaskParticipantRole.ASSIGNEE and filters.participant_user_id is not None:
            tasks = [
                task
                for task in tasks
                if any(assignee.user_id == filters.participant_user_id for assignee in task.assignees)
            ]
        if filters.participant_role == TaskParticipantRole.CREATOR and filters.participant_user_id is not None:
            tasks = [task for task in tasks if task.created_by_user_id == filters.participant_user_id]
        tasks = self._apply_scope_filter(tasks, filters)
        tasks = self._apply_quick_status_filter(tasks, filters)
        if filters.overdue is True and filters.now is not None:
            final_statuses = {
                TaskStatus.DONE.value,
                TaskStatus.CANCELLED.value,
                TaskStatus.REJECTED.value,
            }
            tasks = [
                task
                for task in tasks
                if task.deadline_at is not None
                and task.deadline_at < filters.now
                and task.status not in final_statuses
            ]
        if filters.due_today is True and filters.today_from is not None and filters.today_to is not None:
            tasks = [
                task
                for task in tasks
                if task.deadline_at is not None
                and filters.today_from <= task.deadline_at < filters.today_to
            ]
        if filters.deadline_from is not None:
            tasks = [
                task
                for task in tasks
                if task.deadline_at is not None and task.deadline_at >= filters.deadline_from
            ]
        if filters.deadline_to is not None:
            tasks = [
                task
                for task in tasks
                if task.deadline_at is not None and task.deadline_at <= filters.deadline_to
            ]
        return tasks[offset : offset + limit]

    def _apply_scope_filter(
        self,
        tasks: list[TaskRecord],
        filters: TaskListFilters,
    ) -> list[TaskRecord]:
        if filters.scope == TaskListScope.ALL:
            return tasks
        if filters.viewer_user_id is None:
            return []
        if filters.scope == TaskListScope.ASSIGNED_TO_ME:
            return [
                task
                for task in tasks
                if any(assignee.user_id == filters.viewer_user_id for assignee in task.assignees)
            ]
        if filters.scope == TaskListScope.CREATED_BY_ME:
            return [task for task in tasks if task.created_by_user_id == filters.viewer_user_id]
        if filters.scope == TaskListScope.OBSERVED_BY_ME:
            return [
                task
                for task in tasks
                if any(observer.user_id == filters.viewer_user_id for observer in task.observers)
            ]
        if filters.scope == TaskListScope.AWAITING_REPORT:
            final_statuses = {
                TaskStatus.DONE.value,
                TaskStatus.CANCELLED.value,
                TaskStatus.REJECTED.value,
            }
            return [
                task
                for task in tasks
                if task.status not in final_statuses
                and any(
                    assignee.user_id == filters.viewer_user_id
                    and assignee.response_required
                    and assignee.status
                    not in (
                        TaskAssigneeStatus.RESPONDED.value,
                        TaskAssigneeStatus.COMPLETED.value,
                    )
                    for assignee in task.assignees
                )
            ]
        if filters.scope == TaskListScope.AWAITING_ACCEPTANCE:
            return [
                task
                for task in tasks
                if task.created_by_user_id == filters.viewer_user_id
                and task.status == TaskStatus.WAITING_ACCEPTANCE.value
            ]
        return tasks

    def _apply_quick_status_filter(
        self,
        tasks: list[TaskRecord],
        filters: TaskListFilters,
    ) -> list[TaskRecord]:
        if filters.quick_status is None:
            return tasks
        if filters.quick_status == TaskQuickStatus.NEW:
            return [task for task in tasks if task.status == TaskStatus.NEW.value]
        if filters.quick_status == TaskQuickStatus.AWAITING_REPORT:
            final_statuses = {
                TaskStatus.DONE.value,
                TaskStatus.CANCELLED.value,
                TaskStatus.REJECTED.value,
            }
            return [
                task
                for task in tasks
                if task.status not in final_statuses
                and any(
                    assignee.response_required
                    and assignee.status
                    not in (
                        TaskAssigneeStatus.RESPONDED.value,
                        TaskAssigneeStatus.COMPLETED.value,
                    )
                    for assignee in task.assignees
                )
            ]
        if filters.quick_status == TaskQuickStatus.AWAITING_ACCEPTANCE:
            return [task for task in tasks if task.status == TaskStatus.WAITING_ACCEPTANCE.value]
        if filters.quick_status == TaskQuickStatus.OVERDUE:
            if filters.now is None:
                return []
            final_statuses = {
                TaskStatus.DONE.value,
                TaskStatus.CANCELLED.value,
                TaskStatus.REJECTED.value,
            }
            return [
                task
                for task in tasks
                if task.deadline_at is not None
                and task.deadline_at < filters.now
                and task.status not in final_statuses
            ]
        return tasks

    async def inbox_summary(self, filters: TaskInboxSummaryFilters) -> dict[str, list[TaskRecord]]:
        self.last_inbox_filters = filters
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        tasks = [task for task in self.tasks.values() if self._matches_summary_filters(task, filters)]

        return {
            "my_tasks": [
                task
                for task in tasks
                if any(assignee.user_id == filters.user_id for assignee in task.assignees)
            ],
            "created_by_me": [
                task for task in tasks if task.created_by_user_id == filters.user_id
            ],
            "observed_by_me": [
                task
                for task in tasks
                if any(observer.user_id == filters.user_id for observer in task.observers)
            ],
            "new": [
                task
                for task in tasks
                if self._is_user_related(task, filters.user_id)
                and task.status == TaskStatus.NEW.value
            ],
            "waiting_my_response": [
                task
                for task in tasks
                if any(
                    assignee.user_id == filters.user_id
                    and assignee.response_required
                    and assignee.status
                    not in (
                        TaskAssigneeStatus.RESPONDED.value,
                        TaskAssigneeStatus.COMPLETED.value,
                    )
                    for assignee in task.assignees
                )
            ],
            "waiting_my_acceptance": [
                task
                for task in tasks
                if task.created_by_user_id == filters.user_id
                and task.status == TaskStatus.WAITING_ACCEPTANCE.value
            ],
            "overdue": [
                task
                for task in tasks
                if self._is_user_related(task, filters.user_id)
                and task.deadline_at is not None
                and task.deadline_at < now
                and task.status
                not in (
                    TaskStatus.DONE.value,
                    TaskStatus.CANCELLED.value,
                    TaskStatus.REJECTED.value,
                )
            ],
            "today": [
                task
                for task in tasks
                if self._is_user_related(task, filters.user_id)
                and task.deadline_at is not None
                and today_start <= task.deadline_at < today_end
            ],
        }

    async def get(self, task_id: UUID) -> TaskRecord:
        task = self.tasks.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )
        return task

    def _matches_summary_filters(
        self,
        task: TaskRecord,
        filters: TaskInboxSummaryFilters,
    ) -> bool:
        if filters.organization_id is not None and task.organization_id != filters.organization_id:
            return False
        if filters.chat_id is not None and task.chat_id != filters.chat_id:
            return False
        if filters.status is not None and task.status != filters.status.value:
            return False
        if filters.deadline_from is not None:
            if task.deadline_at is None or task.deadline_at < filters.deadline_from:
                return False
        if filters.deadline_to is not None:
            if task.deadline_at is None or task.deadline_at > filters.deadline_to:
                return False
        return True

    def _is_user_related(self, task: TaskRecord, user_id: UUID) -> bool:
        return (
            task.created_by_user_id == user_id
            or any(assignee.user_id == user_id for assignee in task.assignees)
            or any(observer.user_id == user_id for observer in task.observers)
        )

    async def update(self, task_id: UUID, payload: TaskUpdate) -> TaskRecord:
        task = await self.get(task_id)
        values = payload.model_dump(exclude_unset=True)
        if "priority" in values:
            values["priority"] = values["priority"].value
        if "completion_rule" in values:
            values["completion_rule"] = values["completion_rule"].value
        if "status" in values:
            values["status"] = values["status"].value
        old_status = task.status
        values["updated_at"] = datetime.now(timezone.utc)
        updated = task.model_copy(update=values)

        new_status = values.get("status")
        if new_status is not None and new_status != old_status:
            updated.status_history.append(
                TaskStatusHistoryRecord(
                    id=uuid4(),
                    task_id=task_id,
                    old_status=old_status,
                    new_status=new_status,
                    changed_by_user_id=None,
                    created_at=datetime.now(timezone.utc),
                )
            )

        self.tasks[task_id] = updated
        return updated

    async def cancel(self, task_id: UUID) -> TaskRecord:
        task = await self.get(task_id)
        if task.status == TaskStatus.DONE.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Done task cannot be cancelled without force",
            )

        now = datetime.now(timezone.utc)
        updated = task.model_copy(
            update={
                "status": TaskStatus.CANCELLED.value,
                "cancelled_at": now,
                "updated_at": now,
            }
        )
        if task.status != TaskStatus.CANCELLED.value:
            updated.status_history.append(
                TaskStatusHistoryRecord(
                    id=uuid4(),
                    task_id=task_id,
                    old_status=task.status,
                    new_status=TaskStatus.CANCELLED.value,
                    changed_by_user_id=None,
                    created_at=now,
                )
            )
        self.tasks[task_id] = updated
        return updated

    async def add_assignee(
        self,
        task_id: UUID,
        payload: TaskParticipantCreate,
    ) -> TaskAssigneeRecord:
        task = await self.get(task_id)
        if any(assignee.user_id == payload.user_id for assignee in task.assignees):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task assignee already exists",
            )

        now = datetime.now(timezone.utc)
        assignee = TaskAssigneeRecord(
            id=uuid4(),
            task_id=task_id,
            user_id=payload.user_id,
            status=TaskAssigneeStatus.ASSIGNED.value,
            response_required=True,
            responded_at=None,
            created_at=now,
            updated_at=now,
        )
        task.assignees.append(assignee)
        self.audit_actions.append("task.assignee_added")
        return assignee

    async def remove_assignee(self, task_id: UUID, user_id: UUID) -> None:
        task = await self.get(task_id)
        assignee = next(
            (item for item in task.assignees if item.user_id == user_id),
            None,
        )
        if assignee is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task assignee not found",
            )
        task.assignees.remove(assignee)
        self.audit_actions.append("task.assignee_removed")

    async def add_observer(
        self,
        task_id: UUID,
        payload: TaskParticipantCreate,
    ) -> TaskObserverRecord:
        task = await self.get(task_id)
        if any(observer.user_id == payload.user_id for observer in task.observers):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task observer already exists",
            )

        now = datetime.now(timezone.utc)
        observer = TaskObserverRecord(
            id=uuid4(),
            task_id=task_id,
            user_id=payload.user_id,
            created_at=now,
            updated_at=now,
        )
        task.observers.append(observer)
        self.audit_actions.append("task.observer_added")
        return observer

    async def remove_observer(self, task_id: UUID, user_id: UUID) -> None:
        task = await self.get(task_id)
        observer = next(
            (item for item in task.observers if item.user_id == user_id),
            None,
        )
        if observer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task observer not found",
            )
        task.observers.remove(observer)
        self.audit_actions.append("task.observer_removed")

    async def add_comment(self, task_id: UUID, payload: TaskCommentCreate) -> TaskCommentRecord:
        task = await self.get(task_id)
        if payload.reply_to_comment_id is not None and not any(
            comment.id == payload.reply_to_comment_id for comment in task.comments
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reply comment not found",
            )

        now = datetime.now(timezone.utc)
        comment = TaskCommentRecord(
            id=uuid4(),
            task_id=task_id,
            user_id=payload.user_id,
            text=payload.text,
            reply_to_comment_id=payload.reply_to_comment_id,
            created_at=now,
            updated_at=now,
        )
        task.comments.append(comment)
        return comment

    async def list_comments(self, task_id: UUID) -> list[TaskCommentRecord]:
        task = await self.get(task_id)
        return task.comments

    async def add_file(self, task_id: UUID, payload: TaskFileCreate) -> TaskFileRecord:
        task = await self.get(task_id)
        if payload.comment_id is not None and not any(
            comment.id == payload.comment_id for comment in task.comments
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reply comment not found",
            )

        file = TaskFileRecord(
            id=uuid4(),
            task_id=task_id,
            comment_id=payload.comment_id,
            uploaded_by_user_id=payload.uploaded_by_user_id,
            file_name=payload.file_name,
            file_url=payload.file_url,
            file_storage_key=payload.file_storage_key,
            mime_type=payload.mime_type,
            size_bytes=payload.size_bytes,
            created_at=datetime.now(timezone.utc),
        )
        task.files.append(file)
        return file

    async def list_files(self, task_id: UUID) -> list[TaskFileRecord]:
        task = await self.get(task_id)
        return task.files

    async def submit_response(
        self,
        task_id: UUID,
        payload: TaskResponseCreate,
    ) -> TaskResponseRecord:
        task = await self.get(task_id)
        assignee = next(
            (item for item in task.assignees if item.user_id == payload.user_id),
            None,
        )
        if assignee is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only task assignee can submit response",
            )

        now = datetime.now(timezone.utc)
        response = TaskResponseRecord(
            id=uuid4(),
            task_id=task_id,
            user_id=payload.user_id,
            text=payload.text,
            source_message_id=payload.source_message_id,
            status=TaskResponseStatus.SUBMITTED.value,
            created_at=now,
            updated_at=now,
        )
        task.responses.append(response)
        assignee.status = TaskAssigneeStatus.RESPONDED.value
        assignee.responded_at = now
        assignee.updated_at = now

        new_status = None
        if task.completion_rule == TaskCompletionRule.ANY_ASSIGNEE_RESPONSE.value:
            new_status = TaskStatus.WAITING_ACCEPTANCE.value
        elif task.completion_rule == TaskCompletionRule.ALL_ASSIGNEES_RESPONSE.value and all(
            item.status == TaskAssigneeStatus.RESPONDED.value for item in task.assignees
        ):
            new_status = TaskStatus.WAITING_ACCEPTANCE.value

        if new_status is not None and task.status != new_status:
            old_status = task.status
            task.status = new_status
            task.status_history.append(
                TaskStatusHistoryRecord(
                    id=uuid4(),
                    task_id=task_id,
                    old_status=old_status,
                    new_status=new_status,
                    changed_by_user_id=payload.user_id,
                    created_at=now,
                )
            )
        return response

    async def accept_response(
        self,
        task_id: UUID,
        response_id: UUID,
        payload: TaskAcceptanceCreate,
        *,
        auth_context: object | None = None,
    ) -> TaskAcceptanceRecord:
        task = await self.get(task_id)
        response = self._get_task_response(task, response_id)
        self._ensure_task_creator(task, payload.accepted_by_user_id)
        self._ensure_response_submitted(response)

        now = datetime.now(timezone.utc)
        response.status = TaskResponseStatus.ACCEPTED.value
        response.updated_at = now
        acceptance = TaskAcceptanceRecord(
            id=uuid4(),
            task_id=task_id,
            response_id=response_id,
            accepted_by_user_id=payload.accepted_by_user_id,
            decision=TaskAcceptanceDecision.ACCEPTED.value,
            comment=payload.comment,
            created_at=now,
        )
        self.acceptances.append(acceptance)
        old_status = task.status
        task.status = TaskStatus.DONE.value
        task.completed_at = now
        if old_status != TaskStatus.DONE.value:
            task.status_history.append(
                TaskStatusHistoryRecord(
                    id=uuid4(),
                    task_id=task_id,
                    old_status=old_status,
                    new_status=TaskStatus.DONE.value,
                    changed_by_user_id=payload.accepted_by_user_id,
                    created_at=now,
                )
            )
        return acceptance

    async def reject_response(
        self,
        task_id: UUID,
        response_id: UUID,
        payload: TaskAcceptanceCreate,
        *,
        auth_context: object | None = None,
    ) -> TaskAcceptanceRecord:
        task = await self.get(task_id)
        response = self._get_task_response(task, response_id)
        self._ensure_task_creator(task, payload.accepted_by_user_id)
        self._ensure_response_submitted(response)

        now = datetime.now(timezone.utc)
        response.status = TaskResponseStatus.REJECTED.value
        response.updated_at = now
        acceptance = TaskAcceptanceRecord(
            id=uuid4(),
            task_id=task_id,
            response_id=response_id,
            accepted_by_user_id=payload.accepted_by_user_id,
            decision=TaskAcceptanceDecision.REJECTED.value,
            comment=payload.comment,
            created_at=now,
        )
        self.acceptances.append(acceptance)
        rejected_assignee = next(
            (item for item in task.assignees if item.user_id == response.user_id),
            None,
        )
        if rejected_assignee is not None:
            rejected_assignee.status = TaskAssigneeStatus.IN_PROGRESS.value
            rejected_assignee.updated_at = now

        old_status = task.status
        next_status = TaskStatus.IN_PROGRESS.value
        if task.deadline_at is not None and task.deadline_at < now:
            next_status = TaskStatus.OVERDUE.value
        task.status = next_status
        task.completed_at = None
        if old_status != next_status:
            task.status_history.append(
                TaskStatusHistoryRecord(
                    id=uuid4(),
                    task_id=task_id,
                    old_status=old_status,
                    new_status=next_status,
                    changed_by_user_id=payload.accepted_by_user_id,
                    created_at=now,
                )
            )
        return acceptance

    def _get_task_response(self, task: TaskRecord, response_id: UUID) -> TaskResponseRecord:
        response = next((item for item in task.responses if item.id == response_id), None)
        if response is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task response not found",
            )
        return response

    def _ensure_response_submitted(self, response: TaskResponseRecord) -> None:
        if response.status != TaskResponseStatus.SUBMITTED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task response already decided",
            )

    def _ensure_task_creator(self, task: TaskRecord, accepted_by_user_id: UUID) -> None:
        if task.created_by_user_id != accepted_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only task creator, chat_admin or super_admin can accept or reject response",
            )


@pytest.fixture()
def tasks_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeTaskService]:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    app = create_app()
    service = FakeTaskService()
    app.dependency_overrides[get_task_service] = lambda: service
    with TestClient(
        app,
        headers=auth_headers(
            user_id=uuid4(),
            organization_id=uuid4(),
            chat_id=uuid4(),
            roles=ROLE_SUPER_ADMIN,
        ),
    ) as client:
        yield client, service


def task_payload() -> dict[str, object]:
    return {
        "organization_id": str(uuid4()),
        "chat_id": str(uuid4()),
        "title": "Prepare weekly report",
        "description": "Collect updates from all chats.",
        "created_by_user_id": str(uuid4()),
        "deadline_at": None,
        "assignee_ids": [str(uuid4()), str(uuid4())],
        "observer_ids": [str(uuid4())],
    }


def group_assignment_payload(
    *,
    organization_id: UUID,
    chat_id: UUID,
    created_by_user_id: UUID,
) -> dict[str, object]:
    return {
        "organization_id": str(organization_id),
        "chat_id": str(chat_id),
        "created_by_user_id": str(created_by_user_id),
        "title": "Сдать отчеты",
        "description": "Индивидуальный отчет до конца дня",
        "deadline_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "exclude_creator": True,
        "response_required": True,
    }


def auth_headers(
    *,
    user_id: UUID,
    organization_id: UUID,
    chat_id: UUID,
    roles: str,
) -> dict[str, str]:
    return {
        "X-User-Id": str(user_id),
        "X-Organization-Id": str(organization_id),
        "X-Chat-Id": str(chat_id),
        "X-Roles": roles,
    }


def test_create_task_with_assignees_and_observers(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client

    response = client.post("/api/tasks", json=task_payload())

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Prepare weekly report"
    assert payload["description"] == "Collect updates from all chats."
    assert payload["task_number"] == 1
    assert payload["task_ref"] == "#1"
    assert payload["status"] == TaskStatus.NEW.value
    assert payload["priority"] == TaskPriority.NORMAL.value
    assert payload["completion_rule"] == TaskCompletionRule.ANY_ASSIGNEE_RESPONSE.value
    assert len(payload["assignees"]) == 2
    assert len(payload["observers"]) == 1
    assert all(assignee["status"] == TaskAssigneeStatus.ASSIGNED.value for assignee in payload["assignees"])
    assert all(assignee["response_required"] is True for assignee in payload["assignees"])


def test_create_task_requires_auth(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client

    with TestClient(client.app) as unauthenticated_client:
        response = unauthenticated_client.post("/api/tasks", json=task_payload())

    assert response.status_code == 401


def test_get_tasks_requires_auth(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client

    with TestClient(client.app) as unauthenticated_client:
        response = unauthenticated_client.get("/api/tasks")

    assert response.status_code == 401


def test_get_task_requires_auth(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client

    with TestClient(client.app) as unauthenticated_client:
        response = unauthenticated_client.get(f"/api/tasks/{uuid4()}")

    assert response.status_code == 401


def test_update_task_requires_auth(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client

    with TestClient(client.app) as unauthenticated_client:
        response = unauthenticated_client.patch(f"/api/tasks/{uuid4()}", json={"title": "No auth"})

    assert response.status_code == 401


def test_cancel_task_requires_auth(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client

    with TestClient(client.app) as unauthenticated_client:
        response = unauthenticated_client.post(f"/api/tasks/{uuid4()}/cancel")

    assert response.status_code == 401


def test_create_group_assignment_admin(
    tasks_client: tuple[TestClient, FakeTaskService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service = tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    response = client.post(
        "/api/tasks/group-assignment",
        json=group_assignment_payload(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        headers=auth_headers(
            user_id=creator_id,
            organization_id=organization_id,
            chat_id=chat_id,
            roles=ROLE_CHAT_ADMIN,
        ),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["total_assignees"] == 2
    assert payload["task_number"] == 1
    assert payload["task_ref"] == "#1"
    assert payload["creator_display_name"] == "Иван Руководитель"
    assert payload["creator_role"] == ROLE_CHAT_ADMIN
    assert service.last_group_assignment_payload is not None
    assert service.last_group_assignment_payload.exclude_creator is True
    assert service.last_group_assignment_payload.response_required is True
    assert service.last_group_assignment_context is not None
    assert service.last_group_assignment_context.roles == [ROLE_CHAT_ADMIN]


def test_create_group_assignment_non_admin_forbidden(
    tasks_client: tuple[TestClient, FakeTaskService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service = tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    response = client.post(
        "/api/tasks/group-assignment",
        json=group_assignment_payload(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        headers=auth_headers(
            user_id=creator_id,
            organization_id=organization_id,
            chat_id=chat_id,
            roles=ROLE_MEMBER,
        ),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "insufficient_permissions"
    assert service.last_group_assignment_payload is None


def test_create_group_assignment_requires_deadline(
    tasks_client: tuple[TestClient, FakeTaskService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service = tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    payload = group_assignment_payload(
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=creator_id,
    )
    payload["deadline_at"] = None
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    response = client.post(
        "/api/tasks/group-assignment",
        json=payload,
        headers=auth_headers(
            user_id=creator_id,
            organization_id=organization_id,
            chat_id=chat_id,
            roles=ROLE_CHAT_ADMIN,
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "deadline_required"
    assert service.last_group_assignment_payload is None


def test_member_can_create_self_task(
    tasks_client: tuple[TestClient, FakeTaskService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _service = tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    payload = task_payload()
    payload["organization_id"] = str(organization_id)
    payload["chat_id"] = str(chat_id)
    payload["created_by_user_id"] = str(user_id)
    payload["assignee_ids"] = [str(user_id)]
    payload["observer_ids"] = []

    response = client.post(
        "/api/tasks",
        json=payload,
        headers=auth_headers(
            user_id=user_id,
            organization_id=organization_id,
            chat_id=chat_id,
            roles=ROLE_MEMBER,
        ),
    )

    assert response.status_code == 201
    assert response.json()["assignees"][0]["user_id"] == str(user_id)


def test_member_cannot_create_task_for_another_user(
    tasks_client: tuple[TestClient, FakeTaskService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _service = tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    payload = task_payload()
    payload["organization_id"] = str(organization_id)
    payload["chat_id"] = str(chat_id)
    payload["created_by_user_id"] = str(user_id)
    payload["assignee_ids"] = [str(uuid4())]
    payload["observer_ids"] = []
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    response = client.post(
        "/api/tasks",
        json=payload,
        headers=auth_headers(
            user_id=user_id,
            organization_id=organization_id,
            chat_id=chat_id,
            roles=ROLE_MEMBER,
        ),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Member can create tasks only for self"


def test_get_group_assignment_report(
    tasks_client: tuple[TestClient, FakeTaskService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service = tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    task_id = uuid4()
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    response = client.get(
        f"/api/tasks/{task_id}/group-report",
        headers=auth_headers(
            user_id=creator_id,
            organization_id=organization_id,
            chat_id=chat_id,
            roles=ROLE_CHAT_ADMIN,
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == str(task_id)
    assert payload["task_number"] == 42
    assert payload["task_ref"] == "#42"
    assert payload["title"] == "Сдать отчеты"
    assert payload["creator"] == {
        "user_id": str(creator_id),
        "display_name": "Иван Руководитель",
        "role": ROLE_CHAT_ADMIN,
    }
    assert payload["chat"] == {
        "chat_id": str(chat_id),
        "title": "MAX group",
    }
    assert payload["total"] == 1
    assert payload["responded"] == 1
    assert payload["pending"] == 0
    assert payload["overdue"] == 0
    assert payload["items"][0]["status"] == TaskAssigneeStatus.RESPONDED.value
    assert payload["items"][0]["response_text"] == "Готово"
    assert service.last_group_report_task_id == task_id
    assert service.last_group_report_context is not None
    assert service.last_group_report_context.roles == [ROLE_CHAT_ADMIN]


def test_get_group_assignment_report_requires_auth(
    tasks_client: tuple[TestClient, FakeTaskService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service = tasks_client
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    with TestClient(client.app) as unauthenticated_client:
        response = unauthenticated_client.get(f"/api/tasks/{uuid4()}/group-report")

    assert response.status_code == 401
    assert service.last_group_report_task_id is None


def test_create_task_accepts_custom_priority_and_completion_rule(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    payload = task_payload()
    payload["priority"] = TaskPriority.HIGH.value
    payload["completion_rule"] = TaskCompletionRule.ALL_ASSIGNEES_RESPONSE.value

    response = client.post("/api/tasks", json=payload)

    assert response.status_code == 201
    response_payload = response.json()
    assert response_payload["priority"] == TaskPriority.HIGH.value
    assert response_payload["completion_rule"] == TaskCompletionRule.ALL_ASSIGNEES_RESPONSE.value


def test_create_task_requires_title(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    payload = task_payload()
    payload.pop("title")

    response = client.post("/api/tasks", json=payload)

    assert response.status_code == 422


def test_create_task_rejects_duplicate_assignee_ids(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    duplicate_user_id = str(uuid4())
    payload = task_payload()
    payload["assignee_ids"] = [duplicate_user_id, duplicate_user_id]

    response = client.post("/api/tasks", json=payload)

    assert response.status_code == 422


def test_create_task_rejects_past_deadline(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    payload = task_payload()
    payload["deadline_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    response = client.post("/api/tasks", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == "deadline_must_be_in_future"


def test_create_group_assignment_rejects_past_deadline(
    tasks_client: tuple[TestClient, FakeTaskService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service = tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    payload = group_assignment_payload(
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=creator_id,
    )
    payload["deadline_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()

    response = client.post(
        "/api/tasks/group-assignment",
        json=payload,
        headers=auth_headers(
            user_id=creator_id,
            organization_id=organization_id,
            chat_id=chat_id,
            roles=ROLE_CHAT_ADMIN,
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "deadline_must_be_in_future"
    assert service.last_group_assignment_payload is None


def test_list_tasks_supports_filters_limit_offset(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    payload = task_payload()
    now = datetime.now(timezone.utc)
    future_deadline = now + timedelta(days=3)
    payload["deadline_at"] = future_deadline.isoformat()
    created = client.post("/api/tasks", json=payload).json()
    deadline_from = (now + timedelta(days=2)).isoformat()
    deadline_to = (now + timedelta(days=4)).isoformat()

    response = client.get(
        "/api/tasks",
        params={
            "organization_id": created["organization_id"],
            "chat_id": created["chat_id"],
            "status": TaskStatus.NEW.value,
            "created_by_user_id": created["created_by_user_id"],
            "assignee_id": created["assignees"][0]["user_id"],
            "observer_id": created["observers"][0]["user_id"],
            "deadline_from": deadline_from,
            "deadline_to": deadline_to,
            "limit": 10,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == created["id"]
    assert service.last_filters is not None
    assert service.last_filters.organization_id == UUID(created["organization_id"])
    assert service.last_filters.chat_id == UUID(created["chat_id"])
    assert service.last_filters.status == TaskStatus.NEW
    assert service.last_filters.created_by_user_id == UUID(created["created_by_user_id"])
    assert service.last_filters.assignee_id == UUID(created["assignees"][0]["user_id"])
    assert service.last_filters.observer_id == UUID(created["observers"][0]["user_id"])
    assert service.last_limit == 10
    assert service.last_offset == 0


def test_list_tasks_supports_webapp_scope_filters(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    user_id = uuid4()
    other_user_id = uuid4()
    organization_id = str(uuid4())

    assigned_payload = task_payload()
    assigned_payload["organization_id"] = organization_id
    assigned_payload["created_by_user_id"] = str(other_user_id)
    assigned_payload["assignee_ids"] = [str(user_id)]
    assigned_payload["observer_ids"] = []
    assigned = client.post("/api/tasks", json=assigned_payload).json()

    created_payload = task_payload()
    created_payload["organization_id"] = organization_id
    created_payload["created_by_user_id"] = str(user_id)
    created_payload["assignee_ids"] = [str(other_user_id)]
    created_payload["observer_ids"] = []
    created = client.post("/api/tasks", json=created_payload).json()

    observed_payload = task_payload()
    observed_payload["organization_id"] = organization_id
    observed_payload["created_by_user_id"] = str(other_user_id)
    observed_payload["assignee_ids"] = [str(other_user_id)]
    observed_payload["observer_ids"] = [str(user_id)]
    observed = client.post("/api/tasks", json=observed_payload).json()

    waiting_acceptance_payload = task_payload()
    waiting_acceptance_payload["organization_id"] = organization_id
    waiting_acceptance_payload["created_by_user_id"] = str(user_id)
    waiting_acceptance_payload["assignee_ids"] = [str(other_user_id)]
    waiting_acceptance_payload["observer_ids"] = []
    waiting_acceptance = client.post("/api/tasks", json=waiting_acceptance_payload).json()
    client.patch(
        f"/api/tasks/{waiting_acceptance['id']}",
        json={"status": TaskStatus.WAITING_ACCEPTANCE.value},
    )

    headers = auth_headers(
        user_id=user_id,
        organization_id=UUID(organization_id),
        chat_id=uuid4(),
        roles=ROLE_SUPER_ADMIN,
    )

    assigned_response = client.get(
        "/api/tasks",
        params={"scope": "assigned_to_me"},
        headers=headers,
    )
    created_response = client.get(
        "/api/tasks",
        params={"scope": "created_by_me"},
        headers=headers,
    )
    observed_response = client.get(
        "/api/tasks",
        params={"scope": "observed_by_me"},
        headers=headers,
    )
    awaiting_report_response = client.get(
        "/api/tasks",
        params={"scope": "awaiting_report"},
        headers=headers,
    )
    awaiting_acceptance_response = client.get(
        "/api/tasks",
        params={"scope": "awaiting_acceptance"},
        headers=headers,
    )

    assert assigned_response.status_code == 200
    assert [task["id"] for task in assigned_response.json()] == [assigned["id"]]
    assert {task["id"] for task in created_response.json()} == {
        created["id"],
        waiting_acceptance["id"],
    }
    assert [task["id"] for task in observed_response.json()] == [observed["id"]]
    assert [task["id"] for task in awaiting_report_response.json()] == [assigned["id"]]
    assert [task["id"] for task in awaiting_acceptance_response.json()] == [
        waiting_acceptance["id"]
    ]
    assert service.last_filters is not None
    assert service.last_filters.viewer_user_id == user_id


def test_list_tasks_supports_overdue_and_due_today_filters(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    now = datetime.now(timezone.utc)
    overdue_payload = task_payload()
    overdue = client.post("/api/tasks", json=overdue_payload).json()
    _service.tasks[UUID(overdue["id"])] = _service.tasks[UUID(overdue["id"])].model_copy(
        update={"deadline_at": now - timedelta(days=1)}
    )

    done_overdue_payload = task_payload()
    done_overdue = client.post("/api/tasks", json=done_overdue_payload).json()
    _service.tasks[UUID(done_overdue["id"])] = _service.tasks[UUID(done_overdue["id"])].model_copy(
        update={"deadline_at": now - timedelta(days=2)}
    )
    client.patch(f"/api/tasks/{done_overdue['id']}", json={"status": TaskStatus.DONE.value})

    today_payload = task_payload()
    today_start, today_end = local_day_bounds_utc(now)
    today_deadline = min(now + timedelta(hours=1), today_end - timedelta(minutes=1))
    if today_deadline < now + timedelta(minutes=1):
        today_deadline = now + timedelta(minutes=1)
    assert today_start <= today_deadline < today_end
    today_payload["deadline_at"] = today_deadline.isoformat()
    today = client.post("/api/tasks", json=today_payload).json()

    future_payload = task_payload()
    future_payload["deadline_at"] = (now + timedelta(days=3)).isoformat()
    client.post("/api/tasks", json=future_payload)

    overdue_response = client.get("/api/tasks", params={"overdue": "true"})
    today_response = client.get("/api/tasks", params={"due_today": "true"})

    assert overdue_response.status_code == 200
    assert [task["id"] for task in overdue_response.json()] == [overdue["id"]]
    assert today_response.status_code == 200
    assert [task["id"] for task in today_response.json()] == [today["id"]]


def test_list_tasks_supports_participant_role_filters(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    participant_id = uuid4()
    other_user_id = uuid4()

    assigned_payload = task_payload()
    assigned_payload["created_by_user_id"] = str(other_user_id)
    assigned_payload["assignee_ids"] = [str(participant_id)]
    assigned_payload["observer_ids"] = []
    assigned = client.post("/api/tasks", json=assigned_payload).json()

    created_payload = task_payload()
    created_payload["created_by_user_id"] = str(participant_id)
    created_payload["assignee_ids"] = [str(other_user_id)]
    created_payload["observer_ids"] = []
    created = client.post("/api/tasks", json=created_payload).json()

    assignee_response = client.get(
        "/api/tasks",
        params={
            "participant_role": "assignee",
            "participant_user_id": str(participant_id),
        },
    )
    creator_response = client.get(
        "/api/tasks",
        params={
            "participant_role": "creator",
            "participant_user_id": str(participant_id),
        },
    )

    assert assignee_response.status_code == 200
    assert [task["id"] for task in assignee_response.json()] == [assigned["id"]]
    assert creator_response.status_code == 200
    assert [task["id"] for task in creator_response.json()] == [created["id"]]
    assert service.last_filters is not None
    assert service.last_filters.participant_role == TaskParticipantRole.CREATOR
    assert service.last_filters.participant_user_id == participant_id


def test_list_tasks_rejects_invalid_participant_role(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client

    invalid_role_response = client.get(
        "/api/tasks",
        params={
            "participant_role": "observer",
            "participant_user_id": str(uuid4()),
        },
    )
    missing_user_response = client.get(
        "/api/tasks",
        params={"participant_role": "assignee"},
    )

    assert invalid_role_response.status_code == 422
    assert missing_user_response.status_code == 422


def test_list_tasks_supports_quick_status_filters(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    now = datetime.now(timezone.utc)

    new_task = client.post("/api/tasks", json=task_payload()).json()
    for assignee in service.tasks[UUID(new_task["id"])].assignees:
        assignee.status = TaskAssigneeStatus.RESPONDED.value

    awaiting_report_payload = task_payload()
    awaiting_report = client.post("/api/tasks", json=awaiting_report_payload).json()
    client.patch(
        f"/api/tasks/{awaiting_report['id']}",
        json={"status": TaskStatus.IN_PROGRESS.value},
    )

    awaiting_acceptance_payload = task_payload()
    awaiting_acceptance = client.post("/api/tasks", json=awaiting_acceptance_payload).json()
    client.patch(
        f"/api/tasks/{awaiting_acceptance['id']}",
        json={"status": TaskStatus.WAITING_ACCEPTANCE.value},
    )
    for assignee in service.tasks[UUID(awaiting_acceptance["id"])].assignees:
        assignee.status = TaskAssigneeStatus.RESPONDED.value

    overdue_payload = task_payload()
    overdue = client.post("/api/tasks", json=overdue_payload).json()
    service.tasks[UUID(overdue["id"])] = service.tasks[UUID(overdue["id"])].model_copy(
        update={"deadline_at": now - timedelta(days=1)}
    )
    client.patch(
        f"/api/tasks/{overdue['id']}",
        json={"status": TaskStatus.IN_PROGRESS.value},
    )
    for assignee in service.tasks[UUID(overdue["id"])].assignees:
        assignee.status = TaskAssigneeStatus.RESPONDED.value

    final_overdue_payload = task_payload()
    final_overdue = client.post("/api/tasks", json=final_overdue_payload).json()
    service.tasks[UUID(final_overdue["id"])] = service.tasks[UUID(final_overdue["id"])].model_copy(
        update={"deadline_at": now - timedelta(days=2)}
    )
    client.patch(
        f"/api/tasks/{final_overdue['id']}",
        json={"status": TaskStatus.DONE.value},
    )

    new_response = client.get("/api/tasks", params={"quick_status": "new"})
    awaiting_report_response = client.get(
        "/api/tasks",
        params={"quick_status": "awaiting_report"},
    )
    awaiting_acceptance_response = client.get(
        "/api/tasks",
        params={"quick_status": "awaiting_acceptance"},
    )
    overdue_response = client.get("/api/tasks", params={"quick_status": "overdue"})

    assert new_response.status_code == 200
    assert [task["id"] for task in new_response.json()] == [new_task["id"]]
    assert awaiting_report_response.status_code == 200
    assert [task["id"] for task in awaiting_report_response.json()] == [
        awaiting_report["id"]
    ]
    assert awaiting_acceptance_response.status_code == 200
    assert [task["id"] for task in awaiting_acceptance_response.json()] == [
        awaiting_acceptance["id"]
    ]
    assert overdue_response.status_code == 200
    assert [task["id"] for task in overdue_response.json()] == [overdue["id"]]
    assert service.last_filters is not None
    assert service.last_filters.quick_status == TaskQuickStatus.OVERDUE


def test_list_tasks_filters_inaccessible_chat_results_for_member(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    organization_id = uuid4()
    user_id = uuid4()
    accessible_chat_id = uuid4()
    inaccessible_chat_id = uuid4()
    visible_payload = task_payload()
    visible_payload["organization_id"] = str(organization_id)
    visible_payload["chat_id"] = str(accessible_chat_id)
    visible_payload["created_by_user_id"] = str(user_id)
    visible_payload["assignee_ids"] = [str(user_id)]
    visible = client.post("/api/tasks", json=visible_payload).json()

    hidden_payload = task_payload()
    hidden_payload["organization_id"] = str(organization_id)
    hidden_payload["chat_id"] = str(inaccessible_chat_id)
    hidden_payload["created_by_user_id"] = str(uuid4())
    hidden_payload["assignee_ids"] = [str(uuid4())]
    hidden_payload["observer_ids"] = []
    client.post("/api/tasks", json=hidden_payload)

    member_headers = auth_headers(
        user_id=user_id,
        organization_id=organization_id,
        chat_id=accessible_chat_id,
        roles=ROLE_MEMBER,
    )
    all_response = client.get("/api/tasks", headers=member_headers)
    inaccessible_chat_response = client.get(
        "/api/tasks",
        params={"chat_id": str(inaccessible_chat_id)},
        headers=member_headers,
    )

    assert all_response.status_code == 200
    assert [task["id"] for task in all_response.json()] == [visible["id"]]
    assert inaccessible_chat_response.status_code == 200
    assert inaccessible_chat_response.json() == []


@pytest.mark.parametrize("search", ["1", "#1", "T-1", "t-1"])
def test_list_tasks_searches_by_task_number_reference(
    tasks_client: tuple[TestClient, FakeTaskService],
    search: str,
) -> None:
    client, service = tasks_client
    organization_id = str(uuid4())
    first_payload = task_payload()
    first_payload["organization_id"] = organization_id
    second_payload = task_payload()
    second_payload["organization_id"] = organization_id
    first = client.post("/api/tasks", json=first_payload).json()
    second = client.post("/api/tasks", json=second_payload).json()

    response = client.get("/api/tasks", params={"search": search})

    assert response.status_code == 200
    assert [task["id"] for task in response.json()] == [first["id"]]
    assert service.last_filters is not None
    assert service.last_filters.search == search
    assert service.last_filters.search_task_number == 1
    assert second["task_number"] == 2


def test_list_tasks_supports_explicit_task_number_filter(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    organization_id = str(uuid4())
    first_payload = task_payload()
    first_payload["organization_id"] = organization_id
    second_payload = task_payload()
    second_payload["organization_id"] = organization_id
    client.post("/api/tasks", json=first_payload).json()
    second = client.post("/api/tasks", json=second_payload).json()

    response = client.get("/api/tasks", params={"task_number": 2})

    assert response.status_code == 200
    assert [task["id"] for task in response.json()] == [second["id"]]
    assert service.last_filters is not None
    assert service.last_filters.task_number == 2


def test_list_tasks_searches_by_text_when_search_is_not_task_reference(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    report = client.post("/api/tasks", json=task_payload()).json()
    other_payload = task_payload()
    other_payload["title"] = "Collect invoices"
    client.post("/api/tasks", json=other_payload)

    response = client.get("/api/tasks", params={"search": "weekly"})

    assert response.status_code == 200
    assert [task["id"] for task in response.json()] == [report["id"]]
    assert service.last_filters is not None
    assert service.last_filters.search_task_number is None


def test_list_tasks_rejects_invalid_limit(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client

    response = client.get("/api/tasks", params={"limit": 0})

    assert response.status_code == 422


def test_inbox_summary_uses_authenticated_user_when_user_id_omitted(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client

    response = client.get("/api/tasks/inbox/summary")

    assert response.status_code == 200
    assert service.last_inbox_filters is not None
    assert service.last_inbox_filters.user_id == UUID(client.headers["X-User-Id"])


def test_inbox_summary_returns_user_buckets(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    now = datetime.now(timezone.utc)
    user_id = uuid4()
    other_user_id = uuid4()

    my_task_payload = task_payload()
    my_task_payload["created_by_user_id"] = str(other_user_id)
    my_task_payload["assignee_ids"] = [str(user_id)]
    my_task_payload["observer_ids"] = []
    my_task = client.post("/api/tasks", json=my_task_payload).json()

    created_payload = task_payload()
    created_payload["created_by_user_id"] = str(user_id)
    created_payload["assignee_ids"] = [str(other_user_id)]
    created_task = client.post("/api/tasks", json=created_payload).json()

    observed_payload = task_payload()
    observed_payload["created_by_user_id"] = str(other_user_id)
    observed_payload["assignee_ids"] = [str(other_user_id)]
    observed_payload["observer_ids"] = [str(user_id)]
    observed_task = client.post("/api/tasks", json=observed_payload).json()

    waiting_acceptance_payload = task_payload()
    waiting_acceptance_payload["created_by_user_id"] = str(user_id)
    waiting_acceptance_payload["assignee_ids"] = [str(other_user_id)]
    waiting_acceptance_task = client.post("/api/tasks", json=waiting_acceptance_payload).json()
    client.patch(
        f"/api/tasks/{waiting_acceptance_task['id']}",
        json={"status": TaskStatus.WAITING_ACCEPTANCE.value},
    )

    overdue_payload = task_payload()
    overdue_payload["created_by_user_id"] = str(other_user_id)
    overdue_payload["assignee_ids"] = [str(user_id)]
    overdue_task = client.post("/api/tasks", json=overdue_payload).json()
    service.tasks[UUID(overdue_task["id"])] = service.tasks[UUID(overdue_task["id"])].model_copy(
        update={"deadline_at": now - timedelta(days=1)}
    )

    today_payload = task_payload()
    today_payload["created_by_user_id"] = str(other_user_id)
    today_payload["assignee_ids"] = [str(other_user_id)]
    today_payload["observer_ids"] = [str(user_id)]
    today_start, today_end = local_day_bounds_utc(now)
    today_deadline = min(now + timedelta(hours=1), today_end - timedelta(minutes=1))
    if today_deadline < now + timedelta(minutes=1):
        today_deadline = now + timedelta(minutes=1)
    assert today_start <= today_deadline < today_end
    today_payload["deadline_at"] = today_deadline.isoformat()
    today_task = client.post("/api/tasks", json=today_payload).json()

    response = client.get(
        "/api/tasks/inbox/summary",
        params={"user_id": str(user_id)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert my_task["id"] in _task_ids(payload["my_tasks"])
    assert created_task["id"] in _task_ids(payload["created_by_me"])
    assert observed_task["id"] in _task_ids(payload["observed_by_me"])
    assert my_task["id"] in _task_ids(payload["new"])
    assert my_task["id"] in _task_ids(payload["waiting_my_response"])
    assert waiting_acceptance_task["id"] in _task_ids(payload["waiting_my_acceptance"])
    assert overdue_task["id"] in _task_ids(payload["overdue"])
    assert today_task["id"] in _task_ids(payload["today"])
    assert payload["new_count"] == len(payload["new"])
    assert payload["awaiting_report_count"] == len(payload["waiting_my_response"])
    assert payload["awaiting_acceptance_count"] == len(payload["waiting_my_acceptance"])
    assert payload["overdue_count"] == len(payload["overdue"])
    assert payload["today_count"] == len(payload["today"])


def test_inbox_summary_applies_filters(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    user_id = uuid4()
    organization_id = uuid4()
    chat_id = uuid4()

    target_payload = task_payload()
    target_payload["organization_id"] = str(organization_id)
    target_payload["chat_id"] = str(chat_id)
    target_payload["assignee_ids"] = [str(user_id)]
    target_task = client.post("/api/tasks", json=target_payload).json()
    client.patch(
        f"/api/tasks/{target_task['id']}",
        json={"status": TaskStatus.IN_PROGRESS.value},
    )

    other_payload = task_payload()
    other_payload["assignee_ids"] = [str(user_id)]
    client.post("/api/tasks", json=other_payload)

    response = client.get(
        "/api/tasks/inbox/summary",
        params={
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "chat_id": str(chat_id),
            "status": TaskStatus.IN_PROGRESS.value,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert _task_ids(payload["my_tasks"]) == [target_task["id"]]
    assert payload["created_by_me"] == []


def _task_ids(tasks: list[dict[str, object]]) -> list[str]:
    return [str(task["id"]) for task in tasks]


def test_get_task_returns_full_detail(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.get(f"/api/tasks/{created['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == created["id"]
    assert len(payload["assignees"]) == 2
    assert len(payload["observers"]) == 1
    assert payload["comments"][0]["text"] == "Initial comment"
    assert payload["files"][0]["file_name"] == "brief.pdf"
    assert payload["responses"][0]["status"] == TaskResponseStatus.SUBMITTED.value
    assert payload["status_history"][0]["new_status"] == TaskStatus.NEW.value


def test_wrong_user_cannot_access_unrelated_task(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.get(
        f"/api/tasks/{created['id']}",
        headers=auth_headers(
            user_id=uuid4(),
            organization_id=UUID(created["organization_id"]),
            chat_id=UUID(created["chat_id"]),
            roles=ROLE_MEMBER,
        ),
    )

    assert response.status_code == 403


def test_creator_can_access_task(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.get(
        f"/api/tasks/{created['id']}",
        headers=auth_headers(
            user_id=UUID(created["created_by_user_id"]),
            organization_id=UUID(created["organization_id"]),
            chat_id=UUID(created["chat_id"]),
            roles=ROLE_MEMBER,
        ),
    )

    assert response.status_code == 200


def test_assignee_can_access_task(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    assignee_id = UUID(created["assignees"][0]["user_id"])

    response = client.get(
        f"/api/tasks/{created['id']}",
        headers=auth_headers(
            user_id=assignee_id,
            organization_id=UUID(created["organization_id"]),
            chat_id=UUID(created["chat_id"]),
            roles=ROLE_MEMBER,
        ),
    )

    assert response.status_code == 200


def test_get_task_returns_404_for_missing_id(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client

    response = client.get(f"/api/tasks/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_update_task_changes_fields_and_records_status_history(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    deadline_at = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()

    response = client.patch(
        f"/api/tasks/{created['id']}",
        json={
            "title": "Updated task",
            "description": None,
            "deadline_at": deadline_at,
            "priority": TaskPriority.URGENT.value,
            "completion_rule": TaskCompletionRule.MANUAL_SUBMIT.value,
            "status": TaskStatus.IN_PROGRESS.value,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Updated task"
    assert payload["description"] is None
    assert datetime.fromisoformat(payload["deadline_at"].replace("Z", "+00:00")) == datetime.fromisoformat(deadline_at)
    assert payload["priority"] == TaskPriority.URGENT.value
    assert payload["completion_rule"] == TaskCompletionRule.MANUAL_SUBMIT.value
    assert payload["status"] == TaskStatus.IN_PROGRESS.value
    assert payload["status_history"][-1]["old_status"] == TaskStatus.NEW.value
    assert payload["status_history"][-1]["new_status"] == TaskStatus.IN_PROGRESS.value


def test_update_task_rejects_past_deadline(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.patch(
        f"/api/tasks/{created['id']}",
        json={"deadline_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "deadline_must_be_in_future"


def test_update_task_rejects_null_status(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.patch(f"/api/tasks/{created['id']}", json={"status": None})

    assert response.status_code == 422


def test_cancel_task_sets_cancelled_status_and_history(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.post(f"/api/tasks/{created['id']}/cancel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == TaskStatus.CANCELLED.value
    assert payload["cancelled_at"] is not None
    assert payload["status_history"][-1]["old_status"] == TaskStatus.NEW.value
    assert payload["status_history"][-1]["new_status"] == TaskStatus.CANCELLED.value


def test_cancel_done_task_returns_409(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    client.patch(f"/api/tasks/{created['id']}", json={"status": TaskStatus.DONE.value})

    response = client.post(f"/api/tasks/{created['id']}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"] == "Done task cannot be cancelled without force"


def test_add_task_assignee(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    user_id = uuid4()

    response = client.post(
        f"/api/tasks/{created['id']}/assignees",
        json={"user_id": str(user_id)},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["task_id"] == created["id"]
    assert payload["user_id"] == str(user_id)
    assert payload["status"] == TaskAssigneeStatus.ASSIGNED.value
    assert payload["response_required"] is True
    assert service.audit_actions[-1] == "task.assignee_added"


def test_add_task_assignee_rejects_duplicate(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    existing_user_id = created["assignees"][0]["user_id"]

    response = client.post(
        f"/api/tasks/{created['id']}/assignees",
        json={"user_id": existing_user_id},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Task assignee already exists"


def test_remove_task_assignee(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    user_id = created["assignees"][0]["user_id"]

    response = client.delete(f"/api/tasks/{created['id']}/assignees/{user_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert service.audit_actions[-1] == "task.assignee_removed"
    detail = client.get(f"/api/tasks/{created['id']}").json()
    assert user_id not in [assignee["user_id"] for assignee in detail["assignees"]]


def test_add_task_observer(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    user_id = uuid4()

    response = client.post(
        f"/api/tasks/{created['id']}/observers",
        json={"user_id": str(user_id)},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["task_id"] == created["id"]
    assert payload["user_id"] == str(user_id)
    assert service.audit_actions[-1] == "task.observer_added"


def test_add_task_observer_rejects_duplicate(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    existing_user_id = created["observers"][0]["user_id"]

    response = client.post(
        f"/api/tasks/{created['id']}/observers",
        json={"user_id": existing_user_id},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Task observer already exists"


def test_remove_task_observer(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    user_id = created["observers"][0]["user_id"]

    response = client.delete(f"/api/tasks/{created['id']}/observers/{user_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert service.audit_actions[-1] == "task.observer_removed"
    detail = client.get(f"/api/tasks/{created['id']}").json()
    assert user_id not in [observer["user_id"] for observer in detail["observers"]]


def test_add_task_comment(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    user_id = uuid4()

    response = client.post(
        f"/api/tasks/{created['id']}/comments",
        json={"user_id": str(user_id), "text": "Looks good"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["task_id"] == created["id"]
    assert payload["user_id"] == str(user_id)
    assert payload["text"] == "Looks good"
    assert payload["reply_to_comment_id"] is None


def test_add_task_comment_requires_text(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.post(
        f"/api/tasks/{created['id']}/comments",
        json={"user_id": str(uuid4())},
    )

    assert response.status_code == 422


def test_add_task_comment_reply(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    parent = client.post(
        f"/api/tasks/{created['id']}/comments",
        json={"user_id": str(uuid4()), "text": "Parent"},
    ).json()

    response = client.post(
        f"/api/tasks/{created['id']}/comments",
        json={
            "user_id": str(uuid4()),
            "text": "Reply",
            "reply_to_comment_id": parent["id"],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["text"] == "Reply"
    assert payload["reply_to_comment_id"] == parent["id"]


def test_add_task_comment_reply_returns_404_for_missing_comment(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.post(
        f"/api/tasks/{created['id']}/comments",
        json={
            "user_id": str(uuid4()),
            "text": "Reply",
            "reply_to_comment_id": str(uuid4()),
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Reply comment not found"


def test_list_task_comments(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    client.post(
        f"/api/tasks/{created['id']}/comments",
        json={"user_id": str(uuid4()), "text": "Second comment"},
    )

    response = client.get(f"/api/tasks/{created['id']}/comments")

    assert response.status_code == 200
    assert [comment["text"] for comment in response.json()] == [
        "Initial comment",
        "Second comment",
    ]


def test_add_task_file_metadata(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    user_id = uuid4()

    response = client.post(
        f"/api/tasks/{created['id']}/files",
        json={
            "uploaded_by_user_id": str(user_id),
            "file_name": "report.pdf",
            "file_url": None,
            "file_storage_key": "tasks/report.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 4096,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["task_id"] == created["id"]
    assert payload["comment_id"] is None
    assert payload["uploaded_by_user_id"] == str(user_id)
    assert payload["file_name"] == "report.pdf"
    assert payload["file_storage_key"] == "tasks/report.pdf"
    assert payload["mime_type"] == "application/pdf"
    assert payload["size_bytes"] == 4096


def test_add_task_file_metadata_requires_file_name(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.post(
        f"/api/tasks/{created['id']}/files",
        json={"uploaded_by_user_id": str(uuid4())},
    )

    assert response.status_code == 422


def test_add_task_file_metadata_can_reference_comment(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    comment = client.post(
        f"/api/tasks/{created['id']}/comments",
        json={"user_id": str(uuid4()), "text": "Attach here"},
    ).json()

    response = client.post(
        f"/api/tasks/{created['id']}/files",
        json={
            "uploaded_by_user_id": comment["user_id"],
            "comment_id": comment["id"],
            "file_name": "reply.txt",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["comment_id"] == comment["id"]
    assert payload["file_name"] == "reply.txt"


def test_add_task_file_metadata_returns_404_for_missing_comment(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.post(
        f"/api/tasks/{created['id']}/files",
        json={
            "uploaded_by_user_id": str(uuid4()),
            "comment_id": str(uuid4()),
            "file_name": "missing-comment.txt",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Reply comment not found"


def test_list_task_files(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    client.post(
        f"/api/tasks/{created['id']}/files",
        json={
            "uploaded_by_user_id": str(uuid4()),
            "file_name": "second.txt",
        },
    )

    response = client.get(f"/api/tasks/{created['id']}/files")

    assert response.status_code == 200
    assert [file["file_name"] for file in response.json()] == ["brief.pdf", "second.txt"]


def test_submit_task_response_from_assignee(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    assignee_id = created["assignees"][0]["user_id"]

    response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={
            "user_id": assignee_id,
            "text": "Done",
            "source_message_id": "msg-123",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["task_id"] == created["id"]
    assert payload["user_id"] == assignee_id
    assert payload["text"] == "Done"
    assert payload["source_message_id"] == "msg-123"
    assert payload["status"] == TaskResponseStatus.SUBMITTED.value

    detail = client.get(f"/api/tasks/{created['id']}").json()
    updated_assignee = next(
        assignee for assignee in detail["assignees"] if assignee["user_id"] == assignee_id
    )
    assert updated_assignee["status"] == TaskAssigneeStatus.RESPONDED.value
    assert updated_assignee["responded_at"] is not None


def test_submit_task_response_from_non_assignee_is_forbidden(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()

    response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={"user_id": str(uuid4()), "text": "I am not assigned"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only task assignee can submit response"


def test_submit_task_response_any_assignee_rule_sets_waiting_acceptance(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    assignee_id = created["assignees"][0]["user_id"]

    response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={"user_id": assignee_id},
    )

    assert response.status_code == 201
    detail = client.get(f"/api/tasks/{created['id']}").json()
    assert detail["status"] == TaskStatus.WAITING_ACCEPTANCE.value
    assert detail["status_history"][-1]["old_status"] == TaskStatus.NEW.value
    assert detail["status_history"][-1]["new_status"] == TaskStatus.WAITING_ACCEPTANCE.value


def test_submit_task_response_all_assignees_rule_waits_for_all_responses(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    payload = task_payload()
    payload["completion_rule"] = TaskCompletionRule.ALL_ASSIGNEES_RESPONSE.value
    created = client.post("/api/tasks", json=payload).json()
    first_assignee_id = created["assignees"][0]["user_id"]
    second_assignee_id = created["assignees"][1]["user_id"]

    first_response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={"user_id": first_assignee_id},
    )
    detail_after_first = client.get(f"/api/tasks/{created['id']}").json()

    second_response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={"user_id": second_assignee_id},
    )
    detail_after_second = client.get(f"/api/tasks/{created['id']}").json()

    assert first_response.status_code == 201
    assert detail_after_first["status"] == TaskStatus.NEW.value
    assert second_response.status_code == 201
    assert detail_after_second["status"] == TaskStatus.WAITING_ACCEPTANCE.value
    assert detail_after_second["status_history"][-1]["new_status"] == TaskStatus.WAITING_ACCEPTANCE.value


def test_accept_task_response_by_creator(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={"user_id": created["assignees"][0]["user_id"], "text": "Ready"},
    ).json()

    acceptance_response = client.post(
        f"/api/tasks/{created['id']}/responses/{response['id']}/accept",
        json={
            "accepted_by_user_id": created["created_by_user_id"],
            "comment": "Accepted",
        },
    )

    assert acceptance_response.status_code == 201
    payload = acceptance_response.json()
    assert payload["task_id"] == created["id"]
    assert payload["response_id"] == response["id"]
    assert payload["accepted_by_user_id"] == created["created_by_user_id"]
    assert payload["decision"] == TaskAcceptanceDecision.ACCEPTED.value
    assert payload["comment"] == "Accepted"

    detail = client.get(f"/api/tasks/{created['id']}").json()
    accepted_response = next(item for item in detail["responses"] if item["id"] == response["id"])
    assert accepted_response["status"] == TaskResponseStatus.ACCEPTED.value
    assert detail["status"] == TaskStatus.DONE.value
    assert detail["completed_at"] is not None


def test_reject_task_response_by_creator(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    assignee_id = created["assignees"][0]["user_id"]
    response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={"user_id": assignee_id, "text": "Ready"},
    ).json()

    rejection_response = client.post(
        f"/api/tasks/{created['id']}/responses/{response['id']}/reject",
        json={
            "accepted_by_user_id": created["created_by_user_id"],
            "comment": "Please redo",
        },
    )

    assert rejection_response.status_code == 201
    payload = rejection_response.json()
    assert payload["decision"] == TaskAcceptanceDecision.REJECTED.value
    assert payload["comment"] == "Please redo"

    detail = client.get(f"/api/tasks/{created['id']}").json()
    rejected_response = next(item for item in detail["responses"] if item["id"] == response["id"])
    rejected_assignee = next(item for item in detail["assignees"] if item["user_id"] == assignee_id)
    assert rejected_response["status"] == TaskResponseStatus.REJECTED.value
    assert rejected_assignee["status"] == TaskAssigneeStatus.IN_PROGRESS.value
    assert detail["status"] == TaskStatus.IN_PROGRESS.value


def test_reject_accepted_task_response_is_conflict(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={"user_id": created["assignees"][0]["user_id"], "text": "Ready"},
    ).json()
    accepted = client.post(
        f"/api/tasks/{created['id']}/responses/{response['id']}/accept",
        json={"accepted_by_user_id": created["created_by_user_id"]},
    )
    assert accepted.status_code == 201

    rejected = client.post(
        f"/api/tasks/{created['id']}/responses/{response['id']}/reject",
        json={
            "accepted_by_user_id": created["created_by_user_id"],
            "comment": "Too late",
        },
    )

    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "Task response already decided"
    detail = client.get(f"/api/tasks/{created['id']}").json()
    accepted_response = next(item for item in detail["responses"] if item["id"] == response["id"])
    assert accepted_response["status"] == TaskResponseStatus.ACCEPTED.value
    assert detail["status"] == TaskStatus.DONE.value


def test_accept_rejected_task_response_is_conflict(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={"user_id": created["assignees"][0]["user_id"], "text": "Ready"},
    ).json()
    rejected = client.post(
        f"/api/tasks/{created['id']}/responses/{response['id']}/reject",
        json={
            "accepted_by_user_id": created["created_by_user_id"],
            "comment": "Please redo",
        },
    )
    assert rejected.status_code == 201

    accepted = client.post(
        f"/api/tasks/{created['id']}/responses/{response['id']}/accept",
        json={"accepted_by_user_id": created["created_by_user_id"]},
    )

    assert accepted.status_code == 409
    assert accepted.json()["detail"] == "Task response already decided"
    detail = client.get(f"/api/tasks/{created['id']}").json()
    rejected_response = next(item for item in detail["responses"] if item["id"] == response["id"])
    assert rejected_response["status"] == TaskResponseStatus.REJECTED.value
    assert detail["status"] == TaskStatus.IN_PROGRESS.value


def test_reject_overdue_task_response_returns_to_overdue(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    service.tasks[UUID(created["id"])].deadline_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    assignee_id = created["assignees"][0]["user_id"]
    response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={"user_id": assignee_id, "text": "Ready"},
    ).json()

    rejection_response = client.post(
        f"/api/tasks/{created['id']}/responses/{response['id']}/reject",
        json={
            "accepted_by_user_id": created["created_by_user_id"],
            "comment": "Please redo",
        },
    )

    assert rejection_response.status_code == 201
    detail = client.get(f"/api/tasks/{created['id']}").json()
    assert detail["status"] == TaskStatus.OVERDUE.value


def test_accept_task_response_by_non_creator_is_forbidden(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    created = client.post("/api/tasks", json=task_payload()).json()
    response = client.post(
        f"/api/tasks/{created['id']}/responses",
        json={"user_id": created["assignees"][0]["user_id"]},
    ).json()

    acceptance_response = client.post(
        f"/api/tasks/{created['id']}/responses/{response['id']}/accept",
        json={"accepted_by_user_id": str(uuid4())},
    )

    assert acceptance_response.status_code == 403
    assert (
        acceptance_response.json()["detail"]
        == "Only task creator, chat_admin or super_admin can accept or reject response"
    )


def test_accept_task_response_rejects_response_from_another_task(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    first_task = client.post("/api/tasks", json=task_payload()).json()
    second_task = client.post("/api/tasks", json=task_payload()).json()
    second_response = client.post(
        f"/api/tasks/{second_task['id']}/responses",
        json={"user_id": second_task["assignees"][0]["user_id"]},
    ).json()

    acceptance_response = client.post(
        f"/api/tasks/{first_task['id']}/responses/{second_response['id']}/accept",
        json={"accepted_by_user_id": first_task["created_by_user_id"]},
    )

    assert acceptance_response.status_code == 404
    assert acceptance_response.json()["detail"] == "Task response not found"


def test_accept_and_reject_task_status_transitions(
    tasks_client: tuple[TestClient, FakeTaskService],
) -> None:
    client, _service = tasks_client
    accepted_task = client.post("/api/tasks", json=task_payload()).json()
    accepted_response = client.post(
        f"/api/tasks/{accepted_task['id']}/responses",
        json={"user_id": accepted_task["assignees"][0]["user_id"]},
    ).json()

    client.post(
        f"/api/tasks/{accepted_task['id']}/responses/{accepted_response['id']}/accept",
        json={"accepted_by_user_id": accepted_task["created_by_user_id"]},
    )
    accepted_detail = client.get(f"/api/tasks/{accepted_task['id']}").json()

    rejected_task = client.post("/api/tasks", json=task_payload()).json()
    rejected_response = client.post(
        f"/api/tasks/{rejected_task['id']}/responses",
        json={"user_id": rejected_task["assignees"][0]["user_id"]},
    ).json()
    client.post(
        f"/api/tasks/{rejected_task['id']}/responses/{rejected_response['id']}/reject",
        json={"accepted_by_user_id": rejected_task["created_by_user_id"]},
    )
    rejected_detail = client.get(f"/api/tasks/{rejected_task['id']}").json()

    assert accepted_detail["status"] == TaskStatus.DONE.value
    assert accepted_detail["status_history"][-1]["new_status"] == TaskStatus.DONE.value
    assert rejected_detail["status"] == TaskStatus.IN_PROGRESS.value
    assert rejected_detail["status_history"][-1]["new_status"] == TaskStatus.IN_PROGRESS.value
