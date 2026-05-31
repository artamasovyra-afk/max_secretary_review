from __future__ import annotations

from datetime import date, datetime, timezone as datetime_timezone
import re
from typing import Callable

from app.modules.bot.schemas import (
    AcceptTaskResponseCommand,
    BotCommandResult,
    Command,
    CommandParseError,
    CreateTaskCommand,
    ListTasksCommand,
    MyTasksCommand,
    PingTaskCommand,
    RejectTaskResponseCommand,
    SecretaryCommand,
    SlashHelpCommand,
    TaskLookupCommand,
    TaskReportCommand,
    TaskDoneCommand,
    TaskResponseCommand,
    UnknownCommand,
)
from app.modules.tasks.deadline_parser import DEFAULT_TIMEZONE, parse_deadline
from app.modules.tasks.task_numbering import format_task_ref, normalize_task_ref

CREATE_TASK_HELP = (
    "Чтобы создать задачу:\n"
    "- напишите /задача и следуйте подсказкам;\n"
    "- или ответьте /задача на сообщение;\n"
    "- или напишите /задача текст задачи завтра до 18:00."
)
HELP_COMMAND_NAMES = frozenset({"помощь", "help", "команды"})
BARE_HELP_ALIASES = frozenset({"помощь", "help", "команды", "дьяк помощь", "дьяк help", "дьяк команды"})
MENTION_PATTERN = re.compile(r"^@(?P<name>[\w.-]{1,64})(?=$|[\s,])", flags=re.UNICODE)


class BotCommandParser:
    def __init__(
        self,
        now_provider: Callable[[], datetime] | None = None,
        bot_username: str = "",
    ) -> None:
        self._now_provider = now_provider or (lambda: datetime.now(datetime_timezone.utc))
        self.bot_username = self._normalize_bot_username(bot_username)

    def now(self) -> datetime:
        return self._now_provider()

    def is_command(self, text: str) -> bool:
        stripped_text = self._normalize_input_text(text)
        return (
            stripped_text.startswith("/")
            or self._parse_bare_task_ref(stripped_text) is not None
            or self._is_bare_help_alias(stripped_text)
        )

    def parse(
        self,
        text: str,
        *,
        source_text: str | None = None,
        now: datetime | None = None,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> Command:
        stripped_text = self._normalize_input_text(text)
        if not stripped_text:
            return CommandParseError(raw_text=text, message="Пустое сообщение не является командой.")
        bare_task_ref = self._parse_bare_task_ref(stripped_text)
        if bare_task_ref is not None:
            return self._task_lookup_command(text, bare_task_ref)
        if self._is_bare_help_alias(stripped_text):
            return SlashHelpCommand(raw_text=text)
        if not stripped_text.startswith("/"):
            return CommandParseError(raw_text=text, message="Команда должна начинаться с '/'.")

        command_token, _, args = stripped_text.partition(" ")
        command_name = self._normalize_command_name(command_token.removeprefix("/").split("@", 1)[0])
        args = args.strip()

        if not command_name:
            return SlashHelpCommand(raw_text=text)
        if command_name in HELP_COMMAND_NAMES:
            if args:
                return self._parse_error(text, f"Команда /{command_name} не принимает аргументы.")
            return SlashHelpCommand(raw_text=text)
        task_ref_number = normalize_task_ref(command_name)
        if task_ref_number is not None:
            if args:
                return self._parse_error(text, f"Команда {format_task_ref(task_ref_number)} не принимает аргументы.")
            return self._task_lookup_command(text, task_ref_number)

        if command_name == "задача":
            return self._parse_create_task(
                args,
                text,
                source_text=source_text,
                now=now or self._now_provider(),
                timezone=timezone,
            )
        if command_name == "мои":
            args_token, _, remaining_args = args.partition(" ")
            args_command = self._normalize_command_name(args_token.split("@", 1)[0])
            if args_command == "задачи":
                return self._parse_my_tasks(remaining_args.strip(), text)

        parser = self._command_parsers().get(command_name)
        if parser is None:
            return UnknownCommand(raw_text=text, name=command_name, args=args)

        return parser(args, text)

    def handle(self, text: str) -> BotCommandResult:
        command = self.parse(text)

        if isinstance(command, CommandParseError):
            return BotCommandResult(
                command=command,
                handled=False,
                response_text=f"Ошибка формата команды: {command.message}",
            )
        if isinstance(command, UnknownCommand):
            return BotCommandResult(
                command=command,
                handled=False,
                response_text=f"Неизвестная команда: /{command.name}",
            )

        return BotCommandResult(
            command=command,
            handled=True,
            response_text=self._known_command_response(command),
        )

    def _command_parsers(self) -> dict[str, Callable[[str, str], Command]]:
        return {
            "дьяк": self._parse_secretary,
            "секретарь": self._parse_secretary,
            "задача": self._parse_create_task,
            "задачи": self._parse_list_tasks,
            "мои_задачи": self._parse_my_tasks,
            "ответ": self._parse_task_response,
            "отчет": self._parse_task_report,
            "пинг": self._parse_task_ping,
            "готово": self._parse_task_done,
            "принять": self._parse_accept_response,
            "отклонить": self._parse_reject_response,
        }

    def _parse_create_task(
        self,
        args: str,
        raw_text: str,
        *,
        source_text: str | None,
        now: datetime,
        timezone: str,
    ) -> Command:
        parts = [part.strip() for part in args.split("|")]
        if len(parts) not in {3, 4}:
            return self._parse_create_task_from_text(
                args=args,
                raw_text=raw_text,
                source_text=source_text,
                now=now,
                timezone=timezone,
            )

        title, assignees_text, deadline_text = parts[:3]
        if not title:
            return self._parse_error(raw_text, "Не указан текст задачи.\n" + CREATE_TASK_HELP)

        assignees = self._parse_names_list(assignees_text)
        if not assignees:
            return self._parse_error(raw_text, "Не указаны исполнители.\n" + CREATE_TASK_HELP)

        try:
            deadline = date.fromisoformat(deadline_text)
        except ValueError:
            return self._parse_error(raw_text, "Срок должен быть датой в формате YYYY-MM-DD.")

        observers: list[str] = []
        if len(parts) == 4:
            observer_part = parts[3]
            prefix, separator, observers_text = observer_part.partition(":")
            if separator != ":" or prefix.strip().lower() != "наблюдатели":
                return self._parse_error(
                    raw_text,
                    "Дополнительный блок команды не распознан.",
                )
            observers = self._parse_names_list(observers_text)
            if not observers:
                return self._parse_error(raw_text, "Список дополнительных участников пуст.")

        return CreateTaskCommand(
            raw_text=raw_text,
            title=title,
            source_text=title,
            has_inline_args=bool(args.strip()),
            deadline_raw=deadline_text,
            deadline_confidence=1.0,
            needs_deadline_clarification=False,
            assignees=assignees,
            assignee_mentions=[],
            deadline=deadline,
            observers=observers,
        )

    def _parse_create_task_from_text(
        self,
        *,
        args: str,
        raw_text: str,
        source_text: str | None,
        now: datetime,
        timezone: str,
    ) -> Command:
        assignee_mentions, remaining_args = self._extract_leading_mentions(args)
        inline_args = remaining_args.strip()
        reply_source_text = (source_text or "").strip()
        task_source_text = reply_source_text or inline_args
        if not task_source_text:
            return CreateTaskCommand(
                raw_text=raw_text,
                title="",
                source_text="",
                needs_text_clarification=True,
                has_inline_args=False,
                deadline_raw=None,
                deadline_confidence=0.0,
                needs_deadline_clarification=False,
                assignees=[],
                assignee_mentions=[],
                deadline=None,
                observers=[],
            )

        source_deadline = parse_deadline(task_source_text, now, timezone)
        if reply_source_text and inline_args:
            inline_deadline = parse_deadline(inline_args, now, timezone)
            deadline = inline_deadline if inline_deadline.deadline_at is not None else source_deadline
        else:
            deadline = source_deadline
        title = self._strip_deadline_from_title(task_source_text, source_deadline.raw_text)
        if not title:
            return self._parse_error(raw_text, "Не указан текст задачи.\n" + CREATE_TASK_HELP)

        return CreateTaskCommand(
            raw_text=raw_text,
            title=title,
            source_text=task_source_text,
            has_inline_args=bool(args.strip()),
            deadline_at=deadline.deadline_at,
            deadline_raw=deadline.raw_text,
            deadline_confidence=deadline.confidence,
            needs_deadline_clarification=deadline.needs_clarification,
            assignees=[],
            assignee_mentions=assignee_mentions,
            deadline=None,
            observers=[],
        )

    def _parse_list_tasks(self, args: str, raw_text: str) -> Command:
        if args:
            return self._parse_error(raw_text, "Команда /задачи не принимает аргументы.")
        return ListTasksCommand(raw_text=raw_text)

    def _parse_my_tasks(self, args: str, raw_text: str) -> Command:
        if args:
            return self._parse_error(raw_text, "Команда /мои_задачи не принимает аргументы.")
        return MyTasksCommand(raw_text=raw_text)

    def _parse_task_response(self, args: str, raw_text: str) -> Command:
        parts = args.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            return self._parse_error(raw_text, "Формат: /ответ <task_id> <текст ответа>.")
        return TaskResponseCommand(raw_text=raw_text, task_id=parts[0], text=parts[1].strip())

    def _parse_task_report(self, args: str, raw_text: str) -> Command:
        parts = args.split(maxsplit=1)
        if not parts:
            return self._parse_report_error(raw_text)
        task_number = normalize_task_ref(parts[0])
        if task_number is None:
            return self._parse_report_error(raw_text)
        report_text = parts[1].strip() if len(parts) > 1 else None
        return TaskReportCommand(
            raw_text=raw_text,
            task_number=task_number,
            task_ref=format_task_ref(task_number),
            text=report_text or None,
        )

    def _parse_task_ping(self, args: str, raw_text: str) -> Command:
        parts = args.split(maxsplit=1)
        if not parts:
            return self._parse_ping_error(raw_text)
        task_number = normalize_task_ref(parts[0])
        if task_number is None or len(parts) > 1:
            return self._parse_ping_error(raw_text)
        return PingTaskCommand(
            raw_text=raw_text,
            task_number=task_number,
            task_ref=format_task_ref(task_number),
        )

    def _parse_task_done(self, args: str, raw_text: str) -> Command:
        parts = args.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            return self._parse_error(raw_text, "Формат: /готово <task_id> <текст ответа>.")
        return TaskDoneCommand(raw_text=raw_text, task_id=parts[0], text=parts[1].strip())

    def _parse_accept_response(self, args: str, raw_text: str) -> Command:
        parts = args.split()
        if len(parts) != 2:
            return self._parse_error(raw_text, "Формат: /принять <task_id> <response_id>.")
        return AcceptTaskResponseCommand(raw_text=raw_text, task_id=parts[0], response_id=parts[1])

    def _parse_reject_response(self, args: str, raw_text: str) -> Command:
        parts = args.split(maxsplit=2)
        if len(parts) != 3 or not parts[2].strip():
            return self._parse_error(raw_text, "Формат: /отклонить <task_id> <response_id> <комментарий>.")
        return RejectTaskResponseCommand(
            raw_text=raw_text,
            task_id=parts[0],
            response_id=parts[1],
            comment=parts[2].strip(),
        )

    def _known_command_response(self, command: Command) -> str:
        command_type = getattr(command, "type", "")
        responses = {
            "create_task": "Команда распознана: создание задачи.",
            "list_tasks": "Команда распознана: список задач.",
            "my_tasks": "Команда распознана: мои задачи.",
            "task_lookup": "Команда распознана: карточка задачи.",
            "secretary": "Команда распознана: дьяк.",
            "slash_help": "Команда распознана: справка по командам.",
            "task_report": "Команда распознана: отчет по задаче.",
            "ping_task": "Команда распознана: напоминание по задаче.",
            "task_response": "Команда распознана: ответ исполнителя.",
            "task_done": "Команда распознана: результат готов.",
            "accept_response": "Команда распознана: принять результат.",
            "reject_response": "Команда распознана: отклонить результат.",
        }
        return responses.get(command_type, "Команда распознана.")

    def _parse_secretary(self, args: str, raw_text: str) -> Command:
        normalized_args = self._normalize_command_name(args.strip())
        if not normalized_args:
            return SecretaryCommand(raw_text=raw_text)
        if normalized_args in HELP_COMMAND_NAMES:
            return SlashHelpCommand(raw_text=raw_text)
        return self._parse_error(raw_text, "Команда /дьяк не принимает аргументы.")

    def _normalize_input_text(self, text: str) -> str:
        stripped_text = text.strip()
        mention_command = self._strip_bot_mention_prefix(stripped_text)
        return mention_command if mention_command is not None else stripped_text

    def _strip_bot_mention_prefix(self, stripped_text: str) -> str | None:
        if not self.bot_username:
            return None
        slash_mention = stripped_text.startswith("/@")
        plain_mention = stripped_text.startswith("@")
        if not slash_mention and not plain_mention:
            return None

        token, _, remaining = stripped_text.partition(" ")
        mention_name = token[2:] if slash_mention else token[1:]
        if self._normalize_bot_username(mention_name) != self.bot_username:
            return None

        command_text = remaining.strip()
        if not command_text:
            return "/"
        if command_text.startswith("/") or self._parse_bare_task_ref(command_text) is not None:
            return command_text
        return f"/{command_text}"

    def _normalize_command_name(self, value: str) -> str:
        return " ".join(value.strip().casefold().replace("ё", "е").split())

    def _is_bare_help_alias(self, stripped_text: str) -> bool:
        return self._normalize_command_name(stripped_text) in BARE_HELP_ALIASES

    def _normalize_bot_username(self, value: str) -> str:
        return value.strip().removeprefix("@").casefold()

    def _parse_bare_task_ref(self, stripped_text: str) -> int | None:
        if not stripped_text or " " in stripped_text:
            return None
        if not (stripped_text.startswith("#") or stripped_text.lower().startswith("t-")):
            return None
        return normalize_task_ref(stripped_text)

    def _task_lookup_command(self, raw_text: str, task_number: int) -> TaskLookupCommand:
        return TaskLookupCommand(
            raw_text=raw_text,
            task_number=task_number,
            task_ref=format_task_ref(task_number),
        )

    def _parse_report_error(self, raw_text: str) -> CommandParseError:
        return self._parse_error(
            raw_text,
            "Укажите номер задачи, например:\n/отчет #1042 сделал, доступы проверены",
        )

    def _parse_ping_error(self, raw_text: str) -> CommandParseError:
        return self._parse_error(
            raw_text,
            "Укажите номер задачи, например:\n/пинг #1042",
        )

    def _parse_names_list(self, value: str) -> list[str]:
        return [name.strip() for name in value.split(",") if name.strip()]

    def _extract_leading_mentions(self, value: str) -> tuple[list[str], str]:
        mentions: list[str] = []
        remaining = value.strip()
        while remaining:
            match = MENTION_PATTERN.match(remaining)
            if match is None:
                break
            mentions.append(match.group("name"))
            remaining = remaining[match.end():].lstrip()
            if remaining.startswith(","):
                remaining = remaining[1:].lstrip()
        return mentions, remaining

    def _strip_deadline_from_title(self, value: str, deadline_raw: str | None) -> str:
        if not deadline_raw:
            return value.strip()
        title = re.sub(re.escape(deadline_raw), " ", value, count=1, flags=re.IGNORECASE)
        return " ".join(title.split())

    def _parse_error(self, raw_text: str, message: str) -> CommandParseError:
        return CommandParseError(raw_text=raw_text, message=message)
