from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.base import Base, import_all_models
from app.modules.bot.schemas import BotOutboundMessage
from app.modules.notifications.enums import DeliveryStatus
from app.modules.notifications.max_sender import OutboundPurpose
from app.modules.notifications.service import (
    BACKGROUND_DISABLED_ERROR,
    CHAT_DEADLINE_REMINDERS_DISABLED_ERROR,
    MAX_CHAT_CHANNEL,
    MAX_DM_CHANNEL,
    MAX_GROUP_FALLBACK_CHANNEL,
    MISSING_MAX_CHAT_ID_ERROR,
    MISSING_MAX_USER_ID_ERROR,
    NotificationDeliveryService,
)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commit_count += 1


class FakeNotificationRepository:
    def __init__(
        self,
        *,
        task: SimpleNamespace | None,
        users: dict[object, SimpleNamespace] | None = None,
        chats: dict[object, SimpleNamespace] | None = None,
    ) -> None:
        self.task = task
        self.users = users or {}
        self.chats = chats or {}
        self.deliveries: list[SimpleNamespace] = []
        self.recent_delivery: SimpleNamespace | None = None
        self.recent_queries: list[dict[str, object]] = []

    async def get_task(self, task_id):
        return self.task if self.task is not None and self.task.id == task_id else None

    async def get_user(self, user_id):
        return self.users.get(user_id)

    async def get_chat(self, chat_id):
        return self.chats.get(chat_id)

    async def create_delivery(
        self,
        *,
        task_id,
        user_id=None,
        chat_id=None,
        channel: str,
        reminder_type: str | None = None,
        status: DeliveryStatus = DeliveryStatus.PENDING,
    ) -> SimpleNamespace:
        delivery = SimpleNamespace(
            id=uuid4(),
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            channel=channel,
            reminder_type=reminder_type,
            status=status.value,
            error_code=None,
            error_message=None,
            sent_at=None,
        )
        self.deliveries.append(delivery)
        return delivery

    async def find_recent_delivery(
        self,
        *,
        task_id,
        user_id=None,
        chat_id=None,
        channel: str,
        reminder_type: str | None,
        since=None,
    ) -> SimpleNamespace | None:
        self.recent_queries.append(
            {
                "task_id": task_id,
                "user_id": user_id,
                "chat_id": chat_id,
                "channel": channel,
                "reminder_type": reminder_type,
                "since": since,
            }
        )
        return self.recent_delivery

    async def update_delivery(
        self,
        delivery: SimpleNamespace,
        *,
        status: DeliveryStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        sent_at=None,
    ) -> SimpleNamespace:
        delivery.status = status.value
        delivery.error_code = error_code
        delivery.error_message = error_message
        delivery.sent_at = sent_at
        return delivery


class FakeSender:
    def __init__(self, responses: list[BotOutboundMessage], *, enabled: bool = True) -> None:
        self.responses = responses
        self.enabled = enabled
        self.background_enabled = True
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
    ) -> BotOutboundMessage:
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
        return self.responses.pop(0)


def make_outbound(
    *,
    sent: bool,
    reason: str,
    chat_id: str | None = None,
    user_id: str | None = None,
) -> BotOutboundMessage:
    return BotOutboundMessage(
        adapter="max",
        method="send_message",
        chat_id=chat_id,
        user_id=user_id,
        text="Reminder",
        sent=sent,
        reason=reason,
    )


def make_task() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), chat_id=uuid4())


def make_user(user_id, *, max_user_id: str | None = "max-user-001") -> SimpleNamespace:
    return SimpleNamespace(id=user_id, max_user_id=max_user_id)


def make_chat(
    chat_id,
    *,
    max_chat_id: str | None = "max-chat-001",
    settings: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=chat_id,
        max_chat_id=max_chat_id,
        status="active",
        settings={"deadline_reminders_enabled": True} if settings is None else settings,
    )


def test_delivery_status_values() -> None:
    assert [status.value for status in DeliveryStatus] == [
        "pending",
        "sent",
        "failed",
        "dm_unavailable",
        "skipped",
    ]


def test_notification_delivery_model_columns() -> None:
    import_all_models()
    table = Base.metadata.tables["notification_deliveries"]

    assert set(table.columns.keys()) >= {
        "id",
        "task_id",
        "user_id",
        "chat_id",
        "channel",
        "reminder_type",
        "status",
        "error_code",
        "error_message",
        "created_at",
        "sent_at",
    }
    assert table.columns["error_code"].nullable is True
    assert table.columns["error_message"].nullable is True
    assert table.columns["reminder_type"].nullable is True
    assert table.columns["user_id"].nullable is True
    assert table.columns["chat_id"].nullable is True
    assert table.columns["sent_at"].nullable is True
    assert table.columns["status"].default.arg == DeliveryStatus.PENDING.value
    assert table.columns["status"].server_default.arg == DeliveryStatus.PENDING.value
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == {
        "tasks.id",
        "users.id",
        "chats.id",
    }


@pytest.mark.anyio
async def test_send_personal_task_notification_records_sent_dm() -> None:
    task = make_task()
    user_id = uuid4()
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id="max-user-001")},
    )
    sender = FakeSender([make_outbound(sent=True, reason="sent via MAX API", user_id="max-user-001")])
    session = FakeSession()
    service = NotificationDeliveryService(repository=repository, sender=sender, session=session)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Reminder",
    )

    assert result.status is DeliveryStatus.SENT
    assert result.fallback_delivery is None
    assert repository.deliveries[0].channel == MAX_DM_CHANNEL
    assert repository.deliveries[0].status == DeliveryStatus.SENT.value
    assert repository.deliveries[0].sent_at is not None
    assert sender.messages == [
        {
            "chat_id": None,
            "user_id": "max-user-001",
            "text": "Reminder",
            "reminder_type": None,
            "purpose": "reminder",
        }
    ]
    assert session.commit_count == 1


@pytest.mark.anyio
async def test_send_personal_task_notification_falls_back_to_group_if_dm_unavailable() -> None:
    task = make_task()
    user_id = uuid4()
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id="max-user-001")},
        chats={task.chat_id: make_chat(task.chat_id, max_chat_id="max-chat-001")},
    )
    sender = FakeSender(
        [
            make_outbound(sent=False, reason="dm_unavailable", user_id="max-user-001"),
            make_outbound(sent=True, reason="sent via MAX API", chat_id="max-chat-001"),
        ]
    )
    session = FakeSession()
    service = NotificationDeliveryService(repository=repository, sender=sender, session=session)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Reminder",
    )

    assert result.status is DeliveryStatus.SENT
    assert result.primary_delivery.status == DeliveryStatus.DM_UNAVAILABLE.value
    assert result.fallback_delivery is not None
    assert result.fallback_delivery.channel == MAX_GROUP_FALLBACK_CHANNEL
    assert result.fallback_delivery.status == DeliveryStatus.SENT.value
    assert sender.messages == [
        {
            "chat_id": None,
            "user_id": "max-user-001",
            "text": "Reminder",
            "reminder_type": None,
            "purpose": "reminder",
        },
        {
            "chat_id": "max-chat-001",
            "user_id": None,
            "text": "Reminder",
            "reminder_type": None,
            "purpose": "reminder",
        },
    ]
    assert session.commit_count == 1


@pytest.mark.anyio
async def test_send_personal_task_notification_records_failure_without_fallback() -> None:
    task = make_task()
    user_id = uuid4()
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id="max-user-001")},
    )
    sender = FakeSender([make_outbound(sent=False, reason="MAX API returned HTTP 500.")])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Reminder",
    )

    assert result.status is DeliveryStatus.FAILED
    assert result.primary_delivery.status == DeliveryStatus.FAILED.value
    assert result.primary_delivery.error_code == "send_failed"
    assert result.primary_delivery.error_message == "MAX API returned HTTP 500."
    assert result.fallback_delivery is None
    assert len(sender.messages) == 1


@pytest.mark.anyio
async def test_send_personal_task_notification_skips_user_without_max_user_id() -> None:
    task = make_task()
    user_id = uuid4()
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id=None)},
    )
    sender = FakeSender([])
    session = FakeSession()
    service = NotificationDeliveryService(repository=repository, sender=sender, session=session)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Reminder",
    )

    assert result.status is DeliveryStatus.DM_UNAVAILABLE
    assert result.primary_delivery.status == DeliveryStatus.DM_UNAVAILABLE.value
    assert result.primary_delivery.error_code == MISSING_MAX_USER_ID_ERROR
    assert result.fallback_delivery is None
    assert sender.messages == []
    assert session.commit_count == 1


@pytest.mark.anyio
async def test_send_personal_task_notification_records_sender_disabled_skip() -> None:
    task = make_task()
    user_id = uuid4()
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id="max-user-001")},
    )
    sender = FakeSender([], enabled=False)
    session = FakeSession()
    service = NotificationDeliveryService(repository=repository, sender=sender, session=session)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Reminder",
        reminder_type="after_deadline",
    )

    assert result.status is DeliveryStatus.SKIPPED
    assert result.primary_delivery.status == DeliveryStatus.SKIPPED.value
    assert result.primary_delivery.reminder_type == "after_deadline"
    assert result.primary_delivery.error_code == "sender_disabled"
    assert sender.messages == []
    assert session.commit_count == 1


@pytest.mark.anyio
async def test_send_personal_task_notification_records_background_disabled_skip() -> None:
    task = make_task()
    user_id = uuid4()
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id="max-user-001")},
    )
    sender = FakeSender([], enabled=True)
    sender.background_enabled = False
    session = FakeSession()
    service = NotificationDeliveryService(repository=repository, sender=sender, session=session)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Reminder",
        reminder_type="after_deadline",
    )

    assert result.status is DeliveryStatus.SKIPPED
    assert result.primary_delivery.status == DeliveryStatus.SKIPPED.value
    assert result.primary_delivery.error_code == BACKGROUND_DISABLED_ERROR
    assert sender.messages == []
    assert session.commit_count == 1


@pytest.mark.anyio
async def test_send_personal_task_notification_can_use_ping_purpose_and_buttons() -> None:
    task = make_task()
    user_id = uuid4()
    attachments = [{"type": "inline_keyboard", "payload": {"buttons": [[{"text": "Открыть задачу"}]]}}]
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id="max-user-001")},
    )
    sender = FakeSender([make_outbound(sent=True, reason="sent via MAX API", user_id="max-user-001")])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Ping",
        reminder_type="task_ping",
        attachments=attachments,
        purpose=OutboundPurpose.PING,
        allow_group_fallback=False,
    )

    assert result.status is DeliveryStatus.SENT
    assert repository.deliveries[0].reminder_type == "task_ping"
    assert sender.messages == [
        {
            "chat_id": None,
            "user_id": "max-user-001",
            "text": "Ping",
            "reminder_type": "task_ping",
            "purpose": "ping",
            "attachments": attachments,
        }
    ]


@pytest.mark.anyio
async def test_send_personal_task_notification_can_disable_group_fallback_for_ping() -> None:
    task = make_task()
    user_id = uuid4()
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id="max-user-001")},
        chats={task.chat_id: make_chat(task.chat_id, max_chat_id="max-chat-001")},
    )
    sender = FakeSender([make_outbound(sent=False, reason="dm_unavailable", user_id="max-user-001")])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Ping",
        reminder_type="task_ping",
        purpose=OutboundPurpose.PING,
        allow_group_fallback=False,
    )

    assert result.status is DeliveryStatus.DM_UNAVAILABLE
    assert result.fallback_delivery is None
    assert len(repository.deliveries) == 1
    assert sender.messages == [
        {
            "chat_id": None,
            "user_id": "max-user-001",
            "text": "Ping",
            "reminder_type": "task_ping",
            "purpose": "ping",
        }
    ]


@pytest.mark.anyio
async def test_send_personal_task_notification_skips_recent_duplicate_without_new_row() -> None:
    task = make_task()
    user_id = uuid4()
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id="max-user-001")},
    )
    repository.recent_delivery = SimpleNamespace(
        id=uuid4(),
        task_id=task.id,
        user_id=user_id,
        channel=MAX_DM_CHANNEL,
        reminder_type="after_deadline",
        status=DeliveryStatus.SKIPPED.value,
        error_code="sender_disabled",
        error_message="MAX sender is disabled.",
        sent_at=None,
    )
    sender = FakeSender([], enabled=True)
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Reminder",
        reminder_type="after_deadline",
    )

    assert result.status is DeliveryStatus.SKIPPED
    assert result.primary_delivery is repository.recent_delivery
    assert repository.deliveries == []
    assert sender.messages == []


@pytest.mark.anyio
async def test_send_personal_task_notification_skips_group_fallback_without_max_chat_id() -> None:
    task = make_task()
    user_id = uuid4()
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id="max-user-001")},
        chats={task.chat_id: make_chat(task.chat_id, max_chat_id=None)},
    )
    sender = FakeSender([make_outbound(sent=False, reason="dm_unavailable", user_id="max-user-001")])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Reminder",
    )

    assert result.status is DeliveryStatus.FAILED
    assert result.fallback_delivery is not None
    assert result.fallback_delivery.status == DeliveryStatus.FAILED.value
    assert result.fallback_delivery.error_code == MISSING_MAX_CHAT_ID_ERROR
    assert sender.messages == [
        {
            "chat_id": None,
            "user_id": "max-user-001",
            "text": "Reminder",
            "reminder_type": None,
            "purpose": "reminder",
        }
    ]


@pytest.mark.anyio
async def test_send_personal_task_notification_masks_sensitive_error_message() -> None:
    task = make_task()
    user_id = uuid4()
    repository = FakeNotificationRepository(
        task=task,
        users={user_id: make_user(user_id, max_user_id="max-user-001")},
    )
    sender = FakeSender(
        [
            make_outbound(
                sent=False,
                reason="failed token=secret password=secret webhook/abcdef",
            )
        ]
    )
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_personal_task_notification(
        user_id=user_id,
        task_id=task.id,
        message="Reminder",
    )

    assert result.primary_delivery.error_message == (
        "failed token=<redacted> password=<redacted> webhook/<redacted>"
    )


@pytest.mark.anyio
async def test_send_personal_task_notification_returns_404_for_missing_task() -> None:
    repository = FakeNotificationRepository(task=None)
    sender = FakeSender([make_outbound(sent=True, reason="sent via MAX API")])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    with pytest.raises(HTTPException) as exc_info:
        await service.send_personal_task_notification(
            user_id=uuid4(),
            task_id=uuid4(),
            message="Reminder",
        )

    assert getattr(exc_info.value, "status_code") == 404


@pytest.mark.anyio
async def test_send_chat_task_notification_records_sent_chat_message() -> None:
    task = make_task()
    repository = FakeNotificationRepository(
        task=task,
        chats={task.chat_id: make_chat(task.chat_id, max_chat_id="max-chat-001")},
    )
    sender = FakeSender([make_outbound(sent=True, reason="sent via MAX API", chat_id="max-chat-001")])
    session = FakeSession()
    service = NotificationDeliveryService(repository=repository, sender=sender, session=session)  # type: ignore[arg-type]
    attachments = [{"type": "inline_keyboard", "payload": {"buttons": [[{"text": "Открыть задачу"}]]}}]

    result = await service.send_chat_task_notification(
        chat_id=task.chat_id,
        task_id=task.id,
        message="По задаче #1042 остался 1 час.",
        reminder_type="task_due_in_1h",
        attachments=attachments,
    )

    assert result.status is DeliveryStatus.SENT
    assert result.chat_id == task.chat_id
    assert result.user_id is None
    assert repository.deliveries[0].channel == MAX_CHAT_CHANNEL
    assert repository.deliveries[0].chat_id == task.chat_id
    assert repository.deliveries[0].user_id is None
    assert sender.messages == [
        {
            "chat_id": "max-chat-001",
            "user_id": None,
            "text": "По задаче #1042 остался 1 час.",
            "reminder_type": "task_due_in_1h",
            "purpose": "reminder",
            "attachments": attachments,
        }
    ]
    assert session.commit_count == 1


@pytest.mark.anyio
async def test_send_chat_task_notification_skips_when_background_disabled() -> None:
    task = make_task()
    repository = FakeNotificationRepository(
        task=task,
        chats={task.chat_id: make_chat(task.chat_id, max_chat_id="max-chat-001")},
    )
    sender = FakeSender([], enabled=True)
    sender.background_enabled = False
    session = FakeSession()
    service = NotificationDeliveryService(repository=repository, sender=sender, session=session)  # type: ignore[arg-type]

    result = await service.send_chat_task_notification(
        chat_id=task.chat_id,
        task_id=task.id,
        message="Reminder",
        reminder_type="task_overdue",
    )

    assert result.status is DeliveryStatus.SKIPPED
    assert result.primary_delivery.status == DeliveryStatus.SKIPPED.value
    assert result.primary_delivery.error_code == BACKGROUND_DISABLED_ERROR
    assert result.primary_delivery.channel == MAX_CHAT_CHANNEL
    assert sender.messages == []
    assert session.commit_count == 1


@pytest.mark.anyio
async def test_send_chat_task_notification_skips_without_max_chat_id() -> None:
    task = make_task()
    repository = FakeNotificationRepository(
        task=task,
        chats={task.chat_id: make_chat(task.chat_id, max_chat_id=None)},
    )
    sender = FakeSender([])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_chat_task_notification(
        chat_id=task.chat_id,
        task_id=task.id,
        message="Reminder",
        reminder_type="task_overdue",
    )

    assert result.status is DeliveryStatus.SKIPPED
    assert result.primary_delivery.error_code == MISSING_MAX_CHAT_ID_ERROR
    assert sender.messages == []


@pytest.mark.anyio
async def test_send_chat_task_notification_skips_inactive_chat() -> None:
    task = make_task()
    inactive_chat = make_chat(task.chat_id, max_chat_id="max-chat-001")
    inactive_chat.status = "pending_approval"
    repository = FakeNotificationRepository(
        task=task,
        chats={task.chat_id: inactive_chat},
    )
    sender = FakeSender([])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_chat_task_notification(
        chat_id=task.chat_id,
        task_id=task.id,
        message="Reminder",
        reminder_type="task_overdue",
    )

    assert result.status is DeliveryStatus.SKIPPED
    assert result.primary_delivery.error_code == "chat_not_active"
    assert sender.messages == []


@pytest.mark.anyio
async def test_send_chat_deadline_notification_skips_when_chat_setting_disabled() -> None:
    task = make_task()
    repository = FakeNotificationRepository(
        task=task,
        chats={task.chat_id: make_chat(task.chat_id, settings={})},
    )
    sender = FakeSender([])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_chat_task_notification(
        chat_id=task.chat_id,
        task_id=task.id,
        message="Reminder",
        reminder_type="task_due_in_1h",
    )

    assert result.status is DeliveryStatus.SKIPPED
    assert result.primary_delivery.error_code == CHAT_DEADLINE_REMINDERS_DISABLED_ERROR
    assert sender.messages == []


@pytest.mark.anyio
async def test_send_chat_task_ping_ignores_deadline_reminder_chat_setting() -> None:
    task = make_task()
    repository = FakeNotificationRepository(
        task=task,
        chats={task.chat_id: make_chat(task.chat_id, settings={})},
    )
    sender = FakeSender([make_outbound(sent=True, reason="sent via MAX API", chat_id="max-chat-001")])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_chat_task_notification(
        chat_id=task.chat_id,
        task_id=task.id,
        message="Ping",
        reminder_type="task_ping",
        purpose=OutboundPurpose.PING,
    )

    assert result.status is DeliveryStatus.SENT
    assert sender.messages[0]["reminder_type"] == "task_ping"


@pytest.mark.anyio
async def test_send_chat_task_notification_dedups_existing_delivery() -> None:
    task = make_task()
    repository = FakeNotificationRepository(task=task)
    repository.recent_delivery = SimpleNamespace(
        id=uuid4(),
        task_id=task.id,
        user_id=None,
        chat_id=task.chat_id,
        channel=MAX_CHAT_CHANNEL,
        reminder_type="task_overdue",
        status=DeliveryStatus.SKIPPED.value,
        error_code=BACKGROUND_DISABLED_ERROR,
        error_message="MAX background notifications are disabled.",
        sent_at=None,
    )
    sender = FakeSender([])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]

    result = await service.send_chat_task_notification(
        chat_id=task.chat_id,
        task_id=task.id,
        message="Reminder",
        reminder_type="task_overdue",
    )

    assert result.status is DeliveryStatus.SKIPPED
    assert result.primary_delivery is repository.recent_delivery
    assert repository.deliveries == []
    assert sender.messages == []


@pytest.mark.anyio
async def test_send_chat_task_notification_uses_custom_dedup_since() -> None:
    task = make_task()
    repository = FakeNotificationRepository(
        task=task,
        chats={task.chat_id: make_chat(task.chat_id, max_chat_id="max-chat-001")},
    )
    sender = FakeSender([make_outbound(sent=True, reason="sent via MAX API", chat_id="max-chat-001")])
    service = NotificationDeliveryService(repository=repository, sender=sender)  # type: ignore[arg-type]
    dedup_since = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)

    result = await service.send_chat_task_notification(
        chat_id=task.chat_id,
        task_id=task.id,
        message="Ping",
        reminder_type="task_ping",
        purpose=OutboundPurpose.PING,
        dedup_since=dedup_since,
    )

    assert result.status is DeliveryStatus.SENT
    assert repository.recent_queries[0]["channel"] == MAX_CHAT_CHANNEL
    assert repository.recent_queries[0]["reminder_type"] == "task_ping"
    assert repository.recent_queries[0]["since"] == dedup_since
