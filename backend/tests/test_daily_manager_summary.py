from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_MEMBER, ROLE_SUPER_ADMIN
from app.modules.reminders.manager_summary import (
    DailyManagerSummaryForbidden,
    DailyManagerSummaryService,
)
from app.modules.tasks.enums import TaskStatus


class FakeDailyManagerSummaryRepository:
    def __init__(self, tasks: list[SimpleNamespace]) -> None:
        self.tasks = tasks
        self.chat_calls: list[dict[str, object]] = []
        self.manager_calls: list[dict[str, object]] = []

    async def list_tasks_for_chat(self, *, chat_id, summary_date: date):
        self.chat_calls.append({"chat_id": chat_id, "summary_date": summary_date})
        return [task for task in self.tasks if task.chat_id == chat_id]

    async def list_tasks_for_manager(self, *, manager_user_id, summary_date: date, include_all: bool = False):
        self.manager_calls.append(
            {
                "manager_user_id": manager_user_id,
                "summary_date": summary_date,
                "include_all": include_all,
            }
        )
        if include_all:
            return list(self.tasks)
        return [
            task
            for task in self.tasks
            if task.created_by_user_id == manager_user_id or task.manager_user_id == manager_user_id
        ]


def make_context(
    *,
    user_id,
    roles: list[str],
    chat_id=None,
    is_super_admin: bool = False,
) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        chat_id=chat_id,
        roles=roles,
        is_super_admin=is_super_admin,
    )


def make_task(
    *,
    title: str,
    status: TaskStatus,
    deadline_at: datetime | None,
    chat_id,
    created_by_user_id,
    assignee_ids: list[object] | None = None,
    manager_user_id=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        status=status.value,
        deadline_at=deadline_at,
        chat_id=chat_id,
        created_by_user_id=created_by_user_id,
        manager_user_id=manager_user_id or created_by_user_id,
        assignees=[SimpleNamespace(user_id=user_id) for user_id in (assignee_ids or [])],
    )


@pytest.mark.anyio
async def test_build_summary_for_chat_returns_empty_summary_without_tasks() -> None:
    manager_user_id = uuid4()
    chat_id = uuid4()
    repository = FakeDailyManagerSummaryRepository(tasks=[])
    service = DailyManagerSummaryService(
        repository=repository,  # type: ignore[arg-type]
        auth_context=make_context(user_id=manager_user_id, roles=[ROLE_CHAT_ADMIN], chat_id=chat_id),
    )

    summary = await service.build_summary_for_chat(chat_id, manager_user_id, date(2026, 5, 21))

    assert summary.manager_user_id == manager_user_id
    assert summary.chat_id == chat_id
    assert summary.total_today == 0
    assert summary.overdue == 0
    assert summary.waiting_response == 0
    assert summary.waiting_acceptance == 0
    assert summary.top_overdue_items == ()
    assert summary.pending_acceptance_items == ()


@pytest.mark.anyio
async def test_build_summary_for_chat_counts_overdue_and_top_items() -> None:
    manager_user_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    older_overdue = make_task(
        title="Сдать отчет",
        status=TaskStatus.IN_PROGRESS,
        deadline_at=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
        chat_id=chat_id,
        created_by_user_id=creator_id,
    )
    marked_overdue = make_task(
        title="Проверить доступ",
        status=TaskStatus.OVERDUE,
        deadline_at=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
        chat_id=chat_id,
        created_by_user_id=creator_id,
    )
    done_old_task = make_task(
        title="Закрытая старая задача",
        status=TaskStatus.DONE,
        deadline_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        chat_id=chat_id,
        created_by_user_id=creator_id,
    )
    repository = FakeDailyManagerSummaryRepository(tasks=[marked_overdue, done_old_task, older_overdue])
    service = DailyManagerSummaryService(
        repository=repository,  # type: ignore[arg-type]
        auth_context=make_context(user_id=manager_user_id, roles=[ROLE_CHAT_ADMIN], chat_id=chat_id),
    )

    summary = await service.build_summary_for_chat(chat_id, manager_user_id, date(2026, 5, 21))

    assert summary.overdue == 2
    assert [item.title for item in summary.top_overdue_items] == ["Сдать отчет", "Проверить доступ"]


@pytest.mark.anyio
async def test_build_summary_for_chat_counts_waiting_acceptance_items() -> None:
    manager_user_id = uuid4()
    chat_id = uuid4()
    task = make_task(
        title="Принять результат",
        status=TaskStatus.WAITING_ACCEPTANCE,
        deadline_at=datetime(2026, 5, 21, 16, 0, tzinfo=timezone.utc),
        chat_id=chat_id,
        created_by_user_id=manager_user_id,
    )
    repository = FakeDailyManagerSummaryRepository(tasks=[task])
    service = DailyManagerSummaryService(
        repository=repository,  # type: ignore[arg-type]
        auth_context=make_context(user_id=manager_user_id, roles=[ROLE_CHAT_ADMIN], chat_id=chat_id),
    )

    summary = await service.build_summary_for_chat(chat_id, manager_user_id, date(2026, 5, 21))

    assert summary.total_today == 1
    assert summary.waiting_acceptance == 1
    assert summary.pending_acceptance_items[0].title == "Принять результат"
    assert summary.pending_acceptance_items[0].status == TaskStatus.WAITING_ACCEPTANCE.value


@pytest.mark.anyio
async def test_build_summary_for_chat_preserves_multiple_assignees_in_items() -> None:
    manager_user_id = uuid4()
    chat_id = uuid4()
    assignee_ids = [uuid4(), uuid4(), uuid4()]
    task = make_task(
        title="Собрать индивидуальные отчеты",
        status=TaskStatus.WAITING_ACCEPTANCE,
        deadline_at=datetime(2026, 5, 21, 18, 0, tzinfo=timezone.utc),
        chat_id=chat_id,
        created_by_user_id=manager_user_id,
        assignee_ids=assignee_ids,
    )
    repository = FakeDailyManagerSummaryRepository(tasks=[task])
    service = DailyManagerSummaryService(
        repository=repository,  # type: ignore[arg-type]
        auth_context=make_context(user_id=manager_user_id, roles=[ROLE_CHAT_ADMIN], chat_id=chat_id),
    )

    summary = await service.build_summary_for_chat(chat_id, manager_user_id, date(2026, 5, 21))

    item = summary.pending_acceptance_items[0]
    assert item.assignee_count == 3
    assert item.assignee_ids == tuple(assignee_ids)


@pytest.mark.anyio
async def test_build_summary_for_manager_counts_waiting_response() -> None:
    manager_user_id = uuid4()
    manager_task = make_task(
        title="Ожидаем ответ",
        status=TaskStatus.WAITING_RESPONSE,
        deadline_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
        chat_id=uuid4(),
        created_by_user_id=uuid4(),
        manager_user_id=manager_user_id,
    )
    other_task = make_task(
        title="Чужая задача",
        status=TaskStatus.WAITING_RESPONSE,
        deadline_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
        chat_id=uuid4(),
        created_by_user_id=uuid4(),
        manager_user_id=uuid4(),
    )
    repository = FakeDailyManagerSummaryRepository(tasks=[manager_task, other_task])
    service = DailyManagerSummaryService(
        repository=repository,  # type: ignore[arg-type]
        auth_context=make_context(user_id=manager_user_id, roles=[ROLE_CHAT_ADMIN]),
    )

    summary = await service.build_summary_for_manager(manager_user_id, date(2026, 5, 21))

    assert summary.chat_id is None
    assert summary.total_today == 1
    assert summary.waiting_response == 1
    assert repository.manager_calls[0]["include_all"] is False


@pytest.mark.anyio
async def test_super_admin_can_build_summary_for_another_manager() -> None:
    super_admin_id = uuid4()
    manager_user_id = uuid4()
    task = make_task(
        title="Любая задача",
        status=TaskStatus.WAITING_RESPONSE,
        deadline_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
        chat_id=uuid4(),
        created_by_user_id=uuid4(),
    )
    repository = FakeDailyManagerSummaryRepository(tasks=[task])
    service = DailyManagerSummaryService(
        repository=repository,  # type: ignore[arg-type]
        auth_context=make_context(
            user_id=super_admin_id,
            roles=[ROLE_SUPER_ADMIN],
            is_super_admin=True,
        ),
    )

    summary = await service.build_summary_for_manager(manager_user_id, date(2026, 5, 21))

    assert summary.waiting_response == 1
    assert repository.manager_calls[0]["include_all"] is True


@pytest.mark.anyio
async def test_member_cannot_build_manager_summary() -> None:
    user_id = uuid4()
    repository = FakeDailyManagerSummaryRepository(tasks=[])
    service = DailyManagerSummaryService(
        repository=repository,  # type: ignore[arg-type]
        auth_context=make_context(user_id=user_id, roles=[ROLE_MEMBER]),
    )

    with pytest.raises(DailyManagerSummaryForbidden):
        await service.build_summary_for_manager(user_id, date(2026, 5, 21))


@pytest.mark.anyio
async def test_chat_admin_cannot_build_summary_for_another_admin() -> None:
    user_id = uuid4()
    repository = FakeDailyManagerSummaryRepository(tasks=[])
    service = DailyManagerSummaryService(
        repository=repository,  # type: ignore[arg-type]
        auth_context=make_context(user_id=user_id, roles=[ROLE_CHAT_ADMIN]),
    )

    with pytest.raises(DailyManagerSummaryForbidden):
        await service.build_summary_for_manager(uuid4(), date(2026, 5, 21))


@pytest.mark.anyio
async def test_legacy_manager_role_cannot_build_manager_summary() -> None:
    user_id = uuid4()
    repository = FakeDailyManagerSummaryRepository(tasks=[])
    service = DailyManagerSummaryService(
        repository=repository,  # type: ignore[arg-type]
        auth_context=make_context(user_id=user_id, roles=["manager"]),
    )

    with pytest.raises(DailyManagerSummaryForbidden):
        await service.build_summary_for_manager(user_id, date(2026, 5, 21))
