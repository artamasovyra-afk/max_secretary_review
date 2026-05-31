from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.chats.models import Chat
from app.modules.organizations.models import Organization
from app.modules.tasks.models import ScheduledTask, ScheduledTaskRun, TaskTemplate
from app.modules.users.models import User


class ScheduledTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def organization_exists(self, organization_id: UUID) -> bool:
        return await self.session.get(Organization, organization_id) is not None

    async def get_chat(self, chat_id: UUID) -> Optional[Chat]:
        return await self.session.get(Chat, chat_id)

    async def user_exists(self, user_id: UUID) -> bool:
        return await self.session.get(User, user_id) is not None

    async def get_template(self, template_id: UUID) -> Optional[TaskTemplate]:
        return await self.session.get(TaskTemplate, template_id)

    async def create_scheduled_task(
        self,
        *,
        template_id: UUID,
        organization_id: UUID,
        chat_id: UUID,
        created_by_user_id: UUID,
        schedule_type: str,
        scheduled_for: Optional[datetime],
        repeat_rule: Optional[dict[str, Any]],
        timezone: str,
        next_run_at: datetime,
        is_active: bool,
    ) -> ScheduledTask:
        scheduled_task = ScheduledTask(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=created_by_user_id,
            schedule_type=schedule_type,
            scheduled_for=scheduled_for,
            repeat_rule=repeat_rule,
            timezone=timezone,
            next_run_at=next_run_at,
            is_active=is_active,
        )
        self.session.add(scheduled_task)
        await self.session.flush()
        return scheduled_task

    async def list_scheduled_tasks(
        self,
        *,
        organization_id: UUID | None = None,
        chat_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
        is_active: bool | None = True,
    ) -> list[ScheduledTask]:
        query = select(ScheduledTask).order_by(ScheduledTask.created_at.desc())
        if organization_id is not None:
            query = query.where(ScheduledTask.organization_id == organization_id)
        if chat_id is not None:
            query = query.where(ScheduledTask.chat_id == chat_id)
        if created_by_user_id is not None:
            query = query.where(ScheduledTask.created_by_user_id == created_by_user_id)
        if is_active is not None:
            query = query.where(ScheduledTask.is_active == is_active)
        result = await self.session.scalars(query)
        return list(result)

    async def get_scheduled_task(self, scheduled_task_id: UUID) -> Optional[ScheduledTask]:
        return await self.session.get(ScheduledTask, scheduled_task_id)

    async def update_scheduled_task(
        self,
        scheduled_task: ScheduledTask,
        *,
        values: Mapping[str, Any],
    ) -> ScheduledTask:
        for field_name in (
            "template_id",
            "organization_id",
            "chat_id",
            "created_by_user_id",
            "schedule_type",
            "scheduled_for",
            "repeat_rule",
            "timezone",
            "next_run_at",
            "last_run_at",
            "is_active",
            "last_error",
        ):
            if field_name in values:
                setattr(scheduled_task, field_name, values[field_name])
        await self.session.flush()
        return scheduled_task

    async def get_scheduled_task_run(
        self,
        *,
        scheduled_task_id: UUID,
        planned_run_at: datetime,
    ) -> Optional[ScheduledTaskRun]:
        query = (
            select(ScheduledTaskRun)
            .where(
                ScheduledTaskRun.scheduled_task_id == scheduled_task_id,
                ScheduledTaskRun.planned_run_at == planned_run_at,
            )
            .with_for_update()
        )
        return await self.session.scalar(query)

    async def create_scheduled_task_run(
        self,
        *,
        scheduled_task_id: UUID,
        planned_run_at: datetime,
        status: str,
        started_at: datetime,
    ) -> ScheduledTaskRun:
        scheduled_task_run = ScheduledTaskRun(
            scheduled_task_id=scheduled_task_id,
            planned_run_at=planned_run_at,
            status=status,
            started_at=started_at,
        )
        self.session.add(scheduled_task_run)
        await self.session.flush()
        return scheduled_task_run

    async def update_scheduled_task_run(
        self,
        scheduled_task_run: ScheduledTaskRun,
        *,
        values: Mapping[str, Any],
    ) -> ScheduledTaskRun:
        for field_name in (
            "status",
            "created_task_id",
            "started_at",
            "finished_at",
            "last_error",
        ):
            if field_name in values:
                setattr(scheduled_task_run, field_name, values[field_name])
        await self.session.flush()
        return scheduled_task_run

    async def soft_delete_scheduled_task(self, scheduled_task: ScheduledTask) -> ScheduledTask:
        scheduled_task.is_active = False
        await self.session.flush()
        return scheduled_task

    async def find_due_scheduled_tasks(self, *, now: datetime, limit: int = 50) -> list[ScheduledTask]:
        query = (
            select(ScheduledTask)
            .where(
                ScheduledTask.is_active.is_(True),
                ScheduledTask.next_run_at <= now,
            )
            .options(
                selectinload(ScheduledTask.template).selectinload(TaskTemplate.chat),
                selectinload(ScheduledTask.template).selectinload(TaskTemplate.created_by_user),
                selectinload(ScheduledTask.chat).selectinload(Chat.members),
            )
            .order_by(ScheduledTask.next_run_at.asc(), ScheduledTask.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.scalars(query)
        return list(result.unique())
