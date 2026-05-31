from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.modules.reminders.schemas import ReminderType
from app.modules.reminders.service import ReminderService
from app.modules.tasks.enums import TaskAssigneeStatus, TaskStatus


class FakeReminderRepository:
    def __init__(self, tasks: list[SimpleNamespace]) -> None:
        self.tasks = tasks
        self.before_deadline_args: dict[str, datetime] = {}
        self.at_deadline_args: dict[str, datetime] = {}
        self.due_in_one_hour_args: dict[str, datetime] = {}
        self.overdue_chat_args: dict[str, datetime] = {}

    async def find_tasks_before_deadline(
        self,
        *,
        now: datetime,
        window_end: datetime,
    ) -> list[SimpleNamespace]:
        self.before_deadline_args = {"now": now, "window_end": window_end}
        return [
            task
            for task in self.tasks
            if task.deadline_at is not None and now < task.deadline_at <= window_end
        ]

    async def find_tasks_at_deadline(
        self,
        *,
        window_start: datetime,
        now: datetime,
    ) -> list[SimpleNamespace]:
        self.at_deadline_args = {"window_start": window_start, "now": now}
        return [
            task
            for task in self.tasks
            if task.deadline_at is not None and window_start <= task.deadline_at <= now
        ]

    async def find_tasks_after_deadline(self, *, now: datetime) -> list[SimpleNamespace]:
        return [
            task
            for task in self.tasks
            if task.deadline_at is not None and task.deadline_at < now
        ]

    async def find_tasks_without_response_after_deadline(
        self,
        *,
        now: datetime,
    ) -> list[SimpleNamespace]:
        return [
            task
            for task in self.tasks
            if task.deadline_at is not None and task.deadline_at < now
        ]

    async def find_tasks_waiting_acceptance(self, *, now: datetime) -> list[SimpleNamespace]:
        return list(self.tasks)

    async def find_tasks_due_in_one_hour(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> list[SimpleNamespace]:
        self.due_in_one_hour_args = {"window_start": window_start, "window_end": window_end}
        return [
            task
            for task in self.tasks
            if task.deadline_at is not None and window_start <= task.deadline_at <= window_end
        ]

    async def find_tasks_overdue_for_chat_reminder(self, *, now: datetime) -> list[SimpleNamespace]:
        return [
            task
            for task in self.tasks
            if task.deadline_at is not None and task.deadline_at < now
        ]

    async def find_tasks_overdue_for_chat_reminder_window(
        self,
        *,
        now: datetime,
        window_start: datetime,
    ) -> list[SimpleNamespace]:
        self.overdue_chat_args = {"now": now, "window_start": window_start}
        return [
            task
            for task in self.tasks
            if task.deadline_at is not None and window_start <= task.deadline_at <= now
        ]

    async def list_tasks_for_daily_summary(self, *, user_id: UUID) -> list[SimpleNamespace]:
        return [
            task
            for task in self.tasks
            if task.created_by_user_id == user_id
            or any(assignee.user_id == user_id for assignee in task.assignees)
            or any(observer.user_id == user_id for observer in task.observers)
        ]


def make_task(
    *,
    title: str,
    now: datetime,
    status: str = TaskStatus.NEW.value,
    deadline_delta: timedelta | None = None,
    task_number: int | None = 1042,
    created_by_user_id: UUID | None = None,
    assignees: list[SimpleNamespace] | None = None,
    observers: list[SimpleNamespace] | None = None,
    chat_status: str = "active",
    chat_settings: dict[str, object] | None = None,
) -> SimpleNamespace:
    if chat_settings is None:
        chat_settings = {"deadline_reminders_enabled": True}
    return SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        chat_id=uuid4(),
        chat=SimpleNamespace(status=chat_status, settings=chat_settings),
        task_number=task_number,
        title=title,
        status=status,
        deadline_at=None if deadline_delta is None else now + deadline_delta,
        created_by_user_id=created_by_user_id or uuid4(),
        assignees=assignees or [],
        observers=observers or [],
    )


def make_assignee(
    user_id: UUID,
    *,
    status: str = TaskAssigneeStatus.ASSIGNED.value,
    response_required: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        status=status,
        response_required=response_required,
    )


def make_observer(user_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id)


@pytest.mark.anyio
async def test_find_tasks_before_deadline_builds_payload_and_skips_done_cancelled() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    tasks = [
        make_task(title="Soon", now=now, deadline_delta=timedelta(minutes=30)),
        make_task(title="Later", now=now, deadline_delta=timedelta(hours=2)),
        make_task(title="Done soon", now=now, status=TaskStatus.DONE.value, deadline_delta=timedelta(minutes=15)),
        make_task(title="Cancelled soon", now=now, status=TaskStatus.CANCELLED.value, deadline_delta=timedelta(minutes=10)),
    ]
    repository = FakeReminderRepository(tasks)
    service = ReminderService(repository=repository, before_deadline_window=timedelta(hours=1))

    payload = await service.find_tasks_before_deadline(now)

    assert payload.reminder_type == ReminderType.BEFORE_DEADLINE
    assert [task.title for task in payload.tasks] == ["Soon"]
    assert repository.before_deadline_args == {
        "now": now,
        "window_end": now + timedelta(hours=1),
    }


@pytest.mark.anyio
async def test_find_tasks_at_and_after_deadline() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    tasks = [
        make_task(title="At deadline", now=now, deadline_delta=timedelta(minutes=-2)),
        make_task(title="Old overdue", now=now, deadline_delta=timedelta(days=-1)),
        make_task(title="Future", now=now, deadline_delta=timedelta(minutes=30)),
    ]
    repository = FakeReminderRepository(tasks)
    service = ReminderService(repository=repository, at_deadline_window=timedelta(minutes=5))

    at_deadline = await service.find_tasks_at_deadline(now)
    after_deadline = await service.find_tasks_after_deadline(now)

    assert [task.title for task in at_deadline.tasks] == ["At deadline"]
    assert [task.title for task in after_deadline.tasks] == ["At deadline", "Old overdue"]
    assert repository.at_deadline_args == {
        "window_start": now - timedelta(minutes=5),
        "now": now,
    }


@pytest.mark.anyio
async def test_find_chat_deadline_reminders_builds_due_in_one_hour_payload() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="Due in an hour",
            now=now,
            deadline_delta=timedelta(hours=1, minutes=2),
            assignees=[make_assignee(user_id)],
        ),
        make_task(
            title="Done in an hour",
            now=now,
            status=TaskStatus.DONE.value,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
        ),
        make_task(
            title="Rejected in an hour",
            now=now,
            status=TaskStatus.REJECTED.value,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
        ),
    ]
    repository = FakeReminderRepository(tasks)
    service = ReminderService(repository=repository, at_deadline_window=timedelta(minutes=5))

    payload = await service.find_tasks_due_in_one_hour(now)

    assert payload.reminder_type == ReminderType.TASK_DUE_IN_1H
    assert [task.title for task in payload.tasks] == ["Due in an hour"]
    assert payload.tasks[0].task_number == 1042
    assert repository.due_in_one_hour_args == {
        "window_start": now + timedelta(minutes=55),
        "window_end": now + timedelta(hours=1, minutes=5),
    }


@pytest.mark.anyio
async def test_find_chat_deadline_reminders_builds_overdue_payload() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="Overdue",
            now=now,
            deadline_delta=timedelta(minutes=-10),
            assignees=[make_assignee(user_id)],
        ),
        make_task(
            title="Old overdue",
            now=now,
            deadline_delta=timedelta(hours=-7),
            assignees=[make_assignee(user_id)],
        ),
        make_task(title="No deadline", now=now, assignees=[make_assignee(user_id)]),
        make_task(
            title="Cancelled overdue",
            now=now,
            status=TaskStatus.CANCELLED.value,
            deadline_delta=timedelta(minutes=-15),
            assignees=[make_assignee(user_id)],
        ),
    ]
    service = ReminderService(repository=FakeReminderRepository(tasks))

    payload = await service.find_tasks_overdue_for_chat_reminder(now)

    assert payload.reminder_type == ReminderType.TASK_OVERDUE
    assert [task.title for task in payload.tasks] == ["Overdue"]


@pytest.mark.anyio
async def test_find_chat_deadline_overdue_uses_configured_lookback() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="Inside lookback",
            now=now,
            deadline_delta=timedelta(hours=-3),
            assignees=[make_assignee(user_id)],
        ),
        make_task(
            title="Outside lookback",
            now=now,
            deadline_delta=timedelta(hours=-5),
            assignees=[make_assignee(user_id)],
        ),
    ]
    repository = FakeReminderRepository(tasks)
    service = ReminderService(repository=repository, overdue_notification_lookback=timedelta(hours=4))

    payload = await service.find_tasks_overdue_for_chat_reminder(now)

    assert [task.title for task in payload.tasks] == ["Inside lookback"]
    assert repository.overdue_chat_args == {
        "now": now,
        "window_start": now - timedelta(hours=4),
    }


@pytest.mark.anyio
async def test_deadline_reminder_empty_allowlist_keeps_normal_behavior() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="Allowed by default",
            now=now,
            task_number=53,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
        ),
        make_task(
            title="Also allowed by default",
            now=now,
            task_number=54,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
        ),
    ]
    service = ReminderService(repository=FakeReminderRepository(tasks))

    payload = await service.find_tasks_due_in_one_hour(now)

    assert [task.task_number for task in payload.tasks] == [53, 54]


@pytest.mark.anyio
async def test_deadline_reminder_chat_setting_defaults_to_disabled() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="No chat opt-in",
            now=now,
            task_number=53,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
            chat_settings={},
        ),
    ]
    service = ReminderService(repository=FakeReminderRepository(tasks))

    payload = await service.find_tasks_due_in_one_hour(now)

    assert payload.tasks == []


@pytest.mark.anyio
async def test_deadline_reminder_enabled_chat_is_selected() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="Enabled chat",
            now=now,
            task_number=53,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
            chat_settings={"deadline_reminders_enabled": True},
        ),
    ]
    service = ReminderService(repository=FakeReminderRepository(tasks))

    payload = await service.find_tasks_due_in_one_hour(now)

    assert [task.task_number for task in payload.tasks] == [53]


@pytest.mark.anyio
async def test_deadline_reminder_pending_chat_is_skipped_even_when_enabled() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="Pending chat",
            now=now,
            task_number=53,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
            chat_status="pending_approval",
            chat_settings={"deadline_reminders_enabled": True},
        ),
    ]
    service = ReminderService(repository=FakeReminderRepository(tasks))

    payload = await service.find_tasks_due_in_one_hour(now)

    assert payload.tasks == []


@pytest.mark.anyio
async def test_deadline_reminder_single_task_number_allowlist_filters_due_in_one_hour() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="Allowed",
            now=now,
            task_number=53,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
        ),
        make_task(
            title="Blocked",
            now=now,
            task_number=54,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
        ),
    ]
    service = ReminderService(
        repository=FakeReminderRepository(tasks),
        task_deadline_reminder_allowed_task_numbers=frozenset({53}),
    )

    payload = await service.find_tasks_due_in_one_hour(now)

    assert [task.task_number for task in payload.tasks] == [53]


@pytest.mark.anyio
async def test_deadline_reminder_multiple_task_number_allowlist_filters_overdue() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="Allowed 53",
            now=now,
            task_number=53,
            deadline_delta=timedelta(minutes=-2),
            assignees=[make_assignee(user_id)],
        ),
        make_task(
            title="Allowed 54",
            now=now,
            task_number=54,
            deadline_delta=timedelta(minutes=-3),
            assignees=[make_assignee(user_id)],
        ),
        make_task(
            title="Blocked 55",
            now=now,
            task_number=55,
            deadline_delta=timedelta(minutes=-4),
            assignees=[make_assignee(user_id)],
        ),
    ]
    service = ReminderService(
        repository=FakeReminderRepository(tasks),
        task_deadline_reminder_allowed_task_numbers=frozenset({53, 54}),
    )

    payload = await service.find_tasks_overdue_for_chat_reminder(now)

    assert [task.task_number for task in payload.tasks] == [53, 54]


@pytest.mark.anyio
async def test_deadline_reminder_allowlist_does_not_bypass_existing_guards() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="Final but allowlisted",
            now=now,
            task_number=53,
            status=TaskStatus.DONE.value,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
        ),
        make_task(
            title="Not allowlisted",
            now=now,
            task_number=54,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
        ),
    ]
    service = ReminderService(
        repository=FakeReminderRepository(tasks),
        task_deadline_reminder_allowed_task_numbers=frozenset({53}),
    )

    payload = await service.find_tasks_due_in_one_hour(now)

    assert payload.tasks == []


@pytest.mark.anyio
async def test_find_tasks_without_response_after_deadline_uses_required_assignee_status() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    tasks = [
        make_task(
            title="Needs response",
            now=now,
            deadline_delta=timedelta(minutes=-10),
            assignees=[make_assignee(user_id, status=TaskAssigneeStatus.ASSIGNED.value)],
        ),
        make_task(
            title="Already responded",
            now=now,
            deadline_delta=timedelta(minutes=-20),
            assignees=[make_assignee(user_id, status=TaskAssigneeStatus.RESPONDED.value)],
        ),
        make_task(
            title="Optional response",
            now=now,
            deadline_delta=timedelta(minutes=-30),
            assignees=[make_assignee(user_id, response_required=False)],
        ),
    ]
    service = ReminderService(repository=FakeReminderRepository(tasks))

    payload = await service.find_tasks_without_response_after_deadline(now)

    assert payload.reminder_type == ReminderType.WITHOUT_RESPONSE_AFTER_DEADLINE
    assert [task.title for task in payload.tasks] == ["Needs response"]


@pytest.mark.anyio
async def test_find_tasks_waiting_acceptance_filters_status() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    tasks = [
        make_task(title="Needs acceptance", now=now, status=TaskStatus.WAITING_ACCEPTANCE.value),
        make_task(title="In progress", now=now, status=TaskStatus.IN_PROGRESS.value),
        make_task(title="Done", now=now, status=TaskStatus.DONE.value),
    ]
    service = ReminderService(repository=FakeReminderRepository(tasks))

    payload = await service.find_tasks_waiting_acceptance(now)

    assert payload.reminder_type == ReminderType.WAITING_ACCEPTANCE
    assert [task.title for task in payload.tasks] == ["Needs acceptance"]


@pytest.mark.anyio
async def test_build_daily_summary_groups_user_related_tasks() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    summary_date = date(2026, 5, 19)
    user_id = uuid4()
    other_user_id = uuid4()
    tasks = [
        make_task(
            title="Assigned today",
            now=now,
            deadline_delta=timedelta(hours=3),
            assignees=[make_assignee(user_id)],
        ),
        make_task(
            title="Created waiting acceptance",
            now=now,
            status=TaskStatus.WAITING_ACCEPTANCE.value,
            deadline_delta=timedelta(hours=5),
            created_by_user_id=user_id,
            assignees=[make_assignee(other_user_id, status=TaskAssigneeStatus.RESPONDED.value)],
        ),
        make_task(
            title="Observed overdue",
            now=now,
            deadline_delta=timedelta(days=-1),
            observers=[make_observer(user_id)],
        ),
        make_task(
            title="Done assigned",
            now=now,
            status=TaskStatus.DONE.value,
            deadline_delta=timedelta(hours=1),
            assignees=[make_assignee(user_id)],
        ),
    ]
    service = ReminderService(repository=FakeReminderRepository(tasks))
    service._now = lambda: now  # type: ignore[method-assign]

    summary = await service.build_daily_summary(user_id=user_id, date=summary_date)

    assert [task.title for task in summary.my_tasks] == ["Assigned today"]
    assert [task.title for task in summary.created_by_me] == ["Created waiting acceptance"]
    assert [task.title for task in summary.observed_by_me] == ["Observed overdue"]
    assert [task.title for task in summary.waiting_my_response] == ["Assigned today"]
    assert [task.title for task in summary.waiting_my_acceptance] == ["Created waiting acceptance"]
    assert [task.title for task in summary.overdue] == ["Observed overdue"]
    assert [task.title for task in summary.today] == ["Assigned today", "Created waiting acceptance"]
