from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import httpx

from app.modules.bot.command_parser import BotCommandParser
from app.modules.bot.schemas import MyTasksCommand
from app.modules.integrations.max.bot_commands import (
    DEFAULT_MAX_BOT_COMMANDS,
    build_bot_commands,
    build_bot_commands_patch_payload,
    default_max_bot_commands,
)
from app.modules.integrations.max.client import MaxApiClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.max import register_bot_commands  # noqa: E402


def test_default_bot_commands_payload_uses_names_without_slash() -> None:
    payload = build_bot_commands_patch_payload(DEFAULT_MAX_BOT_COMMANDS)

    assert payload == {
        "commands": [
            {"name": "дьяк", "description": "Открыть меню и сводку задач"},
            {"name": "задача", "description": "Создать задачу из сообщения или текста"},
            {"name": "мои_задачи", "description": "Показать мои активные задачи"},
            {"name": "отчет", "description": "Отправить отчет по задаче"},
            {"name": "пинг", "description": "Напомнить исполнителю о задаче"},
            {"name": "помощь", "description": "Список команд Дьяка"},
        ]
    }
    assert all(not command["name"].startswith("/") for command in payload["commands"])
    assert "секретарь" not in {command["name"] for command in payload["commands"]}


def test_bot_command_builder_strips_slash_and_rejects_whitespace() -> None:
    assert build_bot_commands([{"name": "/дьяк", "description": "Открыть меню"}]) == [
        {"name": "дьяк", "description": "Открыть меню"}
    ]

    try:
        build_bot_commands([{"name": "/мои задачи", "description": "Показать задачи"}])
    except ValueError as exc:
        assert "whitespace" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected whitespace command name to be rejected.")


def test_max_api_client_patches_bot_commands() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"username": "secretary_oren_bot", "commands": default_max_bot_commands()})

    client = MaxApiClient(
        base_url="https://max-api.example.invalid",
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
        **{"bot_" + "token": "credential-placeholder"},
    )

    result = client.patch_bot_commands(default_max_bot_commands())

    assert result["username"] == "secretary_oren_bot"
    assert requests[0].method == "PATCH"
    assert requests[0].url.path == "/me"
    assert requests[0].headers["Authorization"] == "credential-placeholder"
    assert json.loads(requests[0].read()) == {"commands": default_max_bot_commands()}


def test_register_bot_commands_dry_run_does_not_call_max_api(capsys: Any, monkeypatch: Any) -> None:
    class FailIfCalledClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("MAX API client must not be created in dry-run mode.")

    monkeypatch.setattr(register_bot_commands, "MaxApiClient", FailIfCalledClient)

    exit_code = register_bot_commands.main(["--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "dry_run=ok" in output
    assert "max_api_called=no" in output
    assert "MAX_BOT_TOKEN" not in output
    assert "credential-placeholder" not in output
    assert '"name": "дьяк"' in output
    assert '"name": "секретарь"' not in output
    assert '"name": "мои_задачи"' in output
    assert '"name": "помощь"' in output


def test_register_bot_commands_apply_patches_me_without_printing_token(capsys: Any, monkeypatch: Any) -> None:
    calls: list[dict[str, object]] = []

    class FakeMaxApiClient:
        def __init__(self, *, settings: object, base_url: str | None = None) -> None:
            calls.append({"settings": settings, "base_url": base_url})

        def __enter__(self) -> FakeMaxApiClient:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            return None

        def patch_bot_commands(self, commands: list[dict[str, str]]) -> dict[str, object]:
            calls.append({"commands": commands})
            return {"username": "secretary_oren_bot", "commands": commands}

    monkeypatch.setattr(register_bot_commands, "get_settings", lambda: object())
    monkeypatch.setattr(register_bot_commands, "MaxApiClient", FakeMaxApiClient)

    exit_code = register_bot_commands.main(["--apply", "--base-url", "https://max-api.example.invalid"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "apply=ok" in output
    assert "max_api_called=yes" in output
    assert "credential-placeholder" not in output
    assert calls[0]["base_url"] == "https://max-api.example.invalid"
    assert calls[1]["commands"] == default_max_bot_commands()


def test_parser_keeps_spaced_my_tasks_alias() -> None:
    command = BotCommandParser().parse("/мои задачи")

    assert isinstance(command, MyTasksCommand)
