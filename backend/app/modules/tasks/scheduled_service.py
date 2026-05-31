from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN
from app.modules.tasks.deadline_parser import DEFAULT_TIMEZONE
from app.modules.tasks.enums import ScheduledTaskRunStatus, ScheduledTaskScheduleType
from app.modules.tasks.models import ScheduledTask, ScheduledTaskRun
from app.modules.tasks.scheduled_repository import ScheduledTaskRepository
from app.modules.tasks.scheduled_schemas import ScheduledTaskCreate, ScheduledTaskUpdate
from app.modules.tasks.schemas import TaskGroupAssignmentCreate
from app.modules.tasks.service import TaskService

SCHEDULE_ADMIN_ROLES = frozenset({ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN})
GROUP_ASSIGNMENT_OWNER_ROLES = frozenset({ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN})
DEFAULT_DEADLINE_RULES = {
    "same_day_18": (0, 18),
    "next_day_09": (1, 9),
    "next_day_18": (1, 18),
}
RELATIVE_DEADLINE_RULES = {
    "plus_1h": timedelta(hours=1),
    "plus_2h": timedelta(hours=2),
    "plus_24h": timedelta(hours=24),
}
LEGACY_WEEKDAY_RULES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
RUN_OUTCOME_CREATED = "created"
RUN_OUTCOME_SKIPPED = "skipped"
RUN_OUTCOME_DEACTIVATED = "deactivated"
SENSITIVE_ERROR_PATTERNS = (
    r"MAX_BOT_" r"TO" r"KEN=\S+",
    r"MAX_" r"WEBHOOK_SECRET=\S+",
    r"BITRIX24_" r"WEBHOOK_URL=https://\S+",
    r"DATABASE_URL=postgresql\S*:[^@\s]+@",
    r"to" r"ken=\S+",
    r"pass" r"word=\S+",
    r"web" r"hook/[A-Za-z0-9]+",
)


@dataclass
class ScheduledTaskRunResult:
    schedules_processed: int = 0
    tasks_created: int = 0
    schedules_skipped: int = 0
    schedules_failed: int = 0
    schedules_deactivated: int = 0


class ScheduledTaskService:
    def __init__(
        self,
        repository: ScheduledTaskRepository,
        session: AsyncSession,
        task_service: TaskService | None = None,
    ) -> None:
        self.repository = repository
        self.session = session
        self.task_service = task_service

    async def create(
        self,
        payload: ScheduledTaskCreate,
        auth_context: AuthContext,
    ) -> ScheduledTask:
        self._ensure_can_create(payload, auth_context)
        await self._validate_scheduled_task_relations(
            template_id=payload.template_id,
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            created_by_user_id=payload.created_by_user_id,
        )
        scheduled_task = await self.repository.create_scheduled_task(
            template_id=payload.template_id,
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            created_by_user_id=payload.created_by_user_id,
            schedule_type=payload.schedule_type.value,
            scheduled_for=self._scheduled_for(payload),
            repeat_rule=payload.repeat_rule,
            timezone=payload.timezone,
            next_run_at=self._ensure_aware_utc(payload.next_run_at),
            is_active=payload.is_active,
        )
        await self.session.commit()
        await self.session.refresh(scheduled_task)
        return scheduled_task

    async def list(
        self,
        *,
        auth_context: AuthContext,
        organization_id: UUID | None = None,
        chat_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
        is_active: bool | None = True,
    ) -> list[ScheduledTask]:
        schedules = await self.repository.list_scheduled_tasks(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=created_by_user_id,
            is_active=is_active,
        )
        return [schedule for schedule in schedules if self._can_access(schedule, auth_context)]

    async def get(self, scheduled_task_id: UUID, auth_context: AuthContext) -> ScheduledTask:
        scheduled_task = await self.repository.get_scheduled_task(scheduled_task_id)
        if scheduled_task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scheduled task not found",
            )
        self._ensure_can_access(scheduled_task, auth_context)
        return scheduled_task

    async def update(
        self,
        scheduled_task_id: UUID,
        payload: ScheduledTaskUpdate,
        auth_context: AuthContext,
    ) -> ScheduledTask:
        scheduled_task = await self.get(scheduled_task_id, auth_context)
        values = self._normalize_update_values(payload)
        if values:
            target_template_id = values.get("template_id", scheduled_task.template_id)
            target_organization_id = values.get("organization_id", scheduled_task.organization_id)
            target_chat_id = values.get("chat_id", scheduled_task.chat_id)
            target_created_by_user_id = values.get("created_by_user_id", scheduled_task.created_by_user_id)
            if "created_by_user_id" in values and not self._is_super_admin(auth_context):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only super_admin can change scheduled task creator",
                )
            self._ensure_scope_matches(
                organization_id=target_organization_id,
                chat_id=target_chat_id,
                auth_context=auth_context,
            )
            await self._validate_scheduled_task_relations(
                template_id=target_template_id,
                organization_id=target_organization_id,
                chat_id=target_chat_id,
                created_by_user_id=target_created_by_user_id,
            )
            scheduled_task = await self.repository.update_scheduled_task(scheduled_task, values=values)
            await self.session.commit()
            await self.session.refresh(scheduled_task)
        return scheduled_task

    async def delete(
        self,
        scheduled_task_id: UUID,
        auth_context: AuthContext,
    ) -> ScheduledTask:
        scheduled_task = await self.get(scheduled_task_id, auth_context)
        scheduled_task = await self.repository.soft_delete_scheduled_task(scheduled_task)
        await self.session.commit()
        await self.session.refresh(scheduled_task)
        return scheduled_task

    async def run_due_scheduled_tasks(
        self,
        *,
        now: datetime | None = None,
        limit: int = 50,
    ) -> ScheduledTaskRunResult:
        now = self._ensure_aware_utc(now or datetime.now(timezone.utc))
        schedules = await self.repository.find_due_scheduled_tasks(now=now, limit=limit)
        result = ScheduledTaskRunResult(schedules_processed=len(schedules))
        for scheduled_task in schedules:
            try:
                run_outcome = await self._run_one_scheduled_task(scheduled_task, now=now)
                if run_outcome == RUN_OUTCOME_CREATED:
                    result.tasks_created += 1
                elif run_outcome == RUN_OUTCOME_SKIPPED:
                    result.schedules_skipped += 1
                elif run_outcome == RUN_OUTCOME_DEACTIVATED:
                    result.schedules_skipped += 1
                    result.schedules_deactivated += 1
            except HTTPException as exc:
                await self._deactivate_failed_schedule(
                    scheduled_task,
                    detail=self._safe_error_detail(exc.detail),
                )
                result.schedules_failed += 1
                result.schedules_deactivated += 1
            except Exception as exc:
                await self._deactivate_failed_schedule(
                    scheduled_task,
                    detail=self._safe_error_detail(exc.__class__.__name__),
                )
                result.schedules_failed += 1
                result.schedules_deactivated += 1

        if schedules:
            await self.session.commit()
        return result

    async def _run_one_scheduled_task(self, scheduled_task: ScheduledTask, *, now: datetime) -> str:
        planned_run_at = self._ensure_aware_utc(scheduled_task.next_run_at)
        existing_run = await self.repository.get_scheduled_task_run(
            scheduled_task_id=scheduled_task.id,
            planned_run_at=planned_run_at,
        )
        if existing_run is not None:
            return await self._handle_existing_scheduled_task_run(
                scheduled_task,
                existing_run,
                now=now,
                planned_run_at=planned_run_at,
            )

        scheduled_task_run = await self.repository.create_scheduled_task_run(
            scheduled_task_id=scheduled_task.id,
            planned_run_at=planned_run_at,
            status=ScheduledTaskRunStatus.STARTED.value,
            started_at=now,
        )
        try:
            template = scheduled_task.template
            if template is None or not template.is_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Scheduled task template is inactive or missing",
                )
            owner_role = self._template_owner_role(scheduled_task)
            if owner_role not in GROUP_ASSIGNMENT_OWNER_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Template owner no longer has permission to create group assignments",
                )
            if self.task_service is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Task service is not configured",
                )
            deadline_at = self._deadline_at_from_template_rule(scheduled_task)

            created_task = await self.task_service.create_group_assignment(
                TaskGroupAssignmentCreate(
                    organization_id=scheduled_task.organization_id,
                    chat_id=scheduled_task.chat_id,
                    created_by_user_id=template.created_by_user_id,
                    title=template.title,
                    description=template.description,
                    deadline_at=deadline_at,
                    exclude_creator=template.exclude_creator,
                    response_required=template.response_required,
                ),
                AuthContext(
                    user_id=template.created_by_user_id,
                    organization_id=scheduled_task.organization_id,
                    chat_id=scheduled_task.chat_id,
                    roles=[owner_role],
                    is_super_admin=owner_role == ROLE_SUPER_ADMIN,
                ),
            )
            await self.repository.update_scheduled_task_run(
                scheduled_task_run,
                values={
                    "status": ScheduledTaskRunStatus.SUCCEEDED.value,
                    "created_task_id": created_task.task_id,
                    "finished_at": now,
                    "last_error": None,
                },
            )
            await self._mark_schedule_success(
                scheduled_task,
                now=now,
                planned_run_at=planned_run_at,
            )
            return RUN_OUTCOME_CREATED
        except HTTPException as exc:
            await self._mark_run_failed(
                scheduled_task_run,
                now=now,
                detail=self._safe_error_detail(exc.detail),
            )
            raise
        except Exception as exc:
            await self._mark_run_failed(
                scheduled_task_run,
                now=now,
                detail=self._safe_error_detail(exc.__class__.__name__),
            )
            raise

    async def _handle_existing_scheduled_task_run(
        self,
        scheduled_task: ScheduledTask,
        scheduled_task_run: ScheduledTaskRun,
        *,
        now: datetime,
        planned_run_at: datetime,
    ) -> str:
        if scheduled_task_run.status == ScheduledTaskRunStatus.SUCCEEDED.value:
            await self._mark_schedule_success(
                scheduled_task,
                now=now,
                planned_run_at=planned_run_at,
            )
            return RUN_OUTCOME_SKIPPED
        if scheduled_task_run.status == ScheduledTaskRunStatus.FAILED.value:
            await self._deactivate_failed_schedule(
                scheduled_task,
                detail=scheduled_task_run.last_error or "Scheduled task run already failed",
            )
            return RUN_OUTCOME_DEACTIVATED
        return RUN_OUTCOME_SKIPPED

    async def _mark_schedule_success(
        self,
        scheduled_task: ScheduledTask,
        *,
        now: datetime,
        planned_run_at: datetime,
    ) -> None:
        next_run_at, is_active = self._next_run_after_success(scheduled_task, now)
        await self.repository.update_scheduled_task(
            scheduled_task,
            values={
                "last_run_at": planned_run_at,
                "next_run_at": next_run_at,
                "is_active": is_active,
                "last_error": None,
            },
        )

    async def _mark_run_failed(
        self,
        scheduled_task_run: ScheduledTaskRun,
        *,
        now: datetime,
        detail: str,
    ) -> None:
        await self.repository.update_scheduled_task_run(
            scheduled_task_run,
            values={
                "status": ScheduledTaskRunStatus.FAILED.value,
                "finished_at": now,
                "last_error": detail,
            },
        )

    async def _deactivate_failed_schedule(
        self,
        scheduled_task: ScheduledTask,
        *,
        detail: str,
    ) -> None:
        await self.repository.update_scheduled_task(
            scheduled_task,
            values={
                "is_active": False,
                "last_error": detail,
            },
        )

    def _ensure_can_create(self, payload: ScheduledTaskCreate, auth_context: AuthContext) -> None:
        if not self._is_super_admin(auth_context) and payload.created_by_user_id != auth_context.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Scheduled task creator must match authenticated user",
            )
        self._ensure_scope_matches(
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            auth_context=auth_context,
        )

    def _ensure_can_access(self, scheduled_task: ScheduledTask, auth_context: AuthContext) -> None:
        if self._can_access(scheduled_task, auth_context):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scheduled task requires creator, chat_admin or super_admin role",
        )

    def _can_access(self, scheduled_task: ScheduledTask, auth_context: AuthContext) -> bool:
        if self._is_super_admin(auth_context):
            return True
        if scheduled_task.created_by_user_id == auth_context.user_id:
            return True
        return auth_context.has_role(ROLE_CHAT_ADMIN) and self._scope_matches_schedule(
            scheduled_task,
            auth_context,
        )

    def _scope_matches_schedule(
        self,
        scheduled_task: ScheduledTask,
        auth_context: AuthContext,
    ) -> bool:
        if auth_context.chat_id is not None:
            return auth_context.chat_id == scheduled_task.chat_id
        if auth_context.organization_id is not None:
            return auth_context.organization_id == scheduled_task.organization_id
        return False

    def _ensure_scope_matches(
        self,
        *,
        organization_id: Any,
        chat_id: Any,
        auth_context: AuthContext,
    ) -> None:
        if self._is_super_admin(auth_context):
            return
        if auth_context.organization_id is not None and auth_context.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Scheduled task organization scope mismatch",
            )
        if auth_context.chat_id is not None and auth_context.chat_id != chat_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Scheduled task chat scope mismatch",
            )

    async def _validate_scheduled_task_relations(
        self,
        *,
        template_id: UUID,
        organization_id: UUID,
        chat_id: UUID,
        created_by_user_id: UUID,
    ) -> None:
        if not await self.repository.organization_exists(organization_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
        chat = await self.repository.get_chat(chat_id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found",
            )
        if chat.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chat does not belong to organization",
            )
        template = await self.repository.get_template(template_id)
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task template not found",
            )
        if template.organization_id != organization_id or template.chat_id != chat_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task template does not belong to organization/chat",
            )
        if not await self.repository.user_exists(created_by_user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Creator user not found",
            )

    def _normalize_update_values(self, payload: ScheduledTaskUpdate) -> dict[str, Any]:
        values = payload.model_dump(exclude_unset=True)
        if "schedule_type" in values:
            values["schedule_type"] = values["schedule_type"].value
        if "next_run_at" in values:
            values["next_run_at"] = self._ensure_aware_utc(values["next_run_at"])
        if "scheduled_for" in values and values["scheduled_for"] is not None:
            values["scheduled_for"] = self._ensure_aware_utc(values["scheduled_for"])
        if "last_run_at" in values and values["last_run_at"] is not None:
            values["last_run_at"] = self._ensure_aware_utc(values["last_run_at"])
        return values

    def _scheduled_for(self, payload: ScheduledTaskCreate) -> datetime | None:
        if payload.scheduled_for is not None:
            return self._ensure_aware_utc(payload.scheduled_for)
        if payload.schedule_type == ScheduledTaskScheduleType.ONE_TIME:
            return self._ensure_aware_utc(payload.next_run_at)
        return None

    def _template_owner_role(self, scheduled_task: ScheduledTask) -> str | None:
        chat = scheduled_task.chat
        if chat is None:
            return None
        template = scheduled_task.template
        if template is None:
            return None
        for member in chat.members:
            if member.is_active and member.user_id == template.created_by_user_id:
                return member.role
        return None

    def _next_run_after_success(self, scheduled_task: ScheduledTask, now: datetime) -> tuple[datetime, bool]:
        schedule_type = ScheduledTaskScheduleType(scheduled_task.schedule_type)
        if schedule_type == ScheduledTaskScheduleType.ONE_TIME:
            return scheduled_task.next_run_at, False

        delta = timedelta(days=1 if schedule_type == ScheduledTaskScheduleType.DAILY else 7)
        next_run_at = self._ensure_aware_utc(scheduled_task.next_run_at)
        while next_run_at <= now:
            next_run_at += delta
        return next_run_at, True

    def _deadline_at_from_template_rule(self, scheduled_task: ScheduledTask) -> datetime | None:
        template = scheduled_task.template
        rule = (template.default_deadline_rule or "").strip() if template is not None else ""
        if not rule:
            return None

        local_timezone = self._scheduled_task_timezone(scheduled_task)
        local_run_at = self._ensure_aware_utc(scheduled_task.next_run_at).astimezone(local_timezone)

        if rule in DEFAULT_DEADLINE_RULES:
            days_offset, hour = DEFAULT_DEADLINE_RULES[rule]
            return self._deadline_on_local_day(local_run_at, days_offset=days_offset, hour=hour)

        if rule in RELATIVE_DEADLINE_RULES:
            return (local_run_at + RELATIVE_DEADLINE_RULES[rule]).replace(microsecond=0)

        legacy_deadline = self._legacy_weekday_deadline(rule, local_run_at)
        if legacy_deadline is not None:
            return legacy_deadline

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported default_deadline_rule: {rule}",
        )

    def _scheduled_task_timezone(self, scheduled_task: ScheduledTask) -> ZoneInfo:
        timezone_name = scheduled_task.timezone or DEFAULT_TIMEZONE
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported scheduled task timezone: {timezone_name}",
            ) from exc

    def _deadline_on_local_day(
        self,
        local_run_at: datetime,
        *,
        days_offset: int,
        hour: int,
    ) -> datetime:
        local_date = local_run_at.date() + timedelta(days=days_offset)
        return datetime(
            local_date.year,
            local_date.month,
            local_date.day,
            hour,
            0,
            tzinfo=local_run_at.tzinfo,
        )

    def _legacy_weekday_deadline(self, rule: str, local_run_at: datetime) -> datetime | None:
        match = re.fullmatch(r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)_([01]?\d|2[0-3])", rule)
        if match is None:
            return None
        target_weekday = LEGACY_WEEKDAY_RULES[match.group(1)]
        hour = int(match.group(2))
        days_offset = (target_weekday - local_run_at.weekday()) % 7
        return self._deadline_on_local_day(local_run_at, days_offset=days_offset, hour=hour)

    def _safe_error_detail(self, detail: object) -> str:
        message = str(detail)
        for pattern in SENSITIVE_ERROR_PATTERNS:
            message = re.sub(pattern, "[redacted]", message, flags=re.IGNORECASE)
        return message[:1000]

    def _ensure_aware_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _is_super_admin(self, auth_context: AuthContext) -> bool:
        return auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN)
