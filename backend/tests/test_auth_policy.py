from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

from app.modules.auth.context import AuthContext
from app.modules.auth.permissions import ALL_PERMISSIONS, TASK_ACCEPT, TASK_RESPONSE_SUBMIT
from app.modules.auth.policy import PolicyService


def make_task(
    *,
    organization_id: UUID | None = None,
    chat_id: UUID | None = None,
    created_by_user_id: UUID | None = None,
    assignee_ids: list[UUID] | None = None,
    observer_ids: list[UUID] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id or uuid4(),
        chat_id=chat_id or uuid4(),
        created_by_user_id=created_by_user_id or uuid4(),
        assignees=[SimpleNamespace(user_id=user_id) for user_id in (assignee_ids or [])],
        observers=[SimpleNamespace(user_id=user_id) for user_id in (observer_ids or [])],
    )


def test_permissions_registry_contains_required_values() -> None:
    assert TASK_RESPONSE_SUBMIT == "task.response.submit"
    assert TASK_ACCEPT == "task.accept"
    assert {
        "task.view",
        "task.create",
        "task.update",
        "task.cancel",
        "task.assign",
        "task.comment",
        "task.file.add",
        "task.response.submit",
        "task.accept",
        "task.reject",
        "chat.members.manage",
        "chat.settings.manage",
        "bitrix.mapping.manage",
        "bitrix.sync.run",
        "integration.settings.manage",
    } <= ALL_PERMISSIONS


def test_member_executor_can_submit_response() -> None:
    policy = PolicyService()
    user_id = uuid4()
    task = make_task(assignee_ids=[user_id])
    context = AuthContext(user_id=user_id, roles=["member"])

    assert policy.can_view_task(context, task) is True
    assert policy.can_submit_response(context, task) is True
    assert policy.can_accept_task(context, task) is False


def test_observer_can_view_but_cannot_accept() -> None:
    policy = PolicyService()
    observer_id = uuid4()
    task = make_task(observer_ids=[observer_id])
    context = AuthContext(user_id=observer_id, roles=["member"])

    assert policy.can_view_task(context, task) is True
    assert policy.can_submit_response(context, task) is False
    assert policy.can_accept_task(context, task) is False


def test_creator_can_accept_and_reject_task() -> None:
    policy = PolicyService()
    creator_id = uuid4()
    task = make_task(created_by_user_id=creator_id)
    context = AuthContext(user_id=creator_id, roles=["member"])

    assert policy.can_view_task(context, task) is True
    assert policy.can_accept_task(context, task) is True
    assert policy.can_reject_task(context, task) is True


def test_chat_admin_can_view_and_manage_chat_tasks() -> None:
    policy = PolicyService()
    organization_id = uuid4()
    chat_id = uuid4()
    task = make_task(organization_id=organization_id, chat_id=chat_id)
    chat = SimpleNamespace(id=chat_id, organization_id=organization_id)
    context = AuthContext(
        user_id=uuid4(),
        organization_id=organization_id,
        chat_id=chat_id,
        roles=["chat_admin"],
    )

    assert policy.can_view_task(context, task) is True
    assert policy.can_create_task(context, chat) is True
    assert policy.can_update_task(context, task) is True
    assert policy.can_accept_task(context, task) is True
    assert policy.can_reject_task(context, task) is True
    assert policy.can_run_bitrix_sync(context, task) is True


def test_legacy_manager_role_is_not_privileged() -> None:
    policy = PolicyService()
    organization_id = uuid4()
    chat_id = uuid4()
    task = make_task(organization_id=organization_id, chat_id=chat_id)
    chat = SimpleNamespace(id=chat_id, organization_id=organization_id)
    context = AuthContext(
        user_id=uuid4(),
        organization_id=organization_id,
        chat_id=chat_id,
        roles=["manager"],
    )

    assert policy.can_view_task(context, task) is False
    assert policy.can_create_task(context, chat) is False
    assert policy.can_update_task(context, task) is False
    assert policy.can_accept_task(context, task) is False
    assert policy.can_reject_task(context, task) is False
    assert policy.can_run_bitrix_sync(context, task) is False


def test_chat_admin_can_manage_bitrix_mappings() -> None:
    policy = PolicyService()
    organization_id = uuid4()
    context = AuthContext(
        user_id=uuid4(),
        organization_id=organization_id,
        roles=["chat_admin"],
    )

    assert policy.can_manage_bitrix_mapping(context, organization_id) is True
    assert policy.can_manage_bitrix_mapping(context, uuid4()) is False


def test_super_admin_can_do_all_policy_actions() -> None:
    policy = PolicyService()
    organization_id = uuid4()
    chat_id = uuid4()
    task = make_task(organization_id=organization_id, chat_id=chat_id)
    chat = SimpleNamespace(id=chat_id, organization_id=organization_id)
    context = AuthContext(user_id=uuid4(), roles=[], is_super_admin=True)

    assert policy.can_view_task(context, task) is True
    assert policy.can_create_task(context, chat) is True
    assert policy.can_update_task(context, task) is True
    assert policy.can_submit_response(context, task) is True
    assert policy.can_accept_task(context, task) is True
    assert policy.can_reject_task(context, task) is True
    assert policy.can_manage_bitrix_mapping(context, organization_id) is True
    assert policy.can_run_bitrix_sync(context, task) is True
