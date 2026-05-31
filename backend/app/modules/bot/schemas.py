from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class NormalizedMention(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw_text: Optional[str] = None
    external_user_id: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    start: Optional[int] = None
    length: Optional[int] = None


class MaxBotWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chat_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    text: str = ""
    timestamp: Optional[str] = None
    chat_type: Optional[str] = None
    chat_title: Optional[str] = None
    sender_display_name: Optional[str] = None
    sender_username: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    reply_to_text: Optional[str] = None
    reply_to_author_id: Optional[str] = None
    reply_to_author_display_name: Optional[str] = None
    raw_update_type: Optional[str] = None
    mentions: list[NormalizedMention] = Field(default_factory=list)


class NormalizedBotEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chat_id: Optional[str] = None
    user_id: Optional[str] = None
    message_id: Optional[str] = None
    text: str = ""
    timestamp: Optional[str] = None
    chat_type: Optional[str] = None
    chat_title: Optional[str] = None
    sender_display_name: Optional[str] = None
    sender_username: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    reply_to_text: Optional[str] = None
    reply_to_author_id: Optional[str] = None
    reply_to_author_display_name: Optional[str] = None
    mentions: list[NormalizedMention] = Field(default_factory=list)
    raw_update_type: Optional[str] = None
    source: Literal["max"] = "max"
    ignored: bool = False
    ignore_reason: Optional[str] = None


class NormalizedMaxCallbackEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    payload: Optional[str] = None
    callback_id: Optional[str] = None
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    message_text: Optional[str] = None
    timestamp: Optional[str] = None
    chat_type: Optional[str] = None
    sender_display_name: Optional[str] = None
    sender_username: Optional[str] = None
    raw_update_type: Optional[str] = None
    source: Literal["max"] = "max"
    ignored: bool = False
    ignore_reason: Optional[str] = None


class BaseCommand(BaseModel):
    raw_text: str


class CreateTaskCommand(BaseCommand):
    type: Literal["create_task"] = "create_task"
    title: str
    source_text: str
    needs_text_clarification: bool = False
    has_inline_args: bool = False
    deadline_at: Optional[datetime] = None
    deadline_raw: Optional[str] = None
    deadline_confidence: float = 0.0
    needs_deadline_clarification: bool = False
    assignees: list[str]
    assignee_mentions: list[str] = Field(default_factory=list)
    deadline: Optional[date] = None
    observers: list[str] = Field(default_factory=list)


class ListTasksCommand(BaseCommand):
    type: Literal["list_tasks"] = "list_tasks"


class MyTasksCommand(BaseCommand):
    type: Literal["my_tasks"] = "my_tasks"


class TaskLookupCommand(BaseCommand):
    type: Literal["task_lookup"] = "task_lookup"
    task_number: int
    task_ref: str


class TaskReportCommand(BaseCommand):
    type: Literal["task_report"] = "task_report"
    task_number: int
    task_ref: str
    text: Optional[str] = None


class PingTaskCommand(BaseCommand):
    type: Literal["ping_task"] = "ping_task"
    task_number: int
    task_ref: str


class SecretaryCommand(BaseCommand):
    type: Literal["secretary"] = "secretary"


class SlashHelpCommand(BaseCommand):
    type: Literal["slash_help"] = "slash_help"


class TaskResponseCommand(BaseCommand):
    type: Literal["task_response"] = "task_response"
    task_id: str
    text: str


class TaskDoneCommand(BaseCommand):
    type: Literal["task_done"] = "task_done"
    task_id: str
    text: str


class AcceptTaskResponseCommand(BaseCommand):
    type: Literal["accept_response"] = "accept_response"
    task_id: str
    response_id: str


class RejectTaskResponseCommand(BaseCommand):
    type: Literal["reject_response"] = "reject_response"
    task_id: str
    response_id: str
    comment: str


class UnknownCommand(BaseCommand):
    type: Literal["unknown"] = "unknown"
    name: str
    args: str = ""


class CommandParseError(BaseCommand):
    type: Literal["parse_error"] = "parse_error"
    message: str


Command = Union[
    CreateTaskCommand,
    ListTasksCommand,
    MyTasksCommand,
    TaskLookupCommand,
    TaskReportCommand,
    PingTaskCommand,
    SecretaryCommand,
    SlashHelpCommand,
    TaskResponseCommand,
    TaskDoneCommand,
    AcceptTaskResponseCommand,
    RejectTaskResponseCommand,
    UnknownCommand,
    CommandParseError,
]


class BotCommand(BaseModel):
    name: str
    args: str = ""
    raw_text: str


class BotCommandResult(BaseModel):
    command: Command
    handled: bool
    response_text: str


class BotOutboundMessage(BaseModel):
    adapter: Literal["max"]
    method: str
    chat_id: Optional[str]
    user_id: Optional[str] = None
    message_id: Optional[str] = None
    text: Optional[str] = None
    task: Optional[dict[str, Any]] = None
    attachments: Optional[list[dict[str, Any]]] = None
    reminder_type: Optional[str] = None
    purpose: Optional[str] = None
    sent: bool
    reason: str


class BotWebhookResponse(BaseModel):
    ok: bool
    is_command: bool
    action: Literal["ignored", "reply_prepared", "callback_processed", "error"]
    command: Optional[Command] = None
    response_text: Optional[str] = None
    error: Optional[str] = None
    outbound: Optional[BotOutboundMessage] = None
