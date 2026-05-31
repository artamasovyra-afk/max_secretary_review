from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from app.core.config import Settings, get_settings
from app.modules.integrations.bitrix24.exceptions import Bitrix24MappingError
from app.modules.integrations.models import BitrixUserMapping
from app.modules.tasks.models import Task

TASK_SOURCE_MARKER = "Задача создана из max_secretary"


class Bitrix24TaskMapper:
    """Build Bitrix24 task fields from a local max_secretary task."""

    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def to_task_add_fields(
        self,
        *,
        task: Task,
        user_mappings: Iterable[BitrixUserMapping],
    ) -> dict[str, Any]:
        mapping_by_user_id = self._active_mapping_by_user_id(task, user_mappings)
        assignees = list(getattr(task, "assignees", []) or [])
        observers = list(getattr(task, "observers", []) or [])

        responsible_id = self._resolve_responsible_id(assignees, mapping_by_user_id)
        accomplices = self._resolve_accomplices(
            assignees=assignees,
            mapping_by_user_id=mapping_by_user_id,
            responsible_id=responsible_id,
        )
        auditors = self._resolve_auditors(observers, mapping_by_user_id)
        created_by = self._resolve_created_by(task, mapping_by_user_id, responsible_id)

        fields: dict[str, Any] = {
            "TITLE": task.title,
            "DESCRIPTION": self._build_description(
                task=task,
                assignees=assignees,
                observers=observers,
                mapping_by_user_id=mapping_by_user_id,
            ),
            "RESPONSIBLE_ID": responsible_id,
            "CREATED_BY": created_by,
            "ACCOMPLICES": accomplices,
            "AUDITORS": auditors,
        }

        if task.deadline_at is not None:
            fields["DEADLINE"] = task.deadline_at.isoformat()

        group_id = self._optional_setting(self.settings.bitrix24_project_group_id)
        if group_id is not None:
            fields["GROUP_ID"] = group_id

        # TODO: Add Bitrix24 task control field after the exact REST payload key is confirmed.
        return fields

    def map_task_to_fields(
        self,
        *,
        task: Task,
        user_mappings: Iterable[BitrixUserMapping],
    ) -> dict[str, Any]:
        return self.to_task_add_fields(task=task, user_mappings=user_mappings)

    def _active_mapping_by_user_id(
        self,
        task: Task,
        user_mappings: Iterable[BitrixUserMapping],
    ) -> dict[UUID, str]:
        task_organization_id = getattr(task, "organization_id")
        return {
            mapping.user_id: mapping.bitrix_user_id
            for mapping in user_mappings
            if mapping.is_active and mapping.organization_id == task_organization_id
        }

    def _resolve_responsible_id(
        self,
        assignees: list[Any],
        mapping_by_user_id: dict[UUID, str],
    ) -> str:
        for assignee in assignees:
            bitrix_user_id = mapping_by_user_id.get(assignee.user_id)
            if bitrix_user_id:
                return bitrix_user_id

        default_responsible_id = self._optional_setting(self.settings.bitrix24_default_responsible_id)
        if default_responsible_id is not None:
            return default_responsible_id

        raise Bitrix24MappingError(
            "Bitrix24 RESPONSIBLE_ID cannot be resolved: no active assignee mapping "
            "and BITRIX24_DEFAULT_RESPONSIBLE_ID is empty."
        )

    def _resolve_accomplices(
        self,
        *,
        assignees: list[Any],
        mapping_by_user_id: dict[UUID, str],
        responsible_id: str,
    ) -> list[str]:
        accomplices: list[str] = []
        for assignee in assignees:
            bitrix_user_id = mapping_by_user_id.get(assignee.user_id)
            if bitrix_user_id and bitrix_user_id != responsible_id and bitrix_user_id not in accomplices:
                accomplices.append(bitrix_user_id)
        return accomplices

    def _resolve_auditors(
        self,
        observers: list[Any],
        mapping_by_user_id: dict[UUID, str],
    ) -> list[str]:
        auditors: list[str] = []
        for observer in observers:
            bitrix_user_id = mapping_by_user_id.get(observer.user_id)
            if bitrix_user_id and bitrix_user_id not in auditors:
                auditors.append(bitrix_user_id)
        return auditors

    def _resolve_created_by(
        self,
        task: Task,
        mapping_by_user_id: dict[UUID, str],
        responsible_id: str,
    ) -> str:
        bitrix_created_by = mapping_by_user_id.get(task.created_by_user_id)
        if bitrix_created_by:
            return bitrix_created_by

        default_created_by_id = self._optional_setting(self.settings.bitrix24_default_created_by_id)
        if default_created_by_id is not None:
            return default_created_by_id

        return responsible_id

    def _build_description(
        self,
        *,
        task: Task,
        assignees: list[Any],
        observers: list[Any],
        mapping_by_user_id: dict[UUID, str],
    ) -> str:
        lines: list[str] = []
        if task.description:
            lines.extend([task.description.strip(), ""])

        lines.extend(
            [
                TASK_SOURCE_MARKER,
                f"Local task_id: {task.id}",
                f"Chat ID: {task.chat_id}",
            ]
        )

        if task.source_message_id:
            lines.append(f"Source message ID: {task.source_message_id}")

        lines.extend(
            [
                "",
                "Исполнители:",
                *self._format_participants(assignees, mapping_by_user_id),
                "",
                "Наблюдатели:",
                *self._format_participants(observers, mapping_by_user_id),
            ]
        )
        return "\n".join(lines).strip()

    def _format_participants(
        self,
        participants: list[Any],
        mapping_by_user_id: dict[UUID, str],
    ) -> list[str]:
        if not participants:
            return ["- нет"]

        formatted: list[str] = []
        for participant in participants:
            user_id = participant.user_id
            user = getattr(participant, "user", None)
            display_name = getattr(user, "display_name", None) or str(user_id)
            bitrix_user_id = mapping_by_user_id.get(user_id)
            if bitrix_user_id:
                formatted.append(f"- {display_name} (Bitrix24 ID: {bitrix_user_id})")
            else:
                formatted.append(f"- {display_name} (нет active Bitrix24 mapping)")
        return formatted

    def _optional_setting(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped_value = value.strip()
        return stripped_value or None
