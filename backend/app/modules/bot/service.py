from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, time, timezone
from typing import Any
from typing import NoReturn
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_MEMBER, ROLE_SUPER_ADMIN, PolicyService
from app.modules.bot.callback_service import (
    BotCallbackError,
    BotCallbackForbidden,
    BotCallbackResult,
    BotCallbackService,
    NormalizedCallbackEvent,
)
from app.modules.bot.callbacks import CallbackPayloadError
from app.modules.bot.callbacks import build_callback_payload
from app.modules.bot.callbacks import build_task_assignment_callback_payload
from app.modules.bot.callbacks import build_task_report_callback_payload
from app.modules.bot.command_parser import BotCommandParser
from app.modules.bot.identity_resolver import (
    MaxIdentityResolver,
    MaxIdentityResolverError,
    ResolvedMaxIdentity,
    parse_internal_uuid,
)
from app.modules.bot.repository import (
    PENDING_ACTION_CLEANUP_EDITED,
    PENDING_ACTION_CLEANUP_FAILED,
    PENDING_ACTION_CLEANUP_PARTIAL,
    PENDING_ACTION_PENDING,
    PENDING_ACTION_TASK_ACCEPTANCE_REJECT_REASON,
)
from app.modules.tasks.deadline_parser import DEFAULT_TIMEZONE, as_aware_utc, is_future_task_deadline, parse_deadline
from app.modules.bot.schemas import (
    AcceptTaskResponseCommand,
    BotOutboundMessage,
    BotWebhookResponse,
    Command,
    CommandParseError,
    CreateTaskCommand,
    ListTasksCommand,
    MaxBotWebhookEvent,
    MyTasksCommand,
    NormalizedMention,
    NormalizedBotEvent,
    NormalizedMaxCallbackEvent,
    PingTaskCommand,
    RejectTaskResponseCommand,
    SecretaryCommand,
    SlashHelpCommand,
    TaskDoneCommand,
    TaskLookupCommand,
    TaskReportCommand,
    TaskResponseCommand,
    UnknownCommand,
)
from app.modules.chats.models import Chat
from app.modules.chats.repository import ChatRepository
from app.modules.chats.schemas import ChatConnectionStatus
from app.modules.integrations.max.deep_links import build_max_webapp_deep_link
from app.modules.notifications.enums import DeliveryStatus
from app.modules.notifications.max_sender import MaxSender, OutboundPurpose
from app.modules.notifications.service import (
    BACKGROUND_DISABLED_ERROR,
    MISSING_MAX_CHAT_ID_ERROR,
    NotificationDeliveryResult,
    NotificationDeliveryService,
)
from app.modules.tasks.enums import TaskAssigneeStatus, TaskResponseStatus, TaskStatus
from app.modules.tasks.models import Task
from app.modules.tasks.schemas import (
    TaskAcceptanceCreate,
    TaskCreate,
    TaskListFilters,
    TaskResponseCreate,
)
from app.modules.tasks.service import TaskService
from app.modules.users.models import User
from app.modules.users.repository import UserRepository

logger = logging.getLogger(__name__)

MY_TASKS_LIMIT = 7
TASK_PING_REMINDER_TYPE = "task_ping"
FINAL_TASK_STATUSES = frozenset(
    {
        TaskStatus.DONE.value,
        TaskStatus.CANCELLED.value,
        TaskStatus.REJECTED.value,
    }
)
ACTIVE_ASSIGNEE_EXCLUDED_STATUSES = frozenset(
    {
        TaskAssigneeStatus.RESPONDED.value,
        TaskAssigneeStatus.REJECTED.value,
        TaskAssigneeStatus.COMPLETED.value,
    }
)
ASSIGNEE_MENTION_PROMPT = (
    "/задача\n\n"
    "Укажите исполнителя или исполнителей через @упоминание.\n"
    "Чтобы назначить себе, упомяните Дьяка.\n\n"
    "Пример:\n"
    "@Иван Иванов @Мария Петрова"
)
TASK_WIZARD_TEXT_PROMPT = "/задача\n\nНапишите текст задачи одним сообщением."
TASK_WIZARD_DEADLINE_PROMPT = "/задача\n\nУкажите срок задачи.\nНапример: завтра до 18:00."
TASK_WIZARD_PAST_DEADLINE_PROMPT = (
    "/задача\n\n"
    "Срок уже прошел. Укажите будущий срок задачи.\n"
    "Например: сегодня до 18:00 или завтра до 09:00."
)
TASK_WIZARD_UNCLEAR_DEADLINE_PROMPT = (
    "/задача\n\n"
    "Не понял срок задачи.\n"
    "Напишите, например: завтра до 18:00, через 30 минут или до пятницы."
)
TASK_WIZARD_USER_INPUT_MESSAGE_IDS_KEY = "user_input_message_ids"
SLASH_COMMAND_HELP_TEXT = (
    "Команды Дьяка\n\n"
    "/дьяк — сводка и вход в WebApp\n"
    "/задача — создать задачу\n"
    "/мои_задачи — посмотреть мои задачи\n"
    "/отчет #номер — отправить отчет по задаче\n"
    "/пинг #номер — напомнить исполнителю\n\n"
    "Если список команд не открывается в web-версии MAX, отправьте /помощь или /команды."
)
NO_ASSIGNEE_MENTION_TEXT = "Не вижу @упоминаний. Укажите исполнителя или исполнителей через @."
TASK_WIZARD_NO_ASSIGNEE_MENTION_PROMPT = (
    "/задача\n\n"
    "Не вижу @упоминаний.\n"
    "Укажите исполнителя или исполнителей через @."
)
UNRESOLVED_ASSIGNEE_MENTION_TEXT = (
    "Не удалось определить исполнителей из @упоминаний. Попробуйте упомянуть участников еще раз."
)
TASK_WIZARD_UNRESOLVED_ASSIGNEE_MENTION_PROMPT = (
    "/задача\n\n"
    "Не удалось определить исполнителя.\n"
    "Укажите исполнителя или исполнителей через @."
)
TASK_WIZARD_MEMBER_ASSIGN_FORBIDDEN_PROMPT = (
    "/задача\n\n"
    "Назначать задачи другим участникам может только администратор чата."
)
BOT_BRAND_MENTION_NAMES = frozenset({"дьяк"})
PARTIAL_ASSIGNEE_MENTION_TEXT = (
    "Некоторые @упоминания не удалось распознать; задача создана для найденных исполнителей."
)
PING_ADMIN_ONLY_TEXT = "Пинг по задаче доступен только администратору чата."
CHAT_PENDING_APPROVAL_TEXT = "Этот чат еще не подключен к Дьяку. Ожидается подтверждение супер-администратора."
CHAT_REJECTED_TEXT = "Этот чат не подключен к Дьяку: подключение отклонено супер-администратором."
CHAT_SUSPENDED_TEXT = "Этот чат временно отключен в Дьяке. Обратитесь к супер-администратору."
CHAT_UNAVAILABLE_TEXT = "Этот чат сейчас недоступен в Дьяке. Обратитесь к супер-администратору."
TASK_STATUS_LABELS = {
    TaskStatus.NEW.value: "Новая",
    TaskStatus.IN_PROGRESS.value: "В работе",
    TaskStatus.WAITING_RESPONSE.value: "Ждет ответа",
    TaskStatus.WAITING_ACCEPTANCE.value: "Ждет приемки",
    TaskStatus.DONE.value: "Выполнена",
    TaskStatus.OVERDUE.value: "Просрочена",
    TaskStatus.REJECTED.value: "Отклонена",
    TaskStatus.CANCELLED.value: "Отменена",
}


class BotCommandExecutionError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class AssigneeMentionResolution:
    users: list[User]
    unresolved: list[str]
    ambiguous: list[str]


@dataclass(frozen=True)
class NormalizedAssigneeMentionResolution:
    users: list[User]
    unresolved_count: int


@dataclass(frozen=True)
class CommandExecutionResult:
    response_text: str
    task_card: dict[str, object] | None = None
    button_rows: list[list[dict[str, Any]]] | None = None
    edit_message_id: str | None = None
    track_pending_action_id: UUID | None = None
    cleanup_pending_action_id: UUID | None = None
    user_input_message_ids: tuple[str, ...] = ()
    allow_send_fallback: bool = True


@dataclass(frozen=True)
class UserInputCleanupResult:
    attempted: int = 0
    deleted: int = 0
    failed: int = 0
    disabled: bool = False
    error: str | None = None


def normalize_max_event(raw_event: Mapping[str, Any]) -> NormalizedBotEvent | NormalizedMaxCallbackEvent:
    """Normalize supported MAX webhook payloads into the internal bot event DTO."""
    if _looks_like_normalized_event(raw_event):
        event = MaxBotWebhookEvent.model_validate(raw_event)
        return _normalized_or_ignored(
            chat_id=event.chat_id,
            user_id=event.user_id,
            message_id=event.message_id,
            text=event.text,
            timestamp=event.timestamp,
            chat_type=event.chat_type,
            chat_title=event.chat_title,
            sender_display_name=event.sender_display_name,
            sender_username=event.sender_username,
            reply_to_message_id=event.reply_to_message_id,
            reply_to_text=event.reply_to_text,
            reply_to_author_id=event.reply_to_author_id,
            reply_to_author_display_name=event.reply_to_author_display_name,
            mentions=event.mentions,
            raw_update_type=event.raw_update_type,
        )

    callback_event = _extract_max_callback_event(raw_event)
    if callback_event is not None:
        return callback_event

    max_event = _extract_max_message_event(raw_event)
    if max_event is None:
        return NormalizedBotEvent(
            ignored=True,
            ignore_reason="Event ignored: unsupported MAX event type or non-text message.",
            raw_update_type=_string_value(raw_event, "update_type") or _string_value(raw_event, "type"),
        )
    return max_event


def _extract_max_callback_event(raw_event: Mapping[str, Any]) -> NormalizedMaxCallbackEvent | None:
    callback = _mapping_value(raw_event, "callback")
    if callback is None:
        return None

    message = _mapping_value(raw_event, "message")
    body = _mapping_value(message, "body") or message
    recipient = _mapping_value(message, "recipient")
    user = _mapping_value(callback, "user")
    payload = _string_value(callback, "payload")
    if not payload:
        return NormalizedMaxCallbackEvent(
            payload=payload,
            callback_id=_string_value(callback, "callback_id"),
            user_id=_string_value(user, "user_id") or _string_value(user, "id"),
            chat_id=_string_value(recipient, "chat_id") or _string_value(message, "chat_id"),
            message_id=(
                _string_value(body, "mid")
                or _string_value(body, "message_id")
                or _string_value(message, "message_id")
                or _string_value(message, "id")
            ),
            message_text=_string_value(body, "text") or _string_value(message, "text"),
            timestamp=_string_value(callback, "timestamp") or _string_value(raw_event, "timestamp"),
            chat_type=_string_value(recipient, "chat_type"),
            sender_display_name=_display_name_from_profile(user),
            sender_username=_string_value(user, "username"),
            raw_update_type=_string_value(raw_event, "update_type") or _string_value(raw_event, "type"),
            ignored=True,
            ignore_reason="Event ignored: callback payload is missing.",
        )

    return NormalizedMaxCallbackEvent(
        payload=payload,
        callback_id=_string_value(callback, "callback_id"),
        user_id=_string_value(user, "user_id") or _string_value(user, "id"),
        chat_id=_string_value(recipient, "chat_id") or _string_value(message, "chat_id"),
        message_id=(
            _string_value(body, "mid")
            or _string_value(body, "message_id")
            or _string_value(message, "message_id")
            or _string_value(message, "id")
        ),
        message_text=_string_value(body, "text") or _string_value(message, "text"),
        timestamp=_string_value(callback, "timestamp") or _string_value(raw_event, "timestamp"),
        chat_type=_string_value(recipient, "chat_type"),
        sender_display_name=_display_name_from_profile(user),
        sender_username=_string_value(user, "username"),
        raw_update_type=_string_value(raw_event, "update_type") or _string_value(raw_event, "type"),
    )


def _looks_like_normalized_event(raw_event: Mapping[str, Any]) -> bool:
    if "update_type" in raw_event or "type" in raw_event:
        return False
    normalized_keys = {"chat_id", "user_id", "message_id", "text"}
    return bool(normalized_keys.intersection(raw_event.keys()))


def _extract_max_message_event(raw_event: Mapping[str, Any]) -> NormalizedBotEvent | None:
    message = _mapping_value(raw_event, "message")
    if message is None:
        message = _mapping_value(_mapping_value(raw_event, "message_created"), "message")
    if message is None:
        return None

    body = _mapping_value(message, "body") or message
    recipient = _mapping_value(message, "recipient")
    chat = _mapping_value(message, "chat")
    text = _string_value(body, "text") or _string_value(message, "text")
    chat_id = (
        _string_value(message, "chat_id")
        or _string_value(recipient, "chat_id")
        or _string_value(chat, "chat_id")
        or _string_value(chat, "id")
    )
    user_id = (
        _string_value(message, "user_id")
        or _string_value(_mapping_value(message, "sender"), "user_id")
        or _string_value(_mapping_value(message, "from"), "user_id")
        or _string_value(_mapping_value(message, "sender"), "id")
    )
    message_id = (
        _string_value(body, "mid")
        or _string_value(body, "message_id")
        or _string_value(message, "message_id")
        or _string_value(message, "id")
    )
    reply_metadata = _extract_max_link_reply_metadata(message)
    mentions = _extract_max_mentions(body, text)

    if text is None:
        return None

    return _normalized_or_ignored(
        chat_id=chat_id,
        user_id=user_id,
        message_id=message_id,
        text=text,
        timestamp=(
            _string_value(message, "timestamp")
            or _string_value(message, "created_at")
            or _string_value(raw_event, "timestamp")
        ),
        chat_type=(
            _string_value(chat, "type")
            or _string_value(recipient, "chat_type")
        ),
        chat_title=_chat_title_from_event_context(
            raw_event=raw_event,
            message=message,
            body=body,
            recipient=recipient,
            chat=chat,
        ),
        sender_display_name=(
            _string_value(_mapping_value(message, "sender"), "display_name")
            or _string_value(_mapping_value(message, "sender"), "name")
            or _display_name_from_profile(_mapping_value(message, "sender"))
        ),
        sender_username=_string_value(_mapping_value(message, "sender"), "username"),
        reply_to_message_id=reply_metadata["message_id"],
        reply_to_text=reply_metadata["text"],
        reply_to_author_id=reply_metadata["author_id"],
        reply_to_author_display_name=reply_metadata["author_display_name"],
        mentions=mentions,
        raw_update_type=_string_value(raw_event, "update_type") or _string_value(raw_event, "type"),
    )


def _extract_max_link_reply_metadata(message: Mapping[str, Any]) -> dict[str, str | None]:
    link = _mapping_value(message, "link")
    linked_message = _mapping_value(link, "message")
    linked_body = _mapping_value(linked_message, "body") or linked_message
    linked_sender = _mapping_value(link, "sender") or _mapping_value(linked_message, "sender")
    return {
        "message_id": (
            _string_value(linked_body, "mid")
            or _string_value(linked_body, "message_id")
            or _string_value(linked_message, "message_id")
            or _string_value(linked_message, "id")
        ),
        "text": _string_value(linked_body, "text") or _string_value(linked_message, "text"),
        "author_id": _string_value(linked_sender, "user_id") or _string_value(linked_sender, "id"),
        "author_display_name": _display_name_from_profile(linked_sender),
    }


def _extract_max_mentions(body: Mapping[str, Any], text: str | None) -> list[NormalizedMention]:
    markup_items = _sequence_value(body, "markup") or _sequence_value(body, "markups")
    if not markup_items:
        return []

    mentions: list[NormalizedMention] = []
    for item in markup_items:
        if not isinstance(item, Mapping):
            continue
        mention = _mention_from_markup(item, text)
        if mention is not None:
            mentions.append(mention)
    return mentions


def _mention_from_markup(markup: Mapping[str, Any], text: str | None) -> NormalizedMention | None:
    external_user_id = _mention_external_user_id(markup)
    user = _mapping_value(markup, "user")
    user_link = _mapping_value(markup, "user_link") or _mapping_value(markup, "userLink")
    kind = (_string_value(markup, "type") or _string_value(markup, "kind") or "").lower()
    raw_text = _mention_raw_text(markup, text)
    username = (
        _string_value(markup, "username")
        or _string_value(user, "username")
        or _string_value(user_link, "username")
    )
    display_name = (
        _display_name_from_profile(user)
        or _display_name_from_profile(user_link)
        or _string_value(markup, "display_name")
        or _string_value(markup, "name")
    )

    if "mention" not in kind and external_user_id is None and user is None and user_link is None:
        return None
    if not any((raw_text, external_user_id, username, display_name)):
        return None

    return NormalizedMention(
        raw_text=raw_text,
        external_user_id=external_user_id,
        username=username,
        display_name=display_name,
        start=_first_int_value(markup, ("from", "offset", "start")),
        length=_int_value(markup, "length"),
    )


def _mention_external_user_id(markup: Mapping[str, Any]) -> str | None:
    user = _mapping_value(markup, "user")
    user_link = _mapping_value(markup, "user_link") or _mapping_value(markup, "userLink")
    return (
        _string_value(markup, "user_id")
        or _string_value(markup, "userId")
        or _string_value(user, "user_id")
        or _string_value(user, "userId")
        or _string_value(user, "id")
        or _string_value(user_link, "user_id")
        or _string_value(user_link, "userId")
        or _string_value(user_link, "id")
    )


def _mention_raw_text(markup: Mapping[str, Any], text: str | None) -> str | None:
    explicit_text = (
        _string_value(markup, "text")
        or _string_value(markup, "raw_text")
        or _string_value(markup, "rawText")
        or _string_value(markup, "mention")
    )
    if explicit_text:
        return explicit_text
    start = _first_int_value(markup, ("from", "offset", "start"))
    length = _int_value(markup, "length")
    if text is None or start is None or length is None or start < 0 or length <= 0:
        return None
    return text[start : start + length]


def _display_name_from_profile(profile: Mapping[str, Any] | None) -> str | None:
    if profile is None:
        return None
    explicit_name = (
        _string_value(profile, "display_name")
        or _string_value(profile, "name")
        or _string_value(profile, "username")
    )
    if explicit_name:
        return explicit_name
    parts = [
        part.strip()
        for part in (
            _string_value(profile, "first_name"),
            _string_value(profile, "last_name"),
        )
        if part and part.strip()
    ]
    if parts:
        return " ".join(parts)
    return None


def _normalized_or_ignored(
    *,
    chat_id: str | None,
    user_id: str | None,
    message_id: str | None,
    text: str,
    timestamp: str | None = None,
    chat_type: str | None = None,
    chat_title: str | None = None,
    sender_display_name: str | None = None,
    sender_username: str | None = None,
    reply_to_message_id: str | None = None,
    reply_to_text: str | None = None,
    reply_to_author_id: str | None = None,
    reply_to_author_display_name: str | None = None,
    mentions: list[NormalizedMention] | None = None,
    raw_update_type: str | None = None,
) -> NormalizedBotEvent:
    normalized_mentions = mentions or []
    if not text.strip():
        return NormalizedBotEvent(
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            text=text,
            timestamp=timestamp,
            chat_type=chat_type,
            chat_title=chat_title,
            sender_display_name=sender_display_name,
            sender_username=sender_username,
            reply_to_message_id=reply_to_message_id,
            reply_to_text=reply_to_text,
            reply_to_author_id=reply_to_author_id,
            reply_to_author_display_name=reply_to_author_display_name,
            mentions=normalized_mentions,
            raw_update_type=raw_update_type,
            ignored=True,
            ignore_reason="Event ignored: empty text.",
        )
    return NormalizedBotEvent(
        chat_id=chat_id,
        user_id=user_id,
        message_id=message_id,
        text=text,
        timestamp=timestamp,
        chat_type=chat_type,
        chat_title=chat_title,
        sender_display_name=sender_display_name,
        sender_username=sender_username,
        reply_to_message_id=reply_to_message_id,
        reply_to_text=reply_to_text,
        reply_to_author_id=reply_to_author_id,
        reply_to_author_display_name=reply_to_author_display_name,
        mentions=normalized_mentions,
        raw_update_type=raw_update_type,
    )


def _mapping_value(source: Mapping[str, Any] | None, key: str) -> Mapping[str, Any] | None:
    if source is None:
        return None
    value = source.get(key)
    if isinstance(value, Mapping):
        return value
    return None


def _chat_title_from_event_context(
    *,
    raw_event: Mapping[str, Any],
    message: Mapping[str, Any],
    body: Mapping[str, Any],
    recipient: Mapping[str, Any] | None,
    chat: Mapping[str, Any] | None,
) -> str | None:
    message_created = _mapping_value(raw_event, "message_created")
    raw_body = _mapping_value(raw_event, "body")
    sources = (
        chat,
        recipient,
        message,
        _mapping_value(body, "chat"),
        _mapping_value(body, "recipient"),
        _mapping_value(body, "dialog"),
        _mapping_value(body, "conversation"),
        _mapping_value(message, "dialog"),
        _mapping_value(message, "conversation"),
        _mapping_value(raw_event, "chat"),
        _mapping_value(raw_event, "recipient"),
        _mapping_value(raw_event, "dialog"),
        _mapping_value(raw_event, "conversation"),
        _mapping_value(raw_body, "chat"),
        _mapping_value(raw_body, "recipient"),
        _mapping_value(raw_body, "dialog"),
        _mapping_value(raw_body, "conversation"),
        _mapping_value(message_created, "chat"),
        _mapping_value(message_created, "recipient"),
        _mapping_value(message_created, "dialog"),
        _mapping_value(message_created, "conversation"),
    )
    return _chat_title_from_context(*sources)


def _chat_title_from_context(*sources: Mapping[str, Any] | None) -> str | None:
    candidate_keys = (
        "title",
        "chat_title",
        "chatTitle",
        "name",
        "chat_name",
        "chatName",
        "display_name",
        "displayName",
        "dialog_title",
        "dialogTitle",
        "conversation_title",
        "conversationTitle",
        "group_title",
        "groupTitle",
    )
    for source in sources:
        for key in candidate_keys:
            normalized = _normal_chat_title_candidate(_string_value(source, key))
            if normalized is not None:
                return normalized
    return None


def _normal_chat_title_candidate(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or _is_generated_or_identifier_chat_title(normalized):
        return None
    return normalized


UUID_LIKE_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_generated_or_identifier_chat_title(value: str) -> bool:
    normalized = value.strip()
    lowered = normalized.lower()
    return (
        lowered.startswith("max chat #")
        or lowered.startswith("max dialog #")
        or lowered.startswith("max group #")
        or lowered in {"чат без названия", "личный чат", "групповой чат"}
        or lowered.startswith("mid.")
        or UUID_LIKE_RE.match(normalized) is not None
        or normalized.lstrip("-").isdigit()
    )


def _sequence_value(source: Mapping[str, Any] | None, key: str) -> Sequence[Any] | None:
    if source is None:
        return None
    value = source.get(key)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return None


def _string_value(source: Mapping[str, Any] | None, key: str) -> str | None:
    if source is None:
        return None
    value = source.get(key)
    if value is None:
        return None
    return str(value)


def _int_value(source: Mapping[str, Any] | None, key: str) -> int | None:
    if source is None:
        return None
    value = source.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _first_int_value(source: Mapping[str, Any] | None, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = _int_value(source, key)
        if value is not None:
            return value
    return None


class MaxBotWebhookService:
    def __init__(
        self,
        *,
        command_parser: BotCommandParser,
        sender: MaxSender,
        chat_repository: ChatRepository,
        user_repository: UserRepository,
        task_service: TaskService,
        identity_resolver: MaxIdentityResolver | None = None,
        callback_service: BotCallbackService | None = None,
        pending_action_repository: Any | None = None,
        notification_delivery_service: NotificationDeliveryService | None = None,
        webapp_base_url: str = "https://maxsecretary.ru",
        max_bot_username: str = "",
        task_wizard_delete_user_inputs: bool = False,
    ) -> None:
        self.command_parser = command_parser
        self.sender = sender
        self.chat_repository = chat_repository
        self.user_repository = user_repository
        self.task_service = task_service
        self.identity_resolver = identity_resolver
        self.callback_service = callback_service
        self.pending_action_repository = pending_action_repository
        self.notification_delivery_service = notification_delivery_service
        self.webapp_base_url = webapp_base_url.rstrip("/")
        self.max_bot_username = max_bot_username
        self.task_wizard_delete_user_inputs = task_wizard_delete_user_inputs
        self.policy_service = PolicyService()
        self._identity_cache: dict[tuple[str | None, str | None], ResolvedMaxIdentity] = {}

    async def handle_event(
        self,
        event: NormalizedBotEvent | NormalizedMaxCallbackEvent | MaxBotWebhookEvent,
    ) -> BotWebhookResponse:
        if isinstance(event, NormalizedMaxCallbackEvent):
            return await self._handle_callback_event(event)

        if isinstance(event, MaxBotWebhookEvent):
            event = _normalized_or_ignored(
                chat_id=event.chat_id,
                user_id=event.user_id,
                message_id=event.message_id,
                text=event.text,
                timestamp=event.timestamp,
                chat_type=event.chat_type,
                sender_display_name=event.sender_display_name,
                sender_username=event.sender_username,
                reply_to_message_id=event.reply_to_message_id,
                reply_to_text=event.reply_to_text,
                reply_to_author_id=event.reply_to_author_id,
                reply_to_author_display_name=event.reply_to_author_display_name,
                mentions=event.mentions,
                raw_update_type=event.raw_update_type,
            )
        if event.ignored:
            return BotWebhookResponse(
                ok=True,
                is_command=False,
                action="ignored",
                response_text=event.ignore_reason or "Event ignored.",
            )
        if not event.text.strip():
            pending_report_result = await self._complete_pending_report(event)
            if pending_report_result is not None:
                outbound = await self._send_execution_result(event, pending_report_result)
                return BotWebhookResponse(
                    ok=True,
                    is_command=False,
                    action="reply_prepared",
                    response_text=pending_report_result.response_text,
                    outbound=outbound,
                )
            return BotWebhookResponse(
                ok=True,
                is_command=False,
                action="ignored",
                response_text="Event ignored: empty text.",
            )
        if self._event_contains_bot_assignment_mention(event):
            pending_assignment_result = await self._complete_pending_assignment_from_mention(event)
            if pending_assignment_result is not None:
                outbound = await self._send_execution_result(event, pending_assignment_result)
                return BotWebhookResponse(
                    ok=True,
                    is_command=False,
                    action="reply_prepared",
                    response_text=pending_assignment_result.response_text,
                    outbound=outbound,
                )
        if not self.command_parser.is_command(event.text):
            pending_text_result = await self._complete_pending_task_text(event)
            if pending_text_result is not None:
                outbound = await self._send_execution_result(event, pending_text_result)
                return BotWebhookResponse(
                    ok=True,
                    is_command=False,
                    action="reply_prepared",
                    response_text=pending_text_result.response_text,
                    outbound=outbound,
                )
            pending_deadline_result = await self._complete_pending_task_deadline(event)
            if pending_deadline_result is not None:
                outbound = await self._send_execution_result(event, pending_deadline_result)
                return BotWebhookResponse(
                    ok=True,
                    is_command=False,
                    action="reply_prepared",
                    response_text=pending_deadline_result.response_text,
                    outbound=outbound,
                )
            pending_assignment_result = await self._complete_pending_assignment_from_mention(event)
            if pending_assignment_result is not None:
                outbound = await self._send_execution_result(event, pending_assignment_result)
                return BotWebhookResponse(
                    ok=True,
                    is_command=False,
                    action="reply_prepared",
                    response_text=pending_assignment_result.response_text,
                    outbound=outbound,
                )
            pending_reject_reason_result = await self._complete_pending_acceptance_reject_reason(event)
            if pending_reject_reason_result is not None:
                outbound = await self._send_execution_result(event, pending_reject_reason_result)
                return BotWebhookResponse(
                    ok=True,
                    is_command=False,
                    action="reply_prepared",
                    response_text=pending_reject_reason_result.response_text,
                    outbound=outbound,
                )
            pending_report_result = await self._complete_pending_report(event)
            if pending_report_result is not None:
                outbound = await self._send_execution_result(event, pending_report_result)
                return BotWebhookResponse(
                    ok=True,
                    is_command=False,
                    action="reply_prepared",
                    response_text=pending_report_result.response_text,
                    outbound=outbound,
                )
            return BotWebhookResponse(
                ok=True,
                is_command=False,
                action="ignored",
                response_text="Event ignored: message is not a command.",
            )

        command_now = self.command_parser.now()
        command = self.command_parser.parse(event.text, source_text=event.reply_to_text, now=command_now)
        if isinstance(command, CommandParseError):
            return await self._error_response(event, command, f"Ошибка формата команды: {command.message}")
        if isinstance(command, UnknownCommand):
            return await self._error_response(
                event,
                command,
                "Не понял команду. Напишите /дьяк, чтобы открыть меню.",
            )

        try:
            chat_gate_result = await self._check_chat_connection_status(event)
            if chat_gate_result is not None and not isinstance(command, SlashHelpCommand):
                outbound = await self._send_execution_result(event, chat_gate_result)
                return BotWebhookResponse(
                    ok=True,
                    is_command=True,
                    action="reply_prepared",
                    command=command,
                    response_text=chat_gate_result.response_text,
                    outbound=outbound,
                )
            if not isinstance(command, CreateTaskCommand):
                await self._cancel_pending_task_creation_for_command(event)
            result = await self._execute_command(event, command, now=command_now)
        except BotCommandExecutionError as error:
            return await self._error_response(event, command, error.message)

        outbound = await self._send_execution_result(event, result)
        return BotWebhookResponse(
            ok=True,
            is_command=True,
            action="reply_prepared",
            command=command,
            response_text=result.response_text,
            outbound=outbound,
        )

    async def _check_chat_connection_status(
        self,
        event: NormalizedBotEvent,
    ) -> CommandExecutionResult | None:
        chat = await self._get_current_chat(event)
        status = str(getattr(chat, "status", "active") or "active")
        if status == ChatConnectionStatus.active.value:
            return None
        return CommandExecutionResult(response_text=self._chat_connection_status_text(status))

    async def _send_execution_result(
        self,
        event: NormalizedBotEvent,
        result: CommandExecutionResult,
    ) -> BotOutboundMessage:
        edit_error: str | None = None
        if not result.edit_message_id and not result.allow_send_fallback:
            reason = "wizard message id is missing"
            user_cleanup = await self._cleanup_task_wizard_user_inputs(event, result)
            await self._record_wizard_cleanup_result(
                result.cleanup_pending_action_id,
                status=PENDING_ACTION_CLEANUP_FAILED,
                error=self._combine_cleanup_errors(reason, user_cleanup.error),
            )
            return BotOutboundMessage(
                adapter="max",
                method="edit_message",
                chat_id=event.chat_id,
                message_id=None,
                text=result.response_text,
                sent=False,
                reason=reason,
            )
        if result.edit_message_id:
            logger.info(
                "Task wizard edit attempt",
                extra={
                    "message_id_present": True,
                    "message_id_len": len(result.edit_message_id),
                    "has_task_card": result.task_card is not None,
                    "has_buttons": result.button_rows is not None,
                },
            )
            outbound = self._edit_execution_result(result)
            if outbound.sent:
                user_cleanup = await self._cleanup_task_wizard_user_inputs(event, result)
                await self._record_wizard_cleanup_result(
                    result.cleanup_pending_action_id,
                    status=self._cleanup_status_after_user_inputs(
                        default_status=PENDING_ACTION_CLEANUP_EDITED,
                        user_cleanup=user_cleanup,
                    ),
                    error=user_cleanup.error,
                )
                return outbound
            edit_error = outbound.reason
            if not result.allow_send_fallback:
                logger.warning(
                    "Task wizard edit failed; send fallback disabled",
                    extra={
                        "message_id_present": True,
                        "message_id_len": len(result.edit_message_id),
                        "reason": outbound.reason,
                    },
                )
                user_cleanup = await self._cleanup_task_wizard_user_inputs(event, result)
                await self._record_wizard_cleanup_result(
                    result.cleanup_pending_action_id,
                    status=PENDING_ACTION_CLEANUP_FAILED,
                    error=self._combine_cleanup_errors(edit_error, user_cleanup.error),
                )
                return outbound
            logger.warning(
                "Task wizard edit failed; falling back to new message",
                extra={
                    "message_id_present": True,
                    "message_id_len": len(result.edit_message_id),
                    "reason": outbound.reason,
                },
            )

        if result.task_card is not None:
            outbound_chat_id = await self._resolve_outbound_chat_id(event)
            outbound = self.sender.send_task_card(outbound_chat_id, result.task_card)
        elif result.button_rows is not None:
            outbound_chat_id = await self._resolve_outbound_chat_id(event)
            outbound = self.sender.send_inline_keyboard_message(
                chat_id=outbound_chat_id,
                text=result.response_text,
                button_rows=result.button_rows,
            )
        else:
            outbound_chat_id = await self._resolve_outbound_chat_id(event)
            outbound = self.sender.send_message(outbound_chat_id, result.response_text)
        await self._track_wizard_message(result, outbound)
        user_cleanup = await self._cleanup_task_wizard_user_inputs(event, result)
        if result.cleanup_pending_action_id is not None and edit_error:
            await self._record_wizard_cleanup_result(
                result.cleanup_pending_action_id,
                status=PENDING_ACTION_CLEANUP_FAILED,
                error=self._combine_cleanup_errors(edit_error, user_cleanup.error),
            )
        elif result.cleanup_pending_action_id is not None and not result.edit_message_id:
            await self._record_wizard_cleanup_result(
                result.cleanup_pending_action_id,
                status=PENDING_ACTION_CLEANUP_FAILED,
                error=self._combine_cleanup_errors("wizard message id is missing", user_cleanup.error),
            )
        return outbound

    def _edit_execution_result(self, result: CommandExecutionResult) -> BotOutboundMessage:
        attachments = None
        if result.button_rows is not None:
            attachments = [{"type": "inline_keyboard", "payload": {"buttons": result.button_rows}}]
        return self.sender.edit_message(
            message_id=result.edit_message_id,
            text=result.response_text,
            attachments=attachments,
        )

    async def _cleanup_task_wizard_user_inputs(
        self,
        event: NormalizedBotEvent,
        result: CommandExecutionResult,
    ) -> UserInputCleanupResult:
        message_ids = self._deduplicate_user_input_message_ids(result.user_input_message_ids)
        if not message_ids:
            return UserInputCleanupResult()
        if not self.task_wizard_delete_user_inputs:
            return UserInputCleanupResult(attempted=len(message_ids), disabled=True)

        deleted = 0
        failures: list[str] = []
        for message_id in message_ids:
            outbound_chat_id = await self._resolve_outbound_chat_id(event)
            outbound = self.sender.delete_message(message_id=message_id, chat_id=outbound_chat_id)
            if outbound.sent:
                deleted += 1
            else:
                failures.append(outbound.reason)
        failed = len(message_ids) - deleted
        error = None
        if failures:
            unique_reasons = list(dict.fromkeys(failures))
            error = f"user input cleanup deleted {deleted}/{len(message_ids)}; reasons: {'; '.join(unique_reasons)[:300]}"
            logger.warning(
                "Task wizard user input cleanup incomplete",
                extra={
                    "attempted": len(message_ids),
                    "deleted": deleted,
                    "failed": failed,
                },
            )
        elif message_ids:
            logger.info(
                "Task wizard user input cleanup complete",
                extra={"attempted": len(message_ids), "deleted": deleted},
            )
        return UserInputCleanupResult(
            attempted=len(message_ids),
            deleted=deleted,
            failed=failed,
            error=error,
        )

    def _cleanup_status_after_user_inputs(
        self,
        *,
        default_status: str,
        user_cleanup: UserInputCleanupResult,
    ) -> str:
        if user_cleanup.disabled or user_cleanup.attempted == 0 or user_cleanup.failed == 0:
            return default_status
        if user_cleanup.deleted > 0:
            return PENDING_ACTION_CLEANUP_PARTIAL
        return PENDING_ACTION_CLEANUP_FAILED

    def _combine_cleanup_errors(self, primary: str | None, secondary: str | None) -> str | None:
        if primary and secondary:
            return f"{primary}; {secondary}"
        return primary or secondary

    async def _track_wizard_message(
        self,
        result: CommandExecutionResult,
        outbound: BotOutboundMessage,
    ) -> None:
        if result.track_pending_action_id is None:
            return
        if not outbound.message_id:
            logger.warning(
                "Task wizard prompt sent without editable message id",
                extra={
                    "outbound_method": outbound.method,
                    "outbound_sent": outbound.sent,
                    "outbound_reason": outbound.reason,
                },
            )
            return
        mark_wizard_message_sent = getattr(self.pending_action_repository, "mark_wizard_message_sent", None)
        if mark_wizard_message_sent is None:
            return
        await mark_wizard_message_sent(result.track_pending_action_id, message_id=outbound.message_id)

    async def _record_wizard_cleanup_result(
        self,
        pending_action_id: UUID | None,
        *,
        status: str,
        error: str | None,
    ) -> None:
        if pending_action_id is None:
            return
        mark_cleanup_result = getattr(self.pending_action_repository, "mark_cleanup_result", None)
        if mark_cleanup_result is None:
            return
        await mark_cleanup_result(pending_action_id, status=status, error=error)

    async def _handle_callback_event(self, event: NormalizedMaxCallbackEvent) -> BotWebhookResponse:
        if event.ignored:
            return BotWebhookResponse(
                ok=True,
                is_command=False,
                action="ignored",
                response_text=event.ignore_reason or "Event ignored.",
            )
        if self.callback_service is None:
            response_text = "Callback-обработчик не настроен."
            outbound = self.sender.answer_callback(callback_id=event.callback_id, notification=response_text)
            return BotWebhookResponse(
                ok=False,
                is_command=False,
                action="error",
                response_text=response_text,
                error=response_text,
                outbound=outbound,
            )
        if not event.payload:
            response_text = "Callback payload отсутствует."
            outbound = self.sender.answer_callback(callback_id=event.callback_id, notification=response_text)
            return BotWebhookResponse(
                ok=False,
                is_command=False,
                action="error",
                response_text=response_text,
                error=response_text,
                outbound=outbound,
            )

        try:
            actor = await self._get_callback_actor(event)
            callback_chat = await self._get_callback_chat(event)
            result = await self.callback_service.handle_event(
                NormalizedCallbackEvent(
                    payload=event.payload,
                    user_id=actor.id,
                    chat_id=callback_chat.id,
                    message_id=event.message_id,
                    callback_id=event.callback_id,
                )
            )
        except BotCallbackForbidden as exc:
            return self._callback_error_response(event, self._callback_forbidden_message(exc))
        except (BotCallbackError, CallbackPayloadError):
            return self._callback_error_response(event, "Не удалось обработать callback.")
        except BotCommandExecutionError as exc:
            return self._callback_error_response(event, exc.message)

        outbound = self.sender.answer_callback(
            callback_id=event.callback_id,
            notification=result.response_text,
            message=self._callback_answer_message(result),
        )
        await self._record_callback_cleanup_result(result, outbound)
        await self._record_callback_wizard_message(result, outbound)
        return BotWebhookResponse(
            ok=True,
            is_command=False,
            action="callback_processed",
            response_text=result.response_text,
            outbound=outbound,
        )

    def _callback_answer_message(self, result: BotCallbackResult) -> dict[str, Any] | None:
        if not result.answer_message_text:
            return None
        return {
            "text": result.answer_message_text,
            "attachments": result.answer_message_attachments or [],
        }

    def _callback_forbidden_message(self, exc: BotCallbackForbidden) -> str:
        message = str(exc).strip()
        if message and not message.startswith("Only "):
            return message
        return "Действие недоступно."

    async def _record_callback_cleanup_result(
        self,
        result: BotCallbackResult,
        outbound: BotOutboundMessage,
    ) -> None:
        if result.action != "assign" or result.pending_action_id is None or not result.answer_message_text:
            return
        try:
            await self.callback_service.mark_assignment_cleanup(
                result.pending_action_id,
                succeeded=outbound.sent,
                error=None if outbound.sent else outbound.reason,
            )
        except Exception:
            return

    async def _record_callback_wizard_message(
        self,
        result: BotCallbackResult,
        outbound: BotOutboundMessage,
    ) -> None:
        if result.action != "report" or result.pending_action_id is None or not result.answer_message_text:
            return
        if not outbound.message_id:
            logger.warning(
                "Report wizard prompt sent without editable message id",
                extra={
                    "outbound_method": outbound.method,
                    "outbound_sent": outbound.sent,
                    "outbound_reason": outbound.reason,
                },
            )
            return
        pending_repository = self.pending_action_repository or getattr(
            self.callback_service,
            "pending_action_repository",
            None,
        )
        mark_wizard_message_sent = getattr(pending_repository, "mark_wizard_message_sent", None)
        if mark_wizard_message_sent is None:
            return
        await mark_wizard_message_sent(result.pending_action_id, message_id=outbound.message_id)

    async def _get_callback_actor(self, event: NormalizedMaxCallbackEvent) -> User:
        identity_event = self._callback_identity_event(event)
        identity = await self._resolve_external_identity_if_needed(identity_event)
        if identity is not None:
            return identity.user
        user_id = self._parse_internal_event_uuid(
            self._require_event_field(event.user_id, "user_id"),
            field_name="user_id",
            external_id_note="TODO: add lookup or autocreate by max_user_id.",
        )
        user = await self.user_repository.get(user_id)
        if user is None:
            raise BotCommandExecutionError("Пользователь не найден. Передайте существующий внутренний User.id.")
        return user

    async def _get_callback_chat(self, event: NormalizedMaxCallbackEvent) -> Chat:
        identity_event = self._callback_identity_event(event)
        identity = await self._resolve_external_identity_if_needed(identity_event)
        if identity is not None:
            return identity.chat
        chat_id = self._parse_internal_event_uuid(
            self._require_event_field(event.chat_id, "chat_id"),
            field_name="chat_id",
            external_id_note="TODO: add lookup or autocreate by max_chat_id.",
        )
        chat = await self.chat_repository.get_chat(chat_id)
        if chat is None:
            raise BotCommandExecutionError("Чат не найден. Передайте существующий внутренний Chat.id.")
        return chat

    def _callback_identity_event(self, event: NormalizedMaxCallbackEvent) -> NormalizedBotEvent:
        return NormalizedBotEvent(
            chat_id=event.chat_id,
            user_id=event.user_id,
            message_id=event.message_id,
            text=event.message_text or event.payload or "callback",
            timestamp=event.timestamp,
            chat_type=event.chat_type,
            sender_display_name=event.sender_display_name,
            sender_username=event.sender_username,
            raw_update_type=event.raw_update_type,
        )

    def _callback_error_response(self, event: NormalizedMaxCallbackEvent, message: str) -> BotWebhookResponse:
        outbound = self.sender.answer_callback(callback_id=event.callback_id, notification=message)
        return BotWebhookResponse(
            ok=False,
            is_command=False,
            action="error",
            response_text=message,
            error=message,
            outbound=outbound,
        )

    async def _execute_command(
        self,
        event: NormalizedBotEvent,
        command: Command,
        *,
        now: datetime | None = None,
    ) -> CommandExecutionResult:
        if isinstance(command, CreateTaskCommand):
            return await self._create_task(event, command, now=now)
        if isinstance(command, ListTasksCommand):
            return await self._list_chat_tasks(event)
        if isinstance(command, MyTasksCommand):
            return await self._list_my_tasks(event)
        if isinstance(command, TaskLookupCommand):
            return await self._lookup_task(event, command)
        if isinstance(command, TaskReportCommand):
            return await self._submit_task_report(event, command)
        if isinstance(command, PingTaskCommand):
            return await self._ping_task(event, command)
        if isinstance(command, SecretaryCommand):
            return await self._secretary_summary(event)
        if isinstance(command, SlashHelpCommand):
            return await self._slash_command_help(event)
        if isinstance(command, (TaskResponseCommand, TaskDoneCommand)):
            return await self._submit_response(event, command)
        if isinstance(command, AcceptTaskResponseCommand):
            return await self._accept_response(event, command)
        if isinstance(command, RejectTaskResponseCommand):
            return await self._reject_response(event, command)
        self._raise_unhandled_command(command)

    async def _create_task(
        self,
        event: NormalizedBotEvent,
        command: CreateTaskCommand,
        *,
        now: datetime | None = None,
    ) -> CommandExecutionResult:
        chat = await self._get_current_chat(event)
        requester = await self._get_current_user(event)
        auth_context = await self._bot_auth_context(user=requester, chat=chat)
        can_assign_others = self._can_assign_task_to_others(auth_context)
        await self._cancel_incompatible_pending_reports(actor_user_id=requester.id, chat_id=chat.id)
        await self._cancel_incompatible_pending_task_creation(actor_user_id=requester.id, chat_id=chat.id)
        if command.needs_text_clarification:
            pending_text_result = await self._create_task_text_clarification(event, chat, requester)
            if pending_text_result is not None:
                return pending_text_result
            return CommandExecutionResult(response_text=TASK_WIZARD_TEXT_PROMPT)
        assignees = await self._resolve_users_by_display_name(command.assignees)
        mention_resolution = await self._resolve_assignee_mentions(command.assignee_mentions, chat)
        assignees = self._deduplicate_users(
            [
                *assignees,
                *mention_resolution.users,
            ]
        )
        observers = await self._resolve_users_by_display_name(command.observers)
        if not can_assign_others:
            if observers:
                return CommandExecutionResult(response_text="Добавлять наблюдателей может только админ чата.")
            if any(user.id != requester.id for user in assignees) or (
                not assignees and (command.assignees or command.assignee_mentions)
            ):
                return CommandExecutionResult(response_text="Назначать задачи другим может только админ чата.")
        if not assignees and self._should_assign_reply_task_to_requester(event, command):
            assignees = [requester]
        deadline_at = command.deadline_at
        if deadline_at is None and command.deadline is not None:
            deadline_at = datetime.combine(command.deadline, time.max, tzinfo=timezone.utc)
        if deadline_at is None or command.needs_deadline_clarification:
            pending_deadline_result = await self._create_task_deadline_clarification(event, command, chat, requester)
            if pending_deadline_result is not None:
                return pending_deadline_result
            return CommandExecutionResult(
                response_text=TASK_WIZARD_DEADLINE_PROMPT
            )
        if not is_future_task_deadline(deadline_at, now=now):
            pending_deadline_result = await self._create_task_deadline_clarification(
                event,
                command,
                chat,
                requester,
                response_text=TASK_WIZARD_PAST_DEADLINE_PROMPT,
            )
            if pending_deadline_result is not None:
                return pending_deadline_result
            return CommandExecutionResult(response_text=TASK_WIZARD_PAST_DEADLINE_PROMPT)

        if not assignees and not can_assign_others:
            assignees = [requester]

        if not assignees:
            pending_result = await self._create_assignee_mention_prompt(
                event,
                command,
                chat,
                requester,
                mention_resolution=mention_resolution,
                intro_lines=(
                    self._format_assignee_mention_warnings(mention_resolution)
                    if command.assignee_mentions
                    else None
                ),
                deadline_at=as_aware_utc(deadline_at),
            )
            if pending_result is not None:
                return pending_result
            if command.assignee_mentions:
                return CommandExecutionResult(response_text=self._format_assignee_mention_failure(mention_resolution))

        source_message_id = event.reply_to_message_id or event.message_id

        task = await self.task_service.create(
            TaskCreate(
                organization_id=chat.organization_id,
                chat_id=chat.id,
                title=command.title,
                description=self._build_source_description(event, command),
                source_message_id=source_message_id,
                created_by_user_id=requester.id,
                deadline_at=as_aware_utc(deadline_at),
                assignee_ids=[user.id for user in assignees],
                observer_ids=[user.id for user in observers],
            )
        )
        return self._task_creation_result(
            task=task,
            title=task.title,
            assignees=assignees,
            deadline_at=as_aware_utc(deadline_at),
            user_input_message_ids=self._user_input_message_ids_from_event(event),
        )

    async def _create_assignee_mention_prompt(
        self,
        event: NormalizedBotEvent,
        command: CreateTaskCommand,
        chat: Chat,
        requester: User,
        *,
        mention_resolution: AssigneeMentionResolution,
        deadline_at: datetime | None,
        intro_lines: list[str] | None = None,
    ) -> CommandExecutionResult | None:
        if self.pending_action_repository is None:
            return None

        source_message_id = event.reply_to_message_id or event.message_id
        pending = await self.pending_action_repository.create_task_assignee_picker(
            actor_user_id=requester.id,
            chat_id=chat.id,
            title=command.title,
            source_text=command.source_text,
            description=self._build_source_description(event, command),
            source_message_id=source_message_id,
            deadline_at=as_aware_utc(deadline_at),
            reply_context=self._task_wizard_context(event),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        response_lines: list[str] = []
        if intro_lines:
            response_lines.extend(intro_lines)
        response_lines.append(ASSIGNEE_MENTION_PROMPT)
        return CommandExecutionResult(
            response_text="\n".join(response_lines),
            track_pending_action_id=getattr(pending, "id", None),
        )

    async def _create_task_deadline_clarification(
        self,
        event: NormalizedBotEvent,
        command: CreateTaskCommand,
        chat: Chat,
        requester: User,
        *,
        response_text: str = TASK_WIZARD_DEADLINE_PROMPT,
    ) -> CommandExecutionResult | None:
        if self.pending_action_repository is None:
            return None
        create_deadline_clarification = getattr(
            self.pending_action_repository,
            "create_task_deadline_clarification",
            None,
        )
        if create_deadline_clarification is None:
            return None

        source_message_id = event.reply_to_message_id or event.message_id
        pending = await create_deadline_clarification(
            actor_user_id=requester.id,
            chat_id=chat.id,
            title=command.title,
            source_text=command.source_text,
            description=self._build_source_description(event, command),
            source_message_id=source_message_id,
            reply_context=self._task_wizard_context(event),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        return CommandExecutionResult(
            response_text=response_text,
            track_pending_action_id=getattr(pending, "id", None),
        )

    async def _create_task_text_clarification(
        self,
        event: NormalizedBotEvent,
        chat: Chat,
        requester: User,
    ) -> CommandExecutionResult | None:
        if self.pending_action_repository is None:
            return None
        create_text_clarification = getattr(
            self.pending_action_repository,
            "create_task_text_clarification",
            None,
        )
        if create_text_clarification is None:
            return None

        pending = await create_text_clarification(
            actor_user_id=requester.id,
            chat_id=chat.id,
            source_message_id=event.message_id,
            reply_context=self._task_wizard_context(event),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        return CommandExecutionResult(
            response_text=TASK_WIZARD_TEXT_PROMPT,
            track_pending_action_id=getattr(pending, "id", None),
        )

    async def _complete_pending_task_text(
        self,
        event: NormalizedBotEvent,
    ) -> CommandExecutionResult | None:
        if self.pending_action_repository is None:
            return None
        get_latest_pending = getattr(
            self.pending_action_repository,
            "get_latest_pending_task_text_clarification",
            None,
        )
        if get_latest_pending is None:
            return None

        chat = await self._get_current_chat(event)
        actor = await self._get_current_user(event)
        pending = await get_latest_pending(actor_user_id=actor.id, chat_id=chat.id)
        if pending is None:
            return None

        now = datetime.now(timezone.utc)
        if getattr(pending, "expires_at", now) <= now:
            mark_expired = getattr(self.pending_action_repository, "mark_expired", None)
            if mark_expired is not None:
                await mark_expired(pending)
            return CommandExecutionResult(
                response_text="Время создания задачи истекло. Напишите /задача еще раз."
            )

        title = event.text.strip()
        if not title:
            return CommandExecutionResult(response_text=TASK_WIZARD_TEXT_PROMPT)

        mark_text_completed = getattr(self.pending_action_repository, "mark_text_completed", None)
        if mark_text_completed is not None:
            await mark_text_completed(pending)
        else:
            mark_cancelled = getattr(self.pending_action_repository, "mark_cancelled", None)
            if mark_cancelled is not None:
                await mark_cancelled(pending)

        create_deadline_clarification = getattr(
            self.pending_action_repository,
            "create_task_deadline_clarification",
            None,
        )
        if create_deadline_clarification is None:
            return CommandExecutionResult(
                response_text=TASK_WIZARD_DEADLINE_PROMPT
            )

        wizard_message_id = getattr(pending, "picker_message_id", None)
        reply_context = self._task_wizard_context(event, existing=getattr(pending, "reply_context", None))
        deadline_pending = await create_deadline_clarification(
            actor_user_id=actor.id,
            chat_id=chat.id,
            title=title,
            source_text=title,
            description=None,
            source_message_id=event.message_id,
            reply_context=reply_context,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            wizard_message_id=wizard_message_id,
        )
        return CommandExecutionResult(
            response_text=TASK_WIZARD_DEADLINE_PROMPT,
            edit_message_id=wizard_message_id,
            track_pending_action_id=getattr(deadline_pending, "id", None),
        )

    async def _complete_pending_task_deadline(
        self,
        event: NormalizedBotEvent,
    ) -> CommandExecutionResult | None:
        if self.pending_action_repository is None:
            return None
        get_latest_pending = getattr(
            self.pending_action_repository,
            "get_latest_pending_task_deadline_clarification",
            None,
        )
        if get_latest_pending is None:
            return None

        chat = await self._get_current_chat(event)
        actor = await self._get_current_user(event)
        pending = await get_latest_pending(
            actor_user_id=actor.id,
            chat_id=chat.id,
            now=datetime.now(timezone.utc),
        )
        if pending is None:
            return None

        parse_now = self.command_parser.now()
        deadline = parse_deadline(event.text, parse_now, DEFAULT_TIMEZONE)
        if deadline.deadline_at is None or deadline.needs_clarification:
            return self._task_wizard_validation_error_result(
                pending=pending,
                event=event,
                response_text=TASK_WIZARD_UNCLEAR_DEADLINE_PROMPT,
                error_type="deadline_unclear",
            )
        if not is_future_task_deadline(deadline.deadline_at, now=parse_now):
            return self._task_wizard_validation_error_result(
                pending=pending,
                event=event,
                response_text=TASK_WIZARD_PAST_DEADLINE_PROMPT,
                error_type="deadline_past",
            )

        reply_context = self._task_wizard_context(event, existing=getattr(pending, "reply_context", None))
        mark_cancelled = getattr(self.pending_action_repository, "mark_cancelled", None)
        if mark_cancelled is not None:
            await mark_cancelled(pending)

        auth_context = await self._bot_auth_context(user=actor, chat=chat)
        if not self._can_assign_task_to_others(auth_context):
            task = await self.task_service.create(
                TaskCreate(
                    organization_id=chat.organization_id,
                    chat_id=chat.id,
                    title=str(getattr(pending, "title", "Задача")),
                    description=getattr(pending, "description", None),
                    source_message_id=getattr(pending, "source_message_id", None) or event.message_id,
                    created_by_user_id=actor.id,
                    deadline_at=as_aware_utc(deadline.deadline_at),
                    assignee_ids=[actor.id],
                    observer_ids=[],
                )
            )
            mark_task_creation_completed = getattr(
                self.pending_action_repository,
                "mark_task_creation_completed",
                None,
            )
            if mark_task_creation_completed is not None:
                await mark_task_creation_completed(pending, task_id=task.id)
            result = self._task_creation_result(
                task=task,
                title=task.title,
                assignees=[actor],
                deadline_at=deadline.deadline_at,
                user_input_message_ids=self._user_input_message_ids_from_context(reply_context),
            )
            return self._with_wizard_edit(
                result,
                pending=pending,
                cleanup_pending_action_id=getattr(pending, "id", None),
            )

        return await self._create_assignee_mention_prompt_from_pending_deadline(
            event=event,
            pending=pending,
            chat=chat,
            actor=actor,
            deadline_at=deadline.deadline_at,
            reply_context=reply_context,
        )

    async def _create_assignee_mention_prompt_from_pending_deadline(
        self,
        *,
        event: NormalizedBotEvent,
        pending: object,
        chat: Chat,
        actor: User,
        deadline_at: datetime,
        reply_context: dict | None,
    ) -> CommandExecutionResult:
        if self.pending_action_repository is None:
            raise BotCommandExecutionError("Pending action handler is not configured.")
        create_picker = getattr(self.pending_action_repository, "create_task_assignee_picker", None)
        if create_picker is None:
            raise BotCommandExecutionError("Pending action handler is not configured.")

        wizard_message_id = getattr(pending, "picker_message_id", None)
        picker = await create_picker(
            actor_user_id=actor.id,
            chat_id=chat.id,
            title=str(getattr(pending, "title", "Задача")),
            source_text=getattr(pending, "source_text", None),
            description=getattr(pending, "description", None),
            source_message_id=getattr(pending, "source_message_id", None) or event.message_id,
            deadline_at=as_aware_utc(deadline_at),
            reply_context=reply_context,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            wizard_message_id=wizard_message_id,
        )
        response_lines = [
            ASSIGNEE_MENTION_PROMPT,
        ]
        return CommandExecutionResult(
            response_text="\n".join(response_lines),
            edit_message_id=wizard_message_id,
            track_pending_action_id=getattr(picker, "id", None),
        )

    async def _cancel_incompatible_pending_reports(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
    ) -> None:
        if self.pending_action_repository is None:
            return
        cancel_pending_reports = getattr(self.pending_action_repository, "cancel_pending_task_reports", None)
        if cancel_pending_reports is None:
            return
        await cancel_pending_reports(actor_user_id=actor_user_id, chat_id=chat_id)

    async def _cancel_incompatible_pending_task_creation(
        self,
        *,
        actor_user_id: UUID,
        chat_id: UUID,
    ) -> None:
        if self.pending_action_repository is None:
            return
        cancel_pending_task_creation = getattr(
            self.pending_action_repository,
            "cancel_pending_task_creation",
            None,
        )
        if cancel_pending_task_creation is None:
            return
        await cancel_pending_task_creation(actor_user_id=actor_user_id, chat_id=chat_id)

    async def _cancel_pending_task_creation_for_command(self, event: NormalizedBotEvent) -> None:
        if self.pending_action_repository is None:
            return
        chat = await self._get_current_chat(event)
        actor = await self._get_current_user(event)
        await self._cancel_incompatible_pending_task_creation(actor_user_id=actor.id, chat_id=chat.id)

    async def _complete_pending_assignment_from_mention(
        self,
        event: NormalizedBotEvent,
    ) -> CommandExecutionResult | None:
        if self.pending_action_repository is None:
            return None

        chat = await self._get_current_chat(event)
        actor = await self._get_current_user(event)
        get_latest_pending = getattr(
            self.pending_action_repository,
            "get_latest_pending_task_assignee_picker",
            None,
        )
        if get_latest_pending is None:
            return None
        pending = await get_latest_pending(
            actor_user_id=actor.id,
            chat_id=chat.id,
            now=datetime.now(timezone.utc),
        )
        if pending is None:
            return None

        mentions = self._assignment_mentions_from_event(event)
        if not mentions:
            return self._task_wizard_validation_error_result(
                pending=pending,
                event=event,
                response_text=TASK_WIZARD_NO_ASSIGNEE_MENTION_PROMPT,
                error_type="assignee_missing",
            )

        auth_context = await self._bot_auth_context(user=actor, chat=chat)
        if not self._can_assign_task_to_others(auth_context):
            return self._task_wizard_validation_error_result(
                pending=pending,
                event=event,
                response_text=TASK_WIZARD_MEMBER_ASSIGN_FORBIDDEN_PROMPT,
                error_type="assignee_forbidden",
            )

        mention_resolution = await self._resolve_normalized_assignment_mentions(
            mentions=mentions,
            chat=chat,
            actor=actor,
        )
        resolved_assignees = mention_resolution.users
        if not resolved_assignees:
            return self._task_wizard_validation_error_result(
                pending=pending,
                event=event,
                response_text=TASK_WIZARD_UNRESOLVED_ASSIGNEE_MENTION_PROMPT,
                error_type="assignee_unresolved",
            )

        response_prefix = ""
        if mention_resolution.unresolved_count > 0:
            response_prefix = f"{PARTIAL_ASSIGNEE_MENTION_TEXT}\n\n"

        task = await self.task_service.create(
            TaskCreate(
                organization_id=chat.organization_id,
                chat_id=chat.id,
                title=pending.title,
                description=pending.description,
                source_message_id=pending.source_message_id,
                created_by_user_id=pending.actor_user_id,
                deadline_at=as_aware_utc(pending.deadline_at),
                assignee_ids=[assignee.id for assignee in resolved_assignees],
                observer_ids=[],
            )
        )
        wizard_message_id = getattr(pending, "picker_message_id", None) or event.reply_to_message_id
        reply_context = self._task_wizard_context(event, existing=getattr(pending, "reply_context", None))
        await self.pending_action_repository.mark_completed(
            pending,
            task_id=task.id,
            selected_assignee_user_id=resolved_assignees[0].id,
            picker_message_id=wizard_message_id,
        )

        return CommandExecutionResult(
            response_text=(
                response_prefix
                + self._format_task_creation_card(
                    task=task,
                    title=pending.title,
                    assignee_names=[self._user_display_name(assignee) for assignee in resolved_assignees],
                    deadline_at=pending.deadline_at,
                )
            ),
            button_rows=self._open_task_button_rows(task),
            edit_message_id=wizard_message_id,
            cleanup_pending_action_id=getattr(pending, "id", None),
            user_input_message_ids=self._user_input_message_ids_from_context(reply_context),
        )

    def _assignment_mentions_from_event(self, event: NormalizedBotEvent) -> list[NormalizedMention]:
        mentions = list(event.mentions)
        bot_username = self._normalized_bot_username()
        if not bot_username:
            return mentions
        for token in event.text.split():
            if self._normalize_mention_name(token) == bot_username:
                if not any(self._is_bot_mention(mention) for mention in mentions):
                    mentions.insert(0, NormalizedMention(raw_text=token, username=bot_username))
                break
        return mentions

    def _event_contains_bot_assignment_mention(self, event: NormalizedBotEvent) -> bool:
        return any(self._is_bot_mention(mention) for mention in self._assignment_mentions_from_event(event))

    async def _assignee_picker_button_rows(
        self,
        chat: Chat,
        requester: User,
        pending_action_id: UUID,
    ) -> list[list[dict[str, Any]]]:
        members = await self.chat_repository.list_members(chat.id)
        rows: list[list[dict[str, Any]]] = []
        seen_user_ids: set[UUID] = {requester.id}
        for member in members:
            if not getattr(member, "is_active", False):
                continue
            user = getattr(member, "user", None)
            if user is None or user.id in seen_user_ids:
                continue
            seen_user_ids.add(user.id)
            rows.append(
                [
                    {
                        "type": "callback",
                        "text": self._user_display_name(user),
                        "payload": build_task_assignment_callback_payload(
                            pending_action_id=pending_action_id,
                            assignee_id=user.id,
                        ),
                        "intent": "default",
                    }
                ]
            )

        rows.append(
            [
                {
                    "type": "callback",
                    "text": "Назначить себе",
                    "payload": build_task_assignment_callback_payload(
                        pending_action_id=pending_action_id,
                        assign_self=True,
                    ),
                    "intent": "default",
                }
            ]
        )
        rows.append(
            [
                {
                    "type": "link",
                    "text": "Открыть в WebApp",
                    "url": self._webapp_deep_link(startapp=f"assign_{pending_action_id}"),
                }
            ]
        )
        return rows

    def _webapp_deep_link(self, *, startapp: str = "home", fallback_path: str | None = None) -> str:
        return build_max_webapp_deep_link(
            bot_username=self.max_bot_username,
            webapp_base_url=self.webapp_base_url,
            startapp=startapp,
            fallback_path=fallback_path,
        )

    async def _list_chat_tasks(self, event: NormalizedBotEvent) -> CommandExecutionResult:
        chat = await self._get_current_chat(event)
        tasks = await self.task_service.list(
            filters=TaskListFilters(chat_id=chat.id),
            limit=50,
            offset=0,
        )
        active_tasks = [
            task
            for task in tasks
            if task.status not in {TaskStatus.DONE.value, TaskStatus.CANCELLED.value}
        ]
        return CommandExecutionResult(response_text=self._format_tasks("Активные задачи чата", active_tasks))

    async def _list_my_tasks(self, event: NormalizedBotEvent) -> CommandExecutionResult:
        chat = await self._get_current_chat(event)
        user = await self._get_current_user(event)
        tasks = await self.task_service.list(
            filters=TaskListFilters(
                organization_id=chat.organization_id,
                assignee_id=user.id,
            ),
            limit=1000,
            offset=0,
        )
        now = datetime.now(timezone.utc)
        active_tasks = [task for task in tasks if task.status not in FINAL_TASK_STATUSES]
        active_tasks.sort(key=lambda task: self._my_task_sort_key(task, now))
        visible_tasks = active_tasks[:MY_TASKS_LIMIT]
        hidden_count = max(0, len(active_tasks) - MY_TASKS_LIMIT)
        return CommandExecutionResult(
            response_text=self._format_my_tasks_response(
                visible_tasks,
                hidden_count=hidden_count,
                now=now,
            ),
            button_rows=self._my_tasks_button_rows(has_tasks=bool(active_tasks)),
        )

    def _my_task_sort_key(self, task: object, now: datetime) -> tuple[int, float, float]:
        deadline_at = self._aware_datetime(getattr(task, "deadline_at", None))
        created_at = self._aware_datetime(getattr(task, "created_at", None))
        is_overdue = (
            deadline_at is not None
            and deadline_at < now
            and getattr(task, "status", None) not in FINAL_TASK_STATUSES
        )
        group = 0 if is_overdue else 1 if deadline_at is not None else 2
        deadline_sort = deadline_at.timestamp() if deadline_at is not None else 0.0
        created_sort = -(created_at.timestamp()) if created_at is not None else 0.0
        return (group, deadline_sort, created_sort)

    def _format_my_tasks_response(self, tasks: list[Task], *, hidden_count: int, now: datetime) -> str:
        if not tasks:
            return (
                "У вас нет активных задач.\n\n"
                "Создать задачу можно командой /задача в этом чате."
            )

        blocks = ["Ваши задачи:"]
        for task in tasks:
            blocks.append(
                "\n".join(
                    [
                        f"{self._task_ref(task)} · {self._task_status_label(task, now)}",
                        str(getattr(task, "title", "")),
                        f"Срок: {self._format_my_task_deadline(getattr(task, 'deadline_at', None), now)}",
                        f"Постановщик: {self._task_creator_display_name(task)}",
                    ]
                )
            )
        if hidden_count > 0:
            blocks.append(f"Еще {hidden_count} задач — откройте WebApp.")
        return "\n\n".join(blocks)

    def _my_tasks_button_rows(self, *, has_tasks: bool) -> list[list[dict[str, Any]]]:
        if has_tasks:
            return [
                [
                    {
                        "type": "link",
                        "text": "Открыть все в WebApp",
                        "url": self._webapp_deep_link(startapp="my_tasks"),
                    }
                ]
            ]
        return [
            [
                {
                    "type": "link",
                    "text": "Открыть Дьяк",
                    "url": self._webapp_deep_link(startapp="home"),
                }
            ]
        ]

    def _task_creation_result(
        self,
        *,
        task: object,
        title: str,
        assignees: list[User],
        deadline_at: datetime | None,
        user_input_message_ids: Sequence[str] = (),
    ) -> CommandExecutionResult:
        return CommandExecutionResult(
            response_text=self._format_task_creation_card(
                task=task,
                title=title,
                assignee_names=[self._user_display_name(user) for user in assignees],
                deadline_at=deadline_at,
            ),
            button_rows=self._open_task_button_rows(task),
            user_input_message_ids=tuple(user_input_message_ids),
        )

    def _with_wizard_edit(
        self,
        result: CommandExecutionResult,
        *,
        pending: object,
        cleanup_pending_action_id: UUID | None = None,
    ) -> CommandExecutionResult:
        return CommandExecutionResult(
            response_text=result.response_text,
            task_card=result.task_card,
            button_rows=result.button_rows,
            edit_message_id=getattr(pending, "picker_message_id", None),
            cleanup_pending_action_id=cleanup_pending_action_id,
            user_input_message_ids=result.user_input_message_ids,
        )

    def _task_wizard_validation_error_result(
        self,
        *,
        pending: object,
        event: NormalizedBotEvent,
        response_text: str,
        error_type: str,
    ) -> CommandExecutionResult:
        user_input_message_ids = tuple(self._user_input_message_ids_from_event(event))
        logger.info(
            "Task wizard validation error",
            extra={
                "error_type": error_type,
                "cleanup_attempted": bool(self.task_wizard_delete_user_inputs and user_input_message_ids),
                "input_message_id_present": bool(user_input_message_ids),
            },
        )
        return CommandExecutionResult(
            response_text=response_text,
            edit_message_id=getattr(pending, "picker_message_id", None),
            cleanup_pending_action_id=getattr(pending, "id", None),
            user_input_message_ids=user_input_message_ids,
            allow_send_fallback=False,
        )

    def _format_task_creation_card(
        self,
        *,
        task: object,
        title: str,
        assignee_names: list[str],
        deadline_at: datetime | None,
    ) -> str:
        assignee_label = "Исполнители" if len(assignee_names) > 1 else "Исполнитель"
        assignee_value = ", ".join(name for name in assignee_names if name) or "не указан"
        now = datetime.now(timezone.utc)
        lines = [
            f"Задача {self._task_ref_for_user(task)} создана ✅",
            "",
            f"Текст: {title}",
            f"{assignee_label}: {assignee_value}",
            f"Срок: {self._format_my_task_deadline(deadline_at, now)}",
        ]
        return "\n".join(lines)

    async def _lookup_task(
        self,
        event: NormalizedBotEvent,
        command: TaskLookupCommand,
    ) -> CommandExecutionResult:
        chat = await self._get_current_chat(event)
        user = await self._get_current_user(event)
        auth_context = await self._bot_auth_context(user=user, chat=chat)
        tasks = await self.task_service.list(
            filters=TaskListFilters(
                organization_id=chat.organization_id,
                task_number=command.task_number,
            ),
            limit=2,
            offset=0,
        )
        task = tasks[0] if tasks else None
        if task is None or not self.policy_service.can_view_task(auth_context, task):
            return CommandExecutionResult(
                response_text=f"Задача {command.task_ref} не найдена или у вас нет доступа."
            )

        now = datetime.now(timezone.utc)
        return CommandExecutionResult(
            response_text=self._format_task_lookup_response(task, now),
            button_rows=self._task_lookup_button_rows(task, auth_context=auth_context),
        )

    async def _submit_task_report(
        self,
        event: NormalizedBotEvent,
        command: TaskReportCommand,
    ) -> CommandExecutionResult:
        chat = await self._get_current_chat(event)
        user = await self._get_current_user(event)
        task = await self._get_reportable_task_by_number(
            chat=chat,
            user=user,
            task_number=command.task_number,
            task_ref=command.task_ref,
        )
        if command.text:
            await self.task_service.submit_response(
                task.id,
                TaskResponseCreate(
                    user_id=user.id,
                    text=command.text,
                    source_message_id=event.message_id,
                ),
            )
            return self._task_report_submitted_result(
                task,
                user_input_message_ids=self._user_input_message_ids_from_event(event),
            )

        return await self._create_pending_task_report(
            event=event,
            task=task,
            actor_user_id=user.id,
        )

    async def _ping_task(
        self,
        event: NormalizedBotEvent,
        command: PingTaskCommand,
    ) -> CommandExecutionResult:
        chat = await self._get_current_chat(event)
        user = await self._get_current_user(event)
        auth_context = await self._bot_auth_context(user=user, chat=chat)
        if not self._can_assign_task_to_others(auth_context):
            return CommandExecutionResult(response_text=PING_ADMIN_ONLY_TEXT)
        tasks = await self.task_service.list(
            filters=TaskListFilters(
                organization_id=chat.organization_id,
                task_number=command.task_number,
            ),
            limit=2,
            offset=0,
        )
        task = tasks[0] if tasks else None
        if task is None or not (
            self.policy_service.can_update_task(auth_context, task)
            or self._task_has_assignee(task, user.id)
        ):
            return CommandExecutionResult(
                response_text=f"Задача {command.task_ref} не найдена или у вас нет доступа."
            )
        if getattr(task, "status", None) in FINAL_TASK_STATUSES:
            return CommandExecutionResult(response_text=f"Задача {command.task_ref} уже завершена.")

        assignee_ids = self._active_task_assignee_ids(task)
        if not assignee_ids:
            return CommandExecutionResult(response_text="Не удалось отправить напоминание: исполнитель не назначен.")
        if user.id in assignee_ids:
            return await self._create_pending_task_report(
                event=event,
                task=task,
                actor_user_id=user.id,
            )

        if self.notification_delivery_service is None:
            raise BotCommandExecutionError("Отправка напоминаний не настроена.")

        source_chat_id = getattr(task, "chat_id", None)
        if not isinstance(source_chat_id, UUID):
            return CommandExecutionResult(
                response_text="Не удалось отправить напоминание: чат задачи недоступен для отправки."
            )
        result = await self.notification_delivery_service.send_chat_task_notification(
            chat_id=source_chat_id,
            task_id=task.id,
            message=self._format_task_ping_notification(task),
            reminder_type=TASK_PING_REMINDER_TYPE,
            attachments=self._task_ping_attachments(task),
            purpose=OutboundPurpose.PING,
            dedup_since=datetime.now(timezone.utc) - timedelta(minutes=30),
        )

        return CommandExecutionResult(
            response_text=self._format_task_ping_result(command.task_ref, result),
        )

    def _active_task_assignee_ids(self, task: object) -> list[UUID]:
        assignee_ids: list[UUID] = []
        seen: set[UUID] = set()
        for assignee in getattr(task, "assignees", []):
            user_id = getattr(assignee, "user_id", None)
            if not isinstance(user_id, UUID):
                continue
            status = str(getattr(assignee, "status", "") or "")
            if status in ACTIVE_ASSIGNEE_EXCLUDED_STATUSES:
                continue
            if user_id in seen:
                continue
            seen.add(user_id)
            assignee_ids.append(user_id)
        return assignee_ids

    def _format_task_ping_notification(self, task: object) -> str:
        now = datetime.now(timezone.utc)
        lines = [
            f"По задаче {self._task_ref(task)} требуется отчет.",
            "",
            f"{self._format_task_ping_assignee_mentions(task)}, нужен отчет.",
        ]
        deadline_at = getattr(task, "deadline_at", None)
        if deadline_at is not None:
            lines.append(f"Срок: {self._format_my_task_deadline(deadline_at, now)}")
        return "\n".join(lines)

    def _format_task_ping_assignee_mentions(self, task: object) -> str:
        mentions: list[str] = []
        for assignee in getattr(task, "assignees", []):
            user = getattr(assignee, "user", None)
            if user is None:
                continue
            display_name = self._user_display_name(user)
            max_user_id = getattr(user, "max_user_id", None)
            if isinstance(max_user_id, str) and max_user_id.strip():
                mentions.append(f"[@{display_name}](max://user/{max_user_id.strip()})")
            else:
                mentions.append(f"@{display_name}")
        return ", ".join(mentions) if mentions else "@исполнитель"

    def _task_ping_attachments(self, task: object) -> list[dict[str, Any]]:
        return [
            {
                "type": "inline_keyboard",
                "payload": {"buttons": self._task_ping_button_rows(task)},
            }
        ]

    def _task_ping_button_rows(self, task: object) -> list[list[dict[str, Any]]]:
        task_number = getattr(task, "task_number", None)
        startapp = f"task_{task_number}" if task_number is not None else "my_tasks"
        return [
            [
                {
                    "type": "link",
                    "text": "Открыть задачу",
                    "url": self._webapp_deep_link(startapp=startapp, fallback_path="tasks"),
                }
            ],
        ]

    def _format_task_ping_result(self, task_ref: str, result: NotificationDeliveryResult) -> str:
        if self._delivery_status_value(result) == DeliveryStatus.SENT.value:
            return f"Напоминание по задаче {task_ref} отправлено в чат задачи."
        if self._ping_result_is_background_disabled(result):
            return "Фоновые уведомления сейчас отключены. Напоминание в чат задачи не отправлено."
        if self._ping_result_is_missing_max_chat(result):
            return "Не удалось отправить напоминание: чат задачи недоступен для отправки."
        if self._ping_result_is_cooldown(result):
            return "Напоминание уже отправлялось недавно. Попробуйте позже."
        return "Не удалось отправить напоминание. Попробуйте позже."

    def _ping_result_is_background_disabled(self, result: NotificationDeliveryResult) -> bool:
        return self._delivery_error_code(result) in {BACKGROUND_DISABLED_ERROR, "sender_disabled"}

    def _ping_result_is_missing_max_chat(self, result: NotificationDeliveryResult) -> bool:
        return self._delivery_error_code(result) == MISSING_MAX_CHAT_ID_ERROR

    def _ping_result_is_cooldown(self, result: NotificationDeliveryResult) -> bool:
        if self._delivery_status_value(result) != DeliveryStatus.SKIPPED.value:
            return False
        if self._ping_result_is_background_disabled(result):
            return False
        if self._ping_result_is_missing_max_chat(result):
            return False
        return True

    def _delivery_status_value(self, result: NotificationDeliveryResult) -> str:
        status = getattr(result, "status", None)
        return str(getattr(status, "value", status))

    def _delivery_error_code(self, result: NotificationDeliveryResult) -> str | None:
        primary_delivery = getattr(result, "primary_delivery", None)
        error_code = getattr(primary_delivery, "error_code", None)
        return error_code if isinstance(error_code, str) else None

    async def _complete_pending_report(self, event: NormalizedBotEvent) -> CommandExecutionResult | None:
        if self.pending_action_repository is None:
            return None
        get_latest_pending = getattr(
            self.pending_action_repository,
            "get_latest_pending_task_report_submit",
            None,
        )
        if get_latest_pending is None:
            return None

        chat = await self._get_current_chat(event)
        user = await self._get_current_user(event)
        pending = await get_latest_pending(actor_user_id=user.id, chat_id=chat.id)
        if pending is None:
            return None
        if getattr(pending, "status", None) != PENDING_ACTION_PENDING:
            return None

        task_id = self._pending_report_task_id(pending)
        task_ref = self._pending_report_task_ref(pending)
        wizard_message_id = getattr(pending, "picker_message_id", None)
        now = datetime.now(timezone.utc)
        if pending.expires_at <= now:
            await self.pending_action_repository.mark_expired(pending)
            return CommandExecutionResult(
                response_text=(
                    f"/отчет {task_ref}\n\n"
                    f"Время отправки отчета истекло. Используйте /отчет {task_ref} еще раз."
                ),
                edit_message_id=wizard_message_id,
                cleanup_pending_action_id=getattr(pending, "id", None),
                user_input_message_ids=self._user_input_message_ids_from_event(event),
                allow_send_fallback=wizard_message_id is None,
            )

        report_text = event.text.strip()
        if not report_text:
            return CommandExecutionResult(
                response_text=self._report_wizard_empty_text(task_ref),
                edit_message_id=wizard_message_id,
                cleanup_pending_action_id=getattr(pending, "id", None),
                user_input_message_ids=self._user_input_message_ids_from_event(event),
                allow_send_fallback=False,
            )

        task = await self.task_service.get(task_id)
        if getattr(task, "status", None) in FINAL_TASK_STATUSES:
            mark_cancelled = getattr(self.pending_action_repository, "mark_cancelled", None)
            if mark_cancelled is not None:
                await mark_cancelled(pending)
            return CommandExecutionResult(
                response_text=f"/отчет {task_ref}\n\nЗадача {task_ref} уже завершена. Отчет больше не требуется.",
                edit_message_id=wizard_message_id,
                cleanup_pending_action_id=getattr(pending, "id", None),
                user_input_message_ids=self._user_input_message_ids_from_event(event),
                allow_send_fallback=wizard_message_id is None,
            )
        auth_context = await self._bot_auth_context(user=user, chat=chat)
        if not self.policy_service.can_submit_response(auth_context, task):
            mark_cancelled = getattr(self.pending_action_repository, "mark_cancelled", None)
            if mark_cancelled is not None:
                await mark_cancelled(pending)
            return CommandExecutionResult(
                response_text=(
                    f"/отчет {task_ref}\n\n"
                    "Не удалось отправить отчет. Проверьте, что задача существует и вы являетесь исполнителем."
                ),
                edit_message_id=wizard_message_id,
                cleanup_pending_action_id=getattr(pending, "id", None),
                user_input_message_ids=self._user_input_message_ids_from_event(event),
                allow_send_fallback=wizard_message_id is None,
            )

        reply_context = self._task_wizard_context(event, existing=getattr(pending, "reply_context", None))
        await self.task_service.submit_response(
            task.id,
            TaskResponseCreate(
                user_id=user.id,
                text=report_text,
                source_message_id=event.message_id,
            ),
        )
        mark_report_completed = getattr(self.pending_action_repository, "mark_report_completed", None)
        if mark_report_completed is not None:
            await mark_report_completed(pending, task_id=task.id)
        return self._task_report_submitted_result(
            task,
            edit_message_id=wizard_message_id,
            cleanup_pending_action_id=getattr(pending, "id", None),
            user_input_message_ids=self._user_input_message_ids_from_context(reply_context),
        )

    async def _complete_pending_acceptance_reject_reason(
        self,
        event: NormalizedBotEvent,
    ) -> CommandExecutionResult | None:
        if self.pending_action_repository is None:
            return None
        get_latest_pending = getattr(
            self.pending_action_repository,
            "get_latest_pending_task_acceptance_reject_reason",
            None,
        )
        if get_latest_pending is None:
            return None

        chat = await self._get_current_chat(event)
        user = await self._get_current_user(event)
        pending = await get_latest_pending(actor_user_id=user.id, chat_id=chat.id)
        if pending is None:
            return None
        if getattr(pending, "status", None) != PENDING_ACTION_PENDING:
            return None
        if getattr(pending, "action_type", None) != PENDING_ACTION_TASK_ACCEPTANCE_REJECT_REASON:
            return None

        task_ref = self._pending_report_task_ref(pending)
        now = datetime.now(timezone.utc)
        if pending.expires_at <= now:
            await self.pending_action_repository.mark_expired(pending)
            return CommandExecutionResult(
                response_text=(
                    f"Время отклонения приемки истекло. Откройте задачу {task_ref} "
                    "и нажмите «Отклонить» еще раз."
                )
            )

        reason = event.text.strip()
        if not reason:
            return CommandExecutionResult(
                response_text=f"Напишите непустую причину отклонения приемки по задаче {task_ref} одним сообщением."
            )

        task_id = self._pending_report_task_id(pending)
        response_id = self._pending_acceptance_reject_response_id(pending)
        task = await self.task_service.get(task_id)
        response = self._find_task_response(task, response_id)
        if response is None:
            return CommandExecutionResult(response_text=f"Ответ по задаче {task_ref} уже недоступен.")

        auth_context = await self._bot_auth_context(user=user, chat=chat)
        await self.task_service.reject_response(
            task.id,
            response_id,
            TaskAcceptanceCreate(
                accepted_by_user_id=user.id,
                comment=reason,
            ),
            auth_context=auth_context,
        )
        updated_task = await self.task_service.get(task.id)
        updated_response = self._find_task_response(updated_task, response_id) or response
        mark_completed = getattr(self.pending_action_repository, "mark_acceptance_reject_reason_completed", None)
        if mark_completed is not None:
            await mark_completed(pending, task_id=task.id)

        notification_outbound = await self._send_acceptance_rejection_notice(
            task=updated_task,
            response=updated_response,
            reason=reason,
        )
        if notification_outbound is not None and getattr(notification_outbound, "sent", False):
            return CommandExecutionResult(
                response_text=f"Приемка по задаче {self._task_ref(updated_task)} отклонена. Причина отправлена исполнителю."
            )
        return CommandExecutionResult(
            response_text=f"Приемка по задаче {self._task_ref(updated_task)} отклонена. Причина сохранена."
        )

    async def _get_reportable_task_by_number(
        self,
        *,
        chat: Chat,
        user: User,
        task_number: int,
        task_ref: str,
    ) -> Task:
        auth_context = await self._bot_auth_context(user=user, chat=chat)
        tasks = await self.task_service.list(
            filters=TaskListFilters(
                organization_id=chat.organization_id,
                task_number=task_number,
            ),
            limit=2,
            offset=0,
        )
        task = tasks[0] if tasks else None
        if task is None or not self.policy_service.can_submit_response(auth_context, task):
            raise BotCommandExecutionError(f"Задача {task_ref} не найдена или у вас нет доступа.")
        self._ensure_report_task_status(task, task_ref)
        return task

    def _ensure_report_task_status(self, task: object, task_ref: str) -> None:
        if getattr(task, "status", None) in FINAL_TASK_STATUSES:
            raise BotCommandExecutionError(f"Задача {task_ref} уже завершена.")

    async def _create_pending_task_report(
        self,
        *,
        event: NormalizedBotEvent,
        task: Task,
        actor_user_id: UUID,
    ) -> CommandExecutionResult:
        if self.pending_action_repository is None:
            raise BotCommandExecutionError("Pending report handler is not configured.")
        task_ref = self._task_ref(task)
        create_task_report_submit = getattr(self.pending_action_repository, "create_task_report_submit", None)
        if create_task_report_submit is None:
            raise BotCommandExecutionError("Pending report handler is not configured.")
        pending = await create_task_report_submit(
            actor_user_id=actor_user_id,
            chat_id=task.chat_id,
            task_id=task.id,
            task_ref=task_ref,
            title=task.title,
            source_message_id=event.message_id,
            reply_context=self._task_wizard_context(event),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        return CommandExecutionResult(
            response_text=self._report_wizard_prompt_text(task_ref),
            track_pending_action_id=getattr(pending, "id", None),
        )

    def _task_report_submitted_result(
        self,
        task: object,
        *,
        edit_message_id: str | None = None,
        cleanup_pending_action_id: UUID | None = None,
        user_input_message_ids: Sequence[str] = (),
    ) -> CommandExecutionResult:
        return CommandExecutionResult(
            response_text=self._report_wizard_final_text(self._task_ref(task)),
            button_rows=self._open_task_button_rows(task),
            edit_message_id=edit_message_id,
            cleanup_pending_action_id=cleanup_pending_action_id,
            user_input_message_ids=user_input_message_ids,
        )

    def _report_wizard_prompt_text(self, task_ref: str) -> str:
        return f"/отчет {task_ref}\n\nНапишите отчет по задаче {task_ref} одним сообщением."

    def _report_wizard_empty_text(self, task_ref: str) -> str:
        return f"/отчет {task_ref}\n\nОтчет не может быть пустым. Напишите отчет одним сообщением."

    def _report_wizard_final_text(self, task_ref: str) -> str:
        return f"Отчет по задаче {task_ref} отправлен ✅\n\nОтвет передан постановщику на приемку."

    def _open_task_button_rows(self, task: object) -> list[list[dict[str, Any]]]:
        task_number = getattr(task, "task_number", None)
        startapp = f"task_{task_number}" if task_number is not None else "my_tasks"
        return [
            [
                {
                    "type": "link",
                    "text": "Открыть задачу",
                    "url": self._webapp_deep_link(startapp=startapp, fallback_path="tasks"),
                }
            ]
        ]

    def _pending_report_task_id(self, pending: object) -> UUID:
        context = getattr(pending, "reply_context", None)
        task_id = context.get("task_id") if isinstance(context, dict) else None
        if not isinstance(task_id, str):
            raise BotCommandExecutionError("Pending report context is invalid.")
        return self._parse_uuid(task_id, "task_id")

    def _pending_report_task_ref(self, pending: object) -> str:
        context = getattr(pending, "reply_context", None)
        task_ref = context.get("task_ref") if isinstance(context, dict) else None
        return task_ref if isinstance(task_ref, str) and task_ref.strip() else "#?"

    def _pending_acceptance_reject_response_id(self, pending: object) -> UUID:
        context = getattr(pending, "reply_context", None)
        response_id = context.get("response_id") if isinstance(context, dict) else None
        if not isinstance(response_id, str):
            raise BotCommandExecutionError("Pending rejection context is invalid.")
        return self._parse_uuid(response_id, "response_id")

    def _find_task_response(self, task: object, response_id: UUID) -> object | None:
        return next(
            (
                response
                for response in getattr(task, "responses", [])
                if getattr(response, "id", None) == response_id
            ),
            None,
        )

    async def _send_acceptance_rejection_notice(
        self,
        *,
        task: object,
        response: object,
        reason: str,
    ) -> BotOutboundMessage | None:
        assignee = await self.user_repository.get(getattr(response, "user_id"))
        if assignee is None:
            return None
        message = self._format_acceptance_rejection_notice(task=task, reason=reason)
        button_rows = self._acceptance_rejection_button_rows(task)
        max_user_id = getattr(assignee, "max_user_id", None)
        if isinstance(max_user_id, str) and max_user_id.strip():
            return self.sender.send_inline_keyboard_message(
                chat_id=None,
                user_id=max_user_id.strip(),
                text=message,
                button_rows=button_rows,
                purpose=OutboundPurpose.INTERACTIVE,
            )

        chat = await self.chat_repository.get_chat(getattr(task, "chat_id"))
        max_chat_id = getattr(chat, "max_chat_id", None) if chat is not None else None
        if isinstance(max_chat_id, str) and max_chat_id.strip():
            return self.sender.send_inline_keyboard_message(
                chat_id=max_chat_id.strip(),
                user_id=None,
                text=message,
                button_rows=button_rows,
                purpose=OutboundPurpose.INTERACTIVE,
            )
        return None

    def _format_acceptance_rejection_notice(self, *, task: object, reason: str) -> str:
        truncated_reason = reason.strip()
        if len(truncated_reason) > 1000:
            truncated_reason = f"{truncated_reason[:1000].rstrip()}..."
        return "\n".join(
            [
                f"Приемка по задаче {self._task_ref(task)} отклонена ❌",
                "",
                f"Текст: {getattr(task, 'title', 'Задача')}",
                "Причина отклонения:",
                truncated_reason,
                "",
                "Пожалуйста, доработайте задачу и отправьте отчет повторно.",
            ]
        )

    def _acceptance_rejection_button_rows(self, task: object) -> list[list[dict[str, Any]]]:
        task_id = getattr(task, "id")
        return [
            [
                {
                    "type": "callback",
                    "text": "Написать отчет",
                    "payload": build_task_report_callback_payload(task_id),
                    "intent": "default",
                }
            ],
            *self._open_task_button_rows(task),
        ]

    def _format_task_lookup_response(self, task: Task, now: datetime) -> str:
        status_label = self._task_status_label(task, now)
        lines = [
            f"{self._task_ref(task)} · {status_label}",
            "",
            str(getattr(task, "title", "")),
        ]
        if self._latest_submitted_response(task) is not None:
            lines.extend(["", "Исполнитель отправил отчет."])
        lines.extend(
            [
                f"Срок: {self._format_my_task_deadline(getattr(task, 'deadline_at', None), now)}",
                f"Постановщик: {self._task_creator_display_name(task)}",
                f"Исполнитель: {self._task_assignee_display_names(task)}",
                f"Статус: {status_label}",
            ]
        )
        return "\n".join(lines)

    def _task_assignee_display_names(self, task: object) -> str:
        names: list[str] = []
        for assignee in getattr(task, "assignees", []):
            user = getattr(assignee, "user", None)
            if user is None:
                continue
            names.append(self._user_display_name(user))
        return ", ".join(names) if names else "не указан"

    def _task_lookup_button_rows(
        self,
        task: object,
        *,
        auth_context: AuthContext | None = None,
    ) -> list[list[dict[str, Any]]]:
        task_id = getattr(task, "id")
        task_number = getattr(task, "task_number", None)
        startapp = f"task_{task_number}" if task_number is not None else "my_tasks"
        open_button = {
            "type": "link",
            "text": "Открыть в WebApp",
            "url": self._webapp_deep_link(startapp=startapp, fallback_path="tasks"),
        }
        submitted_response = self._latest_submitted_response(task)
        if (
            auth_context is not None
            and submitted_response is not None
            and self._can_accept_for_summary(auth_context, task)
        ):
            response_id = getattr(submitted_response, "id")
            return [
                [
                    {
                        "type": "callback",
                        "text": "Принять",
                        "payload": build_callback_payload("accept", task_id, response_id=response_id),
                        "intent": "default",
                    },
                    {
                        "type": "callback",
                        "text": "Отклонить",
                        "payload": build_callback_payload("reject", task_id, response_id=response_id),
                        "intent": "default",
                    },
                ],
                [open_button],
            ]
        if auth_context is not None and not self._task_has_assignee(task, auth_context.user_id):
            return [[open_button]]
        return [
            [
                {
                    "type": "callback",
                    "text": "Написать отчет",
                    "payload": build_task_report_callback_payload(task_id),
                    "intent": "default",
                }
            ],
            [
                {
                    "type": "callback",
                    "text": "Отложить на 1 час",
                    "payload": f"task:snooze:1h:{task_id}",
                    "intent": "default",
                }
            ],
            [open_button],
        ]

    def _latest_submitted_response(self, task: object) -> object | None:
        submitted_responses = [
            response
            for response in getattr(task, "responses", [])
            if getattr(response, "status", None) == TaskResponseStatus.SUBMITTED.value
        ]
        if not submitted_responses:
            return None
        return max(
            submitted_responses,
            key=lambda response: self._aware_datetime(getattr(response, "created_at", None))
            or datetime.min.replace(tzinfo=timezone.utc),
        )

    def _task_status_label(self, task: object, now: datetime) -> str:
        deadline_at = self._aware_datetime(getattr(task, "deadline_at", None))
        status = str(getattr(task, "status", ""))
        if deadline_at is not None and deadline_at < now and status not in FINAL_TASK_STATUSES:
            return "Просрочена"
        return TASK_STATUS_LABELS.get(status, "В работе")

    def _format_my_task_deadline(self, deadline_at: datetime | None, now: datetime) -> str:
        zone = ZoneInfo(DEFAULT_TIMEZONE)
        value = self._aware_datetime(deadline_at)
        if value is None:
            return "не указан"
        local_value = value.astimezone(zone)
        local_now = self._aware_datetime(now).astimezone(zone) if now is not None else datetime.now(zone)
        if local_value.date() == local_now.date():
            return f"сегодня {local_value:%H:%M}"
        if local_value.date() == (local_now + timedelta(days=1)).date():
            return f"завтра {local_value:%H:%M}"
        if local_value.year == local_now.year:
            return f"{local_value:%d.%m %H:%M}"
        return f"{local_value:%d.%m.%Y %H:%M}"

    def _task_creator_display_name(self, task: object) -> str:
        creator = getattr(task, "created_by_user", None)
        display_name = getattr(creator, "display_name", None) if creator is not None else None
        return (
            display_name
            or getattr(task, "creator_display_name_snapshot", None)
            or "Не указан"
        )

    def _aware_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def _secretary_summary(self, event: NormalizedBotEvent) -> CommandExecutionResult:
        chat = await self._get_current_chat(event)
        user = await self._get_current_user(event)
        auth_context = await self._bot_auth_context(user=user, chat=chat)
        tasks = await self.task_service.list(
            filters=TaskListFilters(organization_id=chat.organization_id),
            limit=1000,
            offset=0,
        )
        accessible_tasks = [
            task
            for task in tasks
            if self.policy_service.can_view_task(auth_context, task)
            and task.status not in {TaskStatus.DONE.value, TaskStatus.CANCELLED.value}
        ]
        now = datetime.now(timezone.utc)
        current_chat_tasks = [task for task in accessible_tasks if task.chat_id == chat.id]
        overdue_tasks = [
            task
            for task in accessible_tasks
            if task.deadline_at is not None
            and task.deadline_at < now
            and task.status not in {TaskStatus.DONE.value, TaskStatus.CANCELLED.value}
        ]
        waiting_response_tasks = [
            task
            for task in accessible_tasks
            if self._task_has_assignee(task, user.id)
            and task.status
            in {
                TaskStatus.NEW.value,
                TaskStatus.IN_PROGRESS.value,
                TaskStatus.WAITING_RESPONSE.value,
                TaskStatus.OVERDUE.value,
                TaskStatus.REJECTED.value,
            }
        ]
        waiting_acceptance_tasks = [
            task
            for task in accessible_tasks
            if self._can_accept_for_summary(auth_context, task)
            and task.status == TaskStatus.WAITING_ACCEPTANCE.value
        ]

        if not accessible_tasks:
            response_text = (
                "Дьяк\n\n"
                "Активных задач пока нет.\n"
                "Создать задачу можно командой /задача в этом чате."
            )
        else:
            response_text = "\n".join(
                [
                    "Дьяк",
                    "",
                    f"Всего задач: {len(accessible_tasks)}",
                    f"В этом чате: {len(current_chat_tasks)}",
                    f"Просрочено: {len(overdue_tasks)}",
                    f"Ждут вашего ответа: {len(waiting_response_tasks)}",
                    f"Ждут приемки: {len(waiting_acceptance_tasks)}",
                ]
            )

        return CommandExecutionResult(
            response_text=response_text,
            button_rows=self._secretary_button_rows(),
        )

    async def _bot_auth_context(self, *, user: User, chat: Chat) -> AuthContext:
        member = await self.chat_repository.get_member(chat_id=chat.id, user_id=user.id)
        role = getattr(member, "role", None) if member is not None and getattr(member, "is_active", False) else None
        roles = [str(role)] if role else []
        return AuthContext(
            user_id=user.id,
            organization_id=chat.organization_id,
            chat_id=chat.id,
            roles=roles,
            is_super_admin=ROLE_SUPER_ADMIN in roles,
            max_user_id=getattr(user, "max_user_id", None),
        )

    def _secretary_button_rows(self) -> list[list[dict[str, Any]]]:
        return [
            [
                {
                    "type": "link",
                    "text": "Открыть Дьяк",
                    "url": self._webapp_deep_link(startapp="home"),
                }
            ],
        ]

    async def _slash_command_help(self, event: NormalizedBotEvent) -> CommandExecutionResult:
        response_text = SLASH_COMMAND_HELP_TEXT
        chat = await self._get_current_chat(event)
        status = str(getattr(chat, "status", "active") or "active")
        if status != ChatConnectionStatus.active.value:
            response_text = f"{response_text}\n\n{self._chat_connection_status_text(status)}"
        return CommandExecutionResult(
            response_text=response_text,
            button_rows=self._secretary_button_rows(),
        )

    def _chat_connection_status_text(self, status: str) -> str:
        if status == ChatConnectionStatus.pending_approval.value:
            return CHAT_PENDING_APPROVAL_TEXT
        if status == ChatConnectionStatus.rejected.value:
            return CHAT_REJECTED_TEXT
        if status == ChatConnectionStatus.suspended.value:
            return CHAT_SUSPENDED_TEXT
        return CHAT_UNAVAILABLE_TEXT

    def _can_accept_for_summary(self, auth_context: AuthContext, task: Task) -> bool:
        return self.policy_service.can_accept_task(auth_context, task)

    def _can_assign_task_to_others(self, auth_context: AuthContext) -> bool:
        return (
            auth_context.is_super_admin
            or auth_context.has_role(ROLE_SUPER_ADMIN)
            or auth_context.has_role(ROLE_CHAT_ADMIN)
        )

    def _task_has_assignee(self, task: Task, user_id: UUID) -> bool:
        return any(assignee.user_id == user_id for assignee in getattr(task, "assignees", []))

    async def _submit_response(
        self,
        event: NormalizedBotEvent,
        command: TaskResponseCommand | TaskDoneCommand,
    ) -> CommandExecutionResult:
        user = await self._get_current_user(event)
        task_id = self._parse_uuid(command.task_id, "task_id")
        response = await self.task_service.submit_response(
            task_id,
            TaskResponseCreate(
                user_id=user.id,
                text=command.text,
                source_message_id=event.message_id,
            ),
        )
        return CommandExecutionResult(response_text=f"Ответ сохранен: {response.id}")

    async def _accept_response(
        self,
        event: NormalizedBotEvent,
        command: AcceptTaskResponseCommand,
    ) -> CommandExecutionResult:
        user = await self._get_current_user(event)
        task_id = self._parse_uuid(command.task_id, "task_id")
        await self.task_service.accept_response(
            task_id,
            self._parse_uuid(command.response_id, "response_id"),
            TaskAcceptanceCreate(accepted_by_user_id=user.id),
        )
        task = await self.task_service.get(task_id)
        return CommandExecutionResult(response_text=f"Ответ по задаче {self._task_ref(task)} принят ✅")

    async def _reject_response(
        self,
        event: NormalizedBotEvent,
        command: RejectTaskResponseCommand,
    ) -> CommandExecutionResult:
        user = await self._get_current_user(event)
        task_id = self._parse_uuid(command.task_id, "task_id")
        await self.task_service.reject_response(
            task_id,
            self._parse_uuid(command.response_id, "response_id"),
            TaskAcceptanceCreate(accepted_by_user_id=user.id, comment=command.comment),
        )
        task = await self.task_service.get(task_id)
        return CommandExecutionResult(response_text=f"Ответ по задаче {self._task_ref(task)} отклонен.")

    async def _get_current_chat(self, event: NormalizedBotEvent) -> Chat:
        identity = await self._resolve_external_identity_if_needed(event)
        if identity is not None:
            return identity.chat
        chat_id = self._parse_internal_event_uuid(
            self._require_event_field(event.chat_id, "chat_id"),
            field_name="chat_id",
            external_id_note="TODO: add lookup or autocreate by max_chat_id.",
        )
        chat = await self.chat_repository.get_chat(chat_id)
        if chat is None:
            raise BotCommandExecutionError("Чат не найден. Передайте существующий внутренний Chat.id.")
        return chat

    async def _resolve_outbound_chat_id(self, event: NormalizedBotEvent) -> str | None:
        chat = await self._get_current_chat(event)
        max_chat_id = getattr(chat, "max_chat_id", None)
        if isinstance(max_chat_id, str) and max_chat_id.strip():
            return max_chat_id.strip()
        return event.chat_id

    async def _get_current_user(self, event: NormalizedBotEvent) -> User:
        identity = await self._resolve_external_identity_if_needed(event)
        if identity is not None:
            return identity.user
        user_id = self._parse_internal_event_uuid(
            self._require_event_field(event.user_id, "user_id"),
            field_name="user_id",
            external_id_note="TODO: add lookup or autocreate by max_user_id.",
        )
        user = await self.user_repository.get(user_id)
        if user is None:
            raise BotCommandExecutionError("Пользователь не найден. Передайте существующий внутренний User.id.")
        return user

    async def _resolve_external_identity_if_needed(
        self,
        event: NormalizedBotEvent,
    ) -> ResolvedMaxIdentity | None:
        if not self._event_uses_external_max_identity(event):
            return None
        if self.identity_resolver is None:
            raise BotCommandExecutionError(
                "MAX external user_id/chat_id не настроены для этого обработчика."
            )
        cache_key = (event.chat_id, event.user_id)
        if cache_key not in self._identity_cache:
            try:
                self._identity_cache[cache_key] = await self.identity_resolver.resolve_event(event)
            except MaxIdentityResolverError as exc:
                raise BotCommandExecutionError(str(exc)) from exc
        return self._identity_cache[cache_key]

    def _event_uses_external_max_identity(self, event: NormalizedBotEvent) -> bool:
        chat_id = self._require_event_field(event.chat_id, "chat_id")
        user_id = self._require_event_field(event.user_id, "user_id")
        return parse_internal_uuid(chat_id) is None or parse_internal_uuid(user_id) is None

    async def _resolve_users_by_display_name(self, display_names: list[str]) -> list[User]:
        users: list[User] = []
        for display_name in display_names:
            matches = await self.user_repository.find_by_display_name(display_name)
            if not matches:
                raise BotCommandExecutionError(f"Пользователь не найден по display_name: {display_name}")
            if len(matches) > 1:
                raise BotCommandExecutionError(
                    f"Найдено несколько пользователей с display_name: {display_name}. "
                    "Уточните пользователя до уникального имени."
                )
            users.append(matches[0])
        return users

    async def _resolve_assignee_mentions(self, mentions: list[str], chat: Chat) -> AssigneeMentionResolution:
        users: list[User] = []
        unresolved: list[str] = []
        ambiguous: list[str] = []
        for mention in mentions:
            matches = await self._find_chat_members_by_mention(mention, chat)
            if not matches:
                unresolved.append(mention)
                continue
            if len(matches) > 1:
                ambiguous.append(mention)
                continue
            users.append(matches[0])
        return AssigneeMentionResolution(
            users=self._deduplicate_users(users),
            unresolved=unresolved,
            ambiguous=ambiguous,
        )

    async def _resolve_normalized_mentions(
        self,
        mentions: list[NormalizedMention],
        chat: Chat,
    ) -> list[User]:
        users: list[User] = []
        for mention in mentions:
            user = await self._resolve_normalized_mention(mention, chat)
            if user is not None:
                users.append(user)
        return self._deduplicate_users(users)

    async def _resolve_normalized_assignment_mentions(
        self,
        *,
        mentions: list[NormalizedMention],
        chat: Chat,
        actor: User,
    ) -> NormalizedAssigneeMentionResolution:
        users: list[User] = []
        unresolved_count = 0
        for mention in mentions:
            if self._is_bot_mention(mention):
                users.append(actor)
                continue
            user = await self._resolve_normalized_mention(mention, chat)
            if user is None:
                unresolved_count += 1
                continue
            users.append(user)
        return NormalizedAssigneeMentionResolution(
            users=self._deduplicate_users(users),
            unresolved_count=unresolved_count,
        )

    async def _resolve_normalized_mention(self, mention: NormalizedMention, chat: Chat) -> User | None:
        if mention.external_user_id:
            user = await self.user_repository.get_by_max_user_id(mention.external_user_id)
            if user is None:
                user = await self.user_repository.create(
                    max_user_id=mention.external_user_id,
                    display_name=self._mention_display_name(mention),
                    username=mention.username,
                )
            await self._ensure_mention_chat_member(chat=chat, user=user)
            return user

        candidates = [
            value
            for value in (
                mention.username,
                mention.raw_text,
                mention.display_name,
            )
            if value and value.strip()
        ]
        for candidate in candidates:
            matches = await self._find_chat_members_by_mention(candidate, chat)
            if len(matches) == 1:
                return matches[0]
        return None

    def _is_bot_mention(self, mention: NormalizedMention) -> bool:
        bot_username = self._normalized_bot_username()
        for value in (mention.username, mention.raw_text, mention.display_name):
            normalized = self._normalize_mention_name(value)
            if bot_username and normalized == bot_username:
                return True
            if normalized in BOT_BRAND_MENTION_NAMES:
                return True
        return False

    def _normalized_bot_username(self) -> str:
        return self._normalize_mention_name(self.max_bot_username)

    @staticmethod
    def _normalize_mention_name(value: str | None) -> str:
        if not value:
            return ""
        return value.strip().lstrip("@").strip(" \t\r\n,.;:!?").casefold()

    async def _ensure_mention_chat_member(self, *, chat: Chat, user: User) -> None:
        member = await self.chat_repository.get_member(chat_id=chat.id, user_id=user.id)
        if member is None:
            await self.chat_repository.create_member(
                chat_id=chat.id,
                user_id=user.id,
                role=ROLE_MEMBER,
                is_active=True,
            )
            return
        if not getattr(member, "is_active", False):
            await self.chat_repository.update_member(member, values={"is_active": True})

    def _mention_display_name(self, mention: NormalizedMention) -> str:
        for value in (mention.display_name, mention.username, mention.raw_text):
            if value and value.strip():
                return value.strip().lstrip("@")
        return f"Пользователь #{self._short_display_id(mention.external_user_id)}"

    def _short_display_id(self, value: str | None) -> str:
        if not value:
            return "unknown"
        return value[-8:] if len(value) > 8 else value

    def _format_assignee_mention_failure(self, resolution: AssigneeMentionResolution) -> str:
        warnings = self._format_assignee_mention_warnings(resolution)
        if warnings:
            return "\n".join(warnings)
        return "Не удалось найти исполнителя."

    def _format_assignee_mention_warnings(self, resolution: AssigneeMentionResolution) -> list[str]:
        warnings: list[str] = []
        warnings.extend(
            f"Не удалось найти исполнителя @{mention}. Уточните исполнителя в WebApp."
            for mention in resolution.unresolved
        )
        warnings.extend(
            f"Нашлось несколько пользователей для @{mention}. Уточните исполнителя в WebApp."
            for mention in resolution.ambiguous
        )
        return warnings

    def _format_assignee_summary(self, assignees: list[User]) -> str | None:
        if not assignees:
            return None
        names = [self._user_display_name(user) for user in assignees]
        if len(names) == 1:
            return f"Исполнитель: {names[0]}."
        return f"Исполнители: {', '.join(names)}."

    def _user_display_name(self, user: User) -> str:
        display_name = getattr(user, "display_name", None)
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
        username = getattr(user, "username", None)
        if isinstance(username, str) and username.strip():
            return username.strip()
        return str(user.id)

    async def _find_chat_members_by_mention(self, mention: str, chat: Chat) -> list[User]:
        normalized_mention = mention.strip().removeprefix("@").lower()
        if not normalized_mention:
            return []
        members = await self.chat_repository.list_members(chat.id)
        matches: list[User] = []
        for member in members:
            if not getattr(member, "is_active", False):
                continue
            user = getattr(member, "user", None)
            if user is None:
                continue
            if self._user_matches_mention(user, normalized_mention):
                matches.append(user)
        return self._deduplicate_users(matches)

    def _user_matches_mention(self, user: User, normalized_mention: str) -> bool:
        return any(
            value.strip().lower() == normalized_mention
            for value in (
                getattr(user, "max_user_id", None),
                getattr(user, "username", None),
                getattr(user, "display_name", None),
            )
            if isinstance(value, str) and value.strip()
        )

    def _deduplicate_users(self, users: list[User]) -> list[User]:
        deduplicated: list[User] = []
        seen_user_ids: set[UUID] = set()
        for user in users:
            if user.id in seen_user_ids:
                continue
            seen_user_ids.add(user.id)
            deduplicated.append(user)
        return deduplicated

    async def _error_response(
        self,
        event: NormalizedBotEvent,
        command: Command,
        message: str,
    ) -> BotWebhookResponse:
        outbound = self.sender.send_message(await self._resolve_outbound_chat_id(event), message)
        return BotWebhookResponse(
            ok=False,
            is_command=True,
            action="error",
            command=command,
            response_text=message,
            error=message,
            outbound=outbound,
        )

    def _require_event_field(self, value: str | None, field_name: str) -> str:
        if not value:
            raise BotCommandExecutionError(f"Поле {field_name} обязательно для выполнения команды.")
        return value

    def _parse_internal_event_uuid(
        self,
        value: str,
        *,
        field_name: str,
        external_id_note: str,
    ) -> UUID:
        try:
            return UUID(value)
        except ValueError as exc:
            raise BotCommandExecutionError(
                f"Поле {field_name} должно содержать внутренний UUID на MVP. {external_id_note}"
            ) from exc

    def _parse_uuid(self, value: str, field_name: str) -> UUID:
        try:
            return UUID(value)
        except ValueError as exc:
            raise BotCommandExecutionError(f"Поле {field_name} должно быть UUID.") from exc

    def _format_tasks(self, title: str, tasks: list[Task]) -> str:
        if not tasks:
            return f"{title}: нет задач."
        lines = [f"{title}:"]
        for task in tasks[:20]:
            lines.append(f"- {self._task_ref(task)} {task.title} ({task.id}) [{task.status}]")
        if len(tasks) > 20:
            lines.append(f"...и еще {len(tasks) - 20}")
        return "\n".join(lines)

    def _build_source_description(self, event: NormalizedBotEvent, command: CreateTaskCommand) -> str | None:
        source_lines: list[str] = []
        if command.source_text and command.source_text != command.title:
            source_lines.append(f"Исходный текст: {command.source_text}")
        if event.reply_to_message_id:
            source_lines.append(f"Исходное сообщение MAX: {event.reply_to_message_id}")
        if event.reply_to_author_id:
            source_lines.append(f"Автор исходного сообщения MAX: {event.reply_to_author_id}")
        if event.message_id:
            source_lines.append(f"Команда MAX: {event.message_id}")
        if not source_lines:
            return None
        return "\n".join(source_lines)

    def _reply_context(self, event: NormalizedBotEvent) -> dict[str, str] | None:
        context = {
            key: value
            for key, value in {
                "reply_to_message_id": event.reply_to_message_id,
                "reply_to_author_id": event.reply_to_author_id,
                "reply_to_author_display_name": event.reply_to_author_display_name,
            }.items()
            if value
        }
        return context or None

    def _task_wizard_context(
        self,
        event: NormalizedBotEvent,
        *,
        existing: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        context: dict[str, Any] = dict(existing or self._reply_context(event) or {})
        message_ids = self._user_input_message_ids_from_context(context)
        message_ids.extend(self._user_input_message_ids_from_event(event))
        deduplicated = self._deduplicate_user_input_message_ids(message_ids)
        if deduplicated:
            context[TASK_WIZARD_USER_INPUT_MESSAGE_IDS_KEY] = deduplicated
        else:
            context.pop(TASK_WIZARD_USER_INPUT_MESSAGE_IDS_KEY, None)
        return context or None

    def _user_input_message_ids_from_event(self, event: NormalizedBotEvent) -> list[str]:
        message_id = (event.message_id or "").strip()
        if not message_id or message_id == event.reply_to_message_id:
            return []
        return [message_id]

    def _user_input_message_ids_from_context(self, context: Mapping[str, Any] | None) -> list[str]:
        if not context:
            return []
        raw_value = context.get(TASK_WIZARD_USER_INPUT_MESSAGE_IDS_KEY)
        if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
            return []
        return [str(item).strip() for item in raw_value if str(item).strip()]

    def _deduplicate_user_input_message_ids(self, message_ids: Sequence[str]) -> list[str]:
        deduplicated: list[str] = []
        seen: set[str] = set()
        for message_id in message_ids:
            normalized = str(message_id).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduplicated.append(normalized)
        return deduplicated

    def _should_assign_reply_task_to_requester(
        self,
        event: NormalizedBotEvent,
        command: CreateTaskCommand,
    ) -> bool:
        return bool(
            event.reply_to_text
            and not command.has_inline_args
            and not command.assignees
            and not command.assignee_mentions
        )

    def _task_card(self, task: Task) -> dict[str, object]:
        return {
            "id": str(task.id),
            "task_number": getattr(task, "task_number", None),
            "task_ref": self._task_ref(task),
            "title": task.title,
            "status": task.status,
            "status_label": self._task_status_label(task, datetime.now(timezone.utc)),
            "assignee_ids": [str(assignee.user_id) for assignee in task.assignees],
            "observer_ids": [str(observer.user_id) for observer in task.observers],
        }

    def _task_ref(self, task: object) -> str:
        task_number = getattr(task, "task_number", None)
        return f"#{task_number}" if task_number is not None else str(getattr(task, "id", ""))

    def _task_ref_for_user(self, task: object) -> str:
        task_number = getattr(task, "task_number", None)
        return f"#{task_number}" if task_number is not None else "#?"

    def _raise_unhandled_command(self, command: Command) -> NoReturn:
        raise BotCommandExecutionError(f"Команда пока не поддержана: {getattr(command, 'type', 'unknown')}")
