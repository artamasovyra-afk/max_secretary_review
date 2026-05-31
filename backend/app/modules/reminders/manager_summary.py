from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, time, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN
from app.modules.chats.models import Chat, ChatMember
from app.modules.tasks.enums import TaskStatus
from app.modules.tasks.models import Task

ADMIN_SUMMARY_ROLES = frozenset({ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN})
SUMMARY_ITEM_LIMIT = 5
TERMINAL_TASK_STATUSES = frozenset({TaskStatus.DONE.value, TaskStatus.CANCELLED.value})


class DailyManagerSummaryForbidden(PermissionError):
    """Raised when a user is not allowed to build daily admin summaries."""


@dataclass(frozen=True)
class DailyManagerSummaryItem:
    task_id: UUID
    title: str
    status: str
    deadline_at: datetime | None
    chat_id: UUID
    created_by_user_id: UUID
    assignee_ids: tuple[UUID, ...]
    assignee_count: int


@dataclass(frozen=True)
class DailyManagerSummary:
    manager_user_id: UUID
    date: Date
    chat_id: UUID | None
    total_today: int
    overdue: int
    waiting_response: int
    waiting_acceptance: int
    top_overdue_items: tuple[DailyManagerSummaryItem, ...]
    pending_acceptance_items: tuple[DailyManagerSummaryItem, ...]


class DailyManagerSummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_chats_for_daily_manager_summary(self) -> list[Chat]:
        result = await self.session.scalars(
            select(Chat)
            .options(selectinload(Chat.members))
            .order_by(Chat.created_at.desc())
        )
        return list(result.unique())

    async def list_tasks_for_chat(self, *, chat_id: UUID, summary_date: Date) -> list[Task]:
        _ = summary_date
        result = await self.session.scalars(
            self._base_query()
            .where(Task.chat_id == chat_id)
            .order_by(Task.created_at.desc())
        )
        return list(result.unique())

    async def list_tasks_for_manager(
        self,
        *,
        manager_user_id: UUID,
        summary_date: Date,
        include_all: bool = False,
    ) -> list[Task]:
        _ = summary_date
        query = self._base_query().order_by(Task.created_at.desc())
        if not include_all:
            managed_chat_ids = (
                select(ChatMember.chat_id)
                .where(
                    ChatMember.user_id == manager_user_id,
                    ChatMember.is_active.is_(True),
                    ChatMember.role == ROLE_CHAT_ADMIN,
                )
                .scalar_subquery()
            )
            query = query.where(
                or_(
                    Task.created_by_user_id == manager_user_id,
                    Task.chat_id.in_(managed_chat_ids),
                )
            )

        result = await self.session.scalars(query)
        return list(result.unique())

    def _base_query(self):
        return select(Task).options(
            selectinload(Task.assignees),
            selectinload(Task.observers),
        )


class DailyManagerSummaryService:
    def __init__(
        self,
        *,
        repository: DailyManagerSummaryRepository,
        auth_context: AuthContext,
    ) -> None:
        self.repository = repository
        self.auth_context = auth_context

    async def build_summary_for_chat(
        self,
        chat_id: UUID,
        manager_user_id: UUID,
        date: Date,
    ) -> DailyManagerSummary:
        self._authorize(manager_user_id=manager_user_id, chat_id=chat_id)
        tasks = await self.repository.list_tasks_for_chat(chat_id=chat_id, summary_date=date)
        return self._build_summary(
            tasks=tasks,
            manager_user_id=manager_user_id,
            summary_date=date,
            chat_id=chat_id,
        )

    async def build_summary_for_manager(
        self,
        manager_user_id: UUID,
        date: Date,
    ) -> DailyManagerSummary:
        self._authorize(manager_user_id=manager_user_id)
        tasks = await self.repository.list_tasks_for_manager(
            manager_user_id=manager_user_id,
            summary_date=date,
            include_all=self._is_super_admin(),
        )
        return self._build_summary(
            tasks=tasks,
            manager_user_id=manager_user_id,
            summary_date=date,
            chat_id=None,
        )

    def _authorize(self, *, manager_user_id: UUID, chat_id: UUID | None = None) -> None:
        if not self.auth_context.has_any_role(ADMIN_SUMMARY_ROLES) and not self.auth_context.is_super_admin:
            raise DailyManagerSummaryForbidden("Daily summary requires chat_admin or super_admin role.")
        if not self._is_super_admin() and self.auth_context.user_id != manager_user_id:
            raise DailyManagerSummaryForbidden("Chat admins can build only their own summary.")
        if chat_id is not None and self.auth_context.chat_id is not None and self.auth_context.chat_id != chat_id:
            raise DailyManagerSummaryForbidden("Daily summary chat scope mismatch.")

    def _build_summary(
        self,
        *,
        tasks: list[Any],
        manager_user_id: UUID,
        summary_date: Date,
        chat_id: UUID | None,
    ) -> DailyManagerSummary:
        today_start, today_end = _date_bounds(summary_date)
        total_today_tasks = [task for task in tasks if _is_due_today(task, today_start, today_end)]
        overdue_tasks = [task for task in tasks if _is_overdue(task, today_start)]
        waiting_response_tasks = [
            task for task in tasks if _task_status(task) == TaskStatus.WAITING_RESPONSE.value
        ]
        waiting_acceptance_tasks = [
            task for task in tasks if _task_status(task) == TaskStatus.WAITING_ACCEPTANCE.value
        ]

        return DailyManagerSummary(
            manager_user_id=manager_user_id,
            date=summary_date,
            chat_id=chat_id,
            total_today=len(total_today_tasks),
            overdue=len(overdue_tasks),
            waiting_response=len(waiting_response_tasks),
            waiting_acceptance=len(waiting_acceptance_tasks),
            top_overdue_items=tuple(
                _to_summary_item(task)
                for task in sorted(overdue_tasks, key=_deadline_sort_key)[:SUMMARY_ITEM_LIMIT]
            ),
            pending_acceptance_items=tuple(
                _to_summary_item(task)
                for task in sorted(waiting_acceptance_tasks, key=_deadline_sort_key)[:SUMMARY_ITEM_LIMIT]
            ),
        )

    def _is_super_admin(self) -> bool:
        return self.auth_context.is_super_admin or self.auth_context.has_role(ROLE_SUPER_ADMIN)


def _date_bounds(summary_date: Date) -> tuple[datetime, datetime]:
    start = datetime.combine(summary_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(summary_date, time.max, tzinfo=timezone.utc)
    return start, end


def _is_due_today(task: Any, today_start: datetime, today_end: datetime) -> bool:
    deadline = _deadline(task)
    if deadline is None:
        return False
    return today_start <= deadline <= today_end


def _is_overdue(task: Any, today_start: datetime) -> bool:
    status = _task_status(task)
    if status in TERMINAL_TASK_STATUSES:
        return False
    if status == TaskStatus.OVERDUE.value:
        return True
    deadline = _deadline(task)
    return deadline is not None and deadline < today_start


def _to_summary_item(task: Any) -> DailyManagerSummaryItem:
    assignee_ids = tuple(_assignee_ids(task))
    return DailyManagerSummaryItem(
        task_id=_task_id(task),
        title=str(getattr(task, "title", "")),
        status=_task_status(task),
        deadline_at=_deadline(task),
        chat_id=getattr(task, "chat_id"),
        created_by_user_id=getattr(task, "created_by_user_id"),
        assignee_ids=assignee_ids,
        assignee_count=len(assignee_ids),
    )


def _task_id(task: Any) -> UUID:
    task_id = getattr(task, "id", None) or getattr(task, "task_id")
    return task_id


def _task_status(task: Any) -> str:
    status = getattr(task, "status")
    return str(getattr(status, "value", status))


def _deadline(task: Any) -> datetime | None:
    value = getattr(task, "deadline_at", None)
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _assignee_ids(task: Any) -> list[UUID]:
    return [assignee.user_id for assignee in getattr(task, "assignees", [])]


def _deadline_sort_key(task: Any) -> tuple[int, datetime]:
    deadline = _deadline(task)
    if deadline is None:
        return (1, datetime.max.replace(tzinfo=timezone.utc))
    return (0, deadline)
