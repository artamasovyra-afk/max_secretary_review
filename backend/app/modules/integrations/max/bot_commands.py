from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

MAX_BOT_COMMANDS_LIMIT = 32
MAX_BOT_COMMAND_NAME_MAX_LENGTH = 64
MAX_BOT_COMMAND_DESCRIPTION_MAX_LENGTH = 128


@dataclass(frozen=True)
class MaxBotCommand:
    name: str
    description: str


DEFAULT_MAX_BOT_COMMANDS: tuple[MaxBotCommand, ...] = (
    MaxBotCommand(name="дьяк", description="Открыть меню и сводку задач"),
    MaxBotCommand(name="задача", description="Создать задачу из сообщения или текста"),
    MaxBotCommand(name="мои_задачи", description="Показать мои активные задачи"),
    MaxBotCommand(name="отчет", description="Отправить отчет по задаче"),
    MaxBotCommand(name="пинг", description="Напомнить исполнителю о задаче"),
    MaxBotCommand(name="помощь", description="Список команд Дьяка"),
)


def default_max_bot_commands() -> list[dict[str, str]]:
    return build_bot_commands(DEFAULT_MAX_BOT_COMMANDS)


def build_bot_commands_patch_payload(commands: Iterable[MaxBotCommand | Mapping[str, str]]) -> dict[str, object]:
    return {"commands": build_bot_commands(commands)}


def build_bot_commands(commands: Iterable[MaxBotCommand | Mapping[str, str]]) -> list[dict[str, str]]:
    built = [_normalize_bot_command(command) for command in commands]
    if len(built) > MAX_BOT_COMMANDS_LIMIT:
        raise ValueError(f"MAX bot commands list cannot contain more than {MAX_BOT_COMMANDS_LIMIT} items.")
    return built


def _normalize_bot_command(command: MaxBotCommand | Mapping[str, str]) -> dict[str, str]:
    if isinstance(command, MaxBotCommand):
        name = command.name
        description = command.description
    else:
        name = command["name"]
        description = command["description"]

    normalized_name = _normalize_command_name(name)
    normalized_description = description.strip()
    if not normalized_description:
        raise ValueError("MAX bot command description cannot be empty.")
    if len(normalized_description) > MAX_BOT_COMMAND_DESCRIPTION_MAX_LENGTH:
        raise ValueError(
            "MAX bot command description cannot be longer than "
            f"{MAX_BOT_COMMAND_DESCRIPTION_MAX_LENGTH} characters."
        )
    return {"name": normalized_name, "description": normalized_description}


def _normalize_command_name(name: str) -> str:
    normalized = name.strip().lstrip("/")
    if not normalized:
        raise ValueError("MAX bot command name cannot be empty.")
    if len(normalized) > MAX_BOT_COMMAND_NAME_MAX_LENGTH:
        raise ValueError(
            f"MAX bot command name cannot be longer than {MAX_BOT_COMMAND_NAME_MAX_LENGTH} characters."
        )
    if any(character.isspace() for character in normalized):
        raise ValueError("MAX bot command name cannot contain whitespace; use an alias such as мои_задачи.")
    return normalized
