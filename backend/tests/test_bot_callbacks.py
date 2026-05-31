from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.bot.callbacks import (
    MAX_CALLBACK_PAYLOAD_LENGTH,
    CallbackPayloadError,
    build_callback_payload,
    build_task_assignment_callback_payload,
    build_task_report_callback_payload,
    parse_callback_payload,
    parse_task_assignment_callback_payload,
    parse_task_report_callback_payload,
)


@pytest.fixture()
def task_id() -> UUID:
    return UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture()
def response_id() -> UUID:
    return UUID("22222222-2222-4222-8222-222222222222")


@pytest.mark.parametrize(
    "action",
    ["start", "reply", "confirm", "open"],
)
def test_builds_and_parses_simple_task_callback_payloads(action: str, task_id: UUID) -> None:
    payload = build_callback_payload(action, task_id)

    assert payload == f"task:{action}:{task_id}"
    parsed = parse_callback_payload(payload)
    assert parsed.action == action
    assert parsed.task_id == task_id
    assert parsed.response_id is None
    assert parsed.snooze is None


@pytest.mark.parametrize(
    "action",
    ["accept", "reject"],
)
def test_builds_and_parses_response_callback_payloads(
    action: str,
    task_id: UUID,
    response_id: UUID,
) -> None:
    payload = build_callback_payload(action, task_id, response_id=response_id)

    assert payload == f"task:{action}:{task_id}:{response_id}"
    parsed = parse_callback_payload(payload)
    assert parsed.action == action
    assert parsed.task_id == task_id
    assert parsed.response_id == response_id
    assert parsed.snooze is None


@pytest.mark.parametrize(
    "snooze",
    ["1h", "tomorrow"],
)
def test_builds_and_parses_snooze_callback_payloads(snooze: str, task_id: UUID) -> None:
    payload = build_callback_payload("snooze", task_id, snooze=snooze)

    assert payload == f"task:snooze:{snooze}:{task_id}"
    parsed = parse_callback_payload(payload)
    assert parsed.action == "snooze"
    assert parsed.task_id == task_id
    assert parsed.response_id is None
    assert parsed.snooze == snooze


def test_parses_required_payload_examples(task_id: UUID, response_id: UUID) -> None:
    examples = [
        f"task:start:{task_id}",
        f"task:reply:{task_id}",
        f"task:confirm:{task_id}",
        f"task:accept:{task_id}:{response_id}",
        f"task:reject:{task_id}:{response_id}",
        f"task:snooze:1h:{task_id}",
        f"task:snooze:tomorrow:{task_id}",
        f"task:open:{task_id}",
    ]

    for payload in examples:
        parsed = parse_callback_payload(payload)
        assert parsed.task_id == task_id


def test_rejects_invalid_task_id() -> None:
    with pytest.raises(CallbackPayloadError, match="task_id must be UUID"):
        parse_callback_payload("task:start:not-a-uuid")


def test_rejects_invalid_response_id(task_id: UUID) -> None:
    with pytest.raises(CallbackPayloadError, match="response_id must be UUID"):
        parse_callback_payload(f"task:accept:{task_id}:not-a-uuid")


def test_rejects_payload_that_is_too_long() -> None:
    with pytest.raises(CallbackPayloadError, match="too long"):
        parse_callback_payload("x" * (MAX_CALLBACK_PAYLOAD_LENGTH + 1))


@pytest.mark.parametrize(
    "payload",
    [
        "task:start:11111111-1111-4111-8111-111111111111:token=secret",
        "task:open:11111111-1111-4111-8111-111111111111:password=hidden",
        "task:reply:11111111-1111-4111-8111-111111111111:webhook/abc",
    ],
)
def test_rejects_secret_like_payload_values(payload: str) -> None:
    with pytest.raises(CallbackPayloadError, match="secret-like"):
        parse_callback_payload(payload)


def test_rejects_unsupported_action(task_id: UUID) -> None:
    with pytest.raises(CallbackPayloadError, match="Unsupported callback action"):
        parse_callback_payload(f"task:unknown:{task_id}")


def test_rejects_wrong_payload_shape(task_id: UUID, response_id: UUID) -> None:
    with pytest.raises(CallbackPayloadError, match="requires task_id only"):
        parse_callback_payload(f"task:start:{task_id}:{response_id}")


def test_build_rejects_response_id_for_simple_action(task_id: UUID, response_id: UUID) -> None:
    with pytest.raises(CallbackPayloadError, match="does not accept"):
        build_callback_payload("start", task_id, response_id=response_id)


def test_build_rejects_missing_response_id_for_response_action(task_id: UUID) -> None:
    with pytest.raises(CallbackPayloadError, match="requires response_id"):
        build_callback_payload("accept", task_id)


def test_build_rejects_unknown_snooze_value(task_id: UUID) -> None:
    with pytest.raises(CallbackPayloadError, match="Unsupported snooze value"):
        build_callback_payload("snooze", task_id, snooze="2h")


def test_build_accepts_string_uuid_values() -> None:
    task_id = uuid4()
    payload = build_callback_payload("open", str(task_id))

    assert parse_callback_payload(payload).task_id == task_id


def test_builds_and_parses_task_assignment_callback_payload() -> None:
    pending_id = uuid4()
    assignee_id = uuid4()

    payload = build_task_assignment_callback_payload(
        pending_action_id=pending_id,
        assignee_id=assignee_id,
    )
    parsed = parse_task_assignment_callback_payload(payload)

    assert payload == f"task:assign:{pending_id}:{assignee_id}"
    assert parsed is not None
    assert parsed.pending_action_id == pending_id
    assert parsed.assignee_id == assignee_id
    assert parsed.assign_self is False


def test_builds_and_parses_task_assignment_self_callback_payload() -> None:
    pending_id = uuid4()

    payload = build_task_assignment_callback_payload(pending_action_id=pending_id, assign_self=True)
    parsed = parse_task_assignment_callback_payload(payload)

    assert payload == f"task:assign:{pending_id}:self"
    assert parsed is not None
    assert parsed.pending_action_id == pending_id
    assert parsed.assignee_id is None
    assert parsed.assign_self is True


def test_builds_and_parses_task_report_callback_payload(task_id: UUID) -> None:
    payload = build_task_report_callback_payload(task_id)
    parsed = parse_task_report_callback_payload(payload)

    assert payload == f"task:report:start:{task_id}"
    assert parsed is not None
    assert parsed.task_id == task_id


def test_task_report_callback_payload_returns_none_for_other_task_payload(task_id: UUID) -> None:
    assert parse_task_report_callback_payload(f"task:open:{task_id}") is None


def test_task_assignment_parser_returns_none_for_other_task_payload(task_id: UUID) -> None:
    assert parse_task_assignment_callback_payload(f"task:open:{task_id}") is None


def test_task_assignment_parser_rejects_invalid_shape() -> None:
    with pytest.raises(CallbackPayloadError, match="requires pending_action_id"):
        parse_task_assignment_callback_payload("task:assign:only-one-id")
