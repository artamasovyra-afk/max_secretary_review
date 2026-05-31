# MAX Webhook Setup

This document describes the public URLs and safe environment settings for connecting the `max_secretary` MAX bot webhook on the pilot VPS.

## Public URLs

- WebApp URL: `https://maxsecretary.ru`
- MAX webhook URL: `https://maxsecretary.ru/api/bot/max/webhook`

## Required VPS Environment Variables

Set these values only in the VPS `.env` file or another protected runtime secret store.

```env
MAX_WEBHOOK_ENABLED=true
MAX_SENDER_ENABLED=true
MAX_INTERACTIVE_RESPONSES_ENABLED=true
MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false
MAX_API_BASE_URL=https://platform-api.max.ru
MAX_WEBHOOK_DEBUG_LOG=false
WEBAPP_BASE_URL=https://maxsecretary.ru
```

Set `MAX_WEBHOOK_ENABLED=true` only together with a configured webhook secret. Also set these secret variables only in the VPS `.env`; do not put literal values in repository files:

- `MAX_BOT_TOKEN` — set only in VPS `.env`
- `MAX_WEBHOOK_SECRET` — set only in VPS `.env`

Do not add real values to git, README, documentation, GitHub Actions logs, chat messages, or screenshots.

## Safety Rules

- Do not commit `MAX_BOT_TOKEN`.
- Do not commit `MAX_WEBHOOK_SECRET`.
- Use a test MAX bot for sandbox validation before enabling a production bot.
- Set `MAX_WEBHOOK_ENABLED=false` when the webhook endpoint must be hidden before sandbox setup.
- Keep `MAX_WEBHOOK_DEBUG_LOG=false` in production by default.
- Enable `MAX_WEBHOOK_DEBUG_LOG=true` only temporarily in sandbox/debug sessions and turn it off after payload capture.
- Use `MAX_SENDER_ENABLED=false` for full silent mode.
- For safe live command handling, use `MAX_SENDER_ENABLED=true`, `MAX_INTERACTIVE_RESPONSES_ENABLED=true`, and `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`.
- Keep `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false` until reminders, pings, summaries, and group sends are approved for a controlled rollout.

## Security Behavior

- `MAX_WEBHOOK_ENABLED=false`: the backend returns HTTP `404` for `POST /api/bot/max/webhook` and does not process or debug-log the event payload.
- `APP_ENV=production`, `MAX_WEBHOOK_ENABLED=true`, empty `MAX_WEBHOOK_SECRET`: the backend returns HTTP `503` with the safe message `MAX webhook is not configured` and does not process or debug-log the event payload.
- Configured `MAX_WEBHOOK_SECRET`, missing secret header: HTTP `401`.
- Configured `MAX_WEBHOOK_SECRET`, invalid `X-Max-Bot-Api-Secret` header: HTTP `401`.
- Configured `MAX_WEBHOOK_SECRET`, valid `X-Max-Bot-Api-Secret` header: payload is accepted and passed to normal event handling.
- The legacy `X-Max-Webhook-Secret` header is accepted temporarily for internal compatibility, but official MAX subscriptions use `X-Max-Bot-Api-Secret`.
- `MAX_WEBHOOK_DEBUG_LOG=false` is the default and expected production value.
- `MAX_SENDER_ENABLED=true` enables the MAX transport, but interactive replies and background notifications are guarded separately.
- `MAX_INTERACTIVE_RESPONSES_ENABLED=true` allows direct command replies and callback answers.
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false` blocks reminders and other background sends without blocking `/дьяк` or `/задача` replies.

## MAX External Identity Mapping

Real MAX webhook payloads contain external MAX identifiers. They are not internal database UUIDs.

The bot command flow resolves them before task creation:

- MAX user id -> `User.max_user_id` -> internal `User.id`;
- MAX chat id -> `Chat.max_chat_id` -> internal `Chat.id`;
- first command webhook from a new MAX user/chat autocreates local records;
- a single default organization, `MAX default organization`, is reused for bot-created MAX chats;
- repeated webhooks for the same external ids reuse the same local records and do not create duplicates;
- chat title extraction checks known MAX title/name locations such as `message.chat`, `message.recipient`, `message.body.chat`, top-level `chat`/`recipient`, `dialog`, `conversation`, and `message_created` variants;
- generated or identifier-like chat titles are ignored, and existing generated fallback titles are updated only when a real title later arrives;
- manual chat aliases in `Chat.settings.display_title` are preserved and have priority in WebApp display;
- the command author is ensured as an active chat `member`;
- reply author metadata is stored only as source context and does not become the assignee automatically;
- reply `/задача` without explicit assignee creates a self-task for the command author;
- Bitrix24 hierarchy is not used for this mapping in `v1.1`.

## MAX Outbound Recipient Mapping

Outbound MAX delivery uses the same external identity model:

- personal notifications store internal `NotificationDelivery.user_id`, but send to `User.max_user_id`;
- group/chat fallback notifications send to `Chat.max_chat_id`;
- internal UUIDs must not be passed to MAX `/messages` as `user_id` or `chat_id`;
- users without `User.max_user_id` are marked `dm_unavailable` or delivery unavailable without calling MAX;
- chats without `Chat.max_chat_id` are skipped with a safe delivery error;
- keep `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false` until broader reminder and notification behavior is deployed, verified, and explicitly approved.

## Verification

After DNS, host nginx, and TLS are configured, verify:

```bash
curl -I https://maxsecretary.ru/
curl https://maxsecretary.ru/api/health
curl -I https://maxsecretary.ru/tasks
curl -I https://maxsecretary.ru/dashboard
curl -I https://maxsecretary.ru/openapi.json
```

Expected:

- WebApp routes return HTTP `200`.
- `/api/health` returns `status=ok`.
- `/openapi.json` returns HTTP `200`, unless intentionally closed by a future security hardening step.

## MAX Control Panel

In the MAX bot control panel, the visible application/mini app URL is configured separately from webhook delivery.
For the current deployment, the mini app URL is:

```text
https://maxsecretary.ru
```

Do not confuse this with the webhook URL. The webhook endpoint is:

```text
https://maxsecretary.ru/api/bot/max/webhook
```

Webhook delivery is configured through the official MAX `/subscriptions` API, not only through the mini app URL field in the control panel.
The official subscription request supports a `secret` field. According to the current MAX docs, that secret is sent to the backend in the `X-Max-Bot-Api-Secret` request header.

## Native Slash Command Menu

MAX bot slash-popup commands are registered by patching the current bot profile through `PATCH /me` with a `commands` list. This is an operator action and is not performed during backend startup.

Use dry-run first:

```bash
python scripts/max/register_bot_commands.py --dry-run
```

On the VPS, run through the backend container so the script uses the same installed dependencies as the app:

```bash
docker compose -f docker-compose.prod.yml run --rm -T \
  -v "$PWD/scripts:/app/scripts:ro" \
  backend python scripts/max/register_bot_commands.py --dry-run
```

Apply only from a protected shell where `MAX_BOT_TOKEN` is already set:

```bash
python scripts/max/register_bot_commands.py --apply
```

Containerized apply:

```bash
docker compose -f docker-compose.prod.yml run --rm -T \
  -v "$PWD/scripts:/app/scripts:ro" \
  backend python scripts/max/register_bot_commands.py --apply
```

The script does not print the bot token. It sends command names without `/`:

- `дьяк` — открыть меню и сводку задач;
- `задача` — создать задачу из сообщения или текста;
- `мои_задачи` — показать мои активные задачи;
- `отчет` — отправить отчет по задаче;
- `пинг` — напомнить исполнителю о задаче.

`MAX_BOT_USERNAME` remains the technical MAX username, for example `secretary_oren_bot`, even though the external product brand and primary command are `Дьяк` and `/дьяк`.

The parser keeps `/мои задачи` as a forgiving alias, but the native command menu uses `мои_задачи` because command names with spaces are not safe for slash-popup registration.

The backend validates the official MAX subscription secret header:

```text
X-Max-Bot-Api-Secret: <secret from VPS .env>
```

For internal backward compatibility, the backend also accepts the legacy pilot header:

```text
X-Max-Webhook-Secret: <secret from VPS .env>
```

When the secret is configured, missing or invalid secret headers return HTTP `401`. A valid `X-Max-Bot-Api-Secret` header is required for official MAX webhook delivery. The backend uses constant-time comparison for the supplied and expected secret and does not include the expected secret in the response body or logs.

Compatibility note:

- official MAX subscription secret header: `X-Max-Bot-Api-Secret`;
- legacy/internal pilot header: `X-Max-Webhook-Secret`;
- do not disable security to work around this difference;
- keep the legacy header only while tests and internal tooling are being migrated.

If `MAX_WEBHOOK_ENABLED=false`, the backend returns HTTP `404` for `POST /api/bot/max/webhook` and does not process the event payload.

If `APP_ENV=production`, `MAX_WEBHOOK_ENABLED=true`, and `MAX_WEBHOOK_SECRET` is empty, the backend returns HTTP `503` with the safe message `MAX webhook is not configured` and does not process the event payload.

## Subscription API Setup

Use the official MAX `/subscriptions` API after the bot credential and webhook secret are set only in the VPS `.env`.

Expected request properties:

- URL: `https://maxsecretary.ru/api/bot/max/webhook`;
- update types: at least `message_created`, `bot_started`, and `message_callback` for the v1.1 chat-native flow;
- version: `1`;
- secret: the VPS webhook secret, only if it matches the official MAX character policy.

Sanitized subscription body shape:

```json
{
  "url": "https://maxsecretary.ru/api/bot/max/webhook",
  "update_types": ["message_created", "bot_started", "message_callback"],
  "secret": "<MAX_WEBHOOK_SECRET from VPS .env>"
}
```

The official secret policy is `[A-Za-z0-9_-]`, length 5-256. If the deployed `MAX_WEBHOOK_SECRET` contains other characters, replace it manually in the VPS `.env` with a compatible generated value before creating the subscription. Do not commit or print that value.

Latest sanitized check on `2026-05-22`:

- `GET /subscriptions`: HTTP `401`, code `verify.token`, message `Invalid access_token`;
- `POST /subscriptions`: HTTP `401`, code `verify.token`, message `Invalid access_token`;
- subscription created: no;
- the currently deployed webhook secret is set, but not compatible with the official subscription secret character policy.

This means the next setup step is to verify or replace the MAX bot credential in the VPS `.env`, replace the webhook secret with a MAX-compatible value if needed, and then configure the subscription again.

## Sandbox Steps

Use these steps only after the test bot is ready for sandbox validation:

1. Add the real bot credential and webhook secret only to the VPS `.env`.
2. Restart backend and worker containers.
3. Configure the mini app URL in the MAX control panel.
4. Configure webhook delivery through the official `/subscriptions` API.
5. Send a normal text message in the sandbox chat.
6. Send `/задача` as a reply to a sandbox message.
7. Trigger a callback/button action, if the MAX sandbox supports it.
8. Test mini app opening through a MAX deep link button.
9. Check direct-message delivery behavior and the unavailable-DM fallback.
10. Update `docs/integrations/max_sandbox_audit.md` with sanitized results only.

## Mini App Deep Links

The MAX control panel mini app URL remains the plain HTTPS WebApp URL:

```text
https://maxsecretary.ru
```

For a message button that opens the WebApp inside the MAX client, use a MAX deep link instead of the plain HTTPS URL:

```text
https://max.ru/<bot_username>?startapp=home
```

For the current bot:

```text
MAX_BOT_USERNAME=secretary_oren_bot
https://max.ru/secretary_oren_bot?startapp=home
```

Sandbox result on `2026-05-22`:

- plain link button to `https://maxsecretary.ru`: opens the WebApp in an external browser;
- link button to `https://max.ru/<bot_username>?startapp=home`: opens the WebApp inside MAX;
- `startapp` payload must remain short and non-secret;
- do not place user ids, chat ids, task ids, tokens, webhook secrets, or personal data in the deep-link payload unless a future signed context flow is implemented;
- native `open_app` button type remains unverified in the current sandbox.
