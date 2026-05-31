from app.modules.tasks.enums import (
    ScheduledTaskRunStatus,
    ScheduledTaskScheduleType,
    TaskAcceptanceDecision,
    TaskAssigneeStatus,
    TaskCompletionRule,
    TaskPriority,
    TaskResponseStatus,
    TaskStatus,
    TaskTemplateAudienceType,
    TaskType,
)


def enum_values(enum_type) -> list[str]:
    return [item.value for item in enum_type]


def test_task_status_values() -> None:
    assert enum_values(TaskStatus) == [
        "new",
        "in_progress",
        "waiting_response",
        "waiting_acceptance",
        "done",
        "overdue",
        "rejected",
        "cancelled",
    ]


def test_task_type_values() -> None:
    assert enum_values(TaskType) == ["personal", "group_assignment"]


def test_task_template_audience_type_values() -> None:
    assert enum_values(TaskTemplateAudienceType) == ["selected_members", "all_chat_members"]


def test_scheduled_task_schedule_type_values() -> None:
    assert enum_values(ScheduledTaskScheduleType) == ["one_time", "daily", "weekly"]


def test_scheduled_task_run_status_values() -> None:
    assert enum_values(ScheduledTaskRunStatus) == ["started", "succeeded", "failed"]


def test_task_assignee_status_values() -> None:
    assert enum_values(TaskAssigneeStatus) == [
        "assigned",
        "in_progress",
        "responded",
        "rejected",
        "completed",
    ]


def test_task_priority_values() -> None:
    assert enum_values(TaskPriority) == ["low", "normal", "high", "urgent"]


def test_task_completion_rule_values() -> None:
    assert enum_values(TaskCompletionRule) == [
        "any_assignee_response",
        "all_assignees_response",
        "manual_submit",
    ]


def test_task_response_status_values() -> None:
    assert enum_values(TaskResponseStatus) == ["submitted", "accepted", "rejected"]


def test_task_acceptance_decision_values() -> None:
    assert enum_values(TaskAcceptanceDecision) == ["accepted", "rejected"]
