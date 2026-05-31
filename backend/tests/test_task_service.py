from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_MEMBER, ROLE_SUPER_ADMIN
from app.modules.tasks.enums import (
    TaskAssigneeStatus,
    TaskCompletionRule,
    TaskPriority,
    TaskResponseStatus,
    TaskStatus,
    TaskType,
)
from app.modules.tasks.schemas import TaskCreate, TaskGroupAssignmentCreate, TaskParticipantCreate, TaskUpdate
from app.modules.tasks.service import PROJECT_TIMEZONE, TaskService


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _instance: object) -> None:
        return None


class FakeMaxSender:
    def __init__(self) -> None:
        self.inline_messages: list[dict[str, object]] = []

    def send_inline_keyboard_message(
        self,
        *,
        chat_id: str | None,
        text: str,
        button_rows: list[list[dict[str, object]]],
        user_id: str | None = None,
        purpose: object = None,
    ) -> SimpleNamespace:
        self.inline_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "button_rows": button_rows,
                "user_id": user_id,
                "purpose": purpose,
            }
        )
        return SimpleNamespace(sent=True, reason="sent")

    def send_message(
        self,
        chat_id: str | None,
        text: str,
        *,
        user_id: str | None = None,
        purpose: object = None,
        reminder_type: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(sent=True, reason="sent")


class FakeTaskRepository:
    def __init__(self, organization_id: UUID, chat_id: UUID, user_ids: set[UUID]) -> None:
        self.organization_id = organization_id
        self.chat_id = chat_id
        self.user_ids = user_ids
        self.task_id = uuid4()
        self.task_number = 1
        self.created_task_values: dict[str, object] = {}
        self.created_assignee_ids: list[UUID] = []
        self.created_assignee_response_required: bool | None = None
        self.created_observer_ids: list[UUID] = []
        self.status_history_values: dict[str, object] = {}
        self.status_history_entries: list[dict[str, object]] = []
        self.audit_log_entries: list[dict[str, object]] = []
        self.assignees: dict[UUID, SimpleNamespace] = {}
        self.observers: dict[UUID, SimpleNamespace] = {}
        self.detail_task = SimpleNamespace(
            id=self.task_id,
            organization_id=organization_id,
            status=TaskStatus.NEW.value,
            cancelled_at=None,
        )
        self.group_report_task: SimpleNamespace | None = None
        self.chat_title = "Project chat"
        self.chat_status = "active"
        self.chat_type = "chat"
        self.max_chat_id = "max-chat-001"
        self.chat_settings: dict[str, object] | None = None
        self.chat_members: list[SimpleNamespace] = []
        self.users: dict[UUID, SimpleNamespace] = {
            user_id: SimpleNamespace(id=user_id, display_name=f"User {str(user_id)[-8:]}")
            for user_id in user_ids
        }

    async def organization_exists(self, organization_id: UUID) -> bool:
        return organization_id == self.organization_id

    async def get_chat(self, chat_id: UUID) -> SimpleNamespace | None:
        if chat_id != self.chat_id:
            return None
        return SimpleNamespace(
            id=chat_id,
            organization_id=self.organization_id,
            title=self.chat_title,
            type=self.chat_type,
            status=self.chat_status,
            max_chat_id=self.max_chat_id,
            settings=self.chat_settings,
            display_title=self.chat_settings.get("display_title") if self.chat_settings else None,
        )

    async def get_chat_with_members(self, chat_id: UUID) -> SimpleNamespace | None:
        if chat_id != self.chat_id:
            return None
        return SimpleNamespace(
            id=chat_id,
            organization_id=self.organization_id,
            title=self.chat_title,
            type=self.chat_type,
            status=self.chat_status,
            max_chat_id=self.max_chat_id,
            settings=self.chat_settings,
            display_title=self.chat_settings.get("display_title") if self.chat_settings else None,
            members=self.chat_members,
        )

    async def get_user(self, user_id: UUID) -> SimpleNamespace | None:
        return self.users.get(user_id)

    async def existing_user_ids(self, user_ids: set[UUID]) -> set[UUID]:
        return self.user_ids & user_ids

    async def create_task(self, **values: object) -> SimpleNamespace:
        self.created_task_values = values
        return SimpleNamespace(id=self.task_id, task_number=self.task_number)

    async def create_assignees(
        self,
        *,
        task_id: UUID,
        assignee_ids: list[UUID],
        response_required: bool = True,
    ) -> list[object]:
        assert task_id == self.task_id
        self.created_assignee_ids = assignee_ids
        self.created_assignee_response_required = response_required
        return []

    async def create_observers(self, *, task_id: UUID, observer_ids: list[UUID]) -> list[object]:
        assert task_id == self.task_id
        self.created_observer_ids = observer_ids
        return []

    async def create_status_history(
        self,
        *,
        task_id: UUID,
        old_status: str | None,
        new_status: str,
        changed_by_user_id: UUID | None,
    ) -> SimpleNamespace:
        assert task_id == self.task_id
        self.status_history_values = {
            "task_id": task_id,
            "old_status": old_status,
            "new_status": new_status,
            "changed_by_user_id": changed_by_user_id,
        }
        self.status_history_entries.append(self.status_history_values)
        return SimpleNamespace(id=uuid4())

    async def get_with_participants(self, task_id: UUID) -> SimpleNamespace:
        assert task_id == self.task_id
        return SimpleNamespace(id=task_id)

    async def get_detail(self, task_id: UUID) -> SimpleNamespace | None:
        if task_id != self.task_id:
            return None
        return self.detail_task

    async def get_group_report_task(self, task_id: UUID) -> SimpleNamespace | None:
        if task_id != self.task_id:
            return None
        return self.group_report_task

    async def update_task(
        self,
        task: SimpleNamespace,
        *,
        values: dict[str, object],
    ) -> SimpleNamespace:
        for field_name, value in values.items():
            setattr(task, field_name, value)
        return task

    async def get_assignee(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
    ) -> SimpleNamespace | None:
        assert task_id == self.task_id
        return self.assignees.get(user_id)

    async def create_assignee(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
    ) -> SimpleNamespace:
        assert task_id == self.task_id
        assignee = SimpleNamespace(
            id=uuid4(),
            task_id=task_id,
            user_id=user_id,
            status="assigned",
            response_required=True,
        )
        self.assignees[user_id] = assignee
        return assignee

    async def delete_assignee(self, assignee: SimpleNamespace) -> None:
        self.assignees.pop(assignee.user_id)

    async def update_assignee_status(self, assignee: SimpleNamespace, *, status: str) -> SimpleNamespace:
        assignee.status = status
        return assignee

    async def get_observer(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
    ) -> SimpleNamespace | None:
        assert task_id == self.task_id
        return self.observers.get(user_id)

    async def create_observer(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
    ) -> SimpleNamespace:
        assert task_id == self.task_id
        observer = SimpleNamespace(
            id=uuid4(),
            task_id=task_id,
            user_id=user_id,
        )
        self.observers[user_id] = observer
        return observer

    async def delete_observer(self, observer: SimpleNamespace) -> None:
        self.observers.pop(observer.user_id)

    async def create_audit_log(
        self,
        *,
        organization_id: UUID,
        entity_id: UUID,
        action: str,
        payload: dict[str, object] | None = None,
    ) -> SimpleNamespace:
        entry = {
            "organization_id": organization_id,
            "entity_id": entity_id,
            "action": action,
            "payload": payload,
        }
        self.audit_log_entries.append(entry)
        return SimpleNamespace(id=uuid4(), **entry)


def _group_report_task(
    *,
    task_id: UUID,
    organization_id: UUID,
    chat_id: UUID,
    creator_id: UUID,
    responded_user_id: UUID,
    pending_user_id: UUID,
) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=task_id,
        task_number=42,
        organization_id=organization_id,
        chat_id=chat_id,
        task_type=TaskType.GROUP_ASSIGNMENT.value,
        title="Сдать отчеты",
        created_by_user_id=creator_id,
        creator_display_name_snapshot="Иван Руководитель",
        creator_role_snapshot=ROLE_CHAT_ADMIN,
        source_chat_title_snapshot="MAX group",
        deadline_at=now - timedelta(hours=1),
        status=TaskStatus.NEW.value,
        created_by_user=SimpleNamespace(id=creator_id, display_name="Fallback Creator"),
        chat=SimpleNamespace(id=chat_id, title="Fallback chat"),
        assignees=[
            SimpleNamespace(
                user_id=responded_user_id,
                status=TaskAssigneeStatus.RESPONDED.value,
                response_required=True,
                responded_at=now,
                user=SimpleNamespace(id=responded_user_id, display_name="Петр Исполнитель"),
            ),
            SimpleNamespace(
                user_id=pending_user_id,
                status=TaskAssigneeStatus.ASSIGNED.value,
                response_required=True,
                responded_at=None,
                user=SimpleNamespace(id=pending_user_id, display_name=None),
            ),
        ],
        responses=[
            SimpleNamespace(
                id=uuid4(),
                user_id=responded_user_id,
                text="Готово",
                status=TaskResponseStatus.SUBMITTED.value,
                created_at=now,
            )
        ],
    )


@pytest.mark.anyio
async def test_task_service_create_records_assignees_observers_and_status_history() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    created_by_user_id = uuid4()
    assignee_ids = [uuid4(), uuid4()]
    observer_ids = [uuid4()]
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={created_by_user_id, *assignee_ids, *observer_ids},
    )
    session = FakeSession()
    service = TaskService(repository=repository, session=session)

    result = await service.create(
        TaskCreate(
            organization_id=organization_id,
            chat_id=chat_id,
            title="Prepare weekly report",
            description=None,
            created_by_user_id=created_by_user_id,
            assignee_ids=assignee_ids,
            observer_ids=observer_ids,
        )
    )

    assert result.id == repository.task_id
    assert session.committed is True
    assert repository.created_task_values["status"] == TaskStatus.NEW.value
    assert repository.created_task_values["priority"] == TaskPriority.NORMAL.value
    assert repository.created_task_values["source_chat_title_snapshot"] == repository.chat_title
    assert (
        repository.created_task_values["completion_rule"]
        == TaskCompletionRule.ANY_ASSIGNEE_RESPONSE.value
    )
    assert repository.created_assignee_ids == assignee_ids
    assert repository.created_observer_ids == observer_ids
    assert repository.status_history_values == {
        "task_id": repository.task_id,
        "old_status": None,
        "new_status": TaskStatus.NEW.value,
        "changed_by_user_id": created_by_user_id,
    }


@pytest.mark.anyio
async def test_task_service_create_rejects_past_deadline() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    created_by_user_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={created_by_user_id},
    )
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create(
            TaskCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                title="Past task",
                created_by_user_id=created_by_user_id,
                deadline_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                assignee_ids=[created_by_user_id],
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "deadline_must_be_in_future"
    assert repository.created_task_values == {}


@pytest.mark.anyio
async def test_task_service_create_rejects_deadline_less_than_one_minute_from_now() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    created_by_user_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={created_by_user_id},
    )
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create(
            TaskCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                title="Too soon task",
                created_by_user_id=created_by_user_id,
                deadline_at=datetime.now(timezone.utc) + timedelta(seconds=30),
                assignee_ids=[created_by_user_id],
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "deadline_must_be_in_future"
    assert repository.created_task_values == {}


@pytest.mark.anyio
async def test_task_service_group_assignment_creates_task_for_active_chat_members() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    assignee_ids = [uuid4(), uuid4()]
    inactive_user_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, *assignee_ids, inactive_user_id},
    )
    repository.users[creator_id] = SimpleNamespace(id=creator_id, display_name="Иван Руководитель")
    repository.chat_title = "MAX group"
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
        *(SimpleNamespace(user_id=user_id, role=ROLE_MEMBER, is_active=True) for user_id in assignee_ids),
        SimpleNamespace(user_id=inactive_user_id, role=ROLE_MEMBER, is_active=False),
    ]
    session = FakeSession()
    service = TaskService(repository=repository, session=session)

    result = await service.create_group_assignment(
        TaskGroupAssignmentCreate(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
            title="Сдать отчеты",
            description="До конца дня",
        ),
        AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
    )

    assert result.task_id == repository.task_id
    assert result.task_number == repository.task_number
    assert result.task_ref == f"#{repository.task_number}"
    assert result.total_assignees == 2
    assert result.creator_display_name == "Иван Руководитель"
    assert result.creator_role == ROLE_CHAT_ADMIN
    assert repository.created_task_values["task_type"] == TaskType.GROUP_ASSIGNMENT.value
    assert repository.created_task_values["requires_individual_report"] is True
    assert repository.created_task_values["completion_rule"] == TaskCompletionRule.ALL_ASSIGNEES_RESPONSE.value
    assert repository.created_task_values["creator_display_name_snapshot"] == "Иван Руководитель"
    assert repository.created_task_values["creator_role_snapshot"] == ROLE_CHAT_ADMIN
    assert repository.created_task_values["source_chat_title_snapshot"] == "MAX group"
    assert repository.created_assignee_ids == assignee_ids
    assert repository.created_assignee_response_required is True
    assert repository.created_task_values["audience_snapshot"] == {
        "source": "chat_members",
        "chat_id": str(chat_id),
        "chat_title": "MAX group",
        "exclude_creator": True,
        "response_required": True,
        "active_member_count": 3,
        "total_assignees": 2,
        "assignee_ids": [str(user_id) for user_id in assignee_ids],
    }
    assert session.committed is True


@pytest.mark.anyio
async def test_task_service_group_assignment_rejects_past_deadline() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, assignee_id},
    )
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
        SimpleNamespace(user_id=assignee_id, role=ROLE_MEMBER, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_group_assignment(
            TaskGroupAssignmentCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=creator_id,
                title="Сдать отчеты",
                deadline_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            ),
            AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "deadline_must_be_in_future"
    assert repository.created_task_values == {}


@pytest.mark.anyio
async def test_task_service_group_assignment_can_include_creator() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, assignee_id},
    )
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
        SimpleNamespace(user_id=assignee_id, role=ROLE_MEMBER, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    result = await service.create_group_assignment(
        TaskGroupAssignmentCreate(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
            title="Сдать отчеты",
            exclude_creator=False,
        ),
        AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
    )

    assert result.total_assignees == 2
    assert repository.created_assignee_ids == [creator_id, assignee_id]


@pytest.mark.anyio
async def test_task_service_group_assignment_uses_selected_active_assignees() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    selected_id = uuid4()
    other_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, selected_id, other_id},
    )
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
        SimpleNamespace(user_id=selected_id, role=ROLE_MEMBER, is_active=True),
        SimpleNamespace(user_id=other_id, role=ROLE_MEMBER, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    result = await service.create_group_assignment(
        TaskGroupAssignmentCreate(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
            title="Сдать отчеты",
            assignee_ids=[selected_id],
        ),
        AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
    )

    assert result.total_assignees == 1
    assert repository.created_assignee_ids == [selected_id]


@pytest.mark.anyio
async def test_task_service_group_assignment_deduplicates_selected_assignees() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    selected_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, selected_id},
    )
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
        SimpleNamespace(user_id=selected_id, role=ROLE_MEMBER, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    await service.create_group_assignment(
        TaskGroupAssignmentCreate(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
            title="Сдать отчеты",
            assignee_ids=[selected_id, selected_id],
        ),
        AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
    )

    assert repository.created_assignee_ids == [selected_id]


@pytest.mark.anyio
async def test_task_service_group_assignment_rejects_empty_assignee_selection() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id},
    )
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_group_assignment(
            TaskGroupAssignmentCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=creator_id,
                title="Сдать отчеты",
                assignee_ids=[],
            ),
            AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "no_assignees"
    assert repository.created_task_values == {}


@pytest.mark.anyio
async def test_task_service_group_assignment_rejects_assignee_outside_chat() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    outside_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, outside_id},
    )
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_group_assignment(
            TaskGroupAssignmentCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=creator_id,
                title="Сдать отчеты",
                assignee_ids=[outside_id],
            ),
            AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "assignee_not_in_chat"
    assert repository.created_task_values == {}


@pytest.mark.anyio
async def test_task_service_group_assignment_rejects_inactive_selected_member() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    inactive_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, inactive_id},
    )
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
        SimpleNamespace(user_id=inactive_id, role=ROLE_MEMBER, is_active=False),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_group_assignment(
            TaskGroupAssignmentCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=creator_id,
                title="Сдать отчеты",
                assignee_ids=[inactive_id],
            ),
            AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "assignee_not_in_chat"
    assert repository.created_task_values == {}


@pytest.mark.anyio
async def test_task_service_group_assignment_exclude_creator_removes_selected_creator() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, assignee_id},
    )
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
        SimpleNamespace(user_id=assignee_id, role=ROLE_MEMBER, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    await service.create_group_assignment(
        TaskGroupAssignmentCreate(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
            title="Сдать отчеты",
            assignee_ids=[creator_id, assignee_id],
            exclude_creator=True,
        ),
        AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
    )

    assert repository.created_assignee_ids == [assignee_id]


@pytest.mark.anyio
async def test_task_service_group_assignment_rejects_non_admin() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id},
    )
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_group_assignment(
            TaskGroupAssignmentCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=creator_id,
                title="Сдать отчеты",
            ),
            AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_MEMBER]),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize("chat_status", ["pending_approval", "rejected", "suspended"])
async def test_task_service_group_assignment_rejects_inactive_chat_statuses(chat_status: str) -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, assignee_id},
    )
    repository.chat_status = chat_status
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
        SimpleNamespace(user_id=assignee_id, role=ROLE_MEMBER, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_group_assignment(
            TaskGroupAssignmentCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=creator_id,
                title="Сдать отчеты",
            ),
            AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "chat_not_active"
    assert repository.created_task_values == {}


@pytest.mark.anyio
async def test_task_service_group_assignment_rejects_chat_without_max_chat_id() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, assignee_id},
    )
    repository.max_chat_id = None
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True),
        SimpleNamespace(user_id=assignee_id, role=ROLE_MEMBER, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_group_assignment(
            TaskGroupAssignmentCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=creator_id,
                title="Сдать отчеты",
            ),
            AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "missing_max_chat_id"
    assert repository.created_task_values == {}


@pytest.mark.anyio
async def test_task_service_group_assignment_rejects_chat_admin_in_member_chat() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, assignee_id},
    )
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_MEMBER, is_active=True),
        SimpleNamespace(user_id=assignee_id, role=ROLE_MEMBER, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_group_assignment(
            TaskGroupAssignmentCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=creator_id,
                title="Сдать отчеты",
            ),
            AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "insufficient_permissions"
    assert repository.created_task_values == {}


@pytest.mark.anyio
async def test_task_service_group_assignment_rejects_chat_admin_outside_chat() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, assignee_id},
    )
    repository.chat_members = [
        SimpleNamespace(user_id=assignee_id, role=ROLE_MEMBER, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_group_assignment(
            TaskGroupAssignmentCreate(
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=creator_id,
                title="Сдать отчеты",
            ),
            AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "insufficient_permissions"
    assert repository.created_task_values == {}


@pytest.mark.anyio
async def test_task_service_group_assignment_super_admin_can_create_in_any_active_chat() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    super_admin_id = uuid4()
    assignee_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={super_admin_id, assignee_id},
    )
    repository.users[super_admin_id] = SimpleNamespace(id=super_admin_id, display_name="Супер Админ")
    repository.chat_members = [
        SimpleNamespace(user_id=assignee_id, role=ROLE_MEMBER, is_active=True),
    ]
    service = TaskService(repository=repository, session=FakeSession())

    result = await service.create_group_assignment(
        TaskGroupAssignmentCreate(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=super_admin_id,
            title="Сдать отчеты",
        ),
        AuthContext(
            user_id=super_admin_id,
            organization_id=organization_id,
            roles=[ROLE_SUPER_ADMIN],
            is_super_admin=True,
        ),
    )

    assert result.total_assignees == 1
    assert result.creator_role == ROLE_SUPER_ADMIN
    assert repository.created_assignee_ids == [assignee_id]


@pytest.mark.anyio
async def test_task_service_group_assignment_sends_clean_summary_to_source_chat() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    first_assignee_id = uuid4()
    second_assignee_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, first_assignee_id, second_assignee_id},
    )
    repository.chat_title = "MAX chat #12345678"
    repository.chat_settings = {"display_title": "Тест ДЬЯК"}
    repository.users[creator_id] = SimpleNamespace(id=creator_id, display_name="Иван Руководитель")
    first_user = SimpleNamespace(id=first_assignee_id, display_name="Мария Петрова")
    second_user = SimpleNamespace(id=second_assignee_id, display_name="Петр Сидоров")
    repository.users[first_assignee_id] = first_user
    repository.users[second_assignee_id] = second_user
    repository.chat_members = [
        SimpleNamespace(user_id=creator_id, role=ROLE_CHAT_ADMIN, is_active=True, user=repository.users[creator_id]),
        SimpleNamespace(user_id=first_assignee_id, role=ROLE_MEMBER, is_active=True, user=first_user),
        SimpleNamespace(user_id=second_assignee_id, role=ROLE_MEMBER, is_active=True, user=second_user),
    ]
    sender = FakeMaxSender()
    service = TaskService(
        repository=repository,
        session=FakeSession(),
        sender=sender,  # type: ignore[arg-type]
        group_assignment_webapp_url="https://max.ru/secretary_oren_bot?startapp=group_assignment",
    )
    deadline_at = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    expected_deadline = deadline_at.astimezone(PROJECT_TIMEZONE).strftime("%d.%m.%Y %H:%M")

    result = await service.create_group_assignment(
        TaskGroupAssignmentCreate(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=creator_id,
            title="Сдать отчеты",
            deadline_at=deadline_at,
        ),
        AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
    )

    assert result.task_ref == "#1"
    assert len(sender.inline_messages) == 1
    message = str(sender.inline_messages[0]["text"])
    assert "Задача участникам чата создана ✅" in message
    assert "Текст: Сдать отчеты" in message
    assert "Исполнители: Мария Петрова, Петр Сидоров" in message
    assert f"Срок: {expected_deadline}" in message
    assert "Отчет: обязателен" in message
    assert "Задача: #1" in message
    assert "payload=" not in message
    assert "MAX chat #" not in message
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f-]{27,}", message, flags=re.IGNORECASE)
    assert sender.inline_messages[0]["chat_id"] == "max-chat-001"
    assert sender.inline_messages[0]["button_rows"] == [
        [
            {
                "type": "link",
                "text": "Открыть Дьяк",
                "url": "https://max.ru/secretary_oren_bot?startapp=group_assignment",
            }
        ]
    ]


@pytest.mark.anyio
async def test_task_service_group_report_creator_can_view_report() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    responded_user_id = uuid4()
    pending_user_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, responded_user_id, pending_user_id},
    )
    repository.group_report_task = _group_report_task(
        task_id=repository.task_id,
        organization_id=organization_id,
        chat_id=chat_id,
        creator_id=creator_id,
        responded_user_id=responded_user_id,
        pending_user_id=pending_user_id,
    )
    service = TaskService(repository=repository, session=FakeSession())

    result = await service.get_group_report(
        repository.task_id,
        AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id),
    )

    assert result.task_id == repository.task_id
    assert result.title == "Сдать отчеты"
    assert result.creator.user_id == creator_id
    assert result.creator.display_name == "Иван Руководитель"
    assert result.creator.role == ROLE_CHAT_ADMIN
    assert result.chat.chat_id == chat_id
    assert result.chat.title == "MAX group"
    assert result.total == 2
    assert result.responded == 1
    assert result.pending == 1
    assert result.overdue == 1
    assert result.items[0].user.user_id == responded_user_id
    assert result.items[0].user.display_name == "Петр Исполнитель"
    assert result.items[0].status == TaskAssigneeStatus.RESPONDED
    assert result.items[0].response_text == "Готово"
    assert result.items[1].user.display_name == "Пользователь #" + str(pending_user_id)[-8:]


@pytest.mark.anyio
async def test_task_service_group_report_allows_scoped_chat_admin() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    manager_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id, manager_id},
    )
    repository.group_report_task = _group_report_task(
        task_id=repository.task_id,
        organization_id=organization_id,
        chat_id=chat_id,
        creator_id=creator_id,
        responded_user_id=uuid4(),
        pending_user_id=uuid4(),
    )
    service = TaskService(repository=repository, session=FakeSession())

    result = await service.get_group_report(
        repository.task_id,
        AuthContext(user_id=manager_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
    )

    assert result.total == 2


@pytest.mark.anyio
async def test_task_service_group_report_allows_super_admin() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id},
    )
    repository.group_report_task = _group_report_task(
        task_id=repository.task_id,
        organization_id=organization_id,
        chat_id=chat_id,
        creator_id=creator_id,
        responded_user_id=uuid4(),
        pending_user_id=uuid4(),
    )
    service = TaskService(repository=repository, session=FakeSession())

    result = await service.get_group_report(
        repository.task_id,
        AuthContext(user_id=uuid4(), is_super_admin=True),
    )

    assert result.total == 2


@pytest.mark.anyio
async def test_task_service_group_report_forbids_outsider() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id},
    )
    repository.group_report_task = _group_report_task(
        task_id=repository.task_id,
        organization_id=organization_id,
        chat_id=chat_id,
        creator_id=creator_id,
        responded_user_id=uuid4(),
        pending_user_id=uuid4(),
    )
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.get_group_report(
            repository.task_id,
            AuthContext(
                user_id=uuid4(),
                organization_id=organization_id,
                chat_id=chat_id,
                roles=[ROLE_MEMBER],
            ),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_task_service_group_report_rejects_personal_task() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={creator_id},
    )
    task = _group_report_task(
        task_id=repository.task_id,
        organization_id=organization_id,
        chat_id=chat_id,
        creator_id=creator_id,
        responded_user_id=uuid4(),
        pending_user_id=uuid4(),
    )
    task.task_type = TaskType.PERSONAL.value
    repository.group_report_task = task
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.get_group_report(
            repository.task_id,
            AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Task is not a group assignment"


@pytest.mark.anyio
async def test_task_service_update_records_status_history_when_status_changes() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids=set(),
    )
    session = FakeSession()
    service = TaskService(repository=repository, session=session)

    result = await service.update(
        repository.task_id,
        TaskUpdate(
            title="Updated task",
            priority=TaskPriority.HIGH,
            status=TaskStatus.IN_PROGRESS,
        ),
    )

    assert result.title == "Updated task"
    assert result.priority == TaskPriority.HIGH.value
    assert result.status == TaskStatus.IN_PROGRESS.value
    assert session.committed is True
    assert repository.status_history_values == {
        "task_id": repository.task_id,
        "old_status": TaskStatus.NEW.value,
        "new_status": TaskStatus.IN_PROGRESS.value,
        "changed_by_user_id": None,
    }


@pytest.mark.anyio
async def test_task_service_update_rejects_past_deadline() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids=set(),
    )
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.update(
            repository.task_id,
            TaskUpdate(deadline_at=datetime.now(timezone.utc) - timedelta(minutes=1)),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "deadline_must_be_in_future"
    assert getattr(repository.detail_task, "deadline_at", None) is None


@pytest.mark.anyio
async def test_task_service_start_assignee_task_marks_task_and_assignee_in_progress() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    assignee_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={assignee_id},
    )
    assignee = SimpleNamespace(
        id=uuid4(),
        task_id=repository.task_id,
        user_id=assignee_id,
        status="assigned",
        response_required=True,
    )
    repository.assignees[assignee_id] = assignee
    repository.detail_task = SimpleNamespace(
        id=repository.task_id,
        organization_id=organization_id,
        status=TaskStatus.NEW.value,
        assignees=[assignee],
        cancelled_at=None,
    )
    session = FakeSession()
    service = TaskService(repository=repository, session=session)

    result = await service.start_assignee_task(repository.task_id, assignee_id)

    assert result.status == TaskStatus.IN_PROGRESS.value
    assert assignee.status == "in_progress"
    assert repository.status_history_values == {
        "task_id": repository.task_id,
        "old_status": TaskStatus.NEW.value,
        "new_status": TaskStatus.IN_PROGRESS.value,
        "changed_by_user_id": assignee_id,
    }
    assert session.committed is True


@pytest.mark.anyio
async def test_task_service_start_assignee_task_forbids_non_assignee() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={user_id},
    )
    repository.detail_task = SimpleNamespace(
        id=repository.task_id,
        organization_id=organization_id,
        status=TaskStatus.NEW.value,
        assignees=[],
        cancelled_at=None,
    )
    service = TaskService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.start_assignee_task(repository.task_id, user_id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Only task assignee can start task"


@pytest.mark.anyio
async def test_task_service_cancel_sets_cancelled_status_and_history() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids=set(),
    )
    session = FakeSession()
    service = TaskService(repository=repository, session=session)

    result = await service.cancel(repository.task_id)

    assert result.status == TaskStatus.CANCELLED.value
    assert result.cancelled_at is not None
    assert session.committed is True
    assert repository.status_history_values == {
        "task_id": repository.task_id,
        "old_status": TaskStatus.NEW.value,
        "new_status": TaskStatus.CANCELLED.value,
        "changed_by_user_id": None,
    }


@pytest.mark.anyio
async def test_task_service_rejects_cancel_for_done_task() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids=set(),
    )
    repository.detail_task.status = TaskStatus.DONE.value
    session = FakeSession()
    service = TaskService(repository=repository, session=session)

    with pytest.raises(HTTPException) as exc_info:
        await service.cancel(repository.task_id)

    assert exc_info.value.status_code == 409
    assert session.committed is False


@pytest.mark.anyio
async def test_task_service_add_assignee_writes_audit_log() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={user_id},
    )
    session = FakeSession()
    service = TaskService(repository=repository, session=session)

    assignee = await service.add_assignee(repository.task_id, TaskParticipantCreate(user_id=user_id))

    assert assignee.user_id == user_id
    assert assignee.status == "assigned"
    assert session.committed is True
    assert repository.audit_log_entries[-1] == {
        "organization_id": organization_id,
        "entity_id": repository.task_id,
        "action": "task.assignee_added",
        "payload": {"user_id": str(user_id)},
    }


@pytest.mark.anyio
async def test_task_service_rejects_duplicate_assignee() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={user_id},
    )
    repository.assignees[user_id] = SimpleNamespace(user_id=user_id)
    session = FakeSession()
    service = TaskService(repository=repository, session=session)

    with pytest.raises(HTTPException) as exc_info:
        await service.add_assignee(repository.task_id, TaskParticipantCreate(user_id=user_id))

    assert exc_info.value.status_code == 409
    assert session.committed is False


@pytest.mark.anyio
async def test_task_service_remove_observer_writes_audit_log() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    repository = FakeTaskRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_ids={user_id},
    )
    repository.observers[user_id] = SimpleNamespace(user_id=user_id)
    session = FakeSession()
    service = TaskService(repository=repository, session=session)

    await service.remove_observer(repository.task_id, user_id)

    assert user_id not in repository.observers
    assert session.committed is True
    assert repository.audit_log_entries[-1] == {
        "organization_id": organization_id,
        "entity_id": repository.task_id,
        "action": "task.observer_removed",
        "payload": {"user_id": str(user_id)},
    }
