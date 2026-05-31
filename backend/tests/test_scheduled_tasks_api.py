from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.scheduled_tasks import get_scheduled_task_service
from app.core.config import get_settings
from app.main import create_app
from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_MEMBER
from app.modules.tasks.enums import ScheduledTaskScheduleType
from app.modules.tasks.scheduled_schemas import (
    ScheduledTaskCreate,
    ScheduledTaskRead,
    ScheduledTaskUpdate,
)


class FakeScheduledTaskService:
    def __init__(self) -> None:
        self.schedules: dict[UUID, ScheduledTaskRead] = {}
        self.last_create_payload: Optional[ScheduledTaskCreate] = None
        self.last_create_context: Optional[AuthContext] = None
        self.last_list_context: Optional[AuthContext] = None
        self.last_get_context: Optional[AuthContext] = None
        self.last_update_payload: Optional[ScheduledTaskUpdate] = None
        self.last_delete_context: Optional[AuthContext] = None

    async def create(
        self,
        payload: ScheduledTaskCreate,
        auth_context: AuthContext,
    ) -> ScheduledTaskRead:
        self.last_create_payload = payload
        self.last_create_context = auth_context
        schedule = _schedule_read(
            template_id=payload.template_id,
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            created_by_user_id=payload.created_by_user_id,
            schedule_type=payload.schedule_type,
            scheduled_for=payload.scheduled_for,
            repeat_rule=payload.repeat_rule,
            timezone_name=payload.timezone,
            next_run_at=payload.next_run_at,
            is_active=payload.is_active,
        )
        self.schedules[schedule.id] = schedule
        return schedule

    async def list(
        self,
        *,
        auth_context: AuthContext,
        organization_id: UUID | None = None,
        chat_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
        is_active: bool | None = True,
    ) -> list[ScheduledTaskRead]:
        self.last_list_context = auth_context
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

    async def get(self, scheduled_task_id: UUID, auth_context: AuthContext) -> ScheduledTaskRead:
        self.last_get_context = auth_context
        return self.schedules[scheduled_task_id]

    async def update(
        self,
        scheduled_task_id: UUID,
        payload: ScheduledTaskUpdate,
        auth_context: AuthContext,
    ) -> ScheduledTaskRead:
        self.last_update_payload = payload
        self.last_get_context = auth_context
        schedule = self.schedules[scheduled_task_id]
        values = payload.model_dump(exclude_unset=True)
        updated = schedule.model_copy(update=values)
        self.schedules[scheduled_task_id] = updated
        return updated

    async def delete(self, scheduled_task_id: UUID, auth_context: AuthContext) -> ScheduledTaskRead:
        self.last_delete_context = auth_context
        schedule = self.schedules[scheduled_task_id].model_copy(update={"is_active": False})
        self.schedules[scheduled_task_id] = schedule
        return schedule


def _schedule_read(
    *,
    template_id: UUID,
    organization_id: UUID,
    chat_id: UUID,
    created_by_user_id: UUID,
    schedule_type: ScheduledTaskScheduleType = ScheduledTaskScheduleType.ONE_TIME,
    scheduled_for: datetime | None = None,
    repeat_rule: dict[str, object] | None = None,
    timezone_name: str = "UTC",
    next_run_at: datetime | None = None,
    is_active: bool = True,
) -> ScheduledTaskRead:
    now = datetime.now(timezone.utc)
    return ScheduledTaskRead(
        id=uuid4(),
        template_id=template_id,
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=created_by_user_id,
        schedule_type=schedule_type,
        scheduled_for=scheduled_for,
        repeat_rule=repeat_rule,
        timezone=timezone_name,
        next_run_at=next_run_at or now,
        last_run_at=None,
        is_active=is_active,
        last_error=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def scheduled_tasks_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeScheduledTaskService]:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    app = create_app()
    service = FakeScheduledTaskService()
    app.dependency_overrides[get_scheduled_task_service] = lambda: service
    with TestClient(app) as client:
        yield client, service


def _payload(
    *,
    template_id: UUID,
    organization_id: UUID,
    chat_id: UUID,
    created_by_user_id: UUID,
) -> dict[str, object]:
    return {
        "template_id": str(template_id),
        "organization_id": str(organization_id),
        "chat_id": str(chat_id),
        "created_by_user_id": str(created_by_user_id),
        "schedule_type": ScheduledTaskScheduleType.ONE_TIME.value,
        "scheduled_for": None,
        "repeat_rule": None,
        "timezone": "UTC",
        "next_run_at": "2026-05-21T09:00:00Z",
        "is_active": True,
    }


def _auth_headers(
    *,
    user_id: UUID,
    organization_id: UUID,
    chat_id: UUID,
    roles: str = ROLE_MEMBER,
) -> dict[str, str]:
    return {
        "X-User-Id": str(user_id),
        "X-Organization-Id": str(organization_id),
        "X-Chat-Id": str(chat_id),
        "X-Roles": roles,
    }


def test_create_scheduled_task(scheduled_tasks_client: tuple[TestClient, FakeScheduledTaskService]) -> None:
    client, service = scheduled_tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    template_id = uuid4()

    response = client.post(
        "/api/scheduled-tasks",
        json=_payload(
            template_id=template_id,
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=user_id,
        ),
        headers=_auth_headers(
            user_id=user_id,
            organization_id=organization_id,
            chat_id=chat_id,
        ),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["template_id"] == str(template_id)
    assert payload["schedule_type"] == ScheduledTaskScheduleType.ONE_TIME.value
    assert payload["timezone"] == "UTC"
    assert service.last_create_payload is not None
    assert service.last_create_context is not None
    assert service.last_create_context.user_id == user_id


def test_list_scheduled_tasks(scheduled_tasks_client: tuple[TestClient, FakeScheduledTaskService]) -> None:
    client, service = scheduled_tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    schedule = _schedule_read(
        template_id=uuid4(),
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=user_id,
    )
    service.schedules[schedule.id] = schedule

    response = client.get(
        "/api/scheduled-tasks",
        params={"organization_id": str(organization_id)},
        headers=_auth_headers(
            user_id=user_id,
            organization_id=organization_id,
            chat_id=chat_id,
            roles=ROLE_CHAT_ADMIN,
        ),
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(schedule.id)
    assert service.last_list_context is not None
    assert service.last_list_context.roles == [ROLE_CHAT_ADMIN]


def test_get_update_and_delete_scheduled_task(
    scheduled_tasks_client: tuple[TestClient, FakeScheduledTaskService],
) -> None:
    client, service = scheduled_tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    schedule = _schedule_read(
        template_id=uuid4(),
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=user_id,
    )
    service.schedules[schedule.id] = schedule
    headers = _auth_headers(
        user_id=user_id,
        organization_id=organization_id,
        chat_id=chat_id,
    )

    get_response = client.get(f"/api/scheduled-tasks/{schedule.id}", headers=headers)
    update_response = client.patch(
        f"/api/scheduled-tasks/{schedule.id}",
        json={
            "schedule_type": ScheduledTaskScheduleType.DAILY.value,
            "repeat_rule": {"interval": 1},
        },
        headers=headers,
    )
    delete_response = client.delete(f"/api/scheduled-tasks/{schedule.id}", headers=headers)

    assert get_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["schedule_type"] == ScheduledTaskScheduleType.DAILY.value
    assert update_response.json()["repeat_rule"] == {"interval": 1}
    assert service.last_update_payload is not None
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False
    assert service.last_delete_context is not None


def test_scheduled_task_endpoints_require_auth(
    scheduled_tasks_client: tuple[TestClient, FakeScheduledTaskService],
) -> None:
    client, service = scheduled_tasks_client
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()

    response = client.post(
        "/api/scheduled-tasks",
        json=_payload(
            template_id=uuid4(),
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=user_id,
        ),
    )

    assert response.status_code == 401
    assert service.last_create_payload is None
