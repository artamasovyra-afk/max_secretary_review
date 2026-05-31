from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.modules.bot.callback_service import (
    BotCallbackForbidden,
    BotCallbackService,
    NormalizedCallbackEvent,
)
from app.modules.bot.callbacks import (
    build_callback_payload,
    build_task_assignment_callback_payload,
    build_task_report_callback_payload,
)
from app.modules.tasks.enums import TaskAssigneeStatus, TaskResponseStatus


TASK_ID = UUID("11111111-1111-4111-8111-111111111111")
SECOND_TASK_ID = UUID("11111111-1111-4111-8111-111111111112")
RESPONSE_ID = UUID("22222222-2222-4222-8222-222222222222")
CREATOR_ID = UUID("33333333-3333-4333-8333-333333333333")
ASSIGNEE_ID = UUID("44444444-4444-4444-8444-444444444444")
OBSERVER_ID = UUID("55555555-5555-4555-8555-555555555555")
OUTSIDER_ID = UUID("66666666-6666-4666-8666-666666666666")
SECOND_ASSIGNEE_ID = UUID("77777777-7777-4777-8777-777777777777")
ORG_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CHAT_ID = UUID("99999999-9999-4999-8999-999999999999")
NOW = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)


class FakeTaskService:
    def __init__(self) -> None:
        self.task = SimpleNamespace(
            id=TASK_ID,
            organization_id=ORG_ID,
            chat_id=CHAT_ID,
            task_number=1042,
            title="Отчетная задача",
            status="in_progress",
            created_by_user_id=CREATOR_ID,
            assignees=[SimpleNamespace(user_id=ASSIGNEE_ID, status=TaskAssigneeStatus.ASSIGNED.value)],
            observers=[SimpleNamespace(user_id=OBSERVER_ID)],
            responses=[SimpleNamespace(id=RESPONSE_ID, status=TaskResponseStatus.SUBMITTED.value)],
        )
        self.tasks: dict[UUID, SimpleNamespace] = {TASK_ID: self.task}
        self.started: tuple[UUID, UUID] | None = None
        self.submitted: tuple[UUID, object] | None = None
        self.accepted: tuple[UUID, UUID, object] | None = None
        self.rejected: tuple[UUID, UUID, object] | None = None
        self.accept_auth_context: object | None = None
        self.reject_auth_context: object | None = None
        self.start_count = 0
        self.submit_count = 0
        self.accept_count = 0
        self.reject_count = 0
        self.created_payloads: list[object] = []

    async def get(self, task_id: UUID) -> SimpleNamespace:
        assert task_id in self.tasks
        return self.tasks[task_id]

    async def create(self, payload: object) -> SimpleNamespace:
        self.created_payloads.append(payload)
        task = SimpleNamespace(
            id=SECOND_TASK_ID,
            task_number=2001,
            title=payload.title,
            status="new",
            created_by_user_id=payload.created_by_user_id,
            assignees=[SimpleNamespace(user_id=user_id, status=TaskAssigneeStatus.ASSIGNED.value) for user_id in payload.assignee_ids],
            observers=[],
            responses=[],
        )
        self.tasks[SECOND_TASK_ID] = task
        return task

    async def start_assignee_task(self, task_id: UUID, user_id: UUID) -> SimpleNamespace:
        self.start_count += 1
        self.started = (task_id, user_id)
        task = self.tasks[task_id]
        for assignee in task.assignees:
            if assignee.user_id == user_id:
                assignee.status = TaskAssigneeStatus.IN_PROGRESS.value
        return task

    async def submit_response(self, task_id: UUID, payload: object) -> SimpleNamespace:
        self.submit_count += 1
        self.submitted = (task_id, payload)
        task = self.tasks[task_id]
        for assignee in task.assignees:
            if assignee.user_id == payload.user_id:
                assignee.status = TaskAssigneeStatus.RESPONDED.value
        return SimpleNamespace(id=RESPONSE_ID)

    async def accept_response(
        self,
        task_id: UUID,
        response_id: UUID,
        payload: object,
        *,
        auth_context: object | None = None,
    ) -> SimpleNamespace:
        self.accept_count += 1
        self.accepted = (task_id, response_id, payload)
        self.accept_auth_context = auth_context
        for response in self.tasks[task_id].responses:
            if response.id == response_id:
                response.status = TaskResponseStatus.ACCEPTED.value
        return SimpleNamespace(response_id=response_id)

    async def reject_response(
        self,
        task_id: UUID,
        response_id: UUID,
        payload: object,
        *,
        auth_context: object | None = None,
    ) -> SimpleNamespace:
        self.reject_count += 1
        self.rejected = (task_id, response_id, payload)
        self.reject_auth_context = auth_context
        for response in self.tasks[task_id].responses:
            if response.id == response_id:
                response.status = TaskResponseStatus.REJECTED.value
        return SimpleNamespace(response_id=response_id)


class FakeReminderService:
    def __init__(self, *, now: datetime = NOW) -> None:
        self.now = now
        self.snoozes: list[SimpleNamespace] = []

    async def create_snooze(
        self,
        task_id: UUID,
        user_id: UUID,
        duration: str,
        *,
        reason: str | None = None,
    ) -> SimpleNamespace:
        snooze = SimpleNamespace(
            task_id=task_id,
            user_id=user_id,
            duration=duration,
            snoozed_until=self._snoozed_until(duration),
            reason=reason,
        )
        self.snoozes.append(snooze)
        return snooze

    def _snoozed_until(self, duration: str) -> datetime:
        if duration == "1h":
            return self.now + timedelta(hours=1)
        if duration == "tomorrow_09":
            tomorrow = (self.now + timedelta(days=1)).date()
            return datetime.combine(tomorrow, datetime.min.time().replace(hour=9), tzinfo=timezone.utc)
        raise AssertionError(f"Unexpected snooze duration: {duration}")


class FakeCallbackReceiptRepository:
    def __init__(self) -> None:
        self.receipts: dict[str, SimpleNamespace] = {}
        self.started: list[tuple[str, str]] = []
        self.logical_contexts: list[tuple[str, str]] = []
        self.succeeded: list[tuple[str, str]] = []
        self.logical_duplicates: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str]] = []

    async def start(self, *, callback_id: str, payload: str) -> tuple[SimpleNamespace, bool]:
        if callback_id in self.receipts:
            return self.receipts[callback_id], False
        receipt = SimpleNamespace(
            callback_id=callback_id,
            payload=payload,
            status="processing",
            response_text=None,
            last_error=None,
            created_at=datetime.now(timezone.utc),
            logical_key=None,
            logical_status=None,
        )
        self.receipts[callback_id] = receipt
        self.started.append((callback_id, payload))
        return receipt, True

    async def set_logical_context(
        self,
        receipt: SimpleNamespace,
        *,
        provider: str,
        actor_user_id: UUID,
        task_id: UUID,
        action_type: str,
        payload_normalized: str,
        logical_key: str,
        logical_window_started_at: datetime,
    ) -> SimpleNamespace:
        receipt.provider = provider
        receipt.actor_user_id = actor_user_id
        receipt.task_id = task_id
        receipt.action_type = action_type
        receipt.payload_normalized = payload_normalized
        receipt.logical_key = logical_key
        receipt.logical_window_started_at = logical_window_started_at
        receipt.logical_status = "processing"
        self.logical_contexts.append((receipt.callback_id, logical_key))
        return receipt

    async def find_recent_logical_duplicate(
        self,
        *,
        logical_key: str,
        since: datetime,
        exclude_callback_id: str,
    ) -> SimpleNamespace | None:
        for receipt in sorted(self.receipts.values(), key=lambda item: item.created_at, reverse=True):
            if receipt.callback_id == exclude_callback_id:
                continue
            if receipt.logical_key != logical_key:
                continue
            if receipt.created_at < since:
                continue
            if receipt.status not in {"processing", "succeeded"}:
                continue
            if receipt.logical_status not in {"processing", "processed"}:
                continue
            return receipt
        return None

    async def mark_succeeded(self, receipt: SimpleNamespace, *, response_text: str) -> SimpleNamespace:
        receipt.status = "succeeded"
        if receipt.logical_key is not None:
            receipt.logical_status = "processed"
        receipt.response_text = response_text
        self.succeeded.append((receipt.callback_id, response_text))
        return receipt

    async def mark_logical_duplicate(self, receipt: SimpleNamespace, *, response_text: str) -> SimpleNamespace:
        receipt.status = "skipped"
        receipt.logical_status = "duplicate_logical"
        receipt.response_text = response_text
        self.logical_duplicates.append((receipt.callback_id, response_text))
        return receipt

    async def mark_failed(self, receipt: SimpleNamespace, *, error: str) -> SimpleNamespace:
        receipt.status = "failed"
        if receipt.logical_key is not None:
            receipt.logical_status = "failed"
        receipt.last_error = error
        self.failed.append((receipt.callback_id, error))
        return receipt


class FakePendingActionRepository:
    def __init__(self, pending: SimpleNamespace | None = None) -> None:
        self.pending = pending
        self.completed: list[tuple[UUID, UUID, str | None]] = []
        self.expired: list[UUID] = []
        self.cleanup_results: list[tuple[UUID, str, str | None]] = []
        self.report_created: list[SimpleNamespace] = []
        self.reject_reason_created: list[SimpleNamespace] = []

    async def get(self, action_id: UUID) -> SimpleNamespace | None:
        if self.pending is not None and self.pending.id == action_id:
            return self.pending
        return None

    async def mark_completed(
        self,
        action: SimpleNamespace,
        *,
        task_id: UUID,
        selected_assignee_user_id: UUID,
        picker_message_id: str | None = None,
    ) -> SimpleNamespace:
        action.status = "completed"
        action.completed_task_id = task_id
        action.selected_assignee_user_id = selected_assignee_user_id
        action.picker_message_id = picker_message_id
        self.completed.append((task_id, selected_assignee_user_id, picker_message_id))
        return action

    async def mark_expired(self, action: SimpleNamespace) -> SimpleNamespace:
        action.status = "expired"
        self.expired.append(action.id)
        return action

    async def mark_cleanup_result(
        self,
        action_id: UUID,
        *,
        status: str,
        error: str | None = None,
    ) -> SimpleNamespace | None:
        self.cleanup_results.append((action_id, status, error))
        if self.pending is not None and self.pending.id == action_id:
            self.pending.cleanup_status = status
            self.pending.cleanup_error = error
            return self.pending
        return None

    async def create_task_report_submit(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        task_id: UUID,
        task_ref: str,
        title: str,
        source_message_id: str | None,
        expires_at: datetime,
        reply_context: dict | None = None,
        wizard_message_id: str | None = None,
    ) -> SimpleNamespace:
        context = dict(reply_context or {})
        context["task_id"] = str(task_id)
        context["task_ref"] = task_ref
        action = SimpleNamespace(
            id=UUID("12121212-1212-4212-8212-121212121212"),
            action_type="task_report_submit",
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            completed_task_id=None,
            title=title,
            source_message_id=source_message_id,
            reply_context=context,
            expires_at=expires_at,
            status="pending",
            picker_message_id=wizard_message_id,
            cleanup_status=None,
            cleanup_error=None,
        )
        self.report_created.append(action)
        return action

    async def create_task_acceptance_reject_reason(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
        task_id: UUID,
        response_id: UUID,
        task_ref: str,
        title: str,
        source_message_id: str | None,
        expires_at: datetime,
    ) -> SimpleNamespace:
        action = SimpleNamespace(
            id=UUID("13131313-1313-4313-8313-131313131313"),
            action_type="task_acceptance_reject_reason",
            actor_user_id=actor_user_id,
            chat_id=chat_id,
            completed_task_id=None,
            title=title,
            source_message_id=source_message_id,
            reply_context={
                "task_id": str(task_id),
                "response_id": str(response_id),
                "task_ref": task_ref,
            },
            expires_at=expires_at,
            status="pending",
        )
        self.reject_reason_created.append(action)
        return action


class FakeChatRepository:
    def __init__(self, *, chat: SimpleNamespace, members: dict[UUID, SimpleNamespace]) -> None:
        self.chat = chat
        self.members = members

    async def get_chat(self, chat_id: UUID) -> SimpleNamespace | None:
        if chat_id == self.chat.id:
            return self.chat
        return None

    async def get_member(self, *, chat_id: UUID, user_id: UUID) -> SimpleNamespace | None:
        if chat_id != self.chat.id:
            return None
        return self.members.get(user_id)


@pytest.fixture()
def task_service() -> FakeTaskService:
    return FakeTaskService()


@pytest.fixture()
def reminder_service() -> FakeReminderService:
    return FakeReminderService()


@pytest.fixture()
def callback_service(
    task_service: FakeTaskService,
    reminder_service: FakeReminderService,
) -> BotCallbackService:
    return BotCallbackService(
        task_service=task_service,
        reminder_service=reminder_service,  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        pending_action_repository=FakePendingActionRepository(),
    )


def pending_action(*, status: str = "pending", expires_at: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID("88888888-8888-4888-8888-888888888888"),
        action_type="task_create_select_assignee",
        actor_user_id=CREATOR_ID,
        chat_id=CHAT_ID,
        source_message_id="mock-source-message",
        title="Подготовить отчет",
        source_text="Подготовить отчет до пятницы",
        description="Команда MAX: mock-source-message",
        deadline_at=datetime(2026, 5, 22, 18, 0, tzinfo=timezone.utc),
        reply_context=None,
        expires_at=expires_at or datetime.now(timezone.utc) + timedelta(minutes=30),
        status=status,
        completed_task_id=SECOND_TASK_ID if status == "completed" else None,
        selected_assignee_user_id=ASSIGNEE_ID if status == "completed" else None,
        picker_message_id=None,
        cleanup_status=None,
        cleanup_error=None,
    )


def assignment_callback_service(
    *,
    task_service: FakeTaskService,
    pending_repository: FakePendingActionRepository,
    member: SimpleNamespace | None = None,
    creator_role: str = "chat_admin",
    receipt_repository: FakeCallbackReceiptRepository | None = None,
) -> BotCallbackService:
    chat = SimpleNamespace(id=CHAT_ID, organization_id=uuid_org())
    assignee_member = member or SimpleNamespace(
        user_id=ASSIGNEE_ID,
        is_active=True,
        user=SimpleNamespace(id=ASSIGNEE_ID, display_name="Иван", username="ivan"),
    )
    creator_member = SimpleNamespace(
        user_id=CREATOR_ID,
        is_active=True,
        role=creator_role,
        user=SimpleNamespace(id=CREATOR_ID, display_name="Постановщик", username="creator"),
    )
    return BotCallbackService(
        task_service=task_service,
        reminder_service=FakeReminderService(),  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        receipt_repository=receipt_repository,
        pending_action_repository=pending_repository,
        chat_repository=FakeChatRepository(
            chat=chat,
            members={
                ASSIGNEE_ID: assignee_member,
                CREATOR_ID: creator_member,
            },
        ),
    )


def uuid_org() -> UUID:
    return ORG_ID


def event(
    payload: str,
    *,
    user_id: UUID = ASSIGNEE_ID,
    chat_id: UUID | None = CHAT_ID,
) -> NormalizedCallbackEvent:
    return NormalizedCallbackEvent(
        payload=payload,
        user_id=user_id,
        chat_id=chat_id,
        message_id="mock-callback-message",
    )


def callback_event(
    payload: str,
    *,
    user_id: UUID = CREATOR_ID,
    callback_id: str = "mock-callback-id",
    chat_id: UUID | None = None,
) -> NormalizedCallbackEvent:
    return NormalizedCallbackEvent(
        payload=payload,
        user_id=user_id,
        chat_id=chat_id,
        message_id="mock-callback-message",
        callback_id=callback_id,
    )


@pytest.mark.anyio
async def test_report_start_callback_creates_pending_report(task_service: FakeTaskService) -> None:
    pending_repository = FakePendingActionRepository()
    service = BotCallbackService(
        task_service=task_service,
        reminder_service=FakeReminderService(),  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        pending_action_repository=pending_repository,
    )

    result = await service.handle_event(
        NormalizedCallbackEvent(
            payload=build_task_report_callback_payload(TASK_ID),
            user_id=ASSIGNEE_ID,
            chat_id=UUID("99999999-9999-4999-8999-999999999999"),
            message_id="mock-message-id",
        )
    )

    assert result.action == "report"
    assert result.task_id == TASK_ID
    assert result.response_text == "Напишите отчет по задаче #1042 одним сообщением."
    assert result.pending_action_id == UUID("12121212-1212-4212-8212-121212121212")
    assert result.answer_message_text == "/отчет #1042\n\nНапишите отчет по задаче #1042 одним сообщением."
    assert len(pending_repository.report_created) == 1
    pending = pending_repository.report_created[0]
    assert pending.actor_user_id == ASSIGNEE_ID
    assert pending.reply_context == {"task_id": str(TASK_ID), "task_ref": "#1042"}


@pytest.mark.anyio
async def test_report_start_callback_denies_non_assignee(task_service: FakeTaskService) -> None:
    service = BotCallbackService(
        task_service=task_service,
        reminder_service=FakeReminderService(),  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        pending_action_repository=FakePendingActionRepository(),
    )

    with pytest.raises(BotCallbackForbidden):
        await service.handle_event(
            NormalizedCallbackEvent(
                payload=build_task_report_callback_payload(TASK_ID),
                user_id=OUTSIDER_ID,
                chat_id=UUID("99999999-9999-4999-8999-999999999999"),
            )
        )


@pytest.mark.anyio
async def test_assign_callback_creates_task_for_selected_assignee(task_service: FakeTaskService) -> None:
    pending = pending_action()
    pending_repository = FakePendingActionRepository(pending)
    service = assignment_callback_service(task_service=task_service, pending_repository=pending_repository)

    result = await service.handle_event(
        callback_event(
            build_task_assignment_callback_payload(
                pending_action_id=pending.id,
                assignee_id=ASSIGNEE_ID,
            )
        )
    )

    assert result.action == "assign"
    assert result.task_id == SECOND_TASK_ID
    assert result.response_text == "Исполнитель назначен: Иван."
    assert len(task_service.created_payloads) == 1
    payload = task_service.created_payloads[0]
    assert payload.title == pending.title
    assert payload.chat_id == pending.chat_id
    assert payload.created_by_user_id == CREATOR_ID
    assert payload.assignee_ids == [ASSIGNEE_ID]
    assert pending_repository.completed == [(SECOND_TASK_ID, ASSIGNEE_ID, "mock-callback-message")]
    assert result.pending_action_id == pending.id
    assert result.answer_message_text is not None
    assert "Задача #2001 создана ✅" in result.answer_message_text
    assert "Текст: Подготовить отчет" in result.answer_message_text
    assert "Исполнитель: Иван" in result.answer_message_text
    assert result.answer_message_attachments is not None
    buttons = result.answer_message_attachments[0]["payload"]["buttons"]
    assert buttons == [[{"type": "link", "text": "Открыть задачу", "url": "https://example.invalid/tasks"}]]


@pytest.mark.anyio
async def test_assign_self_callback_creates_task_for_callback_actor(task_service: FakeTaskService) -> None:
    pending = pending_action()
    pending_repository = FakePendingActionRepository(pending)
    service = assignment_callback_service(task_service=task_service, pending_repository=pending_repository)

    result = await service.handle_event(
        callback_event(
            build_task_assignment_callback_payload(
                pending_action_id=pending.id,
                assign_self=True,
            )
        )
    )

    assert result.action == "assign"
    assert result.response_text == "Исполнитель назначен: Постановщик."
    assert task_service.created_payloads[0].assignee_ids == [CREATOR_ID]
    assert pending_repository.completed == [(SECOND_TASK_ID, CREATOR_ID, "mock-callback-message")]


@pytest.mark.anyio
async def test_member_assign_callback_for_other_user_is_forbidden(task_service: FakeTaskService) -> None:
    pending = pending_action()
    pending_repository = FakePendingActionRepository(pending)
    service = assignment_callback_service(
        task_service=task_service,
        pending_repository=pending_repository,
        creator_role="member",
    )

    with pytest.raises(BotCallbackForbidden, match="Only chat admin can assign tasks to other users"):
        await service.handle_event(
            callback_event(
                build_task_assignment_callback_payload(
                    pending_action_id=pending.id,
                    assignee_id=ASSIGNEE_ID,
                )
            )
        )

    assert task_service.created_payloads == []
    assert pending_repository.completed == []


@pytest.mark.anyio
async def test_assignment_cleanup_result_is_recorded(task_service: FakeTaskService) -> None:
    pending = pending_action()
    pending_repository = FakePendingActionRepository(pending)
    service = assignment_callback_service(task_service=task_service, pending_repository=pending_repository)

    await service.mark_assignment_cleanup(pending.id, succeeded=True)
    await service.mark_assignment_cleanup(pending.id, succeeded=False, error="MAX API returned HTTP 400.")

    assert pending_repository.cleanup_results == [
        (pending.id, "edited", None),
        (pending.id, "failed", "MAX API returned HTTP 400."),
    ]


@pytest.mark.anyio
async def test_completed_pending_action_does_not_create_duplicate_task(task_service: FakeTaskService) -> None:
    pending = pending_action(status="completed")
    service = assignment_callback_service(
        task_service=task_service,
        pending_repository=FakePendingActionRepository(pending),
    )

    result = await service.handle_event(
        callback_event(
            build_task_assignment_callback_payload(
                pending_action_id=pending.id,
                assignee_id=ASSIGNEE_ID,
            )
        )
    )

    assert result.action == "assign"
    assert result.task_id == SECOND_TASK_ID
    assert result.response_text == "Исполнитель уже назначен."
    assert task_service.created_payloads == []


@pytest.mark.anyio
async def test_expired_pending_action_returns_friendly_response(task_service: FakeTaskService) -> None:
    pending = pending_action(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    pending_repository = FakePendingActionRepository(pending)
    service = assignment_callback_service(task_service=task_service, pending_repository=pending_repository)

    result = await service.handle_event(
        callback_event(
            build_task_assignment_callback_payload(
                pending_action_id=pending.id,
                assignee_id=ASSIGNEE_ID,
            )
        )
    )

    assert result.action == "assign"
    assert result.task_id is None
    assert result.response_text == "Выбор исполнителя устарел. Создайте задачу заново."
    assert task_service.created_payloads == []
    assert pending_repository.expired == [pending.id]


@pytest.mark.anyio
async def test_unrelated_user_cannot_assign_pending_action(task_service: FakeTaskService) -> None:
    pending = pending_action()
    service = assignment_callback_service(
        task_service=task_service,
        pending_repository=FakePendingActionRepository(pending),
    )

    with pytest.raises(BotCallbackForbidden):
        await service.handle_event(
            callback_event(
                build_task_assignment_callback_payload(
                    pending_action_id=pending.id,
                    assignee_id=ASSIGNEE_ID,
                ),
                user_id=OUTSIDER_ID,
            )
        )

    assert task_service.created_payloads == []


@pytest.mark.anyio
async def test_assignment_callback_uses_receipt_for_duplicate_callback_id(
    task_service: FakeTaskService,
) -> None:
    pending = pending_action()
    pending_repository = FakePendingActionRepository(pending)
    receipt_repository = FakeCallbackReceiptRepository()
    service = assignment_callback_service(
        task_service=task_service,
        pending_repository=pending_repository,
        receipt_repository=receipt_repository,
    )
    payload = build_task_assignment_callback_payload(
        pending_action_id=pending.id,
        assignee_id=ASSIGNEE_ID,
    )

    first = await service.handle_event(callback_event(payload, callback_id="callback-1"))
    second = await service.handle_event(callback_event(payload, callback_id="callback-1"))

    assert first.response_text == "Исполнитель назначен: Иван."
    assert second.response_text == "Исполнитель назначен: Иван."
    assert len(task_service.created_payloads) == 1


@pytest.mark.anyio
async def test_start_task_callback_allows_assignee(
    callback_service: BotCallbackService,
    task_service: FakeTaskService,
) -> None:
    result = await callback_service.handle_event(event(build_callback_payload("start", TASK_ID)))

    assert result.action == "start"
    assert result.task_id == TASK_ID
    assert result.response_text == "Задача взята в работу."
    assert task_service.started == (TASK_ID, ASSIGNEE_ID)


@pytest.mark.anyio
async def test_reply_callback_prompts_assignee_without_mutating_task(
    callback_service: BotCallbackService,
    task_service: FakeTaskService,
) -> None:
    result = await callback_service.handle_event(event(build_callback_payload("reply", TASK_ID)))

    assert result.action == "reply"
    assert result.response_text == "Напишите ответ на задачу сообщением в чат."
    assert task_service.started is None
    assert task_service.submitted is None


@pytest.mark.anyio
async def test_confirm_callback_submits_completion_response(
    callback_service: BotCallbackService,
    task_service: FakeTaskService,
) -> None:
    result = await callback_service.handle_event(event(build_callback_payload("confirm", TASK_ID)))

    assert result.action == "confirm"
    assert result.response_text == "Отчет о выполнении отправлен постановщику."
    assert task_service.submitted is not None
    task_id, payload = task_service.submitted
    assert task_id == TASK_ID
    assert payload.user_id == ASSIGNEE_ID
    assert payload.text == "Выполнено"
    assert payload.source_message_id == "mock-callback-message"


@pytest.mark.anyio
async def test_accept_callback_allows_task_creator(
    callback_service: BotCallbackService,
    task_service: FakeTaskService,
) -> None:
    result = await callback_service.handle_event(
        event(build_callback_payload("accept", TASK_ID, response_id=RESPONSE_ID), user_id=CREATOR_ID)
    )

    assert result.action == "accept"
    assert result.response_text == "Ответ по задаче #1042 принят ✅"
    assert result.answer_message_text == result.response_text
    assert task_service.accepted is not None
    task_id, response_id, payload = task_service.accepted
    assert task_id == TASK_ID
    assert response_id == RESPONSE_ID
    assert payload.accepted_by_user_id == CREATOR_ID


@pytest.mark.anyio
async def test_accept_callback_allows_chat_admin(task_service: FakeTaskService) -> None:
    admin_member = SimpleNamespace(
        user_id=OUTSIDER_ID,
        is_active=True,
        role="chat_admin",
        user=SimpleNamespace(id=OUTSIDER_ID, display_name="Админ"),
    )
    service = BotCallbackService(
        task_service=task_service,
        reminder_service=FakeReminderService(),  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        chat_repository=FakeChatRepository(
            chat=SimpleNamespace(id=CHAT_ID, organization_id=ORG_ID),
            members={OUTSIDER_ID: admin_member},
        ),
    )

    result = await service.handle_event(
        event(
            build_callback_payload("accept", TASK_ID, response_id=RESPONSE_ID),
            user_id=OUTSIDER_ID,
            chat_id=CHAT_ID,
        )
    )

    assert result.action == "accept"
    assert result.response_text == "Ответ по задаче #1042 принят ✅"
    assert task_service.accepted is not None
    assert task_service.accepted[2].accepted_by_user_id == OUTSIDER_ID
    assert task_service.accept_auth_context is not None
    assert getattr(task_service.accept_auth_context, "roles") == ["chat_admin"]


@pytest.mark.anyio
async def test_accept_callback_does_not_accept_rejected_response(
    callback_service: BotCallbackService,
    task_service: FakeTaskService,
) -> None:
    task_service.task.responses[0].status = TaskResponseStatus.REJECTED.value

    result = await callback_service.handle_event(
        event(build_callback_payload("accept", TASK_ID, response_id=RESPONSE_ID), user_id=CREATOR_ID)
    )

    assert result.action == "accept"
    assert result.response_text == "Результат уже отклонен."
    assert result.answer_message_text == result.response_text
    assert task_service.accepted is None


@pytest.mark.anyio
async def test_reject_callback_does_not_reject_accepted_response(
    task_service: FakeTaskService,
) -> None:
    task_service.task.responses[0].status = TaskResponseStatus.ACCEPTED.value
    pending_repository = FakePendingActionRepository()
    service = BotCallbackService(
        task_service=task_service,
        reminder_service=FakeReminderService(),  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        pending_action_repository=pending_repository,
    )

    result = await service.handle_event(
        event(build_callback_payload("reject", TASK_ID, response_id=RESPONSE_ID), user_id=CREATOR_ID)
    )

    assert result.action == "reject"
    assert result.response_text == "Результат уже принят."
    assert result.answer_message_text == result.response_text
    assert task_service.rejected is None
    assert pending_repository.reject_reason_created == []


@pytest.mark.anyio
async def test_reject_callback_allows_task_creator(
    task_service: FakeTaskService,
) -> None:
    pending_repository = FakePendingActionRepository()
    service = BotCallbackService(
        task_service=task_service,
        reminder_service=FakeReminderService(),  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        pending_action_repository=pending_repository,
    )

    result = await service.handle_event(
        event(build_callback_payload("reject", TASK_ID, response_id=RESPONSE_ID), user_id=CREATOR_ID)
    )

    assert result.action == "reject"
    assert result.response_text == "Напишите причину отклонения приемки по задаче #1042 одним сообщением."
    assert result.answer_message_text == result.response_text
    assert task_service.rejected is None
    assert len(pending_repository.reject_reason_created) == 1
    pending = pending_repository.reject_reason_created[0]
    assert pending.actor_user_id == CREATOR_ID
    assert pending.reply_context == {
        "task_id": str(TASK_ID),
        "response_id": str(RESPONSE_ID),
        "task_ref": "#1042",
    }


@pytest.mark.anyio
async def test_reject_callback_allows_chat_admin(task_service: FakeTaskService) -> None:
    pending_repository = FakePendingActionRepository()
    admin_member = SimpleNamespace(
        user_id=OUTSIDER_ID,
        is_active=True,
        role="chat_admin",
        user=SimpleNamespace(id=OUTSIDER_ID, display_name="Администратор"),
    )
    service = BotCallbackService(
        task_service=task_service,
        reminder_service=FakeReminderService(),  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        chat_repository=FakeChatRepository(
            chat=SimpleNamespace(id=CHAT_ID, organization_id=ORG_ID),
            members={OUTSIDER_ID: admin_member},
        ),
        pending_action_repository=pending_repository,
    )

    result = await service.handle_event(
        event(
            build_callback_payload("reject", TASK_ID, response_id=RESPONSE_ID),
            user_id=OUTSIDER_ID,
            chat_id=CHAT_ID,
        )
    )

    assert result.action == "reject"
    assert result.response_text == "Напишите причину отклонения приемки по задаче #1042 одним сообщением."
    assert task_service.rejected is None
    assert pending_repository.reject_reason_created[0].actor_user_id == OUTSIDER_ID


@pytest.mark.anyio
async def test_snooze_1h_callback_creates_task_reminder_snooze(
    callback_service: BotCallbackService,
    reminder_service: FakeReminderService,
) -> None:
    result = await callback_service.handle_event(event(build_callback_payload("snooze", TASK_ID, snooze="1h")))

    assert result.action == "snooze"
    assert result.snooze == "1h"
    assert result.response_text == "Напоминание отложено на 1 час."
    assert len(reminder_service.snoozes) == 1
    snooze = reminder_service.snoozes[0]
    assert snooze.task_id == TASK_ID
    assert snooze.user_id == ASSIGNEE_ID
    assert snooze.duration == "1h"
    assert snooze.snoozed_until == NOW + timedelta(hours=1)
    assert snooze.reason == "callback/snooze:1h"


@pytest.mark.anyio
async def test_snooze_tomorrow_callback_creates_task_reminder_snooze(
    callback_service: BotCallbackService,
    reminder_service: FakeReminderService,
) -> None:
    result = await callback_service.handle_event(
        event(build_callback_payload("snooze", TASK_ID, snooze="tomorrow"))
    )

    assert result.action == "snooze"
    assert result.snooze == "tomorrow"
    assert result.response_text == "Напоминание отложено до завтра."
    assert len(reminder_service.snoozes) == 1
    snooze = reminder_service.snoozes[0]
    assert snooze.task_id == TASK_ID
    assert snooze.user_id == ASSIGNEE_ID
    assert snooze.duration == "tomorrow_09"
    assert snooze.snoozed_until == datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc)
    assert snooze.reason == "callback/snooze:tomorrow"


@pytest.mark.anyio
async def test_snooze_callback_is_scoped_to_callback_user(
    callback_service: BotCallbackService,
    task_service: FakeTaskService,
    reminder_service: FakeReminderService,
) -> None:
    task_service.task.assignees.append(SimpleNamespace(user_id=SECOND_ASSIGNEE_ID))

    await callback_service.handle_event(
        event(build_callback_payload("snooze", TASK_ID, snooze="1h"), user_id=SECOND_ASSIGNEE_ID)
    )

    assert len(reminder_service.snoozes) == 1
    assert reminder_service.snoozes[0].user_id == SECOND_ASSIGNEE_ID
    assert reminder_service.snoozes[0].user_id != ASSIGNEE_ID


@pytest.mark.anyio
async def test_open_callback_returns_webapp_url_for_observer(callback_service: BotCallbackService) -> None:
    result = await callback_service.handle_event(
        event(build_callback_payload("open", TASK_ID), user_id=OBSERVER_ID)
    )

    assert result.action == "open"
    assert result.response_text == "Откройте карточку задачи в WebApp."
    assert result.webapp_url == f"https://example.invalid/tasks/{TASK_ID}"


@pytest.mark.anyio
async def test_open_callback_returns_max_deep_link_when_username_configured(
    task_service: FakeTaskService,
    reminder_service: FakeReminderService,
) -> None:
    service = BotCallbackService(
        task_service=task_service,
        reminder_service=reminder_service,  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        max_bot_username="@secretary_oren_bot",
    )

    result = await service.handle_event(event(build_callback_payload("open", TASK_ID), user_id=OBSERVER_ID))

    assert result.webapp_url == f"https://max.ru/secretary_oren_bot?startapp=task_{TASK_ID}"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("payload", "user_id"),
    [
        (build_callback_payload("start", TASK_ID), OUTSIDER_ID),
        (build_callback_payload("reply", TASK_ID), OUTSIDER_ID),
        (build_callback_payload("confirm", TASK_ID), OUTSIDER_ID),
        (build_callback_payload("snooze", TASK_ID, snooze="tomorrow"), OUTSIDER_ID),
        (build_callback_payload("accept", TASK_ID, response_id=RESPONSE_ID), OUTSIDER_ID),
        (build_callback_payload("reject", TASK_ID, response_id=RESPONSE_ID), OUTSIDER_ID),
        (build_callback_payload("open", TASK_ID), OUTSIDER_ID),
    ],
)
async def test_callback_actions_forbid_outsider(
    callback_service: BotCallbackService,
    reminder_service: FakeReminderService,
    payload: str,
    user_id: UUID,
) -> None:
    with pytest.raises(BotCallbackForbidden):
        await callback_service.handle_event(event(payload, user_id=user_id))
    if "task:snooze:" in payload:
        assert reminder_service.snoozes == []


@pytest.mark.anyio
async def test_callback_idempotency_skips_duplicate_callback_id(
    task_service: FakeTaskService,
    reminder_service: FakeReminderService,
) -> None:
    receipts = FakeCallbackReceiptRepository()
    service = BotCallbackService(
        task_service=task_service,  # type: ignore[arg-type]
        reminder_service=reminder_service,  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        receipt_repository=receipts,
    )
    callback_event = event(
        build_callback_payload("start", TASK_ID),
        user_id=ASSIGNEE_ID,
    )
    callback_event = NormalizedCallbackEvent(
        payload=callback_event.payload,
        user_id=callback_event.user_id,
        message_id=callback_event.message_id,
        callback_id="mock-callback-idempotent",
    )

    first = await service.handle_event(callback_event)
    second = await service.handle_event(callback_event)

    assert first.response_text == "Задача взята в работу."
    assert second.response_text == "Задача взята в работу."
    assert receipts.started == [("mock-callback-idempotent", build_callback_payload("start", TASK_ID))]
    assert receipts.succeeded == [("mock-callback-idempotent", "Задача взята в работу.")]
    assert task_service.started == (TASK_ID, ASSIGNEE_ID)
    assert task_service.start_count == 1


@pytest.mark.anyio
async def test_logical_idempotency_skips_same_snooze_with_different_callback_id(
    task_service: FakeTaskService,
    reminder_service: FakeReminderService,
) -> None:
    receipts = FakeCallbackReceiptRepository()
    service = BotCallbackService(
        task_service=task_service,  # type: ignore[arg-type]
        reminder_service=reminder_service,  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        receipt_repository=receipts,
    )
    payload = build_callback_payload("snooze", TASK_ID, snooze="1h")

    first = await service.handle_event(
        NormalizedCallbackEvent(payload=payload, user_id=ASSIGNEE_ID, callback_id="mock-callback-001")
    )
    second = await service.handle_event(
        NormalizedCallbackEvent(payload=payload, user_id=ASSIGNEE_ID, callback_id="mock-callback-002")
    )

    assert first.response_text == "Напоминание отложено на 1 час."
    assert second.response_text == "Напоминание уже отложено."
    assert len(reminder_service.snoozes) == 1
    assert receipts.succeeded == [("mock-callback-001", "Напоминание отложено на 1 час.")]
    assert receipts.logical_duplicates == [("mock-callback-002", "Напоминание уже отложено.")]
    assert receipts.receipts["mock-callback-002"].status == "skipped"
    assert receipts.receipts["mock-callback-002"].logical_status == "duplicate_logical"


@pytest.mark.anyio
async def test_logical_idempotency_allows_same_snooze_for_different_actor(
    task_service: FakeTaskService,
    reminder_service: FakeReminderService,
) -> None:
    task_service.task.assignees.append(
        SimpleNamespace(user_id=SECOND_ASSIGNEE_ID, status=TaskAssigneeStatus.ASSIGNED.value)
    )
    receipts = FakeCallbackReceiptRepository()
    service = BotCallbackService(
        task_service=task_service,  # type: ignore[arg-type]
        reminder_service=reminder_service,  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        receipt_repository=receipts,
    )
    payload = build_callback_payload("snooze", TASK_ID, snooze="1h")

    await service.handle_event(
        NormalizedCallbackEvent(payload=payload, user_id=ASSIGNEE_ID, callback_id="mock-callback-actor-a")
    )
    await service.handle_event(
        NormalizedCallbackEvent(payload=payload, user_id=SECOND_ASSIGNEE_ID, callback_id="mock-callback-actor-b")
    )

    assert len(reminder_service.snoozes) == 2
    assert {snooze.user_id for snooze in reminder_service.snoozes} == {ASSIGNEE_ID, SECOND_ASSIGNEE_ID}
    assert receipts.logical_duplicates == []


@pytest.mark.anyio
async def test_logical_idempotency_allows_same_actor_action_for_different_task(
    task_service: FakeTaskService,
    reminder_service: FakeReminderService,
) -> None:
    task_service.tasks[SECOND_TASK_ID] = SimpleNamespace(
        id=SECOND_TASK_ID,
        created_by_user_id=CREATOR_ID,
        assignees=[SimpleNamespace(user_id=ASSIGNEE_ID, status=TaskAssigneeStatus.ASSIGNED.value)],
        observers=[],
        responses=[],
    )
    receipts = FakeCallbackReceiptRepository()
    service = BotCallbackService(
        task_service=task_service,  # type: ignore[arg-type]
        reminder_service=reminder_service,  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        receipt_repository=receipts,
    )

    await service.handle_event(
        NormalizedCallbackEvent(
            payload=build_callback_payload("snooze", TASK_ID, snooze="1h"),
            user_id=ASSIGNEE_ID,
            callback_id="mock-callback-task-a",
        )
    )
    await service.handle_event(
        NormalizedCallbackEvent(
            payload=build_callback_payload("snooze", SECOND_TASK_ID, snooze="1h"),
            user_id=ASSIGNEE_ID,
            callback_id="mock-callback-task-b",
        )
    )

    assert len(reminder_service.snoozes) == 2
    assert {snooze.task_id for snooze in reminder_service.snoozes} == {TASK_ID, SECOND_TASK_ID}
    assert receipts.logical_duplicates == []


@pytest.mark.anyio
async def test_logical_idempotency_allows_different_action_for_same_task(
    task_service: FakeTaskService,
    reminder_service: FakeReminderService,
) -> None:
    receipts = FakeCallbackReceiptRepository()
    service = BotCallbackService(
        task_service=task_service,  # type: ignore[arg-type]
        reminder_service=reminder_service,  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        receipt_repository=receipts,
    )

    await service.handle_event(
        NormalizedCallbackEvent(
            payload=build_callback_payload("snooze", TASK_ID, snooze="1h"),
            user_id=ASSIGNEE_ID,
            callback_id="mock-callback-snooze-1h",
        )
    )
    await service.handle_event(
        NormalizedCallbackEvent(
            payload=build_callback_payload("snooze", TASK_ID, snooze="tomorrow"),
            user_id=ASSIGNEE_ID,
            callback_id="mock-callback-snooze-tomorrow",
        )
    )

    assert [snooze.duration for snooze in reminder_service.snoozes] == ["1h", "tomorrow_09"]
    assert receipts.logical_duplicates == []


@pytest.mark.anyio
async def test_repeated_confirm_callback_is_safe_noop(
    callback_service: BotCallbackService,
    task_service: FakeTaskService,
) -> None:
    payload = build_callback_payload("confirm", TASK_ID)

    first = await callback_service.handle_event(event(payload))
    second = await callback_service.handle_event(event(payload))

    assert first.response_text == "Отчет о выполнении отправлен постановщику."
    assert second.response_text == "Отчет уже отправлен постановщику."
    assert task_service.submit_count == 1


@pytest.mark.anyio
async def test_repeated_accept_callback_is_safe_noop(
    callback_service: BotCallbackService,
    task_service: FakeTaskService,
) -> None:
    payload = build_callback_payload("accept", TASK_ID, response_id=RESPONSE_ID)

    first = await callback_service.handle_event(event(payload, user_id=CREATOR_ID))
    second = await callback_service.handle_event(event(payload, user_id=CREATOR_ID))

    assert first.response_text == "Ответ по задаче #1042 принят ✅"
    assert second.response_text == "Результат уже принят."
    assert task_service.accept_count == 1


@pytest.mark.anyio
async def test_repeated_reject_callback_is_safe_noop(
    task_service: FakeTaskService,
) -> None:
    pending_repository = FakePendingActionRepository()
    receipts = FakeCallbackReceiptRepository()
    service = BotCallbackService(
        task_service=task_service,
        reminder_service=FakeReminderService(),  # type: ignore[arg-type]
        webapp_base_url="https://example.invalid/",
        receipt_repository=receipts,
        pending_action_repository=pending_repository,
    )
    payload = build_callback_payload("reject", TASK_ID, response_id=RESPONSE_ID)

    first = await service.handle_event(
        NormalizedCallbackEvent(payload=payload, user_id=CREATOR_ID, chat_id=CHAT_ID, callback_id="reject-1")
    )
    second = await service.handle_event(
        NormalizedCallbackEvent(payload=payload, user_id=CREATOR_ID, chat_id=CHAT_ID, callback_id="reject-2")
    )

    assert first.response_text == "Напишите причину отклонения приемки по задаче #1042 одним сообщением."
    assert second.response_text == "Причина отклонения уже ожидается."
    assert task_service.reject_count == 0
    assert len(pending_repository.reject_reason_created) == 1
