from __future__ import annotations

from typing import Any

from app.modules.auth.context import AuthContext

ROLE_MEMBER = "member"
ROLE_CHAT_ADMIN = "chat_admin"
ROLE_SUPER_ADMIN = "super_admin"

CHAT_TASK_ADMIN_ROLES = frozenset({ROLE_CHAT_ADMIN})
BITRIX_MAPPING_ADMIN_ROLES = frozenset({ROLE_CHAT_ADMIN})


class PolicyService:
    def can_view_task(self, context: AuthContext, task: Any) -> bool:
        if self._is_super_admin(context):
            return True
        if self._is_task_creator(context, task):
            return True
        if self._is_task_assignee(context, task):
            return True
        if self._is_task_observer(context, task):
            return True
        if context.has_any_role(CHAT_TASK_ADMIN_ROLES) and self._matches_task_scope(context, task):
            return True
        return (
            context.has_role(ROLE_MEMBER)
            and self._matches_task_scope(context, task)
            and self._chat_allows_member_task_view(task)
        )

    def can_create_task(self, context: AuthContext, chat: Any) -> bool:
        if self._is_super_admin(context):
            return True
        return context.has_any_role(CHAT_TASK_ADMIN_ROLES) and self._matches_chat_scope(context, chat)

    def can_update_task(self, context: AuthContext, task: Any) -> bool:
        if self._is_super_admin(context):
            return True
        if self._is_task_creator(context, task):
            return True
        return context.has_any_role(CHAT_TASK_ADMIN_ROLES) and self._matches_task_scope(context, task)

    def can_submit_response(self, context: AuthContext, task: Any) -> bool:
        if self._is_super_admin(context):
            return True
        return self._is_task_assignee(context, task)

    def can_accept_task(self, context: AuthContext, task: Any) -> bool:
        if self._is_super_admin(context):
            return True
        if self._is_task_creator(context, task):
            return True
        return context.has_any_role(CHAT_TASK_ADMIN_ROLES) and self._matches_task_scope(context, task)

    def can_reject_task(self, context: AuthContext, task: Any) -> bool:
        if self._is_super_admin(context):
            return True
        if self._is_task_creator(context, task):
            return True
        return context.has_any_role(CHAT_TASK_ADMIN_ROLES) and self._matches_task_scope(context, task)

    def can_manage_bitrix_mapping(self, context: AuthContext, organization_id: Any) -> bool:
        if self._is_super_admin(context):
            return True
        return context.has_any_role(BITRIX_MAPPING_ADMIN_ROLES) and self._matches_organization_scope(
            context,
            organization_id,
        )

    def can_run_bitrix_sync(self, context: AuthContext, task: Any) -> bool:
        if self._is_super_admin(context):
            return True
        if self._is_task_creator(context, task):
            return True
        return context.has_any_role(CHAT_TASK_ADMIN_ROLES) and self._matches_task_scope(context, task)

    def _is_super_admin(self, context: AuthContext) -> bool:
        return context.is_super_admin or context.has_role(ROLE_SUPER_ADMIN)

    def _is_task_creator(self, context: AuthContext, task: Any) -> bool:
        return _same_id(context.user_id, getattr(task, "created_by_user_id", None))

    def _is_task_assignee(self, context: AuthContext, task: Any) -> bool:
        return _contains_user_id(getattr(task, "assignees", []), context.user_id)

    def _is_task_observer(self, context: AuthContext, task: Any) -> bool:
        return _contains_user_id(getattr(task, "observers", []), context.user_id)

    def _matches_task_scope(self, context: AuthContext, task: Any) -> bool:
        if context.chat_id is not None:
            return _same_id(context.chat_id, getattr(task, "chat_id", None))
        if context.organization_id is not None:
            return _same_id(context.organization_id, getattr(task, "organization_id", None))
        return False

    def _matches_chat_scope(self, context: AuthContext, chat: Any) -> bool:
        if context.chat_id is not None:
            return _same_id(context.chat_id, getattr(chat, "id", None))
        if context.organization_id is not None:
            return _same_id(context.organization_id, getattr(chat, "organization_id", None))
        return False

    def _matches_organization_scope(self, context: AuthContext, organization_id: Any) -> bool:
        if context.organization_id is None:
            return False
        return _same_id(context.organization_id, organization_id)

    def _chat_allows_member_task_view(self, task: Any) -> bool:
        chat = getattr(task, "chat", None)
        settings = getattr(chat, "settings", None) if chat is not None else None
        if not isinstance(settings, dict):
            return False
        return bool(
            settings.get("members_can_view_tasks")
            or settings.get("allow_member_task_view")
            or settings.get("allow_members_to_view_tasks")
        )


def _same_id(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    return str(left) == str(right)


def _contains_user_id(items: list[Any], user_id: Any) -> bool:
    return any(_same_id(getattr(item, "user_id", None), user_id) for item in items)
