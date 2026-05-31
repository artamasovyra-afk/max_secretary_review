from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_auth_context
from app.core.config import get_settings
from app.db.session import get_session
from app.modules.auth.context import AuthContext
from app.modules.auth.policy import PolicyService, ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN
from app.modules.integrations.max.deep_links import build_max_webapp_deep_link
from app.modules.notifications.max_sender_factory import build_max_sender
from app.modules.reminders.repository import ReminderRepository
from app.modules.reminders.schemas import ReminderRuleCreate, ReminderRuleRead, ReminderRuleUpdate
from app.modules.reminders.service import ReminderService
from app.modules.tasks.enums import TaskStatus as TaskLifecycleStatus, TaskType
from app.modules.tasks.deadline_parser import (
    DEADLINE_MUST_BE_IN_FUTURE_DETAIL,
    is_future_task_deadline,
    local_day_bounds_utc,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    TaskCreate,
    TaskAcceptanceCreate,
    TaskAcceptanceRead,
    TaskAssigneeRead,
    TaskCommentCreate,
    TaskCommentRead,
    TaskDetailRead,
    TaskFileCreate,
    TaskFileRead,
    TaskGroupAssignmentCreate,
    TaskGroupAssignmentCreateRead,
    TaskGroupReportRead,
    TaskInboxSummaryFilters,
    TaskInboxSummaryRead,
    TaskListFilters,
    TaskListScope,
    TaskObserverRead,
    TaskParticipantRole,
    TaskParticipantCreate,
    TaskQuickStatus,
    TaskRead,
    TaskResponseCreate,
    TaskResponseRead,
    TaskStatus,
    TaskUpdate,
)
from app.modules.tasks.service import TaskService

router = APIRouter(tags=["tasks"], dependencies=[Depends(get_auth_context)])
GROUP_ASSIGNMENT_API_ROLES = frozenset({ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN})
policy_service = PolicyService()


def get_task_service(
    session: AsyncSession = Depends(get_session),
) -> TaskService:
    settings = get_settings()
    return TaskService(
        repository=TaskRepository(session),
        session=session,
        sender=build_max_sender(settings),
        group_assignment_webapp_url=build_max_webapp_deep_link(
            bot_username=settings.max_bot_username,
            webapp_base_url=settings.webapp_base_url,
            startapp="group_assignment",
            fallback_path="group-assignments",
        ),
    )


def get_reminder_service(
    session: AsyncSession = Depends(get_session),
) -> ReminderService:
    return ReminderService(
        repository=ReminderRepository(session),
        session=session,
    )


@router.get("/status", response_model=TaskStatus)
def tasks_status() -> TaskStatus:
    return TaskStatus(status="ok", module="tasks")


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    _ensure_task_create_allowed(payload, auth_context)
    _ensure_deadline_in_future(payload.deadline_at)
    return await service.create(payload)


@router.post(
    "/group-assignment",
    response_model=TaskGroupAssignmentCreateRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_group_assignment(
    payload: TaskGroupAssignmentCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskGroupAssignmentCreateRead:
    if not (auth_context.is_super_admin or auth_context.has_any_role(GROUP_ASSIGNMENT_API_ROLES)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient_permissions",
        )
    _ensure_group_assignment_deadline_present(payload.deadline_at)
    _ensure_deadline_in_future(payload.deadline_at)
    return await service.create_group_assignment(payload, auth_context)


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    organization_id: Optional[UUID] = None,
    chat_id: Optional[UUID] = None,
    task_status: Optional[TaskLifecycleStatus] = Query(default=None, alias="status"),
    task_type: Optional[TaskType] = None,
    scope: TaskListScope = Query(default=TaskListScope.ALL),
    quick_status: Optional[TaskQuickStatus] = None,
    search: Optional[str] = None,
    task_number: Optional[int] = Query(default=None, ge=1),
    participant_role: Optional[TaskParticipantRole] = None,
    participant_user_id: Optional[UUID] = None,
    created_by_user_id: Optional[UUID] = None,
    assignee_id: Optional[UUID] = None,
    observer_id: Optional[UUID] = None,
    overdue: Optional[bool] = None,
    due_today: Optional[bool] = None,
    deadline_from: Optional[datetime] = None,
    deadline_to: Optional[datetime] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> list[TaskRead]:
    now = datetime.now(timezone.utc)
    today_start, today_end = local_day_bounds_utc(now)
    _ensure_participant_filter_pair(participant_role, participant_user_id)
    filters = TaskListFilters(
        organization_id=organization_id,
        chat_id=chat_id,
        status=task_status,
        task_type=task_type,
        scope=scope,
        quick_status=quick_status,
        viewer_user_id=auth_context.user_id,
        search=search,
        task_number=task_number,
        participant_role=participant_role,
        participant_user_id=participant_user_id,
        created_by_user_id=created_by_user_id,
        assignee_id=assignee_id,
        observer_id=observer_id,
        overdue=overdue,
        due_today=due_today,
        now=now,
        today_from=today_start,
        today_to=today_end,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
    )
    tasks = await service.list(filters=filters, limit=limit, offset=offset)
    return [task for task in tasks if policy_service.can_view_task(auth_context, task)]


@router.get("/inbox/summary", response_model=TaskInboxSummaryRead)
async def get_task_inbox_summary(
    user_id: Optional[UUID] = None,
    organization_id: Optional[UUID] = None,
    chat_id: Optional[UUID] = None,
    task_status: Optional[TaskLifecycleStatus] = Query(default=None, alias="status"),
    deadline_from: Optional[datetime] = None,
    deadline_to: Optional[datetime] = None,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskInboxSummaryRead:
    summary_user_id = user_id or auth_context.user_id
    if user_id is not None:
        _ensure_user_matches_context(auth_context, user_id, detail="Inbox summary user must match authenticated user")
    filters = TaskInboxSummaryFilters(
        user_id=summary_user_id,
        organization_id=organization_id,
        chat_id=chat_id,
        status=task_status,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
    )
    return await service.inbox_summary(filters)


@router.get("/{task_id}", response_model=TaskDetailRead)
async def get_task(
    task_id: UUID,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskDetailRead:
    task = await service.get(task_id)
    _ensure_can_view_task(auth_context, task)
    return task


@router.get("/{task_id}/group-report", response_model=TaskGroupReportRead)
async def get_group_assignment_report(
    task_id: UUID,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskGroupReportRead:
    return await service.get_group_report(task_id, auth_context)


@router.patch("/{task_id}", response_model=TaskDetailRead)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskDetailRead:
    task = await service.get(task_id)
    _ensure_can_update_task(auth_context, task)
    if "deadline_at" in payload.model_fields_set:
        _ensure_deadline_in_future(payload.deadline_at)
    return await service.update(task_id, payload)


@router.post("/{task_id}/cancel", response_model=TaskDetailRead)
async def cancel_task(
    task_id: UUID,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskDetailRead:
    task = await service.get(task_id)
    _ensure_can_update_task(auth_context, task)
    return await service.cancel(task_id)


@router.post(
    "/{task_id}/reminder-rules",
    response_model=ReminderRuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_reminder_rule(
    task_id: UUID,
    payload: ReminderRuleCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    task_service: TaskService = Depends(get_task_service),
    service: ReminderService = Depends(get_reminder_service),
) -> ReminderRuleRead:
    task = await task_service.get(task_id)
    _ensure_can_update_task(auth_context, task)
    return await service.create_task_rule(task_id, payload)


@router.get("/{task_id}/reminder-rules", response_model=list[ReminderRuleRead])
async def list_task_reminder_rules(
    task_id: UUID,
    auth_context: AuthContext = Depends(get_auth_context),
    task_service: TaskService = Depends(get_task_service),
    service: ReminderService = Depends(get_reminder_service),
) -> list[ReminderRuleRead]:
    task = await task_service.get(task_id)
    _ensure_can_view_task(auth_context, task)
    return await service.list_task_rules(task_id)


@router.patch(
    "/{task_id}/reminder-rules/{rule_id}",
    response_model=ReminderRuleRead,
)
async def update_task_reminder_rule(
    task_id: UUID,
    rule_id: UUID,
    payload: ReminderRuleUpdate,
    auth_context: AuthContext = Depends(get_auth_context),
    task_service: TaskService = Depends(get_task_service),
    service: ReminderService = Depends(get_reminder_service),
) -> ReminderRuleRead:
    task = await task_service.get(task_id)
    _ensure_can_update_task(auth_context, task)
    return await service.update_task_rule(
        task_id=task_id,
        rule_id=rule_id,
        payload=payload,
    )


@router.delete(
    "/{task_id}/reminder-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_task_reminder_rule(
    task_id: UUID,
    rule_id: UUID,
    auth_context: AuthContext = Depends(get_auth_context),
    task_service: TaskService = Depends(get_task_service),
    service: ReminderService = Depends(get_reminder_service),
) -> Response:
    task = await task_service.get(task_id)
    _ensure_can_update_task(auth_context, task)
    await service.delete_task_rule(task_id=task_id, rule_id=rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{task_id}/assignees",
    response_model=TaskAssigneeRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_task_assignee(
    task_id: UUID,
    payload: TaskParticipantCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskAssigneeRead:
    task = await service.get(task_id)
    _ensure_can_manage_task_participants(auth_context, task)
    return await service.add_assignee(task_id, payload)


@router.delete(
    "/{task_id}/assignees/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_task_assignee(
    task_id: UUID,
    user_id: UUID,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> Response:
    task = await service.get(task_id)
    _ensure_can_manage_task_participants(auth_context, task)
    await service.remove_assignee(task_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{task_id}/observers",
    response_model=TaskObserverRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_task_observer(
    task_id: UUID,
    payload: TaskParticipantCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskObserverRead:
    task = await service.get(task_id)
    _ensure_can_manage_task_participants(auth_context, task)
    return await service.add_observer(task_id, payload)


@router.delete(
    "/{task_id}/observers/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_task_observer(
    task_id: UUID,
    user_id: UUID,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> Response:
    task = await service.get(task_id)
    _ensure_can_manage_task_participants(auth_context, task)
    await service.remove_observer(task_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{task_id}/comments",
    response_model=TaskCommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_task_comment(
    task_id: UUID,
    payload: TaskCommentCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskCommentRead:
    task = await service.get(task_id)
    _ensure_can_view_task(auth_context, task)
    _ensure_user_matches_context(auth_context, payload.user_id, detail="Comment user must match authenticated user")
    return await service.add_comment(task_id, payload)


@router.get("/{task_id}/comments", response_model=list[TaskCommentRead])
async def list_task_comments(
    task_id: UUID,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> list[TaskCommentRead]:
    task = await service.get(task_id)
    _ensure_can_view_task(auth_context, task)
    return await service.list_comments(task_id)


@router.post(
    "/{task_id}/files",
    response_model=TaskFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_task_file(
    task_id: UUID,
    payload: TaskFileCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskFileRead:
    task = await service.get(task_id)
    _ensure_can_view_task(auth_context, task)
    _ensure_user_matches_context(
        auth_context,
        payload.uploaded_by_user_id,
        detail="File uploader must match authenticated user",
    )
    return await service.add_file(task_id, payload)


@router.get("/{task_id}/files", response_model=list[TaskFileRead])
async def list_task_files(
    task_id: UUID,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> list[TaskFileRead]:
    task = await service.get(task_id)
    _ensure_can_view_task(auth_context, task)
    return await service.list_files(task_id)


@router.post(
    "/{task_id}/responses",
    response_model=TaskResponseRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_task_response(
    task_id: UUID,
    payload: TaskResponseCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskResponseRead:
    task = await service.get(task_id)
    _ensure_user_matches_context(auth_context, payload.user_id, detail="Response user must match authenticated user")
    if not policy_service.can_submit_response(auth_context, task):
        raise _forbidden("Only task assignee can submit response")
    return await service.submit_response(task_id, payload)


@router.post(
    "/{task_id}/responses/{response_id}/accept",
    response_model=TaskAcceptanceRead,
    status_code=status.HTTP_201_CREATED,
)
async def accept_task_response(
    task_id: UUID,
    response_id: UUID,
    payload: TaskAcceptanceCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskAcceptanceRead:
    task = await service.get(task_id)
    _ensure_user_matches_context(
        auth_context,
        payload.accepted_by_user_id,
        detail="Accepted-by user must match authenticated user",
    )
    if not policy_service.can_accept_task(auth_context, task):
        raise _forbidden("Only task creator, chat_admin or super_admin can accept or reject response")
    return await service.accept_response(task_id, response_id, payload, auth_context=auth_context)


@router.post(
    "/{task_id}/responses/{response_id}/reject",
    response_model=TaskAcceptanceRead,
    status_code=status.HTTP_201_CREATED,
)
async def reject_task_response(
    task_id: UUID,
    response_id: UUID,
    payload: TaskAcceptanceCreate,
    auth_context: AuthContext = Depends(get_auth_context),
    service: TaskService = Depends(get_task_service),
) -> TaskAcceptanceRead:
    task = await service.get(task_id)
    _ensure_user_matches_context(
        auth_context,
        payload.accepted_by_user_id,
        detail="Accepted-by user must match authenticated user",
    )
    if not policy_service.can_reject_task(auth_context, task):
        raise _forbidden("Only task creator, chat_admin or super_admin can accept or reject response")
    return await service.reject_response(task_id, response_id, payload, auth_context=auth_context)


def _is_super_admin(auth_context: AuthContext) -> bool:
    return auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN)


def _ensure_task_create_allowed(payload: TaskCreate, auth_context: AuthContext) -> None:
    if _is_super_admin(auth_context):
        return
    if payload.created_by_user_id != auth_context.user_id:
        raise _forbidden("Task creator must match authenticated user")
    if auth_context.chat_id is not None and auth_context.chat_id != payload.chat_id:
        raise _forbidden("Task chat scope mismatch")
    if auth_context.organization_id is not None and auth_context.organization_id != payload.organization_id:
        raise _forbidden("Task organization scope mismatch")
    if auth_context.has_role(ROLE_CHAT_ADMIN):
        return
    if payload.assignee_ids != [auth_context.user_id]:
        raise _forbidden("Member can create tasks only for self")
    if payload.observer_ids:
        raise _forbidden("Member cannot add task observers")


def _ensure_deadline_in_future(deadline_at: datetime | None) -> None:
    if deadline_at is None:
        return
    if not is_future_task_deadline(deadline_at):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=DEADLINE_MUST_BE_IN_FUTURE_DETAIL,
        )


def _ensure_group_assignment_deadline_present(deadline_at: datetime | None) -> None:
    if deadline_at is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="deadline_required",
        )


def _ensure_can_view_task(auth_context: AuthContext, task: object) -> None:
    if not policy_service.can_view_task(auth_context, task):
        raise _forbidden("Not enough permissions to view task")


def _ensure_can_update_task(auth_context: AuthContext, task: object) -> None:
    if not policy_service.can_update_task(auth_context, task):
        raise _forbidden("Not enough permissions to update task")


def _ensure_can_manage_task_participants(auth_context: AuthContext, task: object) -> None:
    if _is_super_admin(auth_context):
        return
    if not auth_context.has_role(ROLE_CHAT_ADMIN):
        raise _forbidden("Task participant changes require chat_admin or super_admin role")
    _ensure_can_update_task(auth_context, task)


def _ensure_user_matches_context(auth_context: AuthContext, user_id: UUID, *, detail: str) -> None:
    if _is_super_admin(auth_context) or auth_context.user_id == user_id:
        return
    raise _forbidden(detail)


def _ensure_participant_filter_pair(
    participant_role: TaskParticipantRole | None,
    participant_user_id: UUID | None,
) -> None:
    if (participant_role is None) == (participant_user_id is None):
        return
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="participant_role and participant_user_id must be provided together",
    )


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
