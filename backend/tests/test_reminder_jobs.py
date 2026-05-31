from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import logging

import pytest

from app.modules.auth.policy import ROLE_CHAT_ADMIN
from app.modules.notifications.max_sender import MaxSender
from app.modules.reminders.jobs import ReminderJobRunner
from app.modules.reminders.schemas import DailySummaryPayload, ReminderPayload, ReminderTaskPayload, ReminderType
from app.modules.tasks.enums import TaskStatus


class FakeReminderService:
    def __init__(
        self,
        now: datetime,
        task: ReminderTaskPayload,
        user_id,
        snoozed_pairs: set[tuple[object, object]] | None = None,
        due_in_one_hour_tasks: list[ReminderTaskPayload] | None = None,
        overdue_chat_tasks: list[ReminderTaskPayload] | None = None,
    ) -> None:
        self.now = now
        self.task = task
        self.user_id = user_id
        self.snoozed_pairs = snoozed_pairs or set()
        self.snooze_checks: list[tuple[object, object, datetime]] = []
        self.due_in_one_hour_tasks = due_in_one_hour_tasks or []
        self.overdue_chat_tasks = overdue_chat_tasks or []

    async def find_tasks_before_deadline(self, now: datetime) -> ReminderPayload:
        return ReminderPayload(
            reminder_type=ReminderType.BEFORE_DEADLINE,
            generated_at=now,
            tasks=[self.task],
        )

    async def find_tasks_at_deadline(self, now: datetime) -> ReminderPayload:
        return ReminderPayload(
            reminder_type=ReminderType.AT_DEADLINE,
            generated_at=now,
            tasks=[],
        )

    async def find_tasks_after_deadline(self, now: datetime) -> ReminderPayload:
        return ReminderPayload(
            reminder_type=ReminderType.AFTER_DEADLINE,
            generated_at=now,
            tasks=[],
        )

    async def find_tasks_without_response_after_deadline(self, now: datetime) -> ReminderPayload:
        return ReminderPayload(
            reminder_type=ReminderType.NO_RESPONSE_AFTER_DEADLINE,
            generated_at=now,
            tasks=[],
        )

    async def find_tasks_waiting_acceptance(self, now: datetime) -> ReminderPayload:
        return ReminderPayload(
            reminder_type=ReminderType.WAITING_ACCEPTANCE,
            generated_at=now,
            tasks=[],
        )

    async def find_tasks_due_in_one_hour(self, now: datetime) -> ReminderPayload:
        return ReminderPayload(
            reminder_type=ReminderType.TASK_DUE_IN_1H,
            generated_at=now,
            tasks=self.due_in_one_hour_tasks,
        )

    async def find_tasks_overdue_for_chat_reminder(self, now: datetime) -> ReminderPayload:
        return ReminderPayload(
            reminder_type=ReminderType.TASK_OVERDUE,
            generated_at=now,
            tasks=self.overdue_chat_tasks,
        )

    async def build_daily_summary(self, *, user_id, date: date) -> DailySummaryPayload:
        return DailySummaryPayload(
            user_id=user_id,
            date=date,
            generated_at=self.now,
            my_tasks=[self.task],
            today=[self.task],
        )

    async def is_snoozed(self, task_id, user_id, now: datetime) -> bool:
        self.snooze_checks.append((task_id, user_id, now))
        return (task_id, user_id) in self.snoozed_pairs


class FakeReminderRepository:
    def __init__(
        self,
        user_ids,
        overdue_tasks: list[SimpleNamespace],
        *,
        user_external_ids: dict[object, str | None] | None = None,
        user_display_names: dict[object, str] | None = None,
        chat_external_ids: dict[object, str | None] | None = None,
    ) -> None:
        self.user_ids = user_ids
        self.overdue_tasks = overdue_tasks
        self.user_external_ids = user_external_ids or {}
        self.user_display_names = user_display_names or {}
        self.chat_external_ids = chat_external_ids or {}
        self.marked_tasks: list[SimpleNamespace] = []
        self.mark_overdue_now = None

    async def list_daily_summary_user_ids(self):
        return self.user_ids

    async def find_tasks_to_mark_overdue(self, *, now: datetime) -> list[SimpleNamespace]:
        self.mark_overdue_now = now
        return self.overdue_tasks

    async def mark_task_overdue(self, task: SimpleNamespace) -> SimpleNamespace:
        task.status = TaskStatus.OVERDUE.value
        self.marked_tasks.append(task)
        return task

    async def get_user(self, user_id):
        max_user_id = self.user_external_ids.get(user_id, _max_user_id(user_id))
        display_name = self.user_display_names.get(user_id, f"User {str(user_id)[-4:]}")
        return SimpleNamespace(id=user_id, max_user_id=max_user_id, display_name=display_name)

    async def get_chat(self, chat_id):
        max_chat_id = self.chat_external_ids.get(chat_id, _max_chat_id(chat_id))
        return SimpleNamespace(id=chat_id, max_chat_id=max_chat_id)


class FakeSender:
    def __init__(self, *, enabled: bool = True, sent: bool = True) -> None:
        self.enabled = enabled
        self.background_enabled = True
        self.sent = sent
        self.messages: list[dict[str, object]] = []

    def send_message(
        self,
        chat_id: str | None,
        text: str,
        *,
        user_id: str | None = None,
        attachments: list[dict[str, object]] | None = None,
        reminder_type: str | None = None,
        purpose: str | None = None,
    ) -> object:
        message = {
            "chat_id": chat_id,
            "user_id": user_id,
            "text": text,
            "reminder_type": reminder_type,
            "purpose": getattr(purpose, "value", purpose),
        }
        if attachments is not None:
            message["attachments"] = attachments
        self.messages.append(message)
        return SimpleNamespace(sent=self.sent)


class FakeManagerSummaryRepository:
    def __init__(self, *, chats: list[SimpleNamespace], tasks: list[SimpleNamespace]) -> None:
        self.chats = chats
        self.tasks = tasks

    async def list_chats_for_daily_manager_summary(self) -> list[SimpleNamespace]:
        return self.chats

    async def list_tasks_for_chat(self, *, chat_id, summary_date: date) -> list[SimpleNamespace]:
        return [task for task in self.tasks if task.chat_id == chat_id]


class FakeNotificationDeliveryService:
    def __init__(self, *, status: str = "sent") -> None:
        self.status = status
        self.messages: list[dict[str, object]] = []
        self.chat_messages: list[dict[str, object]] = []

    async def send_personal_task_notification(
        self,
        *,
        user_id,
        task_id,
        message: str,
        reminder_type: str | None = None,
        attachments: list[dict[str, object]] | None = None,
    ) -> object:
        self.messages.append(
            {
                "user_id": user_id,
                "task_id": task_id,
                "message": message,
                "reminder_type": reminder_type,
                "attachments": attachments,
            }
        )
        return SimpleNamespace(status=self.status)

    async def send_chat_task_notification(
        self,
        *,
        chat_id,
        task_id,
        message: str,
        reminder_type: str,
        attachments: list[dict[str, object]] | None = None,
        purpose=None,
    ) -> object:
        self.chat_messages.append(
            {
                "chat_id": chat_id,
                "task_id": task_id,
                "message": message,
                "reminder_type": reminder_type,
                "attachments": attachments,
                "purpose": getattr(purpose, "value", purpose),
            }
        )
        return SimpleNamespace(status=self.status)


class FakeScheduledTaskService:
    def __init__(self) -> None:
        self.run_calls: list[datetime | None] = []

    async def run_due_scheduled_tasks(self, *, now: datetime | None = None):
        self.run_calls.append(now)
        return SimpleNamespace(
            schedules_processed=2,
            tasks_created=1,
            schedules_failed=1,
            schedules_deactivated=1,
        )


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


def make_task_payload(now: datetime) -> ReminderTaskPayload:
    return ReminderTaskPayload(
        task_id=uuid4(),
        organization_id=uuid4(),
        chat_id=uuid4(),
        task_number=1042,
        title="Prepare weekly report",
        status=TaskStatus.NEW.value,
        deadline_at=now + timedelta(minutes=30),
        created_by_user_id=uuid4(),
        assignee_ids=[uuid4(), uuid4()],
        observer_ids=[uuid4()],
    )


def _max_user_id(user_id) -> str:
    return f"max-user-{str(user_id)[-8:]}"


def _max_chat_id(chat_id) -> str:
    return f"max-chat-{str(chat_id)[-8:]}"


def make_chat(
    *,
    chat_id=None,
    organization_id=None,
    settings: dict | None = None,
    members: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=chat_id or uuid4(),
        organization_id=organization_id or uuid4(),
        title="Project chat",
        settings=settings or {},
        members=members or [],
    )


def make_member(*, user_id=None, role: str = ROLE_CHAT_ADMIN, is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id or uuid4(), role=role, is_active=is_active)


def make_manager_task(
    *,
    chat_id,
    created_by_user_id,
    status: TaskStatus,
    deadline_at: datetime | None,
    assignee_ids: list[object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        title="Manager task",
        chat_id=chat_id,
        created_by_user_id=created_by_user_id,
        status=status.value,
        deadline_at=deadline_at,
        assignees=[SimpleNamespace(user_id=user_id) for user_id in (assignee_ids or [])],
    )


@pytest.mark.anyio
async def test_run_due_reminders_sends_messages_to_task_recipients() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    repository = FakeReminderRepository(user_ids=[], overdue_tasks=[])
    sender = FakeSender(enabled=True, sent=True)
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=task, user_id=task.created_by_user_id),
        repository=repository,
        sender=sender,
    )

    result = await runner.run_due_reminders(now)

    assert result.tasks_processed == 1
    assert result.reminders_sent == 4
    assert {message["user_id"] for message in sender.messages} == {
        _max_user_id(task.created_by_user_id),
        *(_max_user_id(user_id) for user_id in task.assignee_ids),
        *(_max_user_id(user_id) for user_id in task.observer_ids),
    }
    assert all(message["chat_id"] == _max_chat_id(task.chat_id) for message in sender.messages)
    assert all(message["reminder_type"] == ReminderType.BEFORE_DEADLINE.value for message in sender.messages)
    assert "Prepare weekly report" in sender.messages[0]["text"]


@pytest.mark.anyio
async def test_run_due_reminders_skips_only_snoozed_user() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    snoozed_assignee_id = task.assignee_ids[0]
    repository = FakeReminderRepository(user_ids=[], overdue_tasks=[])
    sender = FakeSender(enabled=True, sent=True)
    service = FakeReminderService(
        now=now,
        task=task,
        user_id=task.created_by_user_id,
        snoozed_pairs={(task.task_id, snoozed_assignee_id)},
    )
    runner = ReminderJobRunner(
        service=service,
        repository=repository,
        sender=sender,
    )

    result = await runner.run_due_reminders(now)

    assert result.tasks_processed == 1
    assert result.reminders_sent == 3
    assert _max_user_id(snoozed_assignee_id) not in {message["user_id"] for message in sender.messages}
    assert {message["user_id"] for message in sender.messages} == {
        _max_user_id(task.created_by_user_id),
        _max_user_id(task.assignee_ids[1]),
        _max_user_id(task.observer_ids[0]),
    }
    assert (task.task_id, snoozed_assignee_id, now) in service.snooze_checks


@pytest.mark.anyio
async def test_waiting_acceptance_reminder_is_clean_and_sent_to_creator_only() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    response_id = uuid4()
    response_user_id = uuid4()
    task = make_task_payload(now)
    task.status = TaskStatus.WAITING_ACCEPTANCE.value
    task.response_id = response_id
    task.response_user_id = response_user_id
    task.response_user_display_name = "Иван Иванов"
    delivery_service = FakeNotificationDeliveryService()
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=task, user_id=task.created_by_user_id),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=FakeSender(enabled=True, sent=True),
        notification_delivery_service=delivery_service,
    )

    sent = await runner._send_task_reminders(
        ReminderPayload(
            reminder_type=ReminderType.WAITING_ACCEPTANCE,
            generated_at=now,
            tasks=[task],
        ),
        now=now,
    )

    assert sent == 1
    assert len(delivery_service.messages) == 1
    message = delivery_service.messages[0]
    assert message["user_id"] == task.created_by_user_id
    assert "Ответ ожидает приемки ✅" in message["message"]
    assert "payload=" not in message["message"]
    assert "Пользователь #" not in message["message"]
    buttons = message["attachments"][0]["payload"]["buttons"][0]
    assert [button["text"] for button in buttons] == ["Принять", "Отклонить", "Открыть задачу"]
    assert buttons[0]["payload"] == f"task:accept:{task.task_id}:{response_id}"
    assert buttons[1]["payload"] == f"task:reject:{task.task_id}:{response_id}"


@pytest.mark.anyio
async def test_run_due_reminders_skips_user_without_max_user_id() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    missing_user_id = task.assignee_ids[0]
    repository = FakeReminderRepository(
        user_ids=[],
        overdue_tasks=[],
        user_external_ids={missing_user_id: None},
    )
    sender = FakeSender()
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=task, user_id=task.created_by_user_id),
        repository=repository,
        sender=sender,
    )

    result = await runner.run_due_reminders(now)

    assert result.tasks_processed == 1
    assert result.reminders_sent == 3
    assert _max_user_id(missing_user_id) not in {message["user_id"] for message in sender.messages}
    assert {message["user_id"] for message in sender.messages} == {
        _max_user_id(task.created_by_user_id),
        _max_user_id(task.assignee_ids[1]),
        _max_user_id(task.observer_ids[0]),
    }
    assert all(message["chat_id"] == _max_chat_id(task.chat_id) for message in sender.messages)


@pytest.mark.anyio
async def test_run_due_reminders_skips_chat_without_max_chat_id() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    repository = FakeReminderRepository(
        user_ids=[],
        overdue_tasks=[],
        chat_external_ids={task.chat_id: None},
    )
    sender = FakeSender()
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=task, user_id=task.created_by_user_id),
        repository=repository,
        sender=sender,
    )

    result = await runner.run_due_reminders(now)

    assert result.tasks_processed == 1
    assert result.reminders_sent == 0
    assert sender.messages == []


@pytest.mark.anyio
async def test_run_due_reminders_uses_notification_delivery_service_when_configured() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    repository = FakeReminderRepository(user_ids=[], overdue_tasks=[])
    sender = FakeSender()
    notification_delivery_service = FakeNotificationDeliveryService()
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=task, user_id=task.created_by_user_id),
        repository=repository,
        sender=sender,
        notification_delivery_service=notification_delivery_service,  # type: ignore[arg-type]
    )

    result = await runner.run_due_reminders(now)

    assert result.tasks_processed == 0
    assert result.reminders_sent == 0
    assert sender.messages == []
    assert notification_delivery_service.messages == []
    assert notification_delivery_service.chat_messages == []


@pytest.mark.anyio
async def test_self_assigned_due_task_creates_one_delivery() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    task.assignee_ids = [task.created_by_user_id]
    task.observer_ids = []
    notification_delivery_service = FakeNotificationDeliveryService()
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=task, user_id=task.created_by_user_id),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=FakeSender(),
        notification_delivery_service=notification_delivery_service,  # type: ignore[arg-type]
    )

    result = await runner.run_due_reminders(now)

    assert result.tasks_processed == 0
    assert result.reminders_sent == 0
    assert notification_delivery_service.messages == []
    assert notification_delivery_service.chat_messages == []


@pytest.mark.anyio
async def test_run_due_reminders_does_not_count_sender_disabled_skips_as_sent() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    notification_delivery_service = FakeNotificationDeliveryService(status="skipped")
    runner = ReminderJobRunner(
        service=FakeReminderService(
            now=now,
            task=task,
            user_id=task.created_by_user_id,
            due_in_one_hour_tasks=[task],
        ),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=FakeSender(),
        notification_delivery_service=notification_delivery_service,  # type: ignore[arg-type]
        task_deadline_chat_reminders_enabled=True,
    )

    result = await runner.run_due_reminders(now)

    assert result.tasks_processed == 1
    assert result.reminders_sent == 0
    assert result.reminders_skipped == 1
    assert notification_delivery_service.messages == []
    assert len(notification_delivery_service.chat_messages) == 1


@pytest.mark.anyio
async def test_run_due_reminders_skips_chat_deadline_reminders_when_feature_flag_disabled() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    notification_delivery_service = FakeNotificationDeliveryService()
    runner = ReminderJobRunner(
        service=FakeReminderService(
            now=now,
            task=task,
            user_id=task.created_by_user_id,
            due_in_one_hour_tasks=[task],
            overdue_chat_tasks=[task],
        ),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=FakeSender(),
        notification_delivery_service=notification_delivery_service,  # type: ignore[arg-type]
    )

    result = await runner.run_due_reminders(now)

    assert result.tasks_processed == 0
    assert result.reminders_sent == 0
    assert result.reminders_skipped == 0
    assert notification_delivery_service.chat_messages == []


@pytest.mark.anyio
async def test_run_due_reminders_creates_due_in_one_hour_chat_reminder() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    task.deadline_at = now + timedelta(hours=1)
    notification_delivery_service = FakeNotificationDeliveryService()
    repository = FakeReminderRepository(
        user_ids=[],
        overdue_tasks=[],
        user_display_names={
            task.assignee_ids[0]: "Иван Иванов",
            task.assignee_ids[1]: "Мария Петрова",
        },
    )
    runner = ReminderJobRunner(
        service=FakeReminderService(
            now=now,
            task=task,
            user_id=task.created_by_user_id,
            due_in_one_hour_tasks=[task],
        ),
        repository=repository,
        sender=FakeSender(),
        notification_delivery_service=notification_delivery_service,  # type: ignore[arg-type]
        webapp_base_url="https://maxsecretary.ru",
        max_bot_username="secretary_oren_bot",
        task_deadline_chat_reminders_enabled=True,
    )

    result = await runner.run_due_reminders(now)

    assert result.reminders_sent == 1
    assert len(notification_delivery_service.chat_messages) == 1
    chat_message = notification_delivery_service.chat_messages[0]
    assert chat_message["chat_id"] == task.chat_id
    assert chat_message["task_id"] == task.task_id
    assert chat_message["reminder_type"] == ReminderType.TASK_DUE_IN_1H.value
    assert "⏰ До срока по задаче #1042 остался 1 час" in chat_message["message"]
    assert "Текст: Prepare weekly report" in chat_message["message"]
    assert "Исполнители:" in chat_message["message"]
    assert "Срок: сегодня" in chat_message["message"]
    assert "[@Иван Иванов](max://user/" in chat_message["message"]
    assert "[@Мария Петрова](max://user/" in chat_message["message"]
    assert str(task.task_id) not in chat_message["message"]
    attachments = chat_message["attachments"]
    assert attachments[0]["payload"]["buttons"][0][0]["url"] == (
        "https://max.ru/secretary_oren_bot?startapp=task_1042"
    )


@pytest.mark.anyio
async def test_run_due_reminders_creates_overdue_chat_reminder() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    task.deadline_at = now - timedelta(minutes=10)
    notification_delivery_service = FakeNotificationDeliveryService()
    runner = ReminderJobRunner(
        service=FakeReminderService(
            now=now,
            task=task,
            user_id=task.created_by_user_id,
            overdue_chat_tasks=[task],
        ),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=FakeSender(),
        notification_delivery_service=notification_delivery_service,  # type: ignore[arg-type]
        task_deadline_chat_reminders_enabled=True,
    )

    result = await runner.run_due_reminders(now)

    assert result.reminders_sent == 1
    chat_message = notification_delivery_service.chat_messages[0]
    assert chat_message["reminder_type"] == ReminderType.TASK_OVERDUE.value
    assert "🔴 Срок по задаче #1042 истек" in chat_message["message"]
    assert "Текст: Prepare weekly report" in chat_message["message"]
    assert "Срок:" in chat_message["message"]


@pytest.mark.anyio
async def test_run_due_reminders_handles_assignee_without_max_user_id_in_chat_mention() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    task = make_task_payload(now)
    missing_user_id = task.assignee_ids[0]
    repository = FakeReminderRepository(
        user_ids=[],
        overdue_tasks=[],
        user_external_ids={missing_user_id: None},
        user_display_names={missing_user_id: "Без MAX"},
    )
    notification_delivery_service = FakeNotificationDeliveryService()
    runner = ReminderJobRunner(
        service=FakeReminderService(
            now=now,
            task=task,
            user_id=task.created_by_user_id,
            due_in_one_hour_tasks=[task],
        ),
        repository=repository,
        sender=FakeSender(),
        notification_delivery_service=notification_delivery_service,  # type: ignore[arg-type]
        task_deadline_chat_reminders_enabled=True,
    )

    await runner.run_due_reminders(now)

    chat_message = notification_delivery_service.chat_messages[0]["message"]
    assert "Исполнители: Без MAX" in chat_message
    assert "[@Без MAX](max://user/" not in chat_message


@pytest.mark.anyio
async def test_run_due_reminders_counts_failed_chat_reminder_and_continues() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    first_task = make_task_payload(now)
    second_task = make_task_payload(now)
    notification_delivery_service = FakeNotificationDeliveryService(status="failed")
    runner = ReminderJobRunner(
        service=FakeReminderService(
            now=now,
            task=first_task,
            user_id=first_task.created_by_user_id,
            due_in_one_hour_tasks=[first_task, second_task],
        ),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=FakeSender(),
        notification_delivery_service=notification_delivery_service,  # type: ignore[arg-type]
        task_deadline_chat_reminders_enabled=True,
    )

    result = await runner.run_due_reminders(now)

    assert result.reminders_failed == 2
    assert len(notification_delivery_service.chat_messages) == 2


@pytest.mark.anyio
async def test_run_daily_summary_sends_user_summary() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    task = make_task_payload(now)
    repository = FakeReminderRepository(user_ids=[user_id], overdue_tasks=[])
    sender = FakeSender(enabled=True, sent=True)
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=task, user_id=user_id),
        repository=repository,
        sender=sender,
    )

    result = await runner.run_daily_summary(date(2026, 5, 19))

    assert result.summaries_sent == 1
    assert result.reminders_sent == 1
    assert sender.messages == [
        {
            "chat_id": None,
            "user_id": _max_user_id(user_id),
            "text": "daily_summary: 2026-05-19\n"
            "my_tasks: 1\n"
            "created_by_me: 0\n"
            "observed_by_me: 0\n"
            "waiting_my_response: 0\n"
            "waiting_my_acceptance: 0\n"
            "overdue: 0\n"
            "today: 1",
            "reminder_type": ReminderType.DAILY_SUMMARY.value,
            "purpose": "reminder",
        }
    ]


@pytest.mark.anyio
async def test_run_daily_summary_skips_when_background_notifications_disabled() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    task = make_task_payload(now)
    repository = FakeReminderRepository(user_ids=[user_id], overdue_tasks=[])
    sender = FakeSender(enabled=True, sent=True)
    sender.background_enabled = False
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=task, user_id=user_id),
        repository=repository,
        sender=sender,
    )

    result = await runner.run_daily_summary(date(2026, 5, 19))

    assert result.summaries_sent == 0
    assert result.reminders_sent == 0
    assert sender.messages == []


@pytest.mark.anyio
async def test_run_daily_summary_ignores_snooze_state() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    task = make_task_payload(now)
    repository = FakeReminderRepository(user_ids=[user_id], overdue_tasks=[])
    sender = FakeSender()
    service = FakeReminderService(
        now=now,
        task=task,
        user_id=user_id,
        snoozed_pairs={(task.task_id, user_id)},
    )
    runner = ReminderJobRunner(
        service=service,
        repository=repository,
        sender=sender,
    )

    result = await runner.run_daily_summary(date(2026, 5, 19))

    assert result.summaries_sent == 1
    assert result.reminders_sent == 1
    assert sender.messages[0]["user_id"] == _max_user_id(user_id)
    assert service.snooze_checks == []


@pytest.mark.anyio
async def test_run_daily_manager_summaries_skips_disabled_chat(caplog: pytest.LogCaptureFixture) -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    manager_user_id = uuid4()
    chat = make_chat(members=[make_member(user_id=manager_user_id, role=ROLE_CHAT_ADMIN)])
    manager_repository = FakeManagerSummaryRepository(chats=[chat], tasks=[])
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=make_task_payload(now), user_id=manager_user_id),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=FakeSender(enabled=True, sent=True),
        manager_summary_repository=manager_repository,  # type: ignore[arg-type]
    )
    caplog.set_level(logging.INFO, logger="app.modules.reminders.jobs")

    result = await runner.run_daily_manager_summaries(date(2026, 5, 19), now)

    assert result.summaries_generated == 0
    assert result.summaries_sent == 0
    assert result.summaries_skipped == 1
    assert "Daily manager summary skipped" in caplog.text


@pytest.mark.anyio
async def test_run_daily_manager_summaries_generates_and_skips_empty_summary() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    manager_user_id = uuid4()
    chat = make_chat(
        settings={"daily_summary_enabled": True, "daily_summary_time": "09:00"},
        members=[make_member(user_id=manager_user_id, role=ROLE_CHAT_ADMIN)],
    )
    sender = FakeSender(enabled=True, sent=True)
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=make_task_payload(now), user_id=manager_user_id),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=sender,
        manager_summary_repository=FakeManagerSummaryRepository(chats=[chat], tasks=[]),  # type: ignore[arg-type]
    )

    result = await runner.run_daily_manager_summaries(date(2026, 5, 19), now)

    assert result.summaries_generated == 1
    assert result.summaries_sent == 0
    assert result.summaries_skipped == 1
    assert sender.messages == []


@pytest.mark.anyio
async def test_run_daily_manager_summaries_skips_send_when_sender_disabled() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    manager_user_id = uuid4()
    chat = make_chat(
        settings={"daily_summary_enabled": True, "daily_summary_time": "09:00"},
        members=[make_member(user_id=manager_user_id, role=ROLE_CHAT_ADMIN)],
    )
    task = make_manager_task(
        chat_id=chat.id,
        created_by_user_id=manager_user_id,
        status=TaskStatus.WAITING_RESPONSE,
        deadline_at=now,
    )
    sender = FakeSender(enabled=False, sent=True)
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=make_task_payload(now), user_id=manager_user_id),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=sender,
        manager_summary_repository=FakeManagerSummaryRepository(chats=[chat], tasks=[task]),  # type: ignore[arg-type]
    )

    result = await runner.run_daily_manager_summaries(date(2026, 5, 19), now)

    assert result.summaries_generated == 1
    assert result.summaries_sent == 0
    assert result.summaries_skipped == 1
    assert sender.messages == []


@pytest.mark.anyio
async def test_run_daily_manager_summaries_sends_to_configured_recipient() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    manager_user_id = uuid4()
    other_manager_id = uuid4()
    chat = make_chat(
        settings={
            "daily_summary_enabled": True,
            "daily_summary_time": "09:00",
            "daily_summary_recipients": [str(manager_user_id)],
        },
        members=[
            make_member(user_id=manager_user_id, role=ROLE_CHAT_ADMIN),
            make_member(user_id=other_manager_id, role=ROLE_CHAT_ADMIN),
        ],
    )
    task = make_manager_task(
        chat_id=chat.id,
        created_by_user_id=manager_user_id,
        status=TaskStatus.WAITING_ACCEPTANCE,
        deadline_at=now,
        assignee_ids=[uuid4(), uuid4()],
    )
    sender = FakeSender(enabled=True, sent=True)
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=make_task_payload(now), user_id=manager_user_id),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=sender,
        manager_summary_repository=FakeManagerSummaryRepository(chats=[chat], tasks=[task]),  # type: ignore[arg-type]
    )

    result = await runner.run_daily_manager_summaries(date(2026, 5, 19), now)

    assert result.summaries_generated == 1
    assert result.summaries_sent == 1
    assert result.reminders_sent == 1
    assert result.summaries_skipped == 0
    assert sender.messages == [
        {
            "chat_id": None,
            "user_id": _max_user_id(manager_user_id),
            "text": "daily_manager_summary: 2026-05-19\n"
            "chat: Project chat\n"
            "total_today: 1\n"
            "overdue: 0\n"
            "waiting_response: 0\n"
            "waiting_acceptance: 1\n"
            "top_overdue: 0\n"
            "pending_acceptance: 1",
            "reminder_type": ReminderType.DAILY_MANAGER_SUMMARY.value,
            "purpose": "reminder",
        }
    ]


@pytest.mark.anyio
async def test_mark_overdue_tasks_updates_repository_and_commits() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    overdue_task = SimpleNamespace(id=uuid4(), status=TaskStatus.IN_PROGRESS.value)
    repository = FakeReminderRepository(user_ids=[], overdue_tasks=[overdue_task])
    session = FakeSession()
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=make_task_payload(now), user_id=uuid4()),
        repository=repository,
        sender=FakeSender(),
        session=session,
    )

    result = await runner.mark_overdue_tasks(now)

    assert result.tasks_processed == 1
    assert result.tasks_marked_overdue == 1
    assert overdue_task.status == TaskStatus.OVERDUE.value
    assert repository.marked_tasks == [overdue_task]
    assert repository.mark_overdue_now == now
    assert session.committed is True


@pytest.mark.anyio
async def test_run_due_scheduled_tasks_uses_scheduled_service() -> None:
    now = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    scheduled_service = FakeScheduledTaskService()
    runner = ReminderJobRunner(
        service=FakeReminderService(now=now, task=make_task_payload(now), user_id=uuid4()),
        repository=FakeReminderRepository(user_ids=[], overdue_tasks=[]),
        sender=FakeSender(),
        scheduled_task_service=scheduled_service,  # type: ignore[arg-type]
    )

    result = await runner.run_due_scheduled_tasks(now)

    assert scheduled_service.run_calls == [now]
    assert result.scheduled_tasks_processed == 2
    assert result.scheduled_tasks_created == 1
    assert result.scheduled_tasks_failed == 1
    assert result.scheduled_tasks_deactivated == 1


def test_max_sender_logs_reminder_fields(caplog: pytest.LogCaptureFixture) -> None:
    sender = MaxSender()
    caplog.set_level(logging.INFO, logger="app.modules.notifications.max_sender")

    outbound = sender.send_message(
        chat_id="chat-1",
        user_id="user-1",
        text="Reminder text",
        reminder_type=ReminderType.BEFORE_DEADLINE.value,
    )

    assert outbound.chat_id == "chat-1"
    assert outbound.user_id == "user-1"
    assert outbound.text == "Reminder text"
    assert outbound.reminder_type == ReminderType.BEFORE_DEADLINE.value
    record = caplog.records[0]
    assert record.chat_id == "chat-1"
    assert record.user_id == "user-1"
    assert record.message_text == "Reminder text"
    assert record.reminder_type == ReminderType.BEFORE_DEADLINE.value
