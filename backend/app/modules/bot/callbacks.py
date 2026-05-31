from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

MAX_CALLBACK_PAYLOAD_LENGTH = 128

CallbackAction = Literal["start", "reply", "confirm", "accept", "reject", "snooze", "open", "assign", "report"]
SnoozeValue = Literal["1h", "tomorrow"]

_SIMPLE_ACTIONS: set[CallbackAction] = {"start", "reply", "confirm", "open"}
_RESPONSE_ACTIONS: set[CallbackAction] = {"accept", "reject"}
_SNOOZE_VALUES: set[SnoozeValue] = {"1h", "tomorrow"}
_SECRET_MARKERS = ("token", "secret", "password", "key=", "bearer", "webhook")


class CallbackPayloadError(ValueError):
    """Raised when a bot callback payload is malformed or unsafe."""


@dataclass(frozen=True)
class ParsedCallbackPayload:
    action: CallbackAction
    task_id: UUID
    response_id: UUID | None = None
    snooze: SnoozeValue | None = None


@dataclass(frozen=True)
class ParsedTaskAssignmentPayload:
    pending_action_id: UUID
    assignee_id: UUID | None = None
    assign_self: bool = False


@dataclass(frozen=True)
class ParsedTaskReportPayload:
    task_id: UUID


def parse_callback_payload(payload: str) -> ParsedCallbackPayload:
    _validate_payload_text(payload)
    parts = payload.split(":")
    if len(parts) < 3 or parts[0] != "task":
        raise CallbackPayloadError("Callback payload must start with task:<action>.")

    action = _parse_action(parts[1])
    if action in _SIMPLE_ACTIONS:
        if len(parts) != 3:
            raise CallbackPayloadError(f"Callback action {action} requires task_id only.")
        return ParsedCallbackPayload(action=action, task_id=_parse_uuid(parts[2], "task_id"))

    if action in _RESPONSE_ACTIONS:
        if len(parts) != 4:
            raise CallbackPayloadError(f"Callback action {action} requires task_id and response_id.")
        return ParsedCallbackPayload(
            action=action,
            task_id=_parse_uuid(parts[2], "task_id"),
            response_id=_parse_uuid(parts[3], "response_id"),
        )

    if action == "snooze":
        if len(parts) != 4:
            raise CallbackPayloadError("Callback action snooze requires snooze and task_id.")
        snooze = _parse_snooze(parts[2])
        return ParsedCallbackPayload(
            action=action,
            task_id=_parse_uuid(parts[3], "task_id"),
            snooze=snooze,
        )

    raise CallbackPayloadError(f"Unsupported callback action: {action}.")


def parse_task_assignment_callback_payload(payload: str) -> ParsedTaskAssignmentPayload | None:
    _validate_payload_text(payload)
    parts = payload.split(":")
    if len(parts) < 2 or parts[0] != "task" or parts[1] != "assign":
        return None
    if len(parts) != 4:
        raise CallbackPayloadError("Callback action assign requires pending_action_id and assignee.")

    pending_action_id = _parse_uuid(parts[2], "pending_action_id")
    assignee_token = parts[3]
    if assignee_token == "self":
        return ParsedTaskAssignmentPayload(pending_action_id=pending_action_id, assign_self=True)
    return ParsedTaskAssignmentPayload(
        pending_action_id=pending_action_id,
        assignee_id=_parse_uuid(assignee_token, "assignee_id"),
        assign_self=False,
    )


def parse_task_report_callback_payload(payload: str) -> ParsedTaskReportPayload | None:
    _validate_payload_text(payload)
    parts = payload.split(":")
    if len(parts) < 2 or parts[0] != "task" or parts[1] != "report":
        return None
    if len(parts) != 4 or parts[2] != "start":
        raise CallbackPayloadError("Callback action report requires task:report:start:<task_id>.")
    return ParsedTaskReportPayload(task_id=_parse_uuid(parts[3], "task_id"))


def build_callback_payload(
    action: CallbackAction,
    task_id: UUID | str,
    response_id: UUID | str | None = None,
    snooze: SnoozeValue | None = None,
) -> str:
    task_uuid = _parse_uuid(str(task_id), "task_id")

    if action in _SIMPLE_ACTIONS:
        if response_id is not None or snooze is not None:
            raise CallbackPayloadError(f"Callback action {action} does not accept response_id or snooze.")
        return _validate_and_return(f"task:{action}:{task_uuid}")

    if action in _RESPONSE_ACTIONS:
        if response_id is None or snooze is not None:
            raise CallbackPayloadError(f"Callback action {action} requires response_id and no snooze.")
        response_uuid = _parse_uuid(str(response_id), "response_id")
        return _validate_and_return(f"task:{action}:{task_uuid}:{response_uuid}")

    if action == "snooze":
        if snooze is None or response_id is not None:
            raise CallbackPayloadError("Callback action snooze requires snooze and no response_id.")
        snooze_value = _parse_snooze(snooze)
        return _validate_and_return(f"task:snooze:{snooze_value}:{task_uuid}")

    raise CallbackPayloadError(f"Unsupported callback action: {action}.")


def build_task_assignment_callback_payload(
    *,
    pending_action_id: UUID | str,
    assignee_id: UUID | str | None = None,
    assign_self: bool = False,
) -> str:
    pending_uuid = _parse_uuid(str(pending_action_id), "pending_action_id")
    if assign_self:
        if assignee_id is not None:
            raise CallbackPayloadError("Self assignment callback must not include assignee_id.")
        return _validate_and_return(f"task:assign:{pending_uuid}:self")
    if assignee_id is None:
        raise CallbackPayloadError("Assignment callback requires assignee_id or assign_self=true.")
    assignee_uuid = _parse_uuid(str(assignee_id), "assignee_id")
    return _validate_and_return(f"task:assign:{pending_uuid}:{assignee_uuid}")


def build_task_report_callback_payload(task_id: UUID | str) -> str:
    task_uuid = _parse_uuid(str(task_id), "task_id")
    return _validate_and_return(f"task:report:start:{task_uuid}")


def _validate_payload_text(payload: str) -> None:
    if not payload:
        raise CallbackPayloadError("Callback payload is empty.")
    if len(payload) > MAX_CALLBACK_PAYLOAD_LENGTH:
        raise CallbackPayloadError("Callback payload is too long.")
    lowered = payload.casefold()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        raise CallbackPayloadError("Callback payload must not contain secret-like values.")


def _validate_and_return(payload: str) -> str:
    _validate_payload_text(payload)
    return payload


def _parse_action(value: str) -> CallbackAction:
    if value in {"start", "reply", "confirm", "accept", "reject", "snooze", "open"}:
        return value
    raise CallbackPayloadError(f"Unsupported callback action: {value}.")


def _parse_snooze(value: str) -> SnoozeValue:
    if value in _SNOOZE_VALUES:
        return value
    raise CallbackPayloadError(f"Unsupported snooze value: {value}.")


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise CallbackPayloadError(f"Callback {field_name} must be UUID.") from exc
