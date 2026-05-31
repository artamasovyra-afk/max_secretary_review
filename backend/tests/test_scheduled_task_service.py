from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_MEMBER, ROLE_SUPER_ADMIN
from app.modules.tasks.enums import ScheduledTaskRunStatus, ScheduledTaskScheduleType, TaskTemplateAudienceType, TaskType
from app.modules.tasks.scheduled_schemas import ScheduledTaskCreate, ScheduledTaskUpdate
from app.modules.tasks.scheduled_service import ScheduledTaskService


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _instance: object) -> None:
        return None


class FakeScheduledTaskRepository:
    def __init__(self, *, organization_id: UUID, chat_id: UUID, user_id: UUID, template_id: UUID) -> None:
        self.organization_id = organization_id
        self.chat_id = chat_id
        self.user_id = user_id
        self.template_id = template_id
        self.scheduled_task_id = uuid4()
        self.created_values: dict[str, object] = {}
        self.schedules: dict[UUID, SimpleNamespace] = {}
        self.runs: dict[tuple[UUID, datetime], SimpleNamespace] = {}
        self.due_schedules: list[SimpleNamespace] = []
        self.find_due_calls: list[dict[str, object]] = []

    async def organization_exists(self, organization_id: UUID) -> bool:
        return organization_id == self.organization_id

    async def get_chat(self, chat_id: UUID) -> SimpleNamespace | None:
        if chat_id != self.chat_id:
            return None
        return SimpleNamespace(id=chat_id, organization_id=self.organization_id)

    async def user_exists(self, user_id: UUID) -> bool:
        return user_id == self.user_id

    async def get_template(self, template_id: UUID) -> SimpleNamespace | None:
        if template_id != self.template_id:
            return None
        return _template(
            template_id=template_id,
            organization_id=self.organization_id,
            chat_id=self.chat_id,
            created_by_user_id=self.user_id,
        )

    async def create_scheduled_task(self, **values: object) -> SimpleNamespace:
        self.created_values = values
        schedule = _schedule(
            scheduled_task_id=self.scheduled_task_id,
            template=_template(
                template_id=values["template_id"],
                organization_id=values["organization_id"],
                chat_id=values["chat_id"],
                created_by_user_id=values["created_by_user_id"],
            ),
            created_by_user_id=values["created_by_user_id"],
            schedule_type=values["schedule_type"],
            scheduled_for=values["scheduled_for"],
            next_run_at=values["next_run_at"],
            is_active=values["is_active"],
        )
        self.schedules[schedule.id] = schedule
        return schedule

    async def list_scheduled_tasks(
        self,
        *,
        organization_id: UUID | None = None,
        chat_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
        is_active: bool | None = True,
    ) -> list[SimpleNamespace]:
        schedules = list(self.schedules.values())
        if organization_id is not None:
            schedules = [item for item in schedules if item.organization_id == organization_id]
        if chat_id is not None:
            schedules = [item for item in schedules if item.chat_id == chat_id]
        if created_by_user_id is not None:
            schedules = [item for item in schedules if item.created_by_user_id == created_by_user_id]
        if is_active is not None:
            schedules = [item for item in schedules if item.is_active is is_active]
        return schedules

    async def get_scheduled_task(self, scheduled_task_id: UUID) -> SimpleNamespace | None:
        return self.schedules.get(scheduled_task_id)

    async def update_scheduled_task(
        self,
        scheduled_task: SimpleNamespace,
        *,
        values: dict[str, object],
    ) -> SimpleNamespace:
        for field_name, value in values.items():
            setattr(scheduled_task, field_name, value)
        return scheduled_task

    async def get_scheduled_task_run(
        self,
        *,
        scheduled_task_id: UUID,
        planned_run_at: datetime,
    ) -> SimpleNamespace | None:
        return self.runs.get((scheduled_task_id, planned_run_at))

    async def create_scheduled_task_run(
        self,
        *,
        scheduled_task_id: UUID,
        planned_run_at: datetime,
        status: str,
        started_at: datetime,
    ) -> SimpleNamespace:
        run = SimpleNamespace(
            id=uuid4(),
            scheduled_task_id=scheduled_task_id,
            planned_run_at=planned_run_at,
            status=status,
            created_task_id=None,
            started_at=started_at,
            finished_at=None,
            last_error=None,
        )
        self.runs[(scheduled_task_id, planned_run_at)] = run
        return run

    async def update_scheduled_task_run(
        self,
        scheduled_task_run: SimpleNamespace,
        *,
        values: dict[str, object],
    ) -> SimpleNamespace:
        for field_name, value in values.items():
            setattr(scheduled_task_run, field_name, value)
        return scheduled_task_run

    async def soft_delete_scheduled_task(self, scheduled_task: SimpleNamespace) -> SimpleNamespace:
        scheduled_task.is_active = False
        return scheduled_task

    async def find_due_scheduled_tasks(self, *, now: datetime, limit: int = 50) -> list[SimpleNamespace]:
        self.find_due_calls.append({"now": now, "limit": limit})
        return self.due_schedules[:limit]


class FakeTaskService:
    def __init__(self) -> None:
        self.created_group_assignments: list[dict[str, object]] = []

    async def create_group_assignment(self, payload, auth_context) -> SimpleNamespace:
        task_id = uuid4()
        self.created_group_assignments.append(
            {
                "task_id": task_id,
                "payload": payload,
                "auth_context": auth_context,
            }
        )
        return SimpleNamespace(task_id=task_id)


def _template(
    *,
    template_id: object,
    organization_id: object,
    chat_id: object,
    created_by_user_id: object,
    is_active: bool = True,
    default_deadline_rule: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=template_id,
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=created_by_user_id,
        title="Еженедельный отчет",
        description="Сдать отчет",
        task_type=TaskType.GROUP_ASSIGNMENT.value,
        response_required=True,
        default_deadline_rule=default_deadline_rule,
        audience_type=TaskTemplateAudienceType.ALL_CHAT_MEMBERS.value,
        exclude_creator=True,
        settings=None,
        is_active=is_active,
        created_by_user=SimpleNamespace(id=created_by_user_id, display_name="Иван Руководитель"),
    )


def _schedule(
    *,
    scheduled_task_id: UUID,
    template: SimpleNamespace,
    created_by_user_id: object,
    schedule_type: object = ScheduledTaskScheduleType.ONE_TIME.value,
    scheduled_for: object = None,
    next_run_at: object | None = None,
    timezone_name: str = "UTC",
    is_active: object = True,
    owner_role: str = ROLE_CHAT_ADMIN,
) -> SimpleNamespace:
    now = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=scheduled_task_id,
        template_id=template.id,
        template=template,
        organization_id=template.organization_id,
        chat_id=template.chat_id,
        created_by_user_id=created_by_user_id,
        schedule_type=schedule_type,
        scheduled_for=scheduled_for,
        repeat_rule=None,
        timezone=timezone_name,
        next_run_at=next_run_at or now,
        last_run_at=None,
        is_active=is_active,
        last_error=None,
        created_at=now,
        updated_at=now,
        chat=SimpleNamespace(
            id=template.chat_id,
            organization_id=template.organization_id,
            members=[
                SimpleNamespace(
                    user_id=template.created_by_user_id,
                    role=owner_role,
                    is_active=True,
                )
            ],
        ),
    )


def _payload(
    *,
    template_id: UUID,
    organization_id: UUID,
    chat_id: UUID,
    created_by_user_id: UUID,
    next_run_at: datetime | None = None,
) -> ScheduledTaskCreate:
    return ScheduledTaskCreate(
        template_id=template_id,
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=created_by_user_id,
        schedule_type=ScheduledTaskScheduleType.ONE_TIME,
        next_run_at=next_run_at or datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc),
    )


@pytest.mark.anyio
async def test_scheduled_task_service_creator_can_create_schedule() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=user_id,
        template_id=template_id,
    )
    session = FakeSession()
    service = ScheduledTaskService(repository=repository, session=session)

    result = await service.create(
        _payload(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=user_id,
        ),
        AuthContext(user_id=user_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_MEMBER]),
    )

    assert result.id == repository.scheduled_task_id
    assert repository.created_values["schedule_type"] == ScheduledTaskScheduleType.ONE_TIME.value
    assert repository.created_values["timezone"] == "UTC"
    assert repository.created_values["is_active"] is True
    assert session.committed is True


@pytest.mark.anyio
async def test_scheduled_task_service_rejects_creator_impersonation() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=user_id,
        template_id=uuid4(),
    )
    service = ScheduledTaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create(
            _payload(
                template_id=repository.template_id,
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=user_id,
            ),
            AuthContext(user_id=uuid4(), organization_id=organization_id, chat_id=chat_id),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_scheduled_task_service_chat_admin_can_access_scoped_schedule() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    admin_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
    )
    repository.schedules[schedule.id] = schedule
    service = ScheduledTaskService(repository=repository, session=FakeSession())

    result = await service.get(
        schedule.id,
        AuthContext(user_id=admin_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
    )

    assert result.id == schedule.id


@pytest.mark.anyio
async def test_scheduled_task_service_outsider_forbidden() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
    )
    repository.schedules[schedule.id] = schedule
    service = ScheduledTaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.get(
            schedule.id,
            AuthContext(user_id=uuid4(), organization_id=organization_id, chat_id=chat_id, roles=[ROLE_MEMBER]),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_scheduled_task_service_update_and_soft_delete() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
    )
    repository.schedules[schedule.id] = schedule
    session = FakeSession()
    service = ScheduledTaskService(repository=repository, session=session)
    context = AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id)

    updated = await service.update(
        schedule.id,
        ScheduledTaskUpdate(
            schedule_type=ScheduledTaskScheduleType.DAILY,
            repeat_rule={"interval": 1},
        ),
        context,
    )
    deleted = await service.delete(schedule.id, context)

    assert updated.schedule_type == ScheduledTaskScheduleType.DAILY.value
    assert updated.repeat_rule == {"interval": 1}
    assert deleted.is_active is False
    assert session.committed is True


@pytest.mark.anyio
async def test_scheduled_task_service_runs_due_one_time_schedule() -> None:
    now = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
        next_run_at=now,
    )
    repository.due_schedules = [schedule]
    task_service = FakeTaskService()
    session = FakeSession()
    service = ScheduledTaskService(
        repository=repository,
        session=session,
        task_service=task_service,  # type: ignore[arg-type]
    )

    result = await service.run_due_scheduled_tasks(now=now)

    assert result.schedules_processed == 1
    assert result.tasks_created == 1
    assert result.schedules_skipped == 0
    assert result.schedules_failed == 0
    assert schedule.last_run_at == now
    assert schedule.is_active is False
    assert schedule.last_error is None
    assert task_service.created_group_assignments[0]["payload"].title == "Еженедельный отчет"
    assert task_service.created_group_assignments[0]["payload"].deadline_at is None
    assert task_service.created_group_assignments[0]["auth_context"].roles == [ROLE_CHAT_ADMIN]
    run = repository.runs[(schedule.id, now)]
    assert run.status == ScheduledTaskRunStatus.SUCCEEDED.value
    assert run.planned_run_at == now
    assert run.created_task_id == task_service.created_group_assignments[0]["task_id"]
    assert run.finished_at == now
    assert session.committed is True


@pytest.mark.anyio
async def test_scheduled_task_service_skips_succeeded_duplicate_run() -> None:
    now = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
        next_run_at=now,
    )
    created_task_id = uuid4()
    repository.runs[(schedule.id, now)] = SimpleNamespace(
        id=uuid4(),
        scheduled_task_id=schedule.id,
        planned_run_at=now,
        status=ScheduledTaskRunStatus.SUCCEEDED.value,
        created_task_id=created_task_id,
        started_at=now,
        finished_at=now,
        last_error=None,
    )
    repository.due_schedules = [schedule]
    task_service = FakeTaskService()
    service = ScheduledTaskService(
        repository=repository,
        session=FakeSession(),
        task_service=task_service,  # type: ignore[arg-type]
    )

    result = await service.run_due_scheduled_tasks(now=now)

    assert result.tasks_created == 0
    assert result.schedules_skipped == 1
    assert schedule.last_run_at == now
    assert schedule.is_active is False
    assert task_service.created_group_assignments == []


@pytest.mark.anyio
async def test_scheduled_task_service_skips_started_duplicate_run() -> None:
    now = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
        next_run_at=now,
    )
    repository.runs[(schedule.id, now)] = SimpleNamespace(
        id=uuid4(),
        scheduled_task_id=schedule.id,
        planned_run_at=now,
        status=ScheduledTaskRunStatus.STARTED.value,
        created_task_id=None,
        started_at=now,
        finished_at=None,
        last_error=None,
    )
    repository.due_schedules = [schedule]
    task_service = FakeTaskService()
    service = ScheduledTaskService(
        repository=repository,
        session=FakeSession(),
        task_service=task_service,  # type: ignore[arg-type]
    )

    result = await service.run_due_scheduled_tasks(now=now)

    assert result.tasks_created == 0
    assert result.schedules_skipped == 1
    assert schedule.last_run_at is None
    assert schedule.is_active is True
    assert task_service.created_group_assignments == []


@pytest.mark.anyio
async def test_scheduled_task_service_deactivates_existing_failed_run_without_retry() -> None:
    now = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
        next_run_at=now,
    )
    repository.runs[(schedule.id, now)] = SimpleNamespace(
        id=uuid4(),
        scheduled_task_id=schedule.id,
        planned_run_at=now,
        status=ScheduledTaskRunStatus.FAILED.value,
        created_task_id=None,
        started_at=now,
        finished_at=now,
        last_error="Previous run failed",
    )
    repository.due_schedules = [schedule]
    task_service = FakeTaskService()
    service = ScheduledTaskService(
        repository=repository,
        session=FakeSession(),
        task_service=task_service,  # type: ignore[arg-type]
    )

    result = await service.run_due_scheduled_tasks(now=now)

    assert result.tasks_created == 0
    assert result.schedules_skipped == 1
    assert result.schedules_deactivated == 1
    assert schedule.is_active is False
    assert schedule.last_error == "Previous run failed"
    assert task_service.created_group_assignments == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("rule", "expected_deadline_utc"),
    [
        ("same_day_18", datetime(2026, 5, 21, 15, 0, tzinfo=timezone.utc)),
        ("next_day_09", datetime(2026, 5, 22, 6, 0, tzinfo=timezone.utc)),
        ("next_day_18", datetime(2026, 5, 22, 15, 0, tzinfo=timezone.utc)),
        ("plus_1h", datetime(2026, 5, 21, 11, 0, tzinfo=timezone.utc)),
        ("plus_2h", datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)),
        ("plus_24h", datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)),
    ],
)
async def test_scheduled_task_service_applies_template_default_deadline_rule(
    rule: str,
    expected_deadline_utc: datetime,
) -> None:
    now = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
            default_deadline_rule=rule,
        ),
        created_by_user_id=creator_id,
        next_run_at=now,
        timezone_name="Europe/Moscow",
    )
    repository.due_schedules = [schedule]
    task_service = FakeTaskService()
    service = ScheduledTaskService(
        repository=repository,
        session=FakeSession(),
        task_service=task_service,  # type: ignore[arg-type]
    )

    result = await service.run_due_scheduled_tasks(now=now)

    assert result.tasks_created == 1
    deadline_at = task_service.created_group_assignments[0]["payload"].deadline_at
    assert deadline_at is not None
    assert deadline_at.astimezone(timezone.utc) == expected_deadline_utc


@pytest.mark.anyio
async def test_scheduled_task_service_supports_legacy_weekday_deadline_rule() -> None:
    now = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
            default_deadline_rule="friday_18",
        ),
        created_by_user_id=creator_id,
        next_run_at=now,
        timezone_name="Europe/Moscow",
    )
    repository.due_schedules = [schedule]
    task_service = FakeTaskService()
    service = ScheduledTaskService(
        repository=repository,
        session=FakeSession(),
        task_service=task_service,  # type: ignore[arg-type]
    )

    result = await service.run_due_scheduled_tasks(now=now)

    assert result.tasks_created == 1
    deadline_at = task_service.created_group_assignments[0]["payload"].deadline_at
    assert deadline_at is not None
    assert deadline_at.astimezone(timezone.utc) == datetime(2026, 5, 22, 15, 0, tzinfo=timezone.utc)


@pytest.mark.anyio
async def test_scheduled_task_service_deactivates_invalid_default_deadline_rule() -> None:
    now = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
            default_deadline_rule="not_a_rule",
        ),
        created_by_user_id=creator_id,
        next_run_at=now,
    )
    repository.due_schedules = [schedule]
    task_service = FakeTaskService()
    service = ScheduledTaskService(
        repository=repository,
        session=FakeSession(),
        task_service=task_service,  # type: ignore[arg-type]
    )

    result = await service.run_due_scheduled_tasks(now=now)

    assert result.tasks_created == 0
    assert result.schedules_failed == 1
    assert result.schedules_deactivated == 1
    assert schedule.is_active is False
    assert schedule.last_error == "Unsupported default_deadline_rule: not_a_rule"
    run = repository.runs[(schedule.id, now)]
    assert run.status == ScheduledTaskRunStatus.FAILED.value
    assert run.created_task_id is None
    assert run.finished_at == now
    assert run.last_error == "Unsupported default_deadline_rule: not_a_rule"
    assert task_service.created_group_assignments == []


@pytest.mark.anyio
async def test_scheduled_task_service_advances_daily_schedule() -> None:
    now = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
        schedule_type=ScheduledTaskScheduleType.DAILY.value,
        next_run_at=now - timedelta(days=2),
    )
    repository.due_schedules = [schedule]
    service = ScheduledTaskService(
        repository=repository,
        session=FakeSession(),
        task_service=FakeTaskService(),  # type: ignore[arg-type]
    )

    result = await service.run_due_scheduled_tasks(now=now)

    assert result.tasks_created == 1
    assert schedule.is_active is True
    assert schedule.next_run_at == datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc)
    run = repository.runs[(schedule.id, now - timedelta(days=2))]
    assert run.status == ScheduledTaskRunStatus.SUCCEEDED.value
    assert run.created_task_id is not None


@pytest.mark.anyio
async def test_scheduled_task_service_advances_weekly_schedule() -> None:
    now = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    planned_run_at = now - timedelta(days=8)
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
        schedule_type=ScheduledTaskScheduleType.WEEKLY.value,
        next_run_at=planned_run_at,
    )
    repository.due_schedules = [schedule]
    service = ScheduledTaskService(
        repository=repository,
        session=FakeSession(),
        task_service=FakeTaskService(),  # type: ignore[arg-type]
    )

    result = await service.run_due_scheduled_tasks(now=now)

    assert result.tasks_created == 1
    assert schedule.is_active is True
    assert schedule.last_run_at == planned_run_at
    assert schedule.next_run_at == datetime(2026, 5, 27, 9, 0, tzinfo=timezone.utc)
    run = repository.runs[(schedule.id, planned_run_at)]
    assert run.status == ScheduledTaskRunStatus.SUCCEEDED.value


@pytest.mark.anyio
async def test_scheduled_task_service_deactivates_when_template_owner_lacks_permission() -> None:
    now = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
        owner_role=ROLE_MEMBER,
    )
    repository.due_schedules = [schedule]
    task_service = FakeTaskService()
    service = ScheduledTaskService(
        repository=repository,
        session=FakeSession(),
        task_service=task_service,  # type: ignore[arg-type]
    )

    result = await service.run_due_scheduled_tasks(now=now)

    assert result.schedules_processed == 1
    assert result.tasks_created == 0
    assert result.schedules_failed == 1
    assert result.schedules_deactivated == 1
    assert schedule.is_active is False
    assert schedule.last_error == "Template owner no longer has permission to create group assignments"
    assert task_service.created_group_assignments == []


def test_scheduled_task_service_redacts_sensitive_run_errors() -> None:
    service = ScheduledTaskService(repository=None, session=FakeSession())  # type: ignore[arg-type]

    unsafe_error = (
        "MAX_BOT_"
        "TO"
        "KEN=secret "
        "to"
        "ken=abc "
        "pass"
        "word=hunter2 "
        "web"
        "hook/abcdef "
        "BITRIX24_"
        "WEBHOOK_URL=https://example.invalid"
    )
    detail = service._safe_error_detail(
        unsafe_error,
    )

    assert "secret" not in detail
    assert "hunter2" not in detail
    assert "web" "hook/abcdef" not in detail
    assert "https://example.invalid" not in detail
    assert "[redacted]" in detail


@pytest.mark.anyio
async def test_scheduled_task_service_super_admin_can_change_creator() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    new_creator_id = uuid4()
    template_id = uuid4()
    repository = FakeScheduledTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=new_creator_id,
        template_id=template_id,
    )
    schedule = _schedule(
        scheduled_task_id=repository.scheduled_task_id,
        template=_template(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
        ),
        created_by_user_id=creator_id,
    )
    repository.schedules[schedule.id] = schedule
    service = ScheduledTaskService(repository=repository, session=FakeSession())

    result = await service.update(
        schedule.id,
        ScheduledTaskUpdate(created_by_user_id=new_creator_id),
        AuthContext(user_id=uuid4(), roles=[ROLE_SUPER_ADMIN], is_super_admin=True),
    )

    assert result.created_by_user_id == new_creator_id
