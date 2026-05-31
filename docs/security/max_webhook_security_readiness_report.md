# MAX Webhook Security Readiness Report

Status date: 2026-05-23

Version: `1.1.0-rc.1`

Branch: `main`

HEAD at update time: `9f450ce fix: add logical idempotency for task callbacks`

## Readiness

Status: ready for controlled real MAX sandbox and limited pilot validation.

This means the webhook endpoint is hardened, the official MAX webhook secret
header is supported, the real webhook subscription has been created, and the
main chat-native task flow has been verified with real MAX events.

This does not mean the integration is unrestricted production-ready. Broader
direct-message behavior, reminder volume, rate limits, production WebApp auth
hardening and operational monitoring still need pilot validation.

## Current Verified State

Application:

- `VERSION`: `1.1.0-rc.1`.
- Main branch includes the v1.1 chat-native flow and subsequent real MAX fixes.
- Latest relevant hardening commit: `9f450ce fix: add logical idempotency for task callbacks`.

Webhook security:

- `MAX_WEBHOOK_ENABLED=false` disables the endpoint with HTTP `404`.
- Production plus enabled webhook plus missing `MAX_WEBHOOK_SECRET` returns a safe configuration rejection before payload handling.
- Missing official MAX webhook secret header returns HTTP `401` when a secret is configured.
- Invalid official MAX webhook secret header returns HTTP `401`.
- Valid official MAX webhook secret header is accepted.
- Official header: `X-Max-Bot-Api-Secret`.
- Legacy internal header `X-Max-Webhook-Secret` is still accepted only for compatibility with older tests/internal tooling.
- Secret comparison uses constant-time comparison.
- Expected webhook secret is not included in response body or logs.
- Debug logging is disabled by default and uses sanitized shapes when temporarily enabled.

MAX subscription:

- MAX mini app URL in the control panel: `https://maxsecretary.ru`.
- Webhook URL: `https://maxsecretary.ru/api/bot/max/webhook`.
- Webhook subscription is created through the official subscriptions API.
- Subscription update types verified:
  - `message_created`;
  - `bot_started`;
  - `message_callback`.
- Official secret delivery through `X-Max-Bot-Api-Secret` is confirmed.

Real MAX sandbox findings:

- Ordinary message webhook: captured and accepted.
- Reply `/задача` webhook: captured and accepted.
- Real reply metadata path `message.link` is mapped into `NormalizedBotEvent.reply_to_*`.
- External MAX user/chat identifiers are resolved into internal `User` and `Chat` records.
- Reply `/задача` creates a task from real MAX payloads.
- Self-task from reply assigns the task to the command author.
- Source message id is saved from the replied MAX message.
- Natural deadline parsing from reply text is confirmed in the live flow.
- Sender single-message test is confirmed with external `User.max_user_id`.
- Internal UUIDs are not sent to MAX as outbound recipients.
- WebApp link button is delivered and visible.
- MAX deep link opens the WebApp inside MAX.
- Callback button shape is confirmed active.
- Real `message_callback` events are routed to `callback_service`.
- Callback answers through MAX are confirmed.
- Controlled `task:snooze:1h` callback E2E is confirmed.
- `TaskReminderSnooze` is created from real task callbacks.
- `bot_callback_receipts` are written for real task callbacks.
- Logical idempotency was added because MAX can emit multiple callback events with different `callback_id` values for one manual interaction.

## Checks Performed

Backend:

- Latest full backend test result before this report update: `490 passed`.
- Latest `ruff check .`: passed.
- Latest Alembic head: `f3a4b5c6d7e8`.

Secret handling:

- No real MAX bot credential is committed.
- No real MAX webhook secret is committed.
- Production `.env` remains VPS-only.
- Docs use sanitized findings only.
- Raw MAX payloads are not committed.
- Full real user, chat, message and callback identifiers are not committed.

Operational safeguards:

- `MAX_SENDER_ENABLED` is kept disabled after controlled live sender tests unless a test explicitly needs it.
- `MAX_WEBHOOK_DEBUG_LOG` is kept disabled after capture windows.
- Mass sends were not performed during sandbox checks.
- Scheduled jobs, daily summaries and group assignment fan-out were not manually triggered during callback/sender tests.

## Remaining Risks

- Broader direct-message behavior still needs pilot validation beyond the controlled single-message test.
- Reminder and notification behavior must be validated under realistic pilot volume before enabling broad outbound sends.
- MAX formatting behavior and rate limits need measured pilot evidence.
- Production WebApp auth and MAX WebApp init-data validation should be tightened before a real production pilot.
- Native `open_app` button behavior is still not fully confirmed; the working path is MAX deep link.
- Request body size limits should be configured or rechecked at nginx/backend before broader exposure.
- Monitoring and alerting for webhook errors, callback failures and outbound MAX failures should be improved before production pilot.

## VPS Safety Baseline

Production `.env` should remain VPS-only or in a protected secret store.

Expected VPS-only MAX variables:

- `MAX_WEBHOOK_ENABLED=true`
- `MAX_SENDER_ENABLED=false` by default, enabled only for controlled outbound tests or a deliberate pilot window
- `MAX_API_BASE_URL=https://platform-api.max.ru`
- `MAX_BOT_TOKEN` set only in VPS `.env`
- `MAX_WEBHOOK_SECRET` set only in VPS `.env`
- `MAX_WEBHOOK_DEBUG_LOG=false` by default

Do not print, paste or commit the bot credential or webhook secret.

## Recommended Next Steps

Before broader pilot:

1. Keep `MAX_WEBHOOK_DEBUG_LOG=false` except during short sanitized capture windows.
2. Keep `MAX_SENDER_ENABLED=false` until the next deliberate outbound pilot test.
3. Validate direct-message unavailable behavior with a controlled test user.
4. Validate reminder delivery with a tiny controlled dataset before enabling real reminder volume.
5. Add or verify MAX WebApp init-data validation before relying on in-app user context.
6. Add monitoring for webhook status, callback receipt failures and outbound delivery failures.
7. Recheck nginx/backend request body and rate-limit protections.

## Recommendation

Keep the report as the current security readiness record.

The stale 2026-05-21 draft has been updated rather than deleted because it is
now the clearest single-page summary of the MAX webhook security posture after
real sandbox validation.
