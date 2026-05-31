# MAX Bot Slash Command Menu Research

## Goal

Find out whether `Дьяк` can populate the native MAX slash command popup so that users see bot commands when they type `/` in a MAX chat.

## Current Symptom

In the live MAX chat, typing `/` shows:

```text
команды не найдены
```

The bot already supports text commands in incoming messages:

- `/дьяк`
- `/задача`
- `/мои задачи`
- `/отчет`
- `/пинг`
- task references such as `#1042`

## Sources Checked

- MAX API docs: `https://dev.max.ru/docs-api`
- Official Go SDK: `https://github.com/max-messenger/max-bot-api-client-go`
- Local clone of the official Go SDK OpenAPI schema and examples
- Reference implementation: `https://github.com/artamasovyra-afk/bot_comment_max`
- Existing local MAX integration docs in `docs/integrations/`

No real MAX API calls were made during this research.

## Findings

### API Support

API support is confirmed through the official Go SDK and its generated OpenAPI schema.

The SDK exposes current bot profile update through `Bots.PatchBot`, backed by `PATCH /me`. `BotPatch` includes a `commands` field, and `BotCommand` contains:

- `name`
- `description`

The generated OpenAPI schema describes:

- `PATCH /me` as editing current bot info;
- `BotPatch.commands` as commands supported by the bot;
- `BotInfo.commands` as commands returned for the bot;
- max commands count: 32;
- command name length: 1 to 64;
- description length: 1 to 128.

The official Go SDK example updates commands with:

```go
api.Bots.PatchBot(ctx, &schemes.BotPatch{
    Commands: []schemes.BotCommand{
        {Name: "shutdown", Description: "Перезапускает бота"},
    },
})
```

This is the closest MAX equivalent to Telegram-style `setMyCommands`.

### Slash Popup Behavior

The public API evidence strongly suggests that setting `commands` on the bot profile is the intended way to populate native command hints.

One point remains to verify live: whether the MAX client slash popup immediately renders these bot profile commands in the exact chat where the bot is installed. The current symptom, `команды не найдены`, is consistent with the bot profile command list being empty or unset.

### LK Manual Support

LK/manual support was not confirmed in this run.

If MAX has a bot settings screen for commands, it likely writes the same bot profile `commands` data. This should be checked manually in the MAX bot cabinet or MasterBot UI before building an operator runbook around manual setup.

### SDK Support

SDK support is confirmed in the official Go SDK:

- `schemes.BotCommand`
- `schemes.BotPatch.Commands`
- `schemes.BotInfo.Commands`
- `api.Bots.PatchBot(...)`

There is no separate `setMyCommands` method in the Go SDK; command registration is done by patching the bot profile.

### bot_comment_max Reference

`bot_comment_max` uses text commands such as `/setup_channel` and `/bind_comments`, but this reference does not show bot command menu registration.

It is useful as a working bot/WebApp reference, but not as evidence for slash-popup setup.

## Recommended Commands

The API `name` should be sent without a leading `/`. MAX clients are expected to render slash commands with `/` in the UI.

| Command | Description | Notes |
|---|---|---|
| `дьяк` | Открыть меню и сводку задач | Primary command center entry. |
| `задача` | Создать задачу из сообщения или текста | Existing parser command. |
| `мои_задачи` | Показать мои активные задачи | Slash command names usually cannot contain spaces; keep `/мои задачи` as parser alias. |
| `отчет` | Отправить отчет по задаче | Expected format: `/отчет #1042 текст`. |
| `пинг` | Напомнить исполнителю о задаче | Guarded by permissions and cooldown when implemented. |

If MAX rejects Cyrillic command names during registration, fall back to ASCII aliases in a separate implementation task, for example:

- `secretary`
- `task`
- `my_tasks`
- `report`
- `ping`

The current schema does not state a charset restriction, only length restrictions.

## Implementation Path

Recommended implementation path: API registration script.

Implemented operator script:

```text
scripts/max/register_bot_commands.py
```

Behavior:

- reads `MAX_BOT_TOKEN` from environment;
- never prints the token;
- supports `--dry-run`;
- sends `PATCH /me` with a sanitized `commands` list only with `--apply`;
- can clear commands by sending an empty list only with an explicit flag;
- logs only command names/descriptions and response status;
- documents expected 401/400 failure modes.

No production registration should be performed implicitly during backend startup or deploy. Command registration is an operator action, not app runtime behavior.

Dry-run:

```bash
python scripts/max/register_bot_commands.py --dry-run
```

On the VPS, where Python dependencies live in the backend container, run the same script with a read-only scripts mount:

```bash
docker compose -f docker-compose.prod.yml run --rm -T \
  -v "$PWD/scripts:/app/scripts:ro" \
  backend python scripts/max/register_bot_commands.py --dry-run
```

Apply:

```bash
python scripts/max/register_bot_commands.py --apply
```

Containerized apply:

```bash
docker compose -f docker-compose.prod.yml run --rm -T \
  -v "$PWD/scripts:/app/scripts:ro" \
  backend python scripts/max/register_bot_commands.py --apply
```

The script sends command names without a leading slash, matching the official Go SDK example and real `/me` command payloads.

## Risks and Limitations

- Native slash-popup rendering is confirmed in the live MAX chat after controlled `PATCH /me` registration.
- Cyrillic command names were accepted by the API and appeared in the native slash-popup in the live MAX client.
- Command names with spaces should not be used in the native menu. Use `мои_задачи` in the menu and keep `/мои задачи` as a forgiving parser alias.
- In live MAX clients the slash-popup can insert commands as `@secretary_oren_bot <command>`. Backend command parsing therefore supports the mention-prefix format for the configured `MAX_BOT_USERNAME`, including `@secretary_oren_bot отчет #1042`, `@secretary_oren_bot отчёт #1042`, and `@secretary_oren_bot пинг #1042`.
- `#1042` is not a slash command and cannot be registered as a slash-popup command. It remains a normal message/task reference pattern.
- Bot command registration uses bot profile mutation and requires the bot token. It must be handled as an ops script with secret-safe logging.

## Live Registration Result — 2026-05-24

Registration was applied once from the VPS using the containerized script flow:

```text
docker compose -f docker-compose.prod.yml run --rm -T \
  -v "$PWD/scripts:/app/scripts:ro" \
  backend python scripts/max/register_bot_commands.py --apply
```

Sanitized result:

- deployed code: `41ae33c` including `6c4f26e`;
- dry-run on VPS: passed, `max_api_called=no`;
- apply on VPS: passed, `max_api_called=yes`;
- MAX API operation: `PATCH /me`;
- command name format: without slash;
- token printed: no;
- Authorization header printed: no;
- native slash-popup shows commands: yes.

The 2026-05-24 run confirmed that `PATCH /me` populates the native slash-popup. After the external rebrand to `Дьяк`, the command payload must be applied again manually after deploy. Expected visible commands after that operator step:

- `/дьяк`;
- `/задача`;
- `/мои_задачи`;
- `/отчет`;
- `/пинг`.

The parser still keeps `/мои задачи` as a human-friendly alias, and `/секретарь` remains a deprecated command-center alias even though it is no longer part of the native slash-popup payload.

## Next Steps

1. Keep bot command registration as a manual operator action.
2. Re-run the script only when command names or descriptions change.
3. If MAX later changes command constraints, add ASCII aliases in a separate task.
