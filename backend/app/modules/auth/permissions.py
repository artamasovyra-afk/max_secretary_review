from __future__ import annotations

TASK_VIEW = "task.view"
TASK_CREATE = "task.create"
TASK_UPDATE = "task.update"
TASK_CANCEL = "task.cancel"
TASK_ASSIGN = "task.assign"
TASK_COMMENT = "task.comment"
TASK_FILE_ADD = "task.file.add"
TASK_RESPONSE_SUBMIT = "task.response.submit"
TASK_ACCEPT = "task.accept"
TASK_REJECT = "task.reject"
CHAT_MEMBERS_MANAGE = "chat.members.manage"
CHAT_SETTINGS_MANAGE = "chat.settings.manage"
BITRIX_MAPPING_MANAGE = "bitrix.mapping.manage"
BITRIX_SYNC_RUN = "bitrix.sync.run"
INTEGRATION_SETTINGS_MANAGE = "integration.settings.manage"

ALL_PERMISSIONS = frozenset(
    {
        TASK_VIEW,
        TASK_CREATE,
        TASK_UPDATE,
        TASK_CANCEL,
        TASK_ASSIGN,
        TASK_COMMENT,
        TASK_FILE_ADD,
        TASK_RESPONSE_SUBMIT,
        TASK_ACCEPT,
        TASK_REJECT,
        CHAT_MEMBERS_MANAGE,
        CHAT_SETTINGS_MANAGE,
        BITRIX_MAPPING_MANAGE,
        BITRIX_SYNC_RUN,
        INTEGRATION_SETTINGS_MANAGE,
    }
)
