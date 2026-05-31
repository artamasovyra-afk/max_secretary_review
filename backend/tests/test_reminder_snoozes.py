from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.modules.reminders.service import ReminderService


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.refreshed: object | None = None

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, instance: object) -> None:
        self.refreshed = instance


class FakeReminderRepository:
    def __init__(self, task_id: UUID) -> None:
        self.task_id = task_id
        self.task = SimpleNamespace(id=task_id)
        self.snoozes: list[SimpleNamespace] = []

    async def get_task(self, task_id: UUID) -> SimpleNamespace | None:
        if task_id == self.task_id:
            return self.task
        return None

    async def create_snooze(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        snoozed_until: datetime,
        reason: str | None = None,
    ) -> SimpleNamespace:
        snooze = SimpleNamespace(
            id=uuid4(),
            task_id=task_id,
            user_id=user_id,
            snoozed_until=snoozed_until,
            reason=reason,
            created_at=datetime.now(timezone.utc),
        )
        self.snoozes.append(snooze)
        return snooze

    async def get_active_snooze(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> SimpleNamespace | None:
        active = [
            snooze
            for snooze in self.snoozes
            if snooze.task_id == task_id
            and snooze.user_id == user_id
            and snooze.snoozed_until > now
        ]
        if not active:
            return None
        return max(active, key=lambda snooze: snooze.snoozed_until)


@pytest.mark.anyio
async def test_create_snooze_for_one_hour() -> None:
    task_id = uuid4()
    user_id = uuid4()
    now = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    repository = FakeReminderRepository(task_id)
    session = FakeSession()
    service = ReminderService(repository=repository, session=session)

    snooze = await service.create_snooze(task_id, user_id, "1h", now=now)

    assert snooze.task_id == task_id
    assert snooze.user_id == user_id
    assert snooze.snoozed_until == now + timedelta(hours=1)
    assert snooze.reason == "1h"
    assert session.committed is True
    assert session.refreshed is snooze


@pytest.mark.anyio
async def test_create_snooze_for_three_hours() -> None:
    task_id = uuid4()
    user_id = uuid4()
    now = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    service = ReminderService(repository=FakeReminderRepository(task_id), session=FakeSession())

    snooze = await service.create_snooze(task_id, user_id, "3h", now=now, reason="manual callback")

    assert snooze.snoozed_until == now + timedelta(hours=3)
    assert snooze.reason == "manual callback"


@pytest.mark.anyio
async def test_create_snooze_until_tomorrow_09_utc() -> None:
    task_id = uuid4()
    user_id = uuid4()
    now = datetime(2026, 5, 21, 23, 30, tzinfo=timezone.utc)
    service = ReminderService(repository=FakeReminderRepository(task_id), session=FakeSession())

    snooze = await service.create_snooze(task_id, user_id, "tomorrow_09", now=now)

    assert snooze.snoozed_until == datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc)
    assert snooze.reason == "tomorrow_09"


@pytest.mark.anyio
async def test_get_active_snooze_returns_latest_active_snooze() -> None:
    task_id = uuid4()
    user_id = uuid4()
    now = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    repository = FakeReminderRepository(task_id)
    service = ReminderService(repository=repository, session=FakeSession())
    await service.create_snooze(task_id, user_id, "1h", now=now)
    latest = await service.create_snooze(task_id, user_id, "3h", now=now)

    active = await service.get_active_snooze(task_id, user_id, now)

    assert active is latest


@pytest.mark.anyio
async def test_is_snoozed_returns_false_after_snooze_expires() -> None:
    task_id = uuid4()
    user_id = uuid4()
    now = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    repository = FakeReminderRepository(task_id)
    service = ReminderService(repository=repository, session=FakeSession())
    await service.create_snooze(task_id, user_id, "1h", now=now)

    assert await service.is_snoozed(task_id, user_id, now + timedelta(minutes=30)) is True
    assert await service.is_snoozed(task_id, user_id, now + timedelta(hours=2)) is False


@pytest.mark.anyio
async def test_create_snooze_returns_404_for_unknown_task() -> None:
    task_id = uuid4()
    service = ReminderService(repository=FakeReminderRepository(task_id), session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_snooze(uuid4(), uuid4(), "1h")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Task not found"
