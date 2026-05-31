from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.modules.bot.command_parser import BotCommandParser
from app.modules.bot.schemas import (
    AcceptTaskResponseCommand,
    CommandParseError,
    CreateTaskCommand,
    ListTasksCommand,
    MyTasksCommand,
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


def test_parse_create_task_command_without_observers() -> None:
    command = BotCommandParser().parse("/задача Подготовить отчет | Иван | 2026-05-20")

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "Подготовить отчет"
    assert command.source_text == "Подготовить отчет"
    assert command.assignees == ["Иван"]
    assert command.deadline == date(2026, 5, 20)
    assert command.deadline_raw == "2026-05-20"
    assert command.deadline_confidence == 1.0
    assert command.needs_deadline_clarification is False
    assert command.observers == []


def test_parse_create_task_command_with_multiple_assignees_and_observers() -> None:
    command = BotCommandParser().parse(
        "/задача Подготовить отчет | Иван, Мария | 2026-05-20 | наблюдатели: Сергей, Анна"
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "Подготовить отчет"
    assert command.source_text == "Подготовить отчет"
    assert command.assignees == ["Иван", "Мария"]
    assert command.deadline == date(2026, 5, 20)
    assert command.observers == ["Сергей", "Анна"]


def test_parse_create_task_command_from_free_text_with_weekday_deadline() -> None:
    command = BotCommandParser().parse(
        "/задача Подготовить отчет до пятницы",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "Подготовить отчет"
    assert command.source_text == "Подготовить отчет до пятницы"
    assert command.deadline_at == datetime(2026, 5, 22, 18, 0, tzinfo=ZoneInfo("UTC"))
    assert command.deadline_raw == "до пятницы"
    assert command.deadline_confidence > 0
    assert command.needs_deadline_clarification is False
    assert command.assignees == []
    assert command.assignee_mentions == []
    assert command.deadline is None


def test_parse_create_task_command_from_free_text_with_leading_mention() -> None:
    command = BotCommandParser().parse(
        "/задача @ivan подготовь отчет до пятницы",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "подготовь отчет"
    assert command.source_text == "подготовь отчет до пятницы"
    assert command.assignee_mentions == ["ivan"]
    assert command.assignees == []
    assert command.deadline_at == datetime(2026, 5, 22, 18, 0, tzinfo=ZoneInfo("UTC"))


def test_parse_create_task_command_from_free_text_with_multiple_mentions() -> None:
    command = BotCommandParser().parse(
        "/задача @ivan @maria подготовить материалы до пятницы",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "подготовить материалы"
    assert command.source_text == "подготовить материалы до пятницы"
    assert command.assignee_mentions == ["ivan", "maria"]
    assert command.deadline_at == datetime(2026, 5, 22, 18, 0, tzinfo=ZoneInfo("UTC"))


def test_parse_create_task_command_only_extracts_leading_mentions() -> None:
    command = BotCommandParser().parse(
        "/задача @ivan подготовить @отчет до пятницы",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "подготовить @отчет"
    assert command.source_text == "подготовить @отчет до пятницы"
    assert command.assignee_mentions == ["ivan"]
    assert command.deadline_at == datetime(2026, 5, 22, 18, 0, tzinfo=ZoneInfo("UTC"))


def test_parse_create_task_command_from_free_text_with_tomorrow_time() -> None:
    command = BotCommandParser().parse(
        "/задача Проверить доступ завтра в 15:00",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "Проверить доступ"
    assert command.source_text == "Проверить доступ завтра в 15:00"
    assert command.deadline_at == datetime(2026, 5, 21, 15, 0, tzinfo=ZoneInfo("UTC"))
    assert command.deadline_raw == "завтра в 15:00"
    assert command.needs_deadline_clarification is False


def test_parse_create_task_command_from_free_text_with_bare_tomorrow_time() -> None:
    command = BotCommandParser().parse(
        "/задача Проверить доступ завтра 15:00",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "Проверить доступ"
    assert command.source_text == "Проверить доступ завтра 15:00"
    assert command.deadline_at == datetime(2026, 5, 21, 15, 0, tzinfo=ZoneInfo("UTC"))
    assert command.deadline_raw == "завтра 15:00"


def test_parse_create_task_command_from_reply_source_text() -> None:
    command = BotCommandParser().parse(
        "/задача",
        source_text="Иван, подготовь отчет до пятницы",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "Иван, подготовь отчет"
    assert command.source_text == "Иван, подготовь отчет до пятницы"
    assert command.deadline_at == datetime(2026, 5, 22, 18, 0, tzinfo=ZoneInfo("UTC"))
    assert command.deadline_raw == "до пятницы"
    assert command.needs_deadline_clarification is False


def test_parse_create_task_command_from_reply_source_text_with_mention() -> None:
    command = BotCommandParser().parse(
        "/задача @ivan",
        source_text="Проверить доступ завтра в 15:00",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "Проверить доступ"
    assert command.source_text == "Проверить доступ завтра в 15:00"
    assert command.assignee_mentions == ["ivan"]
    assert command.deadline_at == datetime(2026, 5, 21, 15, 0, tzinfo=ZoneInfo("UTC"))


def test_parse_create_task_command_reply_source_text_takes_priority_over_inline_params() -> None:
    command = BotCommandParser().parse(
        "/задача @ivan подготовь отчет до пятницы",
        source_text="Проверить доступ завтра в 15:00",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "Проверить доступ"
    assert command.source_text == "Проверить доступ завтра в 15:00"
    assert command.assignee_mentions == ["ivan"]
    assert command.deadline_at == datetime(2026, 5, 22, 18, 0, tzinfo=ZoneInfo("UTC"))
    assert command.has_inline_args is True


def test_parse_create_task_command_reply_inline_deadline_uses_reply_source_text() -> None:
    command = BotCommandParser().parse(
        "/задача завтра 15:00",
        source_text="Отпуск2",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "Отпуск2"
    assert command.source_text == "Отпуск2"
    assert command.deadline_at == datetime(2026, 5, 21, 15, 0, tzinfo=ZoneInfo("UTC"))
    assert command.deadline_raw == "завтра 15:00"
    assert command.has_inline_args is True


def test_parse_create_task_command_rejects_non_reply_deadline_without_title() -> None:
    command = BotCommandParser().parse(
        "/задача завтра 15:00",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CommandParseError)
    assert "Не указан текст задачи" in command.message
    assert "наблюдатели" not in command.message


def test_parse_create_task_command_returns_clarification_when_deadline_is_unknown() -> None:
    command = BotCommandParser().parse(
        "/задача Подготовить отчет",
        now=datetime(2026, 5, 20, 10, 0, tzinfo=ZoneInfo("UTC")),
        timezone="UTC",
    )

    assert isinstance(command, CreateTaskCommand)
    assert command.title == "Подготовить отчет"
    assert command.source_text == "Подготовить отчет"
    assert command.deadline_at is None
    assert command.deadline_raw is None
    assert command.deadline_confidence == 0
    assert command.needs_deadline_clarification is True


def test_parse_list_tasks_command_with_bot_mention() -> None:
    command = BotCommandParser().parse("/задачи@max_secretary_bot")

    assert isinstance(command, ListTasksCommand)


def test_parse_my_tasks_command() -> None:
    command = BotCommandParser().parse("/мои_задачи")

    assert isinstance(command, MyTasksCommand)


def test_parse_spaced_my_tasks_command_alias() -> None:
    command = BotCommandParser().parse("/мои задачи")

    assert isinstance(command, MyTasksCommand)


def test_parse_my_tasks_command_alias_with_bot_mention() -> None:
    underscored = BotCommandParser().parse("/мои_задачи@secretary_oren_bot")
    spaced = BotCommandParser().parse("/мои задачи@secretary_oren_bot")

    assert isinstance(underscored, MyTasksCommand)
    assert isinstance(spaced, MyTasksCommand)


def test_parse_slash_help_command() -> None:
    command = BotCommandParser().parse("/")

    assert isinstance(command, SlashHelpCommand)


def test_parse_slash_help_command_with_bot_mention_prefix() -> None:
    command = BotCommandParser(bot_username="secretary_oren_bot").parse("@secretary_oren_bot /")

    assert isinstance(command, SlashHelpCommand)


@pytest.mark.parametrize("text", ["/помощь", "/help", "/команды"])
def test_parse_reliable_slash_help_aliases(text: str) -> None:
    command = BotCommandParser().parse(text)

    assert isinstance(command, SlashHelpCommand)


@pytest.mark.parametrize("text", ["помощь", "help", "команды", "дьяк помощь", "дьяк help", "дьяк команды"])
def test_parse_reliable_bare_help_aliases(text: str) -> None:
    parser = BotCommandParser()
    command = parser.parse(text)

    assert parser.is_command(text) is True
    assert isinstance(command, SlashHelpCommand)


def test_parse_task_lookup_hash_ref() -> None:
    command = BotCommandParser().parse("#1042")

    assert isinstance(command, TaskLookupCommand)
    assert command.task_number == 1042
    assert command.task_ref == "#1042"


def test_parse_task_lookup_slash_number() -> None:
    command = BotCommandParser().parse("/1042")

    assert isinstance(command, TaskLookupCommand)
    assert command.task_number == 1042
    assert command.task_ref == "#1042"


def test_parse_task_lookup_t_ref() -> None:
    command = BotCommandParser().parse("T-1042")

    assert isinstance(command, TaskLookupCommand)
    assert command.task_number == 1042
    assert command.task_ref == "#1042"


def test_task_lookup_does_not_match_arbitrary_number_in_text() -> None:
    parser = BotCommandParser()

    assert parser.is_command("посмотрите #1042") is False
    command = parser.parse("посмотрите #1042")

    assert isinstance(command, CommandParseError)


def test_parse_secretary_command() -> None:
    command = BotCommandParser().parse("/дьяк")

    assert isinstance(command, SecretaryCommand)


def test_parse_secretary_deprecated_alias() -> None:
    command = BotCommandParser().parse("/секретарь")

    assert isinstance(command, SecretaryCommand)


def test_parse_secretary_deprecated_alias_help() -> None:
    command = BotCommandParser().parse("/секретарь помощь")

    assert isinstance(command, SlashHelpCommand)


def test_parse_secretary_help_command() -> None:
    command = BotCommandParser().parse("/дьяк помощь")

    assert isinstance(command, SlashHelpCommand)


def test_parse_secretary_help_alias_command() -> None:
    command = BotCommandParser().parse("/дьяк help")

    assert isinstance(command, SlashHelpCommand)


def test_parse_task_response_command() -> None:
    command = BotCommandParser().parse("/ответ task-1 Сделал первую часть")

    assert isinstance(command, TaskResponseCommand)
    assert command.task_id == "task-1"
    assert command.text == "Сделал первую часть"


@pytest.mark.parametrize("task_ref", ["#1042", "1042", "T-1042"])
def test_parse_task_report_command_without_text(task_ref: str) -> None:
    command = BotCommandParser().parse(f"/отчет {task_ref}")

    assert isinstance(command, TaskReportCommand)
    assert command.task_number == 1042
    assert command.task_ref == "#1042"
    assert command.text is None


def test_parse_task_report_command_with_text() -> None:
    command = BotCommandParser().parse("/отчет #1042 сделал, доступы проверены")

    assert isinstance(command, TaskReportCommand)
    assert command.task_number == 1042
    assert command.task_ref == "#1042"
    assert command.text == "сделал, доступы проверены"


def test_parse_task_report_accepts_yo_alias() -> None:
    command = BotCommandParser().parse("/отчёт #1042 сделал, доступы проверены")

    assert isinstance(command, TaskReportCommand)
    assert command.task_number == 1042
    assert command.task_ref == "#1042"
    assert command.text == "сделал, доступы проверены"


def test_parse_task_report_requires_task_ref() -> None:
    command = BotCommandParser().parse("/отчет сделал")

    assert isinstance(command, CommandParseError)
    assert "Укажите номер задачи" in command.message


@pytest.mark.parametrize("task_ref", ["#1042", "1042", "T-1042"])
def test_parse_task_ping_command(task_ref: str) -> None:
    command = BotCommandParser().parse(f"/пинг {task_ref}")

    assert isinstance(command, PingTaskCommand)
    assert command.task_number == 1042
    assert command.task_ref == "#1042"


def test_parse_task_ping_requires_task_ref() -> None:
    command = BotCommandParser().parse("/пинг")

    assert isinstance(command, CommandParseError)
    assert "Укажите номер задачи" in command.message


@pytest.mark.parametrize(
    ("text", "command_type"),
    [
        ("@secretary_oren_bot дьяк", SecretaryCommand),
        ("@secretary_oren_bot секретарь", SecretaryCommand),
        ("@secretary_oren_bot мои_задачи", MyTasksCommand),
        ("@secretary_oren_bot мои задачи", MyTasksCommand),
        ("@secretary_oren_bot отчет #6", TaskReportCommand),
        ("@secretary_oren_bot отчёт #6", TaskReportCommand),
        ("@secretary_oren_bot пинг #6", PingTaskCommand),
        ("/@secretary_oren_bot дьяк", SecretaryCommand),
        ("/@secretary_oren_bot секретарь", SecretaryCommand),
        ("/дьяк@secretary_oren_bot", SecretaryCommand),
        ("/отчет@secretary_oren_bot #6", TaskReportCommand),
        ("/пинг@secretary_oren_bot #6", PingTaskCommand),
    ],
)
def test_parse_slash_popup_bot_mention_prefix(text: str, command_type: type[object]) -> None:
    parser = BotCommandParser(bot_username="secretary_oren_bot")

    assert parser.is_command(text) is True
    command = parser.parse(text)

    assert isinstance(command, command_type)


def test_parse_slash_popup_ignores_other_bot_prefix() -> None:
    parser = BotCommandParser(bot_username="secretary_oren_bot")

    assert parser.is_command("@other_bot дьяк") is False
    assert parser.is_command("@other_bot секретарь") is False


def test_parse_task_done_command() -> None:
    command = BotCommandParser().parse("/готово task-1 Готово, проверьте")

    assert isinstance(command, TaskDoneCommand)
    assert command.task_id == "task-1"
    assert command.text == "Готово, проверьте"


def test_parse_accept_response_command() -> None:
    command = BotCommandParser().parse("/принять task-1 response-1")

    assert isinstance(command, AcceptTaskResponseCommand)
    assert command.task_id == "task-1"
    assert command.response_id == "response-1"


def test_parse_reject_response_command() -> None:
    command = BotCommandParser().parse("/отклонить task-1 response-1 Нужно подробнее")

    assert isinstance(command, RejectTaskResponseCommand)
    assert command.task_id == "task-1"
    assert command.response_id == "response-1"
    assert command.comment == "Нужно подробнее"


def test_parse_unknown_command() -> None:
    command = BotCommandParser().parse("/неизвестно аргументы")

    assert isinstance(command, UnknownCommand)
    assert command.name == "неизвестно"
    assert command.args == "аргументы"


def test_parse_empty_create_task_command_starts_text_clarification() -> None:
    command = BotCommandParser().parse("/задача")

    assert isinstance(command, CreateTaskCommand)
    assert command.needs_text_clarification is True
    assert command.title == ""
    assert command.source_text == ""


def test_parse_error_for_bad_deadline() -> None:
    command = BotCommandParser().parse("/задача Подготовить отчет | Иван | завтра")

    assert isinstance(command, CommandParseError)
    assert command.message == "Срок должен быть датой в формате YYYY-MM-DD."


def test_parse_error_for_missing_response_text() -> None:
    command = BotCommandParser().parse("/ответ task-1")

    assert isinstance(command, CommandParseError)
    assert command.message == "Формат: /ответ <task_id> <текст ответа>."
