from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.api.chats import get_chat_service, get_reminder_service as get_chat_reminder_service
from app.api.tasks import get_reminder_service as get_task_reminder_service, get_task_service
from app.core.config import get_settings
from app.main import create_app
from app.modules.reminders.schemas import ReminderRuleCreate, ReminderRuleUpdate, ReminderType


class ReminderRuleRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    chat_id: Optional[UUID]
    task_id: Optional[UUID]
    reminder_type: str
    offset_minutes: Optional[int]
    repeat_interval_minutes: Optional[int]
    max_repeats: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FakeReminderRuleService:
    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.task_id = uuid4()
        self.chat_id = uuid4()
        self.task_rules: dict[UUID, ReminderRuleRecord] = {}
        self.chat_rules: dict[UUID, ReminderRuleRecord] = {}

    async def create_task_rule(
        self,
        task_id: UUID,
        payload: ReminderRuleCreate,
    ) -> ReminderRuleRecord:
        self._ensure_task(task_id)
        rule = self._rule(
            task_id=task_id,
            chat_id=None,
            reminder_type=payload.reminder_type.value,
            offset_minutes=payload.offset_minutes,
            repeat_interval_minutes=payload.repeat_interval_minutes,
            max_repeats=payload.max_repeats,
            is_active=payload.is_active,
        )
        self.task_rules[rule.id] = rule
        return rule

    async def list_task_rules(self, task_id: UUID) -> list[ReminderRuleRecord]:
        self._ensure_task(task_id)
        return [rule for rule in self.task_rules.values() if rule.task_id == task_id]

    async def update_task_rule(
        self,
        *,
        task_id: UUID,
        rule_id: UUID,
        payload: ReminderRuleUpdate,
    ) -> ReminderRuleRecord:
        self._ensure_task(task_id)
        rule = self.task_rules.get(rule_id)
        if rule is None or rule.task_id != task_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reminder rule not found",
            )
        values = payload.model_dump(exclude_unset=True)
        if "reminder_type" in values:
            values["reminder_type"] = values["reminder_type"].value
        values["updated_at"] = datetime.now(timezone.utc)
        updated = rule.model_copy(update=values)
        self.task_rules[rule_id] = updated
        return updated

    async def delete_task_rule(self, *, task_id: UUID, rule_id: UUID) -> None:
        self._ensure_task(task_id)
        rule = self.task_rules.get(rule_id)
        if rule is None or rule.task_id != task_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reminder rule not found",
            )
        self.task_rules.pop(rule_id)

    async def create_chat_rule(
        self,
        chat_id: UUID,
        payload: ReminderRuleCreate,
    ) -> ReminderRuleRecord:
        self._ensure_chat(chat_id)
        rule = self._rule(
            task_id=None,
            chat_id=chat_id,
            reminder_type=payload.reminder_type.value,
            offset_minutes=payload.offset_minutes,
            repeat_interval_minutes=payload.repeat_interval_minutes,
            max_repeats=payload.max_repeats,
            is_active=payload.is_active,
        )
        self.chat_rules[rule.id] = rule
        return rule

    async def list_chat_rules(self, chat_id: UUID) -> list[ReminderRuleRecord]:
        self._ensure_chat(chat_id)
        return [rule for rule in self.chat_rules.values() if rule.chat_id == chat_id]

    def _rule(
        self,
        *,
        task_id: UUID | None,
        chat_id: UUID | None,
        reminder_type: str,
        offset_minutes: int | None,
        repeat_interval_minutes: int | None,
        max_repeats: int | None,
        is_active: bool,
    ) -> ReminderRuleRecord:
        now = datetime.now(timezone.utc)
        return ReminderRuleRecord(
            id=uuid4(),
            organization_id=self.organization_id,
            chat_id=chat_id,
            task_id=task_id,
            reminder_type=reminder_type,
            offset_minutes=offset_minutes,
            repeat_interval_minutes=repeat_interval_minutes,
            max_repeats=max_repeats,
            is_active=is_active,
            created_at=now,
            updated_at=now,
        )

    def _ensure_task(self, task_id: UUID) -> None:
        if task_id != self.task_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

    def _ensure_chat(self, chat_id: UUID) -> None:
        if chat_id != self.chat_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found",
            )


@pytest.fixture()
def reminder_rules_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, FakeReminderRuleService]:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    app = create_app()
    service = FakeReminderRuleService()
    app.dependency_overrides[get_task_reminder_service] = lambda: service
    app.dependency_overrides[get_chat_reminder_service] = lambda: service
    app.dependency_overrides[get_task_service] = lambda: FakeTaskAccessService(service)
    app.dependency_overrides[get_chat_service] = lambda: FakeChatAccessService(service)
    with TestClient(app, headers=_auth_headers()) as client:
        yield client, service


class FakeTaskAccessService:
    def __init__(self, service: FakeReminderRuleService) -> None:
        self.service = service

    async def get(self, task_id: UUID) -> SimpleNamespace:
        self.service._ensure_task(task_id)
        return SimpleNamespace(
            id=task_id,
            organization_id=self.service.organization_id,
            chat_id=self.service.chat_id,
            created_by_user_id=uuid4(),
            assignees=[],
            observers=[],
        )


class FakeChatAccessService:
    def __init__(self, service: FakeReminderRuleService) -> None:
        self.service = service

    async def get(self, chat_id: UUID) -> SimpleNamespace:
        self.service._ensure_chat(chat_id)
        return SimpleNamespace(
            id=chat_id,
            organization_id=self.service.organization_id,
        )


def _auth_headers() -> dict[str, str]:
    return {
        "X-User-Id": str(uuid4()),
        "X-Roles": "super_admin",
    }


def test_task_reminder_rule_crud(
    reminder_rules_client: tuple[TestClient, FakeReminderRuleService],
) -> None:
    client, service = reminder_rules_client

    create_response = client.post(
        f"/api/tasks/{service.task_id}/reminder-rules",
        json={
            "reminder_type": ReminderType.BEFORE_DEADLINE.value,
            "offset_minutes": 60,
            "repeat_interval_minutes": 30,
            "max_repeats": 3,
            "is_active": True,
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    rule_id = created["id"]
    assert created["task_id"] == str(service.task_id)
    assert created["chat_id"] is None
    assert created["reminder_type"] == ReminderType.BEFORE_DEADLINE.value
    assert created["offset_minutes"] == 60

    list_response = client.get(f"/api/tasks/{service.task_id}/reminder-rules")

    assert list_response.status_code == 200
    assert [rule["id"] for rule in list_response.json()] == [rule_id]

    update_response = client.patch(
        f"/api/tasks/{service.task_id}/reminder-rules/{rule_id}",
        json={
            "reminder_type": ReminderType.NO_RESPONSE_AFTER_DEADLINE.value,
            "is_active": False,
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["reminder_type"] == ReminderType.NO_RESPONSE_AFTER_DEADLINE.value
    assert updated["is_active"] is False
    assert updated["offset_minutes"] == 60

    delete_response = client.delete(f"/api/tasks/{service.task_id}/reminder-rules/{rule_id}")

    assert delete_response.status_code == 204
    assert client.get(f"/api/tasks/{service.task_id}/reminder-rules").json() == []


def test_chat_reminder_rules_can_be_created_and_listed(
    reminder_rules_client: tuple[TestClient, FakeReminderRuleService],
) -> None:
    client, service = reminder_rules_client

    create_response = client.post(
        f"/api/chats/{service.chat_id}/reminder-rules",
        json={
            "reminder_type": ReminderType.DAILY_SUMMARY.value,
            "is_active": True,
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["chat_id"] == str(service.chat_id)
    assert created["task_id"] is None
    assert created["reminder_type"] == ReminderType.DAILY_SUMMARY.value

    list_response = client.get(f"/api/chats/{service.chat_id}/reminder-rules")

    assert list_response.status_code == 200
    assert [rule["id"] for rule in list_response.json()] == [created["id"]]


def test_reminder_rule_rejects_unknown_type(
    reminder_rules_client: tuple[TestClient, FakeReminderRuleService],
) -> None:
    client, service = reminder_rules_client

    response = client.post(
        f"/api/tasks/{service.task_id}/reminder-rules",
        json={"reminder_type": "unsupported"},
    )

    assert response.status_code == 422
