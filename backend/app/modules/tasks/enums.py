from enum import Enum


class TaskStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    WAITING_RESPONSE = "waiting_response"
    WAITING_ACCEPTANCE = "waiting_acceptance"
    DONE = "done"
    OVERDUE = "overdue"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    PERSONAL = "personal"
    GROUP_ASSIGNMENT = "group_assignment"


class TaskTemplateAudienceType(str, Enum):
    SELECTED_MEMBERS = "selected_members"
    ALL_CHAT_MEMBERS = "all_chat_members"


class ScheduledTaskScheduleType(str, Enum):
    ONE_TIME = "one_time"
    DAILY = "daily"
    WEEKLY = "weekly"


class ScheduledTaskRunStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskAssigneeStatus(str, Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESPONDED = "responded"
    REJECTED = "rejected"
    COMPLETED = "completed"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TaskCompletionRule(str, Enum):
    ANY_ASSIGNEE_RESPONSE = "any_assignee_response"
    ALL_ASSIGNEES_RESPONSE = "all_assignees_response"
    MANUAL_SUBMIT = "manual_submit"


class TaskResponseStatus(str, Enum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class TaskAcceptanceDecision(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
