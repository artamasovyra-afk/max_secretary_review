# MAX Real Bot Sandbox Audit

Status: draft checklist for real MAX bot sandbox verification.

This document is for the `v1.1.0 — Chat-Native Task Flow` audit. It must be updated with real sanitized sandbox payloads before implementing reply-based task creation, callbacks, personal reminders, WebApp buttons, and snooze actions.

## 1. Test environment

- bot type: pending real sandbox test
- chat type: pending real sandbox test
- date: 2026-05-20
- app version / commit: v1.0.1 / 5f74c49
- MAX sender enabled: no by default (`MAX_SENDER_ENABLED=false`)
- webhook enabled: yes by configuration (`MAX_WEBHOOK_ENABLED=true`)
- webhook debug logging: off by default (`MAX_WEBHOOK_DEBUG_LOG=false`)

Sandbox requirements:

- use a test bot, not a production bot;
- use a test chat with non-sensitive messages;
- keep production `.env` unchanged;
- do not save bot credentials, webhook secrets, personal phone numbers, or production chat identifiers in this document;
- if raw payloads are needed, store only sanitized examples.

## 2. Text message event

Expected from MAX documentation and current adapter assumptions:

- an incoming text message is delivered as a message-created update;
- message payload should contain sender, recipient/chat, timestamp, message body, and message id;
- text is expected under message body or equivalent message text field.

Fields to verify in sandbox:

| Field | Sandbox result | Notes |
|---|---|---|
| `chat_id` | pending | Need exact field path. |
| `user_id` | pending | Need exact sender field path. |
| `message_id` | pending | Need exact message id field path. |
| `text` | pending | Need exact text field path. |
| `timestamp` | pending | Need format and timezone behavior. |
| sender profile fields | pending | Need list of safe fields returned by webhook. |
| chat type | pending | Need to confirm `chat`, `channel`, or `dialog`. |
| forwarded/replied data | pending | Need to confirm if absent for normal message. |

Safe structure example, without real values:

```json
{
  "update_type": "message_created",
  "message": {
    "recipient": {
      "chat_id": "CHAT_ID_MASKED"
    },
    "sender": {
      "user_id": "USER_ID_MASKED",
      "username": "USERNAME_MASKED"
    },
    "timestamp": 0,
    "body": {
      "mid": "MESSAGE_ID_MASKED",
      "text": "TEXT_REDACTED"
    }
  }
}
```

Current mapping into `NormalizedBotEvent`:

- `chat_id`: from `message.chat_id`, `message.recipient.chat_id`, `message.chat.chat_id`, or `message.chat.id`;
- `user_id`: from `message.user_id`, `message.sender.user_id`, `message.from.user_id`, or `message.sender.id`;
- `message_id`: from `message.body.mid`, `message.body.message_id`, `message.message_id`, or `message.id`;
- `text`: from `message.body.text` or `message.text`;
- `source`: `max`.

Current gap: `timestamp`, sender profile, chat type, and reply/forward metadata are not yet included in `NormalizedBotEvent`.

## 3. Reply message event

Test scenario:

1. In a test chat, send:

```text
Иван, подготовь отчет до пятницы
```

2. Reply to that message with:

```text
/задача
```

Fields to verify:

| Question | Sandbox result | Notes |
|---|---|---|
| Is there a `reply_to_message_id` or equivalent? | pending | MAX docs suggest linked message metadata may exist. |
| Is original text embedded in webhook payload? | pending | Required for zero-extra-call task creation. |
| Is original author embedded? | pending | Useful for audit/history and future assignment hints. |
| Is an additional API call required? | pending | If webhook only has linked message id, backend needs a fetch-message method. |

Expected implementation path:

- if original message text is embedded, create task directly from reply context;
- if only a linked message id is present, add a safe `get_message` method to MAX client;
- if reply metadata is not available, keep explicit `/задача <text> | ...` command as fallback.

## 4. Buttons / callbacks

Expected from MAX documentation:

- inline keyboard buttons are supported;
- callback buttons can generate callback-style webhook events;
- there is an API method to answer callback actions;
- bot messages can be edited through a message edit API in supported contexts.

Fields to verify:

| Item | Sandbox result | Notes |
|---|---|---|
| Inline buttons supported in group chat | pending | Need actual client behavior. |
| Callback event type | pending | Need exact update type and field names. |
| Callback id field | pending | Needed to answer callback. |
| Callback payload field | pending | Needed for task actions. |
| Payload size limit | pending | Need practical limit for task/action ids. |
| Can edit message after callback | pending | Need behavior in group chat and dialog. |
| Can remove/update keyboard | pending | Needed for accepted/done states. |

Backend additions likely needed:

- callback event normalization;
- callback payload schema with action, task id, response id, and optional snooze value;
- MAX client method for callback answers;
- MAX client method for sending inline keyboard task cards;
- safe fallback to text commands if callbacks are unavailable.

## 5. Direct messages

Questions to verify:

| Question | Sandbox result | Notes |
|---|---|---|
| Can bot send DM to user who started dialog? | pending | Needed for personal reminders. |
| Can bot send DM to user from group chat only? | pending | Important for reminder delivery. |
| What happens when DM is unavailable? | pending | Need status code and safe error category. |
| Is explicit bot start required? | pending | Need user onboarding rule. |
| Can unavailable DM be detected reliably? | pending | Needed for fallback strategy. |

Fallback strategy if DM is unavailable:

- send reminder to the source chat with a mention if supported;
- show reminder in WebApp/dashboard;
- include the task in daily manager summary;
- log a safe delivery status without blocking task workflow.

## 6. WebApp button

Expected from MAX documentation:

- there is an `open_app` style button type for opening an app from a bot message.

Questions to verify:

| Question | Sandbox result | Notes |
|---|---|---|
| Can WebApp open from group chat? | pending | Required for "Open task" button. |
| Can task context be passed? | pending | Need safe way to pass `task_id`. |
| Can user context be passed? | pending | Must not become final auth by itself. |
| URL/context length limits | pending | Need limit for deep links. |
| Desktop/mobile behavior | pending | Need manual client check. |

Expected implementation decision:

- pass only non-secret context such as `task_id`;
- do not trust URL user context as production auth;
- keep future MAX WebApp auth as a separate security task.

## 7. Message formatting

Expected from MAX documentation:

- messages support plain text;
- message text has a length limit;
- markdown and html formatting modes are documented;
- attachments and links are supported.

Sandbox checks:

| Formatting item | Sandbox result | Notes |
|---|---|---|
| Line breaks | pending | Verify mobile and desktop rendering. |
| Bullet lists | pending | Verify markdown/html behavior. |
| Numbered lists | pending | Verify markdown/html behavior. |
| Bold/italic/code | pending | Verify supported subset. |
| Links | pending | Verify display and safety behavior. |
| Long text near limit | pending | Verify API response and client rendering. |

Initial guidance:

- keep task cards short;
- prefer plain text with simple line breaks for MVP;
- avoid relying on complex formatting until sandbox rendering is verified.

## 8. API errors / rate limits

Expected from MAX documentation:

- common API statuses include client errors, unauthorized access, not found, rate limit, and service unavailable responses;
- API usage has request-rate recommendations.

Sandbox checks:

| Error scenario | Sandbox result | Notes |
|---|---|---|
| Invalid bot credentials | pending | Need status and response shape. |
| Invalid chat id | pending | Need safe error category. |
| Invalid user id | pending | Needed for DM fallback. |
| Missing recipient | pending | Needed for client validation. |
| Oversized message | pending | Needed for task card truncation. |
| Unsupported formatting mode | pending | Needed for formatting fallback. |
| Rate limit response | pending | Need to check retry headers. |
| Timeout/network failure | pending | Handled by http client, but needs operational guidance. |

Current backend retry logic:

- retries only safe outgoing MAX requests;
- treats temporary statuses as retryable;
- logs sender/client errors without breaking the core task workflow.

What to add after sandbox:

- map MAX error response bodies into stable internal error categories;
- preserve retry-after behavior if MAX returns such a header;
- add tests for the actual response schema observed in sandbox.

## 9. Impact on v1.1 implementation

| Feature | Supported by MAX? | Notes | Implementation decision |
|---|---|---|---|
| task creation from reply | partial | Docs indicate linked message metadata, but exact reply payload is pending sandbox capture. | Implement only after confirming reply metadata or fetch-message fallback. |
| inline buttons | partial | Docs indicate inline keyboards and callback-style events. | Add callback normalization and keyboard sender after capturing real callback payload. |
| personal reminders | partial | Docs indicate sending by user id, but DM availability rules are pending. | Implement DM with fallback to chat/WebApp once unavailable-DM error is known. |
| WebApp open task | partial | Docs indicate app-opening button type. | Add open-task button only with non-secret task context and future auth boundary. |
| snooze callbacks | partial | Depends on callback payload support and payload limits. | Implement as callback action if reliable; fallback to text commands. |

## 10. Recommendations

Before coding v1.1 features:

1. Enable `MAX_WEBHOOK_DEBUG_LOG=true` only in a sandbox environment.
2. Capture sanitized raw payload shape for a normal text message.
3. Capture sanitized raw payload shape for `/задача` sent as a reply.
4. Verify whether linked reply text and author are embedded.
5. If reply text is not embedded, validate message fetch API behavior.
6. Send a test inline keyboard and capture callback payload.
7. Test callback answer and message edit behavior.
8. Test direct messages before and after the user starts a bot dialog.
9. Test WebApp open button from group chat on mobile and desktop.
10. Test markdown/html rendering with short task card examples.
11. Capture representative API error responses and rate-limit behavior.
12. Update this document with real sanitized findings.
13. Only then implement reply-based task creation, inline actions, personal reminders, and snooze.

Do not commit real bot credentials, webhook secrets, raw personal data, production chat ids, or unsanitized payloads.
