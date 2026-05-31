from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.modules.integrations.bitrix24.exceptions import Bitrix24MappingError
from app.modules.integrations.bitrix24.mapper import Bitrix24TaskMapper, TASK_SOURCE_MARKER
from app.modules.integrations.enums import BitrixUserMatchSource


def make_mapping(
    *,
    organization_id: UUID,
    user_id: UUID,
    bitrix_user_id: str,
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        organization_id=organization_id,
        user_id=user_id,
        bitrix_user_id=bitrix_user_id,
        match_source=BitrixUserMatchSource.MANUAL.value,
        is_active=is_active,
    )


def make_participant(user_id: UUID, display_name: str) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, user=SimpleNamespace(display_name=display_name))


def make_task(
    *,
    organization_id: UUID,
    created_by_user_id: UUID,
    assignees: list[SimpleNamespace],
    observers: list[SimpleNamespace] | None = None,
    deadline_at: datetime | None = None,
    description: str | None = "Подготовить отчет",
    source_message_id: str | None = "max-message-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        chat_id=uuid4(),
        source_message_id=source_message_id,
        title="Подготовить отчет",
        description=description,
        created_by_user_id=created_by_user_id,
        deadline_at=deadline_at,
        assignees=assignees,
        observers=observers or [],
    )


def test_maps_single_assignee_with_active_mapping_to_responsible_id() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
    )
    mapper = Bitrix24TaskMapper(settings=Settings())

    fields = mapper.to_task_add_fields(
        task=task,
        user_mappings=[
            make_mapping(organization_id=organization_id, user_id=assignee_id, bitrix_user_id="101"),
        ],
    )

    assert fields["TITLE"] == task.title
    assert fields["RESPONSIBLE_ID"] == "101"
    assert fields["ACCOMPLICES"] == []
    assert fields["CREATED_BY"] == "101"


def test_maps_multiple_assignees_to_responsible_and_accomplices() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    first_assignee_id = uuid4()
    second_assignee_id = uuid4()
    third_assignee_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[
            make_participant(first_assignee_id, "Иван"),
            make_participant(second_assignee_id, "Мария"),
            make_participant(third_assignee_id, "Петр"),
        ],
    )
    mapper = Bitrix24TaskMapper(settings=Settings())

    fields = mapper.to_task_add_fields(
        task=task,
        user_mappings=[
            make_mapping(organization_id=organization_id, user_id=first_assignee_id, bitrix_user_id="101"),
            make_mapping(organization_id=organization_id, user_id=second_assignee_id, bitrix_user_id="102"),
            make_mapping(organization_id=organization_id, user_id=third_assignee_id, bitrix_user_id="103"),
        ],
    )

    assert fields["RESPONSIBLE_ID"] == "101"
    assert fields["ACCOMPLICES"] == ["102", "103"]
    assert "101" not in fields["ACCOMPLICES"]


def test_maps_observers_to_auditors() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    observer_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
        observers=[make_participant(observer_id, "Сергей")],
    )
    mapper = Bitrix24TaskMapper(settings=Settings())

    fields = mapper.to_task_add_fields(
        task=task,
        user_mappings=[
            make_mapping(organization_id=organization_id, user_id=assignee_id, bitrix_user_id="101"),
            make_mapping(organization_id=organization_id, user_id=observer_id, bitrix_user_id="201"),
        ],
    )

    assert fields["AUDITORS"] == ["201"]


def test_maps_deadline_to_iso_format() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    deadline_at = datetime(2026, 5, 20, 9, 30, tzinfo=timezone.utc)
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
        deadline_at=deadline_at,
    )
    mapper = Bitrix24TaskMapper(settings=Settings())

    fields = mapper.to_task_add_fields(
        task=task,
        user_mappings=[
            make_mapping(organization_id=organization_id, user_id=assignee_id, bitrix_user_id="101"),
        ],
    )

    assert fields["DEADLINE"] == deadline_at.isoformat()


def test_omits_deadline_when_task_has_no_deadline() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
        deadline_at=None,
    )
    mapper = Bitrix24TaskMapper(settings=Settings())

    fields = mapper.to_task_add_fields(
        task=task,
        user_mappings=[
            make_mapping(organization_id=organization_id, user_id=assignee_id, bitrix_user_id="101"),
        ],
    )

    assert "DEADLINE" not in fields


def test_uses_default_responsible_when_assignee_mapping_is_missing() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
    )
    mapper = Bitrix24TaskMapper(
        settings=Settings(bitrix24_default_responsible_id="900")
    )

    fields = mapper.to_task_add_fields(task=task, user_mappings=[])

    assert fields["RESPONSIBLE_ID"] == "900"
    assert fields["CREATED_BY"] == "900"


def test_raises_when_responsible_cannot_be_resolved() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
    )
    mapper = Bitrix24TaskMapper(settings=Settings())

    with pytest.raises(Bitrix24MappingError, match="RESPONSIBLE_ID cannot be resolved"):
        mapper.to_task_add_fields(task=task, user_mappings=[])


def test_uses_creator_mapping_for_created_by() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
    )
    mapper = Bitrix24TaskMapper(settings=Settings())

    fields = mapper.to_task_add_fields(
        task=task,
        user_mappings=[
            make_mapping(organization_id=organization_id, user_id=assignee_id, bitrix_user_id="101"),
            make_mapping(organization_id=organization_id, user_id=creator_id, bitrix_user_id="301"),
        ],
    )

    assert fields["CREATED_BY"] == "301"


def test_uses_default_created_by_when_creator_mapping_is_missing() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
    )
    mapper = Bitrix24TaskMapper(
        settings=Settings(bitrix24_default_created_by_id="302")
    )

    fields = mapper.to_task_add_fields(
        task=task,
        user_mappings=[
            make_mapping(organization_id=organization_id, user_id=assignee_id, bitrix_user_id="101"),
        ],
    )

    assert fields["CREATED_BY"] == "302"


def test_created_by_falls_back_to_responsible_id() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
    )
    mapper = Bitrix24TaskMapper(settings=Settings())

    fields = mapper.to_task_add_fields(
        task=task,
        user_mappings=[
            make_mapping(organization_id=organization_id, user_id=assignee_id, bitrix_user_id="101"),
        ],
    )

    assert fields["CREATED_BY"] == fields["RESPONSIBLE_ID"]


def test_description_contains_local_context_and_source_marker() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    observer_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
        observers=[make_participant(observer_id, "Сергей")],
    )
    mapper = Bitrix24TaskMapper(settings=Settings())

    fields = mapper.to_task_add_fields(
        task=task,
        user_mappings=[
            make_mapping(organization_id=organization_id, user_id=assignee_id, bitrix_user_id="101"),
            make_mapping(organization_id=organization_id, user_id=observer_id, bitrix_user_id="201"),
        ],
    )

    description = fields["DESCRIPTION"]
    assert "Подготовить отчет" in description
    assert f"Local task_id: {task.id}" in description
    assert f"Chat ID: {task.chat_id}" in description
    assert "Source message ID: max-message-1" in description
    assert "Иван" in description
    assert "Сергей" in description
    assert TASK_SOURCE_MARKER in description


def test_adds_group_id_when_configured() -> None:
    organization_id = uuid4()
    creator_id = uuid4()
    assignee_id = uuid4()
    task = make_task(
        organization_id=organization_id,
        created_by_user_id=creator_id,
        assignees=[make_participant(assignee_id, "Иван")],
    )
    mapper = Bitrix24TaskMapper(settings=Settings(bitrix24_project_group_id="77"))

    fields = mapper.to_task_add_fields(
        task=task,
        user_mappings=[
            make_mapping(organization_id=organization_id, user_id=assignee_id, bitrix_user_id="101"),
        ],
    )

    assert fields["GROUP_ID"] == "77"
