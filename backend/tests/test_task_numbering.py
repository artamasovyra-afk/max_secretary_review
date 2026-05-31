from __future__ import annotations

import pytest

from app.modules.tasks.enums import TaskCompletionRule, TaskPriority, TaskStatus
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.task_numbering import format_task_ref, normalize_task_ref


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1042", 1042),
        ("#1042", 1042),
        ("T-1042", 1042),
        ("t-1042", 1042),
        ("  #1042  ", 1042),
        (1042, 1042),
    ],
)
def test_normalize_task_ref_accepts_supported_formats(value: str | int, expected: int) -> None:
    assert normalize_task_ref(value) == expected


@pytest.mark.parametrize("value", [None, "", "#", "T-", "task-1042", "#0", 0, -1, "abc"])
def test_normalize_task_ref_rejects_invalid_values(value: str | int | None) -> None:
    assert normalize_task_ref(value) is None


def test_format_task_ref() -> None:
    assert format_task_ref(1042) == "#1042"


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.flushed = False

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed = True


class FixedNumberTaskRepository(TaskRepository):
    async def next_task_number(self, organization_id):  # type: ignore[override]
        self.last_organization_id = organization_id
        return 7


@pytest.mark.anyio
async def test_repository_assigns_next_task_number_on_create() -> None:
    from uuid import uuid4

    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    session = FakeSession()
    repository = FixedNumberTaskRepository(session)  # type: ignore[arg-type]

    task = await repository.create_task(
        organization_id=organization_id,
        chat_id=chat_id,
        title="Prepare report",
        description=None,
        source_message_id=None,
        created_by_user_id=user_id,
        deadline_at=None,
        status=TaskStatus.NEW.value,
        priority=TaskPriority.NORMAL.value,
        completion_rule=TaskCompletionRule.ANY_ASSIGNEE_RESPONSE.value,
    )

    assert task.task_number == 7
    assert repository.last_organization_id == organization_id
    assert session.added == [task]
    assert session.flushed is True
