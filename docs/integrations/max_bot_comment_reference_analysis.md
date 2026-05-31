# MAX Bot/WebApp Reference Analysis — bot_comment_max

## 1. Source repository

- URL: `https://github.com/artamasovyra-afk/bot_comment_max`
- analyzed branch: `main`
- analyzed commit: `7bcdd8de61993eaea023eb8b9cdfb08eb7aa598a`
- date: `2026-05-22`

The repository was cloned to a temporary local directory for read-only analysis. No code was transferred automatically.

## 2. Why this repository matters

`bot_comment_max` is a useful practical reference because it already has a working MAX bot + mini app flow:

- MAX Bot API client;
- webhook and polling delivery modes;
- `/subscriptions` management;
- webhook secret validation through the official MAX header;
- static WebApp/mini app served behind HTTPS;
- WebApp deep links through `startapp`;
- inline keyboard link buttons that open the mini app with context;
- MAX WebApp init data verification.

This differs from `max_secretary`, where the production WebApp is already live, but real MAX bot subscription and sandbox payload capture are still being connected.

## 3. MAX token and authorization

### bot_comment_max

- Token variable: `MAX_BOT_TOKEN`.
- Runtime config requires it on startup.
- Bot API requests send the token in the HTTP `Authorization` header as-is.
- No `Bearer` or `Bot` prefix is added.
- The same raw `Authorization` pattern is used for:
  - `GET /me`;
  - `GET /updates`;
  - `GET /subscriptions`;
  - `POST /subscriptions`;
  - `POST /messages`;
  - `PUT /messages`.

### max_secretary

- Token variable: `MAX_BOT_TOKEN`.
- Current `MaxApiClient` also sends the configured value in the `Authorization` header as-is.
- Safe VPS checks tried the raw value and common prefixed variants, and `/subscriptions` still returned a 401 invalid credential response.

### Difference and likely cause

There is no evidence from `bot_comment_max` that a `Bearer` or `Bot` prefix is needed. The working reference uses the same raw-token header style as `max_secretary`.

Most likely causes of the invalid credential response in `max_secretary`:

1. The value in VPS `.env` is not the Bot API token from `Чат-боты -> Интеграция -> Получить токен`.
2. The MAX partner platform exposes more than one credential-like value, and the wrong one was copied.
3. The token was regenerated after being copied to the VPS.
4. The token is copied with an invisible/invalid character that length-only checks do not reveal.
5. The bot/account does not yet have API access for `/subscriptions`, even though moderation has passed.

## 4. Webhook subscription

### bot_comment_max

Delivery mode is controlled by `MAX_DELIVERY_MODE`:

- `polling`: uses `GET /updates`;
- `webhook`: configures subscriptions and waits for webhook delivery.

Webhook-related environment variables:

- `MAX_WEBHOOK_PATH`, default `/webhook`;
- `MAX_WEBHOOK_PUBLIC_URL`;
- `MAX_WEB_APP_PUBLIC_URL`;
- `MAX_WEBHOOK_SECRET`;
- `MAX_DELIVERY_MODE`.

If `MAX_WEBHOOK_PUBLIC_URL` is empty, it builds the webhook URL from:

```text
MAX_WEB_APP_PUBLIC_URL + MAX_WEBHOOK_PATH
```

Subscription management:

- reads current subscriptions with `GET /subscriptions`;
- deletes existing subscriptions, including stale subscriptions with other URLs;
- creates a fresh subscription with `POST /subscriptions`;
- update types are `message_created` and `bot_started`;
- includes `secret` only when `MAX_WEBHOOK_SECRET` is set.

Subscription body shape:

```json
{
  "url": "https://example.invalid/webhook",
  "update_types": ["message_created", "bot_started"],
  "secret": "<MAX_WEBHOOK_SECRET_REDACTED>"
}
```

### max_secretary

- Webhook endpoint: `https://maxsecretary.ru/api/bot/max/webhook`.
- Webhook enable flag: `MAX_WEBHOOK_ENABLED`.
- Webhook secret variable: `MAX_WEBHOOK_SECRET`.
- Official header support has been added for `X-Max-Bot-Api-Secret`.
- Legacy/internal header `X-Max-Webhook-Secret` is still accepted temporarily.
- There is no first-class subscription management helper yet.

### Recommendation

Adapt the `bot_comment_max` subscription flow into a safe `max_secretary` ops script:

- read `MAX_BOT_TOKEN` and `MAX_WEBHOOK_SECRET` from VPS `.env`;
- print only set/length/pattern status;
- call `GET /subscriptions`;
- create/update subscription only after token validation succeeds;
- use `message_created` and `bot_started` first;
- add `message_callback` after callback payload behavior is confirmed;
- avoid deleting unknown subscriptions automatically without an explicit flag.

## 5. Webhook endpoint and payload

### bot_comment_max

Webhook endpoint:

- default path: `/webhook`;
- path configurable through `MAX_WEBHOOK_PATH`;
- accepts a single update object or a list of updates;
- queues accepted update dictionaries into a worker queue.

Webhook secret validation:

- expected header: `X-Max-Bot-Api-Secret`;
- comparison uses `hmac.compare_digest`;
- if `MAX_WEBHOOK_SECRET` is empty, webhook requests are accepted without secret protection and a startup warning is logged.

Payload handling:

- top-level `update_type`;
- `bot_started` reads user id from `update.user.user_id`, `userId`, `id`, or `update.user_id`;
- `message_created` reads `update.message`;
- chat id is read mainly from `message.recipient.chat_id`;
- sender user id is read from `message.sender.user_id`, nested `sender.user.user_id`, nested `sender.user.id`, or `sender.id`;
- message id is read from `message.body.mid` or `message.mid`;
- text is read from `message.body.payload` first, then `message.body.text`.

Forward/reply-like data:

- the project does not implement generic task reply flow;
- it has broad forward/link extraction helpers that inspect `message.link`, `body.link`, `body.forward`, `body.forwarded_message`, `body.shared_message`, and nested attachment payloads;
- it normalizes linked message ids from `mid`, `message_id`, and `messageId`.

Callbacks:

- no `message_callback` handling was found in the active delivery update list;
- current buttons are link buttons, not callback buttons.

### max_secretary

- `NormalizedBotEvent` supports normalized text events and reply metadata fields.
- Raw MAX-like message normalization currently handles `message.recipient.chat_id`, `message.sender.user_id`, and `message.body.mid`.
- Mock fixtures cover assumptions, but real payload capture is still pending.
- `bot_started` is safely ignored today.
- Callback payload handling exists internally, but real MAX `message_callback` mapping is still pending.

### Recommendation

Use `bot_comment_max` field extraction as practical evidence for:

- `message.recipient.chat_id`;
- `message.sender.user_id`;
- `message.body.mid`;
- `message.body.text`;
- `message.body.payload` as a possible text/payload path;
- `update.user` for `bot_started`.

Do not assume reply metadata until real sandbox capture. The forward/link extraction strategy in `bot_comment_max` is useful as a pattern, but too broad to transplant directly.

## 6. WebApp / mini app URL

### bot_comment_max

Mini app setup:

- public mini app URL is configured in MAX partner UI;
- runtime variable: `MAX_WEB_APP_PUBLIC_URL`;
- WebApp is served by the same Python process in the reference project.

Deep links:

- button URL format:

```text
https://max.ru/<bot_username>?startapp=<payload>
```

- payload stores a compact post reference;
- WebApp reads `window.WebApp.initDataUnsafe.start_param`;
- fallback query parameter is supported for browser/dev mode.

WebApp auth:

- browser sends `X-Max-Init-Data` to backend;
- backend verifies MAX init data with HMAC using the bot token;
- verification checks duplicate keys, `hash`, `auth_date`, max age, user payload, and signature.

### max_secretary

- WebApp URL: `https://maxsecretary.ru`;
- mini app URL in MAX partner UI is separate from webhook subscription URL;
- routes include `/tasks`, `/dashboard`, `/group-assignments`;
- production MAX WebApp auth is still a known gap.

### Recommendation

For `max_secretary`, adapt the deep-link approach before relying on `open_app` callbacks:

- generate `https://max.ru/<bot_username>?startapp=task_<id>` or another compact payload;
- keep payload short and non-secret;
- pass actual task context through backend after WebApp auth, not through unsigned URL data;
- implement MAX init data verification before production pilot.

## 7. Buttons and callbacks

### bot_comment_max

Buttons:

- uses an `inline_keyboard` attachment;
- button type is `link`;
- URL opens the MAX mini app deep link;
- button text displays comment count.

No active callback flow was found:

- update types do not include `message_callback`;
- no `/answers` or callback-answer flow was found;
- no callback payload parser was found.

### max_secretary

Internal callback payload schema exists:

- `task:start:{task_id}`;
- `task:reply:{task_id}`;
- `task:confirm:{task_id}`;
- `task:accept:{task_id}:{response_id}`;
- `task:reject:{task_id}:{response_id}`;
- `task:snooze:*:{task_id}`;
- `task:open:{task_id}`.

### Recommendation

Do not copy callback assumptions from `bot_comment_max`; it does not exercise real MAX callback events. For demo-safe behavior, copy the proven link-button/deep-link pattern first, then add real callback handling after sandbox capture confirms the event shape.

## 8. Sender / outgoing messages

### bot_comment_max

Message sending:

- endpoint: `POST /messages`;
- query includes `chat_id` or `user_id`;
- JSON body includes:
  - `text`;
  - `notify`;
  - `format`, usually `markdown`;
  - optional `attachments`;
  - optional `link`.

Message editing:

- endpoint: `PUT /messages`;
- query includes `message_id`;
- can update text, attachments, and link.

Other useful methods:

- `GET /me`;
- `GET /updates`;
- `GET /messages/{message_id}`;
- `GET /chats/{chat_id}`;
- `GET /chats/{chat_id}/members`;
- `GET /chats/{chat_id}/members/admins`;
- upload flow through `/uploads`.

Error handling:

- raises `MaxApiError` with method, URL, HTTP code and response preview;
- no robust retry/rate-limit handling in the reference;
- logs may include request URL and response text, so secret-bearing URLs must be avoided.

### max_secretary

- `MaxApiClient` already isolates outgoing calls;
- it supports retry handling for temporary status codes;
- `NotificationDelivery` tracks pending/sent/failed/DM-unavailable states;
- current `send_task_card` is text-only and still has a TODO for native attachments/buttons.

### Recommendation

Transfer/adapt:

- query-based `chat_id`/`user_id` sending shape;
- `attachments` and `link` support in sender schemas;
- `PUT /messages` support for updating task cards later;
- `GET /me` as a startup credential check;
- `GET /chats/{chat_id}/members*` patterns for group assignment membership checks only after real permission behavior is verified.

Do not transfer raw error logging style without redaction.

## 9. Security comparison

| Area | bot_comment_max | max_secretary | Recommendation |
|---|---|---|---|
| Bot token auth | Raw token in `Authorization` header | Raw token in `Authorization` header | The 401 is likely credential/source issue, not missing prefix. Add a safe `/me` or `/subscriptions` checker. |
| Webhook secret | `X-Max-Bot-Api-Secret`, constant-time compare | `X-Max-Bot-Api-Secret` plus legacy `X-Max-Webhook-Secret` | Keep official header primary; remove legacy later. |
| Subscription setup | Built-in `GET`, `DELETE`, `POST /subscriptions` refresh | Manual checks only | Add a safe ops script; avoid automatic deletion unless explicitly requested. |
| Payload logging | Some structured warnings include keys and ids | Sanitized debug shape and masked ids | Keep max_secretary's stricter sanitization. |
| WebApp context | `startapp` payload + signed MAX init data | WebApp auth still not production-grade | Adapt init data verification before production pilot. |
| Buttons/callbacks | Link button opens mini app; no callback flow | Internal callback schema exists | Use link/deep-link for first real MAX demo; defer callbacks until capture. |
| Sender | Standard library client, no robust retry | httpx client with temporary retry handling | Keep max_secretary adapter; add attachment/link/edit support from reference. |
| Secrets storage | `.env`; `.env.example` placeholders | VPS `.env`; docs warn not to commit | Keep current secret policy; add pattern validation for subscription secret. |

## 10. Recommended implementation tasks for max_secretary

### P0

1. Fix token/header/subscription mismatch by re-checking the exact Bot API token source in MAX partner UI.
2. Replace VPS `MAX_WEBHOOK_SECRET` with a value matching `^[A-Za-z0-9_-]{5,256}$`.
3. Add a safe subscription check script based on the `bot_comment_max` flow.
4. Confirm `GET /subscriptions` succeeds before `POST /subscriptions`.
5. Create webhook subscription with official `X-Max-Bot-Api-Secret`.
6. Capture a real sanitized `message_created` payload.

### P1

1. Adapt real callback mapping after capturing `message_callback`.
2. Add link-button/deep-link task open flow using `https://max.ru/<bot_username>?startapp=<payload>`.
3. Add production MAX WebApp init data verification.
4. Add sender support for inline keyboard attachments and message editing.
5. Update `max_sandbox_audit.md` with sanitized real findings.

### P2

1. Improve retry and rate-limit handling after seeing real MAX errors.
2. Add safer debug tooling for subscription and payload capture.
3. Add a MAX sandbox smoke script that never prints credentials.
4. Remove legacy `X-Max-Webhook-Secret` once all tooling is migrated.

## 11. Do not transfer blindly

Do not copy:

- comments/post/channel-specific domain logic;
- SQLite schema and moderation logic;
- channel admin bootstrap and legacy binding flows;
- broad forward-payload heuristics without tests;
- raw exception messages that include full request URLs;
- anything that contains or could expose secrets;
- webhook subscription deletion behavior without explicit operator confirmation.

## 12. Open questions

- Which exact credential from MAX partner UI is accepted by `/subscriptions` for `max_secretary`?
- Should the first `max_secretary` subscription include only `message_created` and `bot_started`, or include `message_callback` immediately?
- What real reply metadata does MAX send for reply-to-message commands?
- Does MAX send callback data through `message_callback` exactly as expected by the current internal callback parser?
- Should task opening use `link` deep links first, or `open_app` buttons after sandbox confirmation?
- What MAX init data fields are available for group-chat-launched WebApp sessions?
