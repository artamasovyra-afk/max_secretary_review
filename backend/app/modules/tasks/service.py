from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN
from app.modules.chats.models import Chat, ChatMember
from app.modules.notifications.max_sender import MaxSender, OutboundPurpose
from app.modules.tasks.enums import (
    TaskAcceptanceDecision,
    TaskAssigneeStatus,
    TaskCompletionRule,
    TaskPriority,
    TaskResponseStatus,
    TaskStatus,
    TaskType,
)
from app.modules.tasks.models import (
    Task,
    TaskAcceptance,
    TaskAssignee,
    TaskComment,
    TaskFile,
    TaskObserver,
    TaskResponse,
)
from app.modules.tasks.deadline_parser import (
    DEADLINE_MUST_BE_IN_FUTURE_DETAIL,
    as_aware_utc,
    is_future_task_deadline,
    local_day_bounds_utc,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    TaskAcceptanceCreate,
    TaskCommentCreate,
    TaskCreate,
    TaskGroupAssignmentCreate,
    TaskGroupAssignmentCreateRead,
    TaskGroupReportChatRead,
    TaskGroupReportCreatorRead,
    TaskGroupReportItemRead,
    TaskGroupReportRead,
    TaskGroupReportUserRead,
    TaskFileCreate,
    TaskInboxSummaryFilters,
    TaskInboxSummaryRead,
    TaskListFilters,
    TaskParticipantCreate,
    TaskResponseCreate,
    TaskUpdate,
)

GROUP_ASSIGNMENT_ROLES = frozenset({ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN})
GROUP_ASSIGNMENT_CHAT_NOTIFICATION_TYPE = "group_assignment_created"
logger = logging.getLogger(__name__)
PROJECT_TIMEZONE = ZoneInfo("Asia/Yekaterinburg")


class TaskService:
    def __init__(
        self,
        repository: TaskRepository,
        session: AsyncSession,
        *,
        sender: MaxSender | None = None,
        group_assignment_webapp_url: str | None = None,
    ) -> None:
        self.repository = repository
        self.session = session
        self.sender = sender
        self.group_assignment_webapp_url = group_assignment_webapp_url

    async def create(self, payload: TaskCreate) -> Task:
        self._ensure_deadline_in_future(payload.deadline_at)
        chat = await self._validate_task_relations(payload)
        task = await self.repository.create_task(
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            title=payload.title,
            description=payload.description,
            source_message_id=payload.source_message_id,
            created_by_user_id=payload.created_by_user_id,
            deadline_at=as_aware_utc(payload.deadline_at),
            status=TaskStatus.NEW.value,
            priority=payload.priority.value,
            completion_rule=payload.completion_rule.value,
            source_chat_title_snapshot=chat.title,
        )
        await self.repository.create_assignees(
            task_id=task.id,
            assignee_ids=payload.assignee_ids,
        )
        await self.repository.create_observers(
            task_id=task.id,
            observer_ids=payload.observer_ids,
        )
        await self.repository.create_status_history(
            task_id=task.id,
            old_status=None,
            new_status=TaskStatus.NEW.value,
            changed_by_user_id=payload.created_by_user_id,
        )
        await self.session.commit()

        created_task = await self.repository.get_with_participants(task.id)
        if created_task is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Created task was not found",
            )
        return created_task

    async def create_group_assignment(
        self,
        payload: TaskGroupAssignmentCreate,
        auth_context: AuthContext,
    ) -> TaskGroupAssignmentCreateRead:
        self._ensure_deadline_in_future(payload.deadline_at)
        self._ensure_group_assignment_allowed(payload, auth_context)
        await self._ensure_organization_exists(payload.organization_id)
        chat = await self.repository.get_chat_with_members(payload.chat_id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found",
            )
        if chat.organization_id != payload.organization_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chat does not belong to organization",
            )
        active_members = [member for member in chat.members if member.is_active]
        self._ensure_group_assignment_chat_allowed(
            payload=payload,
            auth_context=auth_context,
            chat=chat,
            active_members=active_members,
        )
        creator = await self.repository.get_user(payload.created_by_user_id)
        if creator is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Creator user not found",
            )

        creator_member = self._find_chat_member(active_members, payload.created_by_user_id)
        assignee_members = self._resolve_group_assignment_assignees(
            payload=payload,
            active_members=active_members,
        )
        assignee_ids = [member.user_id for member in assignee_members]
        if not assignee_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="no_assignees",
            )

        creator_role_snapshot = self._creator_role_snapshot(auth_context, creator_member)
        chat_display_title = _chat_display_title(chat)
        audience_snapshot = self._group_assignment_audience_snapshot(
            chat_id=chat.id,
            chat_title=chat_display_title,
            active_members=active_members,
            assignee_members=assignee_members,
            exclude_creator=payload.exclude_creator,
            response_required=payload.response_required,
        )
        task = await self.repository.create_task(
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            title=payload.title,
            description=payload.description,
            source_message_id=None,
            created_by_user_id=payload.created_by_user_id,
            deadline_at=as_aware_utc(payload.deadline_at),
            status=TaskStatus.NEW.value,
            priority=TaskPriority.NORMAL.value,
            completion_rule=TaskCompletionRule.ALL_ASSIGNEES_RESPONSE.value,
            task_type=TaskType.GROUP_ASSIGNMENT.value,
            requires_individual_report=payload.response_required,
            audience_snapshot=audience_snapshot,
            creator_display_name_snapshot=creator.display_name,
            creator_role_snapshot=creator_role_snapshot,
            source_chat_title_snapshot=chat_display_title,
        )
        await self.repository.create_assignees(
            task_id=task.id,
            assignee_ids=assignee_ids,
            response_required=payload.response_required,
        )
        await self.repository.create_status_history(
            task_id=task.id,
            old_status=None,
            new_status=TaskStatus.NEW.value,
            changed_by_user_id=payload.created_by_user_id,
        )
        await self.session.commit()
        self._send_group_assignment_chat_summary(
            chat=chat,
            task=task,
            title=payload.title,
            deadline_at=as_aware_utc(payload.deadline_at),
            assignee_members=assignee_members,
            response_required=payload.response_required,
        )
        return TaskGroupAssignmentCreateRead(
            task_id=task.id,
            task_number=task.task_number,
            task_ref=f"#{task.task_number}",
            total_assignees=len(assignee_ids),
            creator_display_name=creator.display_name,
            creator_role=creator_role_snapshot,
        )

    async def list(
        self,
        *,
        filters: TaskListFilters,
        limit: int,
        offset: int,
    ) -> list[Task]:
        return await self.repository.list_tasks(
            filters=filters,
            limit=limit,
            offset=offset,
        )

    async def inbox_summary(self, filters: TaskInboxSummaryFilters) -> TaskInboxSummaryRead:
        now = datetime.now(timezone.utc)
        today_start, today_end = local_day_bounds_utc(now)
        summary = await self.repository.inbox_summary(
            filters=filters,
            now=now,
            today_start=today_start,
            today_end=today_end,
        )
        return TaskInboxSummaryRead(**summary)

    async def get(self, task_id: UUID) -> Task:
        task = await self.repository.get_detail(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )
        return task

    async def get_group_report(
        self,
        task_id: UUID,
        auth_context: AuthContext,
    ) -> TaskGroupReportRead:
        task = await self.repository.get_group_report_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )
        if task.task_type != TaskType.GROUP_ASSIGNMENT.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task is not a group assignment",
            )
        self._ensure_group_report_allowed(task, auth_context)

        responses_by_user = self._latest_responses_by_user(task.responses)
        now = datetime.now(timezone.utc)
        items: list[TaskGroupReportItemRead] = []
        responded = 0
        overdue = 0
        for assignee in task.assignees:
            latest_response = responses_by_user.get(assignee.user_id)
            has_responded = self._assignee_has_responded(assignee, latest_response)
            if has_responded:
                responded += 1
            elif self._is_group_report_item_overdue(task, now):
                overdue += 1

            items.append(
                TaskGroupReportItemRead(
                    user=TaskGroupReportUserRead(
                        user_id=assignee.user_id,
                        display_name=self._user_display_name(assignee.user, assignee.user_id),
                    ),
                    status=assignee.status,
                    responded_at=assignee.responded_at,
                    response_text=latest_response.text if latest_response is not None else None,
                )
            )

        total = len(items)
        return TaskGroupReportRead(
            task_id=task.id,
            task_number=task.task_number,
            task_ref=f"#{task.task_number}",
            title=task.title,
            creator=TaskGroupReportCreatorRead(
                user_id=task.created_by_user_id,
                display_name=(
                    task.creator_display_name_snapshot
                    or self._user_display_name(task.created_by_user, task.created_by_user_id)
                ),
                role=task.creator_role_snapshot,
            ),
            chat=TaskGroupReportChatRead(
                chat_id=task.chat_id,
                title=task.source_chat_title_snapshot or getattr(task.chat, "title", "Чат"),
            ),
            total=total,
            responded=responded,
            pending=total - responded,
            overdue=overdue,
            items=items,
        )

    async def update(self, task_id: UUID, payload: TaskUpdate) -> Task:
        task = await self.get(task_id)
        old_status = task.status
        values = self._normalize_update_values(payload)
        if "deadline_at" in values:
            self._ensure_deadline_in_future(values["deadline_at"])
        task = await self.repository.update_task(task, values=values)

        new_status = values.get("status")
        if new_status is not None and new_status != old_status:
            await self.repository.create_status_history(
                task_id=task.id,
                old_status=old_status,
                new_status=new_status,
                changed_by_user_id=None,
            )

        await self.session.commit()
        return await self.get(task.id)

    async def cancel(self, task_id: UUID) -> Task:
        task = await self.get(task_id)
        if task.status == TaskStatus.DONE.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Done task cannot be cancelled without force",
            )

        old_status = task.status
        values = {
            "status": TaskStatus.CANCELLED.value,
            "cancelled_at": datetime.now(timezone.utc),
        }
        task = await self.repository.update_task(task, values=values)

        if old_status != TaskStatus.CANCELLED.value:
            await self.repository.create_status_history(
                task_id=task.id,
                old_status=old_status,
                new_status=TaskStatus.CANCELLED.value,
                changed_by_user_id=None,
            )

        await self.session.commit()
        return await self.get(task.id)

    async def add_assignee(
        self,
        task_id: UUID,
        payload: TaskParticipantCreate,
    ) -> TaskAssignee:
        task = await self.get(task_id)
        await self._ensure_users_exist({payload.user_id})

        existing_assignee = await self.repository.get_assignee(
            task_id=task.id,
            user_id=payload.user_id,
        )
        if existing_assignee is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task assignee already exists",
            )

        assignee = await self.repository.create_assignee(
            task_id=task.id,
            user_id=payload.user_id,
        )
        await self.repository.create_audit_log(
            organization_id=task.organization_id,
            entity_id=task.id,
            action="task.assignee_added",
            payload={"user_id": str(payload.user_id)},
        )
        await self.session.commit()
        await self.session.refresh(assignee)
        return assignee

    async def remove_assignee(self, task_id: UUID, user_id: UUID) -> None:
        task = await self.get(task_id)
        assignee = await self.repository.get_assignee(task_id=task.id, user_id=user_id)
        if assignee is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task assignee not found",
            )

        await self.repository.delete_assignee(assignee)
        await self.repository.create_audit_log(
            organization_id=task.organization_id,
            entity_id=task.id,
            action="task.assignee_removed",
            payload={"user_id": str(user_id)},
        )
        await self.session.commit()

    async def add_observer(
        self,
        task_id: UUID,
        payload: TaskParticipantCreate,
    ) -> TaskObserver:
        task = await self.get(task_id)
        await self._ensure_users_exist({payload.user_id})

        existing_observer = await self.repository.get_observer(
            task_id=task.id,
            user_id=payload.user_id,
        )
        if existing_observer is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task observer already exists",
            )

        observer = await self.repository.create_observer(
            task_id=task.id,
            user_id=payload.user_id,
        )
        await self.repository.create_audit_log(
            organization_id=task.organization_id,
            entity_id=task.id,
            action="task.observer_added",
            payload={"user_id": str(payload.user_id)},
        )
        await self.session.commit()
        await self.session.refresh(observer)
        return observer

    async def remove_observer(self, task_id: UUID, user_id: UUID) -> None:
        task = await self.get(task_id)
        observer = await self.repository.get_observer(task_id=task.id, user_id=user_id)
        if observer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task observer not found",
            )

        await self.repository.delete_observer(observer)
        await self.repository.create_audit_log(
            organization_id=task.organization_id,
            entity_id=task.id,
            action="task.observer_removed",
            payload={"user_id": str(user_id)},
        )
        await self.session.commit()

    async def add_comment(self, task_id: UUID, payload: TaskCommentCreate) -> TaskComment:
        task = await self.get(task_id)
        await self._ensure_users_exist({payload.user_id})

        if payload.reply_to_comment_id is not None:
            await self._ensure_reply_comment_belongs_to_task(
                task_id=task.id,
                comment_id=payload.reply_to_comment_id,
            )

        comment = await self.repository.create_comment(
            task_id=task.id,
            user_id=payload.user_id,
            text=payload.text,
            reply_to_comment_id=payload.reply_to_comment_id,
        )
        await self.session.commit()
        await self.session.refresh(comment)
        return comment

    async def list_comments(self, task_id: UUID) -> list[TaskComment]:
        task = await self.get(task_id)
        return await self.repository.list_comments(task.id)

    async def add_file(self, task_id: UUID, payload: TaskFileCreate) -> TaskFile:
        task = await self.get(task_id)
        await self._ensure_users_exist({payload.uploaded_by_user_id})

        if payload.comment_id is not None:
            await self._ensure_reply_comment_belongs_to_task(
                task_id=task.id,
                comment_id=payload.comment_id,
            )

        file = await self.repository.create_file(
            task_id=task.id,
            uploaded_by_user_id=payload.uploaded_by_user_id,
            comment_id=payload.comment_id,
            file_name=payload.file_name,
            file_url=payload.file_url,
            file_storage_key=payload.file_storage_key,
            mime_type=payload.mime_type,
            size_bytes=payload.size_bytes,
        )
        await self.session.commit()
        await self.session.refresh(file)
        return file

    async def list_files(self, task_id: UUID) -> list[TaskFile]:
        task = await self.get(task_id)
        return await self.repository.list_files(task.id)

    async def start_assignee_task(self, task_id: UUID, user_id: UUID) -> Task:
        task = await self.get(task_id)
        assignee = self._find_assignee(task, user_id)
        if assignee is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only task assignee can start task",
            )
        if task.status in {TaskStatus.DONE.value, TaskStatus.CANCELLED.value}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Done or cancelled task cannot be started",
            )

        await self.repository.update_assignee_status(
            assignee,
            status=TaskAssigneeStatus.IN_PROGRESS.value,
        )
        if task.status != TaskStatus.IN_PROGRESS.value:
            old_status = task.status
            await self.repository.update_task(task, values={"status": TaskStatus.IN_PROGRESS.value})
            await self.repository.create_status_history(
                task_id=task.id,
                old_status=old_status,
                new_status=TaskStatus.IN_PROGRESS.value,
                changed_by_user_id=user_id,
            )

        await self.session.commit()
        return await self.get(task.id)

    async def submit_response(self, task_id: UUID, payload: TaskResponseCreate) -> TaskResponse:
        task = await self.get(task_id)
        assignee = self._find_assignee(task, payload.user_id)
        if assignee is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only task assignee can submit response",
            )

        response = await self.repository.create_response(
            task_id=task.id,
            user_id=payload.user_id,
            text=payload.text,
            source_message_id=payload.source_message_id,
            status=TaskResponseStatus.SUBMITTED.value,
        )
        await self.repository.update_assignee_response(
            assignee,
            responded_at=datetime.now(timezone.utc),
            status=TaskAssigneeStatus.RESPONDED.value,
        )
        await self._apply_completion_rule_after_response(task, changed_by_user_id=payload.user_id)
        await self.session.commit()
        await self.session.refresh(response)
        return response

    async def accept_response(
        self,
        task_id: UUID,
        response_id: UUID,
        payload: TaskAcceptanceCreate,
        *,
        auth_context: AuthContext | None = None,
    ) -> TaskAcceptance:
        task = await self.get(task_id)
        response = self._find_response(task, response_id)
        if response is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task response not found",
            )
        self._ensure_can_accept_response(task, payload.accepted_by_user_id, auth_context=auth_context)
        self._ensure_response_can_be_decided(response)

        await self.repository.update_response_status(
            response,
            status=TaskResponseStatus.ACCEPTED.value,
        )
        acceptance = await self.repository.create_acceptance(
            task_id=task.id,
            response_id=response.id,
            accepted_by_user_id=payload.accepted_by_user_id,
            decision=TaskAcceptanceDecision.ACCEPTED.value,
            comment=payload.comment,
        )

        old_status = task.status
        await self.repository.update_task(
            task,
            values={
                "status": TaskStatus.DONE.value,
                "completed_at": datetime.now(timezone.utc),
            },
        )
        if old_status != TaskStatus.DONE.value:
            await self.repository.create_status_history(
                task_id=task.id,
                old_status=old_status,
                new_status=TaskStatus.DONE.value,
                changed_by_user_id=payload.accepted_by_user_id,
            )

        await self.session.commit()
        await self.session.refresh(acceptance)
        return acceptance

    async def reject_response(
        self,
        task_id: UUID,
        response_id: UUID,
        payload: TaskAcceptanceCreate,
        *,
        auth_context: AuthContext | None = None,
    ) -> TaskAcceptance:
        task = await self.get(task_id)
        response = self._find_response(task, response_id)
        if response is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task response not found",
            )
        self._ensure_can_accept_response(task, payload.accepted_by_user_id, auth_context=auth_context)
        self._ensure_response_can_be_decided(response)

        await self.repository.update_response_status(
            response,
            status=TaskResponseStatus.REJECTED.value,
        )
        acceptance = await self.repository.create_acceptance(
            task_id=task.id,
            response_id=response.id,
            accepted_by_user_id=payload.accepted_by_user_id,
            decision=TaskAcceptanceDecision.REJECTED.value,
            comment=payload.comment,
        )
        rejected_assignee = self._find_assignee(task, response.user_id)
        if rejected_assignee is not None:
            await self.repository.update_assignee_status(
                rejected_assignee,
                status=TaskAssigneeStatus.IN_PROGRESS.value,
            )

        now = datetime.now(timezone.utc)
        new_status = self._status_after_rejected_response(task, now=now)
        old_status = task.status
        await self.repository.update_task(task, values={"status": new_status, "completed_at": None})
        if old_status != new_status:
            await self.repository.create_status_history(
                task_id=task.id,
                old_status=old_status,
                new_status=new_status,
                changed_by_user_id=payload.accepted_by_user_id,
            )

        await self.session.commit()
        await self.session.refresh(acceptance)
        return acceptance

    def _status_after_rejected_response(self, task: Task, *, now: datetime) -> str:
        deadline_at = task.deadline_at
        if deadline_at is None:
            return TaskStatus.IN_PROGRESS.value
        if deadline_at.tzinfo is None:
            deadline_at = deadline_at.replace(tzinfo=timezone.utc)
        if deadline_at.astimezone(timezone.utc) < now:
            return TaskStatus.OVERDUE.value
        return TaskStatus.IN_PROGRESS.value

    def _ensure_group_assignment_allowed(
        self,
        payload: TaskGroupAssignmentCreate,
        auth_context: AuthContext,
    ) -> None:
        if not (auth_context.is_super_admin or auth_context.has_any_role(GROUP_ASSIGNMENT_ROLES)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient_permissions",
            )
        if not auth_context.is_super_admin and auth_context.user_id != payload.created_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient_permissions",
            )
        if auth_context.chat_id is not None and auth_context.chat_id != payload.chat_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient_permissions",
            )
        if auth_context.organization_id is not None and auth_context.organization_id != payload.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient_permissions",
            )

    def _ensure_group_assignment_chat_allowed(
        self,
        *,
        payload: TaskGroupAssignmentCreate,
        auth_context: AuthContext,
        chat: Chat,
        active_members: list[ChatMember],
    ) -> None:
        if str(getattr(chat, "status", "active") or "active") != "active":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="chat_not_active",
            )
        if not _max_chat_id(chat):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="missing_max_chat_id",
            )
        if auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN):
            return
        creator_member = self._find_chat_member(active_members, payload.created_by_user_id)
        if creator_member is None or creator_member.role != ROLE_CHAT_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient_permissions",
            )

    def _resolve_group_assignment_assignees(
        self,
        *,
        payload: TaskGroupAssignmentCreate,
        active_members: list[ChatMember],
    ) -> list[ChatMember]:
        active_member_by_user_id = {member.user_id: member for member in active_members}
        if payload.assignee_ids is None:
            return [
                member
                for member in active_members
                if not payload.exclude_creator or member.user_id != payload.created_by_user_id
            ]

        assignee_members: list[ChatMember] = []
        for user_id in payload.assignee_ids:
            member = active_member_by_user_id.get(user_id)
            if member is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="assignee_not_in_chat",
                )
            if payload.exclude_creator and user_id == payload.created_by_user_id:
                continue
            assignee_members.append(member)
        return assignee_members

    def _send_group_assignment_chat_summary(
        self,
        *,
        chat: Chat,
        task: Task,
        title: str,
        deadline_at: datetime | None,
        assignee_members: list[ChatMember],
        response_required: bool,
    ) -> None:
        if self.sender is None:
            return
        max_chat_id = _max_chat_id(chat)
        if max_chat_id is None:
            return
        message = _format_group_assignment_chat_summary(
            task=task,
            title=title,
            deadline_at=deadline_at,
            assignee_members=assignee_members,
            response_required=response_required,
        )
        button_rows: list[list[dict[str, object]]] = []
        if self.group_assignment_webapp_url:
            button_rows.append(
                [
                    {
                        "type": "link",
                        "text": "Открыть Дьяк",
                        "url": self.group_assignment_webapp_url,
                    }
                ]
            )
        if button_rows:
            outbound = self.sender.send_inline_keyboard_message(
                chat_id=max_chat_id,
                text=message,
                button_rows=button_rows,
                purpose=OutboundPurpose.INTERACTIVE,
            )
        else:
            outbound = self.sender.send_message(
                chat_id=max_chat_id,
                text=message,
                purpose=OutboundPurpose.INTERACTIVE,
                reminder_type=GROUP_ASSIGNMENT_CHAT_NOTIFICATION_TYPE,
            )
        if not outbound.sent:
            logger.info(
                "Group assignment chat summary was not sent",
                extra={
                    "task_number": getattr(task, "task_number", None),
                    "reason": _safe_sender_reason(outbound.reason),
                },
            )

    def _ensure_group_report_allowed(self, task: Task, auth_context: AuthContext) -> None:
        if auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN):
            return
        if auth_context.user_id == task.created_by_user_id:
            return
        if not auth_context.has_any_role(GROUP_ASSIGNMENT_ROLES):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Group report requires creator, chat_admin or super_admin role",
            )
        if auth_context.chat_id is not None and auth_context.chat_id != task.chat_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Group report chat scope mismatch",
            )
        if auth_context.organization_id is not None and auth_context.organization_id != task.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Group report organization scope mismatch",
            )
        if auth_context.chat_id is None and auth_context.organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Group report requires chat or organization scope",
            )

    def _find_chat_member(
        self,
        members: list[ChatMember],
        user_id: UUID,
    ) -> ChatMember | None:
        return next((member for member in members if member.user_id == user_id), None)

    def _creator_role_snapshot(
        self,
        auth_context: AuthContext,
        creator_member: ChatMember | None,
    ) -> str | None:
        if creator_member is not None:
            return creator_member.role
        if auth_context.is_super_admin:
            return ROLE_SUPER_ADMIN
        role_values = auth_context.role_values
        for role in (ROLE_CHAT_ADMIN,):
            if role in role_values:
                return role
        return None

    def _group_assignment_audience_snapshot(
        self,
        *,
        chat_id: UUID,
        chat_title: str,
        active_members: list[ChatMember],
        assignee_members: list[ChatMember],
        exclude_creator: bool,
        response_required: bool,
    ) -> dict[str, object]:
        return {
            "source": "chat_members",
            "chat_id": str(chat_id),
            "chat_title": chat_title,
            "exclude_creator": exclude_creator,
            "response_required": response_required,
            "active_member_count": len(active_members),
            "total_assignees": len(assignee_members),
            "assignee_ids": [str(member.user_id) for member in assignee_members],
        }

    def _latest_responses_by_user(self, responses: list[TaskResponse]) -> dict[UUID, TaskResponse]:
        latest: dict[UUID, TaskResponse] = {}
        for response in sorted(
            responses,
            key=lambda item: getattr(item, "created_at", datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        ):
            latest.setdefault(response.user_id, response)
        return latest

    def _assignee_has_responded(
        self,
        assignee: TaskAssignee,
        response: TaskResponse | None,
    ) -> bool:
        return (
            assignee.responded_at is not None
            or assignee.status
            in {
                TaskAssigneeStatus.RESPONDED.value,
                TaskAssigneeStatus.COMPLETED.value,
            }
            or response is not None
        )

    def _is_group_report_item_overdue(self, task: Task, now: datetime) -> bool:
        return (
            task.deadline_at is not None
            and task.deadline_at < now
            and task.status not in {TaskStatus.DONE.value, TaskStatus.CANCELLED.value}
        )

    def _user_display_name(self, user: object | None, user_id: UUID) -> str:
        display_name = getattr(user, "display_name", None)
        if display_name:
            return display_name
        username = getattr(user, "username", None)
        if username:
            return str(username)
        return f"Пользователь #{str(user_id)[-8:]}"

    async def _validate_task_relations(self, payload: TaskCreate) -> Chat:
        await self._ensure_organization_exists(payload.organization_id)

        chat = await self.repository.get_chat(payload.chat_id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found",
            )
        if chat.organization_id != payload.organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chat does not belong to organization",
            )

        required_user_ids = {
            payload.created_by_user_id,
            *payload.assignee_ids,
            *payload.observer_ids,
        }
        existing_user_ids = await self.repository.existing_user_ids(required_user_ids)
        missing_user_ids = required_user_ids - existing_user_ids
        if missing_user_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return chat

    async def _ensure_organization_exists(self, organization_id: UUID) -> None:
        if not await self.repository.organization_exists(organization_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

    async def _ensure_users_exist(self, user_ids: set[UUID]) -> None:
        existing_user_ids = await self.repository.existing_user_ids(user_ids)
        missing_user_ids = user_ids - existing_user_ids
        if missing_user_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    async def _ensure_reply_comment_belongs_to_task(
        self,
        *,
        task_id: UUID,
        comment_id: UUID,
    ) -> None:
        comment = await self.repository.get_comment(comment_id)
        if comment is None or comment.task_id != task_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reply comment not found",
            )

    def _normalize_update_values(self, payload: TaskUpdate) -> dict[str, object]:
        values = payload.model_dump(exclude_unset=True)
        if "priority" in values:
            values["priority"] = values["priority"].value
        if "completion_rule" in values:
            values["completion_rule"] = values["completion_rule"].value
        if "status" in values:
            values["status"] = values["status"].value
        if "deadline_at" in values:
            values["deadline_at"] = as_aware_utc(values["deadline_at"])
        return values

    def _ensure_deadline_in_future(self, deadline_at: object) -> None:
        if deadline_at is None:
            return
        if not isinstance(deadline_at, datetime):
            return
        if not is_future_task_deadline(deadline_at):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=DEADLINE_MUST_BE_IN_FUTURE_DETAIL,
            )

    def _find_assignee(self, task: Task, user_id: UUID) -> TaskAssignee | None:
        return next((assignee for assignee in task.assignees if assignee.user_id == user_id), None)

    def _find_response(self, task: Task, response_id: UUID) -> TaskResponse | None:
        return next((response for response in task.responses if response.id == response_id), None)

    def _ensure_response_can_be_decided(self, response: TaskResponse) -> None:
        if response.status != TaskResponseStatus.SUBMITTED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task response already decided",
            )

    def _ensure_creator_can_accept(self, task: Task, accepted_by_user_id: UUID) -> None:
        if accepted_by_user_id != task.created_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only task creator, chat_admin or super_admin can accept or reject response",
            )

    def _ensure_can_accept_response(
        self,
        task: Task,
        accepted_by_user_id: UUID,
        *,
        auth_context: AuthContext | None,
    ) -> None:
        if auth_context is None:
            self._ensure_creator_can_accept(task, accepted_by_user_id)
            return
        if auth_context.user_id != accepted_by_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accepted-by user must match authenticated user",
            )
        if auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN):
            return
        if accepted_by_user_id == task.created_by_user_id:
            return
        if auth_context.has_any_role(GROUP_ASSIGNMENT_ROLES) and self._same_id(auth_context.chat_id, task.chat_id):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only task creator, chat_admin or super_admin can accept or reject response",
        )

    def _same_id(self, left: UUID | None, right: UUID | None) -> bool:
        if left is None or right is None:
            return False
        return str(left) == str(right)

    async def _apply_completion_rule_after_response(
        self,
        task: Task,
        *,
        changed_by_user_id: UUID,
    ) -> None:
        new_status = None
        if task.completion_rule == TaskCompletionRule.ANY_ASSIGNEE_RESPONSE.value:
            new_status = TaskStatus.WAITING_ACCEPTANCE.value
        elif task.completion_rule == TaskCompletionRule.ALL_ASSIGNEES_RESPONSE.value:
            if all(assignee.status == TaskAssigneeStatus.RESPONDED.value for assignee in task.assignees):
                new_status = TaskStatus.WAITING_ACCEPTANCE.value
        elif task.completion_rule == TaskCompletionRule.MANUAL_SUBMIT.value:
            # TODO: define manual submit transition when the MVP acceptance flow is finalized.
            return

        if new_status is not None and task.status != new_status:
            old_status = task.status
            await self.repository.update_task(task, values={"status": new_status})
            await self.repository.create_status_history(
                task_id=task.id,
                old_status=old_status,
                new_status=new_status,
                changed_by_user_id=changed_by_user_id,
            )


def _format_group_assignment_chat_summary(
    *,
    task: Task,
    title: str,
    deadline_at: datetime | None,
    assignee_members: list[ChatMember],
    response_required: bool,
) -> str:
    task_number = getattr(task, "task_number", None)
    task_ref = f"#{task_number}" if task_number is not None else "создана"
    return "\n".join(
        [
            "Задача участникам чата создана ✅",
            "",
            f"Текст: {_safe_message_line(title)}",
            f"Исполнители: {_format_assignee_names(assignee_members)}",
            f"Срок: {_format_project_deadline(deadline_at)}",
            f"Отчет: {'обязателен' if response_required else 'не требуется'}",
            "",
            f"Задача: {task_ref}",
        ]
    )


def _format_assignee_names(members: list[ChatMember]) -> str:
    names: list[str] = []
    for member in members:
        user = getattr(member, "user", None)
        display_name = getattr(user, "display_name", None)
        if isinstance(display_name, str) and display_name.strip():
            names.append(display_name.strip())
        else:
            names.append("Участник")
    return ", ".join(names) if names else "Не указаны"


def _format_project_deadline(deadline_at: datetime | None) -> str:
    if deadline_at is None:
        return "Без срока"
    value = deadline_at if deadline_at.tzinfo is not None else deadline_at.replace(tzinfo=timezone.utc)
    return value.astimezone(PROJECT_TIMEZONE).strftime("%d.%m.%Y %H:%M")


def _safe_message_line(value: str) -> str:
    return " ".join(value.strip().split())


def _chat_display_title(chat: Chat) -> str:
    display_title = getattr(chat, "display_title", None)
    if not display_title:
        settings = getattr(chat, "settings", None)
        if isinstance(settings, dict):
            value = settings.get("display_title")
            if isinstance(value, str) and value.strip():
                display_title = value.strip()
    if display_title:
        return display_title
    title = (getattr(chat, "title", "") or "").strip()
    if title and not _is_generated_chat_title(title):
        return title
    if "dialog" in (getattr(chat, "type", "") or "").lower():
        return "Личный чат"
    return "Чат без названия"


def _is_generated_chat_title(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        normalized.startswith("max chat #")
        or normalized.startswith("max dialog #")
        or normalized.startswith("max group #")
        or normalized in {"чат без названия", "личный чат", "групповой чат"}
        or _looks_like_identifier(value)
    )


def _looks_like_identifier(value: str) -> bool:
    normalized = value.strip()
    return bool(
        re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}", normalized)
        or re.fullmatch(r"-?\d{6,}", normalized)
    )


def _max_chat_id(chat: Chat) -> str | None:
    value = getattr(chat, "max_chat_id", None)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _safe_sender_reason(value: str | None) -> str | None:
    if value is None:
        return None
    token_pattern = r"(" + "token" + r"=)[^&\s]+"
    password_pattern = r"(" + "password" + r"=)[^&\s]+"
    sanitized = re.sub(token_pattern, r"\1***", value, flags=re.IGNORECASE)
    sanitized = re.sub(password_pattern, r"\1***", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"(webhook/)[A-Za-z0-9_-]+", r"\1***", sanitized, flags=re.IGNORECASE)
    return sanitized[:255]
