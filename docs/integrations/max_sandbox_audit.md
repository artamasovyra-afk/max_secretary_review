# MAX Real Bot Sandbox Audit

Date: `2026-05-20`.

Status: documentation-based pre-audit. Real sandbox execution is pending because no MAX sandbox token or captured real webhook payloads are available in the current environment.

This document is a pre-implementation audit for `v1.1.0 — Chat-Native Task Flow`.
It does not introduce new product features and does not change application code.

## Scope

Target `v1.1.0` features that depend on real MAX behavior:

- task creation from reply message;
- natural deadline parsing;
- reminder snooze;
- personal reminders to assignees;
- inline task action buttons;
- daily manager summary.

Before coding these features, the project needs a real MAX bot sandbox check.

## Group Assignment Backend Stabilization — 2026-05-31

Status: implemented for the WebApp `Задача участникам чата` backend path.

- `member` cannot create group assignments.
- `chat_admin` can create group assignments only in an active chat where that actor is an active `chat_admin`.
- `chat_admin` cannot create group assignments in member-only chats, чужие chats, inactive chats, or chats without `max_chat_id`.
- `super_admin` can create group assignments in any active chat with `max_chat_id`.
- The API requires a deadline for WebApp group assignment creation and keeps future-deadline validation.
- The service supports explicit selected `assignee_ids`; omitted `assignee_ids` preserves the existing “all active chat members” behavior.
- Selected assignees are deduplicated, must be active members of the selected chat, and inactive/out-of-chat users are rejected.
- `exclude_creator=true` removes the actor from selected or implicit assignees.
- After successful creation, the API sends one clean summary message to the source MAX chat with task ref, text, assignee display names, project-local deadline, report requirement, and an `Открыть Дьяк` deep-link button.
- The summary message does not include UUIDs, raw task/user/chat ids, MAX ids, or callback payloads.
- Deadline scheduler, reminder selection, production flags, and worker jobs were not changed.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Group Assignment WebApp Screen Polish — 2026-05-31

Status: implemented for the customer-facing WebApp screen `Задача участникам чата`.

- The navigation item is hidden for plain `member` users; a direct route opens a friendly no-access state instead of the form.
- The chat dropdown is limited to available active chats: own admin chats for `chat_admin`, all active chats for `super_admin`.
- Chat display titles use the shared safe display-title helper and do not expose UUIDs, `max_chat_id`, generated `MAX chat #...` labels, or raw ids.
- Selecting a chat loads active chat participants and resets the previous participant selection.
- The participants selector supports search, explicit select/deselect, `Выбрать всех`, and `Снять всех`.
- Participant labels show display name, Dyak role, and `вы` for the current user without raw user ids.
- `Не назначать постановщику` removes the actor from selected assignees and keeps `Выбрать всех` from re-adding the actor.
- The form requires chat, at least one assignee, task text, and a future deadline before submission.
- The payload sends explicit selected `assignee_ids` to the verified backend path.
- Friendly errors are shown for insufficient permissions, missing assignees, inactive chat, out-of-chat assignee, and past deadline.
- DatePicker localization, Monday-first week, visible footer controls, and mobile overflow guards remain in place.
- Deadline scheduler, reminder selection, production flags, worker jobs, and backend code were not changed.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Real MAX Chat Participants Task Flow Check — 2026-05-31

Status: completed on the production VPS after deploying `095b94b`.

- VPS HEAD: `095b94b`.
- VERSION remained `1.1.0-rc.3`.
- Route and menu access work as expected.
- Plain `member` users do not see `Задача участникам чата`; direct route opens a friendly no-access state.
- `chat_admin` users can open the screen.
- The chat dropdown shows only allowed active chats.
- Chat names are clean and do not expose UUIDs, raw ids, or generated `MAX chat #...` labels.
- Participants load after chat selection.
- `Выбрать всех` and `Снять всех` work.
- `Не назначать постановщику` works.
- Form validation works.
- DatePicker remains Russian, Monday-first, with visible `OK` and `Сейчас`.
- Creating a task for selected chat participants works.
- The source MAX chat receives one clean final summary message.
- Task refs and assignee display names are visible.
- UUIDs, raw ids, callback payloads, and technical fields are not visible in user-facing messages.
- Created tasks appear on the `Задачи` screen.
- Chat filter finds the created tasks.
- Task action sheet works for created tasks.
- Mobile layout has no horizontal scroll.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## WebApp task action sheet — 2026-05-31

Status: implemented for the task list WebApp UX.

- Tapping a task card now opens a bottom action sheet instead of immediately navigating away from the list.
- The sheet shows only user-facing fields: task ref, title, status, deadline, assignees, creator, and a short report status.
- The sheet keeps `Открыть полностью`, which preserves the existing task detail route.
- Role/status-aware actions are shown only when available: report submission for assignees, accept/reject for waiting-acceptance reviewers, and deadline/assignee edits for task managers.
- Completed/final tasks show no working actions and remain openable through the full detail view.
- `Пинг` is not shown in the sheet because there is no ready WebApp API for that action yet.
- User-facing sheet content strips UUID-like values, callback payload markers, and technical metadata lines.
- The implementation uses existing task APIs and does not change deadline scheduler, reminder selection, production flags, or MAX bot flows.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## WebApp task action form modals — 2026-05-31

Status: implemented as a UX fix for the task action sheet.

- The task action sheet remains a short action menu and no longer renders report/reject/deadline/assignee forms inline below the visible viewport.
- `Написать отчет`, `Отклонить`, `Изменить срок`, and `Изменить исполнителей` now open separate modals over the action sheet.
- Modal bodies are scrollable and capped to the mobile viewport so text areas, date/time picker, select, and footer buttons remain visible.
- `Принять` now opens a confirmation modal and does not call the accept API before the user confirms.
- Existing backend APIs and role/status policies are preserved.
- Deadline scheduler, reminder selection, production flags, and MAX bot flows were not changed.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## WebApp task deadline picker localization — 2026-05-31

Status: implemented after the MAX WebApp modal live check found DatePicker issues.

- Ant Design locale is set to Russian through the shared WebApp `ConfigProvider`.
- Dayjs locale is set to `ru`, with Monday configured as the first day of the week.
- Date/time pickers use the user-facing format `DD.MM.YYYY HH:mm`.
- The task deadline edit modal DatePicker uses a bounded popup class/container so the calendar does not overflow left in the MAX WebApp mobile viewport.
- The picker dropdown is additionally reduced by about 5% and horizontal overflow is hidden for mobile WebApp containers.
- The DatePicker/Calendar locale object explicitly uses the Dayjs `ru` locale and Monday week start while keeping weekday labels indexed in the order expected by rc-picker.
- Date/time pickers explicitly enable the standard footer quick action and use Russian labels: `Сейчас` for the current moment, `Сегодня` where date-only pickers use today, and a visible `OK` apply button.
- The DatePicker footer is styled inside the bounded mobile popup so `Сейчас` and `OK` remain visible and clickable without reintroducing horizontal scroll.
- Past-deadline validation remains in the WebApp and backend validation remains the source of truth.
- Report, reject, assignee edit, and accept confirmation modals were not changed functionally.
- Backend, deadline scheduler, reminder selection, and production flags were not changed.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Real MAX DatePicker footer controls check — 2026-05-31

Status: live MAX WebApp check passed.

- Deployed commit: `a1a541d`.
- `OK` apply button visible: yes.
- `Сейчас` restored for date/time picker: yes.
- `Сегодня` restored where applicable: yes.
- Russian locale preserved: yes.
- Monday first preserved: yes.
- Horizontal scroll absent: yes.
- Task deadline picker checked: yes.
- Group assignment picker checked: yes.
- Future deadline save: yes.
- Past deadline validation: yes.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Real MAX WebApp task action sheet check — 2026-05-31

Status: live MAX WebApp check passed.

- Deployed commit: `ee6ca40`.
- Card tap opens action sheet: yes.
- Role/status-aware actions: yes.
- `Открыть полностью` opens the task detail route: yes.
- Report action works: yes.
- Accept/reject action works: yes.
- Rejection reason is required for reject: yes.
- Deadline edit works with future-deadline validation: yes.
- Assignee edit works: yes.
- UUID/raw ids/callback payload are hidden: yes.
- Mobile layout is readable and the sheet can be closed: yes.
- Smoke result: `release_smoke=ok`.
- Deadline reminder flags were unchanged.
- Remaining gaps: `Пинг` is intentionally hidden until a WebApp API exists.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Report wizard cleanup — 2026-05-31

Status: implemented for `/отчет` report submission flows.

- `/отчет #номер` without text now creates a `task_report_submit` wizard and sends one editable bot prompt.
- The `Написать отчет` callback starts the same wizard and tracks the callback answer message id when MAX returns one.
- A successful report edits the wizard message into `Отчет по задаче #... отправлен ✅` and keeps the waiting-acceptance notification clean.
- Inline `/отчет #номер текст` submits immediately and can clean the command message when wizard input cleanup is enabled.
- When `TASK_WIZARD_DELETE_USER_INPUTS=true`, report cleanup deletes only exact saved input message ids for the current actor and pending action.
- Other users' messages, messages between wizard steps, source task messages, final bot messages, `/задача`, `/пинг`, and `#номер` messages are preserved.
- Empty report text edits the report wizard with a validation error and keeps the pending action open.
- Cleanup does not use timestamps, ranges, raw ids, or payload matching.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Real MAX clean report wizard flow check — 2026-05-31

Status: live controlled check passed.

- Deployed commit: `0da1f30`.
- `/отчет #номер` wizard works: yes.
- Report prompt edits to final: yes.
- `/отчет` command message deleted: yes.
- Report text message deleted: yes.
- Immediate `/отчет #номер текст` works: yes.
- Immediate report command cleaned: yes.
- Callback `Написать отчет` works: yes.
- Waiting acceptance notification is clean: yes.
- Other user messages were preserved: yes.
- No payload, UUID, raw ids, or callback payload appeared in user-facing messages.
- Deadline flags were unchanged during the check.
- Smoke result: `release_smoke=ok`.
- Visual issues reported: no.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Task wizard validation cleanup — 2026-05-31

Status: implemented for bot-side task creation wizard validation errors.

- Deadline and assignee validation errors edit the current `/задача` wizard message instead of sending a separate bot error message.
- The pending action remains open after invalid input, so the same user can continue with a corrected deadline or `@mention`.
- When `TASK_WIZARD_DELETE_USER_INPUTS=true`, invalid wizard input messages are deleted best-effort after processing.
- Cleanup is exact-message-id based and scoped to the current actor and pending action. It does not use time ranges or delete "all messages between" wizard steps.
- Source reply messages, final task cards, `/отчет`, `/пинг`, `#номер`, and ordinary messages from other chat participants are preserved.
- Delete failures are diagnostic only and do not create or roll back tasks.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Real MAX invalid wizard input cleanup check — 2026-05-31

Status: live controlled check passed.

- Deployed commit: `695fa9e`.
- Invalid deadline edits the existing wizard message: yes.
- Extra bot error messages avoided: yes.
- Invalid user inputs were deleted: yes (`Через пол часа`, `Завтра через час`).
- Pending action was preserved after invalid deadlines: yes.
- Valid deadline continued the same wizard flow: yes.
- Missing `@mention` error uses wizard edit: yes.
- User message without `@` was deleted as invalid wizard input: yes.
- Final task card was preserved: yes.
- Other user messages were preserved: yes.
- Cleanup uses exact saved message ids only.
- No range or timestamp cleanup is used.
- Visual issues reported: no.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Task wizard bot mention self-assignee priority — 2026-05-31

Status: implemented as a pending-flow priority fix.

- Root cause: bot mention help aliases were parsed before the active `task_create_select_assignee` pending handler, so `@secretary_oren_bot` could open command help instead of selecting an assignee.
- While assignee selection is pending, bot mentions are now handled by the pending assignee flow before command parsing.
- `@Дьяк`, `@secretary_oren_bot`, `@secretary_oren_bot /`, and `@secretary_oren_bot помощь` mean “assign to the current actor” in that step.
- `@secretary_oren_bot` plus participant mentions creates a multi-assignee task for the actor and resolved participants, with normal deduplication.
- Outside pending assignee selection, mention-prefix help aliases still return the command list and do not create tasks.
- If wizard input cleanup is enabled, the bot-mention wizard input is still cleaned up by exact saved message id after successful task creation.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Real MAX bot mention self-assignee check — 2026-05-31

Status: live controlled check passed.

- Deployed commit: `da99674`.
- `@bot` in the assignee-selection step creates a self-task for the current actor: yes.
- Help was not shown in the pending assignee flow: yes.
- Test task created: `#69`.
- Wizard input cleanup remained active and completed after the final card: yes.
- `@bot + @user` live check: skipped, covered by regression tests.
- Help aliases outside pending flow: skipped live, covered by regression tests.
- Smoke result after deploy: `release_smoke=ok`.
- Runtime errors observed: no.
- Secret leak observed: no.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Current Local Environment

Local environment check:

- sandbox bot token: not configured;
- webhook secret: not configured;
- MAX API base URL override: not configured.

Result: real API calls and real webhook capture were not executed.

## Existing max_secretary Adapter State

Current backend already has:

- `POST /api/bot/max/webhook`;
- normalized bot event support;
- MAX-like event normalization;
- command parser;
- `MaxSender`;
- MAX API client adapter;
- webhook secret validation through the official `X-Max-Bot-Api-Secret` header;
- temporary legacy secret validation through `X-Max-Webhook-Secret` for internal compatibility.

Current normalization extracts:

- chat id from `message.chat_id`, `message.recipient.chat_id`, `message.chat.chat_id`, or `message.chat.id`;
- user id from `message.user_id`, `message.sender.user_id`, `message.from.user_id`, or `message.sender.id`;
- message id from `message.body.mid`, `message.body.message_id`, `message.message_id`, or `message.id`;
- text from `message.body.text` or `message.text`.

Current command flow resolves external MAX `user_id` and `chat_id` into internal `User.id` and `Chat.id` records before task creation.

## Webhook Subscription API Check

Date: `2026-05-22`.

The MAX control panel accepts the mini app URL separately from the bot webhook URL. The configured mini app URL is:

```text
https://maxsecretary.ru
```

The webhook URL for max_secretary remains:

```text
https://maxsecretary.ru/api/bot/max/webhook
```

Official MAX docs indicate that bot webhook delivery is configured through the `/subscriptions` API:

- `GET /subscriptions` returns the current subscription;
- `POST /subscriptions` creates or updates the webhook subscription;
- request body supports `url`, `update_types`, `version`, and optional `secret`;
- the official `secret` value must match `[A-Za-z0-9_-]`, length 5-256;
- when configured, the official secret is delivered in the `X-Max-Bot-Api-Secret` request header.

Sanitized VPS configuration check:

- `MAX_WEBHOOK_ENABLED`: `true`;
- `MAX_SENDER_ENABLED`: `true`;
- `MAX_API_BASE_URL`: `https://platform-api.max.ru`;
- bot credential: set, length-only verified;
- webhook secret: set, length-only verified;
- `MAX_WEBHOOK_DEBUG_LOG`: `true`.

Initial subscription API results before credential replacement:

- `GET /subscriptions`: HTTP `401`, sanitized body code `verify.token`, invalid credential message;
- `POST /subscriptions`: HTTP `401`, sanitized body code `verify.token`, invalid credential message;
- subscription created: no.

Updated subscription API results after replacing the bot credential and using a MAX-compatible webhook secret:

- `GET /subscriptions`: HTTP `200`;
- `POST /subscriptions`: HTTP `200`;
- subscription created: yes;
- webhook URL: `https://maxsecretary.ru/api/bot/max/webhook`;
- subscription update types: `message_created`, `bot_started`;
- official secret header: `X-Max-Bot-Api-Secret`.

Additional finding from the `2026-05-22` VPS check before official-header support was added:

- the current VPS webhook secret is set, but it does not match the official `/subscriptions.secret` character policy;
- backend validation expected `X-Max-Webhook-Secret`;
- official MAX docs describe `X-Max-Bot-Api-Secret`;
- therefore real MAX webhook events were expected to be rejected by that backend version.

Backend logs checked after the subscription attempts. No real MAX webhook delivery was observed. The only recent webhook entries were earlier sanitized mock checks.

Backend action added after this finding:

- support validating the official `X-Max-Bot-Api-Secret` header with constant-time comparison;
- keep temporary support for the legacy `X-Max-Webhook-Secret` header for internal compatibility;
- keep the existing disabled/missing/invalid-secret rejection behavior;
- update tests for missing, invalid and valid official header and legacy compatibility;
- use a MAX-compatible webhook secret value in the VPS `.env`;
- retry `/subscriptions` after the bot credential is accepted by the API.

## Real Sandbox Capture — 2026-05-22

### 1. Environment

- app version: `1.1.0-rc.1`;
- webhook URL: `https://maxsecretary.ru/api/bot/max/webhook`;
- subscription update types: `message_created`, `bot_started`;
- debug logging enabled during capture: yes;
- debug logging disabled after capture: yes.

Only sanitized event shapes were used for this report. Full raw payloads, full user ids, full chat ids, full message ids, bot credential, and webhook secret were not copied into documentation.

### 2. Subscription

- `GET /subscriptions` status: HTTP `200`;
- subscription created: yes;
- subscribed URL: `https://maxsecretary.ru/api/bot/max/webhook`;
- subscribed update types: `message_created`, `bot_started`;
- official secret header confirmed: yes. Real webhook events were accepted by the backend after subscription creation, which confirms MAX sent the configured secret through the supported official path.

### 3. Bot Started Payload

A real start/dialog event was observed before the normal message capture.

Sanitized shape:

```text
top_level_keys:
- chat_id
- timestamp
- update_type
- user
- user_id
- user_locale

user:
- avatar_url
- first_name
- full_avatar_url
- is_bot
- last_activity_time
- last_name
- name
- user_id
```

Current backend result:

- HTTP status: `422`;
- required backend change: support this real `bot_started` shape as an ignored or handled event instead of returning validation error.

### 4. Text Message Payload

Real ordinary message tested:

```text
привет
```

Sanitized shape:

```text
top_level_keys:
- message
- timestamp
- update_type
- user_locale

message.body:
- mid
- seq
- text

message.recipient:
- chat_id
- chat_type
- user_id, present in dialog context

message.sender:
- first_name
- is_bot
- last_activity_time
- last_name
- name
- user_id

message.timestamp:
- present
```

Normalized backend result:

- `chat_id`: present and masked in debug logs;
- `user_id`: present and masked in debug logs;
- `message_id`: present and masked in debug logs;
- `text`: present;
- `text_length`: captured;
- `is_command`: false;
- backend response: HTTP `200`.

### 5. Reply Payload

Reply command scenarios were executed with:

```text
Иван, подготовь отчет до пятницы
```

and:

```text
Проверить доступ завтра в 15:00
```

followed by:

```text
/задача
```

Sanitized reply command shape:

```text
top_level_keys:
- message
- timestamp
- update_type
- user_locale, present in dialog context

message.body:
- mid
- seq
- text

message.link:
- chat_id
- message
- sender
- type

message.link.message:
- mid
- seq
- text

message.link.sender:
- first_name
- is_bot
- last_activity_time
- last_name
- name
- user_id

message.recipient:
- chat_id
- chat_type
- user_id, present in dialog context

message.sender:
- first_name
- is_bot
- last_activity_time
- last_name
- name
- user_id
```

Finding:

- `reply_to_message_id` field name is not sent directly at top level;
- equivalent source message id is available at `message.link.message.mid`;
- original source text is available at `message.link.message.text`;
- original source author is available at `message.link.sender`;
- no extra API call is required for these tested reply payloads because MAX embedded the linked message body and sender in `message.link`.

Captured backend gap before follow-up implementation:

- current normalizer does not map `message.link` into `NormalizedBotEvent.reply_to_message_id`;
- current normalizer does not map `message.link.message.text` into `NormalizedBotEvent.reply_to_text`;
- current normalizer does not map `message.link.sender.user_id` or name into reply author fields;
- normalized debug output for reply commands did not show reply metadata;
- reply command events were accepted with HTTP `200`, and bot replies were sent to the test chat, but no new tasks were created in the database during the capture window.

Implementation update:

- follow-up backend change maps real MAX `message.link` metadata into `NormalizedBotEvent.reply_to_*`;
- sanitized dialog and group reply fixtures were added for this real-shape payload;
- self-task creation from a real-like reply payload is covered by tests.

### 6. Self-Task From Reply

Observed result:

- reply to another message: captured;
- reply to own message: captured;
- task assigned to command author: no;
- task created from reply: no;
- deadline parsed from reply: no;
- `source_message_id` saved: no.

Reason:

- the implemented self-task behavior depends on `NormalizedBotEvent.reply_to_text`;
- real MAX reply payload carries the source message under `message.link`, which is not yet normalized.

### 7. Callback Payload

Status: captured later; see "Real MAX Callback Capture — 2026-05-23".

Initial capture status:

- `message_created`;
- `bot_started`.

No real `message_callback` event was captured in this run. Callback capture requires adding the official callback update type to the subscription and sending a bot message with callback buttons.

### 8. DM Behavior

Status: pending.

No dedicated direct-message availability test was executed beyond the user dialog used for sandbox messages. The bot did send ordinary command responses to the test chat/dialog through `POST /messages`, and MAX returned HTTP `200` for those test replies.

### 9. WebApp Button

Status: pending.

No `open_app` or deep-link button was tested in this capture. The WebApp URL remains:

```text
https://maxsecretary.ru
```

### 10. Required Backend Changes

P0 before relying on reply task creation:

- done: map real MAX reply metadata from `message.link` into `NormalizedBotEvent.reply_to_message_id`;
- done: map `message.link.message.text` into `NormalizedBotEvent.reply_to_text`;
- done: map `message.link.sender.user_id` into `NormalizedBotEvent.reply_to_author_id`;
- done: map `message.link.sender.name` or display fields into `NormalizedBotEvent.reply_to_author_display_name`;
- done: add tests using sanitized real-shape fixtures for dialog and group reply payloads;
- done: support the observed `bot_started` shape without returning HTTP `422`.

P1 before callback demo:

- add `message_callback` to the subscription only when callback capture is planned;
- capture sanitized callback payload;
- map real callback payload into the existing task callback actions.

P1 before production pilot:

- add real MAX id mapping/autocreate for users and chats, or define a controlled mapping workflow;
- confirm direct-message availability and fallback behavior;
- confirm WebApp open/deep-link behavior.

### 11. Notes

- No bot credential or webhook secret was printed or committed.
- No full raw payload was committed.
- Debug logging was disabled after capture by setting `MAX_WEBHOOK_DEBUG_LOG=false` in the VPS `.env` and recreating backend/worker.
- Mass sending was not performed.
- The only outbound MAX messages during this capture were automatic bot responses in the test chat/dialog.

## Real Reply Task Flow Check — 2026-05-22

### Environment

- backend commit: `987ac90 fix: map real MAX reply metadata`;
- app version: `1.1.0-rc.1`;
- test type: ordinary MAX message followed by reply command `/задача`;
- debug logging enabled only during the check: yes;
- debug logging disabled after the check: yes.

### Observed Result

The live reply command was received and accepted by the webhook endpoint.

Sanitized normalized debug shape confirmed:

- ordinary message: `reply_to_message_id` absent, `reply_to_text_length=0`;
- reply command: `reply_to_message_id` present and masked;
- reply command: `reply_to_text_length` present and non-zero;
- reply command: `reply_to_author_id` present and masked;
- backend response to webhook: HTTP `200`.

Confirmed real MAX mapping:

- `message.link.message.mid` -> `NormalizedBotEvent.reply_to_message_id`;
- `message.link.message.text` -> `NormalizedBotEvent.reply_to_text`;
- `message.link.sender` -> `NormalizedBotEvent.reply_to_author_*`.

Task flow result:

- real reply metadata mapping: passed;
- real reply task creation: failed/blocked;
- self-task assigned to command author: no persisted task;
- deadline parsed into persisted task: no persisted task;
- `source_message_id` saved: no persisted task;
- task visible in WebApp: no.

Reason:

- real MAX webhook supplies external MAX `chat_id` and `user_id`;
- current command execution still expects internal `Chat.id` and `User.id` UUIDs;
- task creation is blocked before persistence because external MAX ids are not mapped/autocreated to internal records.

Historical backend gap identified by this check:

- MAX external id mapping/autocreate for chats and users was required before real reply-created tasks could persist;
- after deploying the mapping, rerun the same live `/задача` reply scenario and verify `deadline_at`, `source_message_id`, assignee and WebApp visibility.

## MAX External Identity Mapping

Implementation status: added after the real reply metadata capture.

The bot command flow now treats real MAX identifiers as external ids:

- MAX `sender.user_id` / normalized `event.user_id` maps to `User.max_user_id`;
- MAX `recipient.chat_id` / normalized `event.chat_id` maps to `Chat.max_chat_id`;
- internal `User.id` and `Chat.id` remain UUID primary keys and are used for task persistence;
- a default organization named `MAX default organization` is created or reused for bot-created MAX chats;
- new MAX users and chats are autocreated from webhook payload data without calling the MAX API;
- repeated webhooks for the same external user/chat reuse the same internal records;
- the command author is ensured as an active `member` of the resolved chat;
- reply author metadata is preserved as source context but is not assigned automatically;
- `/задача` as a reply without explicit assignee is assigned to the command author;
- Bitrix24 organization hierarchy remains future work.

The next live sandbox check should rerun the same reply scenario and verify:

- task is persisted;
- assignee is the command author;
- `deadline_at` is parsed from `message.link.message.text`;
- `source_message_id` stores the linked MAX message id;
- the task appears in the WebApp.

## Real Reply Task Flow After Identity Resolver — 2026-05-22

### Environment

- backend commit: `11f3d36 feat: resolve MAX external identities for bot tasks`;
- app version: `1.1.0-rc.1`;
- test type: ordinary MAX message followed by reply command `/задача`;
- debug logging enabled only during the check: yes;
- debug logging disabled after the check: yes.

### Result

The live reply command was received and accepted by the webhook endpoint.

Sanitized normalized debug shape confirmed:

- ordinary message: accepted, no reply metadata;
- reply command: accepted, `message.link` mapped into `reply_to_*`;
- `reply_to_message_id`: present and masked;
- `reply_to_text_length`: present and non-zero;
- `reply_to_author_id`: present and masked;
- backend response to webhook: HTTP `200`.

Task flow result:

- external MAX user id resolved to internal `User.id`: yes;
- external MAX chat id resolved to internal `Chat.id`: yes;
- default organization behavior: `MAX default organization` reused, single record observed;
- task created from reply `/задача`: yes;
- self-task assigned to command author: yes;
- deadline parsed from `завтра в 15:00`: yes;
- `source_message_id` saved from linked MAX message id: yes;
- task persisted with one assignee, and the assignee matched the creator;
- WebApp route `/tasks` returned HTTP `200`; task persistence was verified through a sanitized database check.

Idempotency check:

- repeated webhook events from the same MAX user/chat did not create duplicate external-user records;
- repeated webhook events from the same MAX user/chat did not create duplicate external-chat records;
- `users_with_max_id == distinct_max_users` in the sanitized check;
- `chats_with_max_id == distinct_max_chats` in the sanitized check.

Additional finding:

- after recreating the worker with `MAX_SENDER_ENABLED=true`, reminder delivery attempted real MAX `POST /messages` calls for existing internal UUID users and received HTTP `400`;
- no successful mass delivery was observed, but the attempts are a production-safety gap;
- `MAX_SENDER_ENABLED` was set to `false` after the check to stop further outbound attempts;
- before enabling sender again, notification delivery must use MAX external ids (`User.max_user_id`) or skip users without a MAX external id.

Outbound delivery rule:

- internal `User.id` and `Chat.id` values are database identifiers only and must never be sent to the MAX Bot API as recipients;
- personal MAX delivery resolves internal `User.id` to `User.max_user_id` before calling `/messages`;
- group/chat fallback delivery resolves internal `Chat.id` to `Chat.max_chat_id` before calling `/messages`;
- users without `User.max_user_id` are marked as delivery unavailable and skipped without a MAX API call;
- chats without `Chat.max_chat_id` are marked as delivery unavailable/failed and skipped without a MAX API call;
- `MAX_SENDER_ENABLED` should stay `false` on production until this recipient mapping fix is deployed and verified.

## Real MAX Sender Single-Message Test — 2026-05-22

Environment:

- deployed backend commit: `34494e3 fix: send MAX notifications to external recipient ids`;
- app version: `1.1.0-rc.1`;
- sender enabled during test: yes;
- sender state after test: disabled again for safety;
- test scope: one personal notification to one sandbox user with `User.max_user_id`;
- mass sends: no;
- scheduler/daily summary jobs were not manually triggered.

Result:

- test recipient with `User.max_user_id`: found;
- delivery path: `NotificationDeliveryService.send_personal_task_notification`;
- recipient mapping: internal `User.id` -> `User.max_user_id`;
- internal UUID sent to MAX API: no;
- external MAX user id used as `/messages` recipient: yes;
- real MAX API send attempts during controlled test: one;
- message text: `Тестовое уведомление Дьяк`;
- delivery status: sent;
- fallback/group send attempts: none;
- HTTP `400` internal-UUID issue: not reproduced;
- token/secret leak in logs: no;
- full external user/chat/message ids committed: no.

Operational note:

- `MAX_SENDER_ENABLED` was returned to `false` after the single-message test to avoid accidental reminder backlogs while callback, DM and WebApp-button sandbox checks remain pending.

## Real MAX WebApp Button Test — 2026-05-22

Environment:

- deployed backend commit: `0d1eae6 feat: add MAX WebApp open button support`;
- app version: `1.1.0-rc.1`;
- sender enabled during test: yes;
- sender state after test: disabled again for safety;
- test scope: one personal message to one sandbox user with `User.max_user_id`;
- mass sends: no;
- scheduler/daily summary jobs were not manually triggered.

Message and button:

- message sent: yes;
- button displayed in MAX: yes;
- button text: `Открыть Дьяк`;
- button type: `link`;
- URL used: `https://maxsecretary.ru`;
- WebApp opened: yes;
- open location: external browser;
- opened inside MAX: no.

Result:

- link button delivery through MAX Bot API: passed;
- plain WebApp URL opens correctly from MAX client;
- plain URL opens in an external browser, not inside MAX;
- deep link / `startapp` flow was not tested in this step;
- native `open_app` button type was not tested in this step;
- token/secret leak in logs: no;
- full external user/chat/message ids committed: no.

Remaining gaps:

- callback payload capture: pending;
- DM behavior: pending;
- inside-MAX WebApp deep link / `startapp` behavior: pending;
- native `open_app` button behavior: pending;
- broader production reminder delivery verification with external MAX ids: pending.

## Real MAX Deep Link / Startapp Button Test — 2026-05-22

Environment:

- deployed backend commit before the test: `23a6899 docs: confirm MAX WebApp button behavior`;
- WebApp button support commit: `0d1eae6 feat: add MAX WebApp open button support`;
- app version: `1.1.0-rc.1`;
- sender enabled during test: yes;
- sender state after test: disabled again for safety;
- test scope: one personal message to one sandbox user with `User.max_user_id`;
- mass sends: no;
- scheduler/daily summary jobs were not manually triggered.

Message and button:

- message sent: yes;
- button displayed in MAX: yes;
- button text: `Открыть Дьяк в MAX`;
- button type: `link`;
- URL format used: `https://max.ru/<bot_username>?startapp=home`;
- `startapp` payload used: `home`;
- payload contains user ids, tokens, secrets, or personal data: no.

Result:

- deep link tested: yes;
- WebApp opened: yes;
- opened inside MAX: yes;
- working format for inside-MAX open: `https://max.ru/<bot_username>?startapp=home`;
- native `open_app` button type was not tested in this step;
- token/secret leak in logs: no;
- full external user/chat/message ids committed: no.

Updated gaps:

- callback payload capture: pending;
- DM behavior: pending;
- native `open_app` button behavior: pending;
- broader production reminder delivery verification with external MAX ids: pending.

## Real MAX Callback Capture — 2026-05-23

Environment:

- app version: `1.1.0-rc.1`;
- subscription before update: `message_created`, `bot_started`;
- subscription update request: `POST /subscriptions`;
- subscription after update: `message_callback`, `message_created`, `bot_started`;
- sender enabled during test: yes;
- debug logging enabled during capture: yes;
- sender and debug logging after capture: disabled again for safety;
- test scope: one personal message to one sandbox user with `User.max_user_id`;
- mass sends: no;
- scheduler/daily summary jobs were not manually triggered.

Controlled test message:

- message sent: yes;
- message text: `Тест callback-кнопки Дьяк`;
- button displayed in MAX: yes;
- button type: `callback`;
- button text: `Проверить callback`;
- callback payload: `test:callback:ping`;
- payload contains user ids, tokens, secrets, or personal data: no.

Observed webhook shape:

- callback webhook received: yes;
- HTTP status returned by backend: `200`;
- top-level keys:
  - `callback`;
  - `message`;
  - `timestamp`;
  - `update_type`;
  - `user_locale`;
- official/inferred callback update type: `message_callback`;
- exact raw `update_type` value was not printed by sanitized debug logging.

Callback paths:

- callback id path: `callback.callback_id`;
- callback payload path: `callback.payload`;
- callback timestamp path: `callback.timestamp`;
- callback actor path: `callback.user.user_id`;
- callback actor display fields observed as shape:
  - `callback.user.first_name`;
  - `callback.user.last_name`;
  - `callback.user.name`;
  - `callback.user.is_bot`;
  - `callback.user.last_activity_time`.

Message context paths:

- original bot message id path: `message.body.mid`;
- original bot message text path: `message.body.text`;
- original bot message attachments path: `message.body.attachments`;
- chat path: `message.recipient.chat_id`;
- chat type path: `message.recipient.chat_type`;
- recipient user path: `message.recipient.user_id`;
- bot sender path: `message.sender.user_id`;
- bot sender username path: `message.sender.username`.

Current backend behavior:

- webhook authentication with `X-Max-Bot-Api-Secret`: passed;
- raw callback shape was logged only in sanitized form;
- captured before implementation: `normalize_max_event` did not extract `callback.payload` or `callback.callback_id`;
- captured before implementation: the normalizer treated the event as a regular message event because `message.body.text` was present;
- captured before implementation: existing `callback_service` was not invoked.

Implementation update:

- real MAX callback events are now detected before ordinary message normalization;
- `callback.payload` is mapped and routed to the existing `callback_service`;
- `callback.callback_id` is stored for callback answer/idempotency;
- callback actor is resolved from external `callback.user.user_id` to internal `User.id`;
- message context is preserved from `message.recipient` and `message.body`;
- `POST /answers` support was added for callback notification answers;
- DB-backed callback idempotency was added through unique `callback_id` receipts;
- sanitized fixture/test coverage was added for the real callback shape.

Retry / duplication note:

- multiple callback webhook deliveries were observed after the manual test click;
- cause is not yet confirmed;
- likely explanations are repeated client click or MAX retry because the backend does not yet call `POST /answers`;
- implementation should add idempotency around `callback.callback_id` and send a callback answer.

Required backend changes:

- done: add real MAX callback normalization before ordinary message normalization;
- done: map `callback.payload` into the internal callback payload;
- done: map `callback.callback_id` for answer/idempotency;
- done: map actor from `callback.user.user_id` through `User.max_user_id` into internal `User.id`;
- done: map chat/message context from `message.recipient` and `message.body`;
- done: route real callback events into existing `callback_service`;
- done: add `POST /answers` support for callback notification answers;
- done: add sanitized fixtures and tests for this real callback shape;
- keep callback payloads free of secrets and personal data.

Remaining gaps:

- live task callback actions after deployment: pending;
- live `POST /answers` behavior after deployment: pending;
- DM unavailable behavior: pending;
- native `open_app` button behavior: pending.

## Real MAX Callback Button Retest — 2026-05-23

Context:

- deployed backend commit before retest: `dde8e51 fix: send active MAX callback buttons`;
- previous controlled callback message rendered a visible but inactive MAX button;
- root cause: the one-off callback button payload omitted the MAX button `intent` field;
- reference source: the official MAX Go SDK models `CallbackButton` as `type`, `text`, `payload`, and optional `intent`, defaulting to `default`.

Correct callback button shape:

```json
{
  "type": "inline_keyboard",
  "payload": {
    "buttons": [
      [
        {
          "type": "callback",
          "text": "Проверить callback",
          "payload": "test:callback:ping",
          "intent": "default"
        }
      ]
    ]
  }
}
```

Implementation update:

- added `build_callback_button_attachment()`;
- added `MaxApiClient.send_callback_button_message()`;
- added `MaxSender.send_callback_button_message()`;
- kept existing `link` and MAX deep-link button behavior unchanged;
- added exact JSON tests for callback and link button payloads.

Live retest:

- sender enabled during retest: yes;
- debug logging enabled during retest: yes;
- message sent to one resolved MAX chat: yes;
- mass sends: no;
- scheduler/daily summary jobs were not manually triggered;
- callback button displayed in MAX: yes;
- callback button was active: yes;
- `message_callback` webhook received: yes;
- callback payload path confirmed: `callback.payload`;
- callback id path confirmed: `callback.callback_id`;
- callback actor path confirmed: `callback.user.user_id`;
- backend normalized event kind: `callback`;
- `POST /answers` result: `200 OK`;
- sender and debug logging after retest: disabled again for safety.

Notes:

- the retest payload `test:callback:ping` is intentionally non-secret and contains no ids;
- the retest payload is not a production `task:*` callback payload, so it verifies button activity, webhook routing, and callback answer delivery, but does not create a successful task-action receipt;
- `bot_callback_receipts` remained empty for this test payload because the existing business callback parser accepts only `task:*` payloads;
- a follow-up controlled test with a safe valid `task:*` payload is needed to verify task callback receipt/idempotency end-to-end;
- `httpx` INFO request logs exposed full callback ids in query strings during this retest; logging was updated to suppress `httpx` and `httpcore` request URL logs at INFO level.

Remaining gaps:

- live task callback action with a valid `task:*` payload: pending;
- live callback idempotency receipt with a valid `task:*` payload: pending;
- DM unavailable behavior: pending;
- native `open_app` button behavior: pending.

## Real MAX Task Callback E2E Test — 2026-05-23

Context:

- deployed backend commit before test: `30c992e fix: suppress MAX callback id request logs`;
- tested task callback payload family: `task:snooze:1h:{task_id}`;
- safe test task was selected from a previous live reply-task flow;
- selected task was assigned to a test user with `User.max_user_id`;
- selected task belonged to a chat with `Chat.max_chat_id`;
- sender and webhook debug logging were enabled only during the controlled test.

Controlled send:

- one test message was sent to one resolved MAX chat;
- message text: `Тест task callback: отложить напоминание`;
- button text: `Отложить на 1 час`;
- button shape used the confirmed active MAX callback format:

```json
{
  "type": "callback",
  "text": "Отложить на 1 час",
  "payload": "task:snooze:1h:<TASK_ID_REDACTED>",
  "intent": "default"
}
```

Live callback result:

- callback button active: yes;
- manual click performed: yes;
- `message_callback` webhook received: yes;
- `callback.payload` extracted: yes;
- `callback.callback_id` extracted: yes, stored only in masked form in logs/docs;
- callback actor resolved through `User.max_user_id`: yes;
- existing `callback_service` invoked: yes;
- `TaskReminderSnooze` rows created: yes;
- latest snooze reason: `callback/snooze:1h`;
- `bot_callback_receipts` rows written: yes;
- receipt status: `succeeded`;
- receipt response text: `Напоминание отложено на 1 час.`;
- callback answer failure logs: no;
- `POST /answers` behavior: no failure observed during this task callback test; the same deployed path previously returned `200 OK` during the non-task callback retest.

Duplication / idempotency:

- four `message_callback` events were observed during the manual test window;
- all observed callback ids were unique;
- `bot_callback_receipts` stored four succeeded receipts;
- duplicate delivery with the same `callback_id` was not observed live;
- same-callback-id idempotency therefore remains covered by automated tests rather than by this live run.

Safety:

- raw payload was not committed;
- full real user/chat/message/callback ids were not committed;
- token and webhook secret were not printed or committed;
- mass sends were not performed;
- scheduler, reminders and group assignment jobs were not manually triggered;
- `MAX_SENDER_ENABLED=false` after the test;
- `MAX_WEBHOOK_DEBUG_LOG=false` after the test.

Remaining gaps:

- live duplicate delivery with the same `callback_id`: not observed;
- broader DM/reminder behavior: pending;
- native `open_app` button behavior: pending.

## Logical Idempotency For Task Callbacks — 2026-05-23

Background:

- live `task:snooze:1h` testing showed that MAX can send several `message_callback` events for one manual interaction;
- those events can have different `callback.callback_id` values;
- callback-id idempotency remains necessary but is not sufficient for task actions;
- without logical idempotency, repeated events can create repeated snoozes or re-apply destructive task actions.

Implementation:

- callback-id idempotency remains unchanged through unique `callback_id` receipts;
- task callback receipts now also store sanitized logical metadata:
  - provider;
  - internal actor user id;
  - internal task id;
  - action type;
  - normalized callback payload;
  - logical status;
  - logical window timestamp;
- logical duplicates are detected for the same provider, actor, task and normalized payload in a short 60-second window;
- `task:snooze:1h` and `task:snooze:tomorrow` logical duplicates do not create another `TaskReminderSnooze`;
- duplicate snooze answer text: `Напоминание уже отложено.`;
- repeated destructive actions are handled as safe no-ops when the task/response is already in the target state:
  - `task:confirm` -> `Отчет уже отправлен постановщику.`;
  - `task:accept` -> `Результат уже принят.`;
  - `task:reject` -> `Результат уже отклонен.`;
- callback answers are still returned for logical duplicates so MAX receives a user-friendly response.

Safety:

- logical metadata uses internal UUIDs and sanitized payloads only;
- no raw MAX payloads, tokens, webhook secrets, full external user ids or chat ids are stored in docs;
- this is a code/test hardening step and does not require real MAX API calls.

## Real MAX `/задача` No-Response Diagnosis — 2026-05-23

Context:

- deployed version during diagnosis: `1.1.0-rc.2`;
- deployed commit during diagnosis: `cbabbb2 chore: release 1.1.0-rc.2`;
- webhook subscription was present and included `message_created`;
- `MAX_WEBHOOK_ENABLED=true`;
- `MAX_SENDER_ENABLED=false` before diagnosis;
- `MAX_WEBHOOK_DEBUG_LOG=false` before diagnosis;
- backend was temporarily recreated with webhook debug and sender enabled only for the controlled test window;
- worker was not recreated with sender enabled, to avoid reminder or summary sends.

Test scenarios:

- inline command: `/задача Проверить обработку команды завтра в 15:00`;
- command without text: `/задача`;
- ordinary source message: `Проверить доступ завтра в 15:00`;
- reply command: `/задача` as a reply to the ordinary source message.

Observed webhook behavior:

- inline command webhook received: yes;
- inline command HTTP response: `200`;
- inline command normalized as command: yes;
- command without text webhook received: yes;
- command without text HTTP response: `200`;
- command without text normalized as command: yes;
- ordinary source message webhook received: yes;
- ordinary source message normalized as command: no;
- reply command webhook received: yes;
- reply command HTTP response: `200`;
- `message.link.message.mid` mapped to `reply_to_message_id`: yes;
- `message.link.message.text` mapped to `reply_to_text`: yes;
- `message.link.sender` mapped to reply author context where provided: yes.

Observed persistence:

- tasks created during the diagnostic window: `2`;
- inline command created a task: yes;
- inline command task source message id saved: yes;
- inline command assignee count: `0`;
- reply command created a task: yes;
- reply command task source message id saved: yes;
- reply command assignee count: `1`;
- `/задача` without text did not create a task, as expected.

Root cause:

- inbound webhook delivery, secret validation, event normalization, command parsing and task creation were working;
- the visible "no reaction" was caused by outbound bot replies being disabled in the safe steady-state configuration: `MAX_SENDER_ENABLED=false`;
- when sender is disabled, command handling can still create tasks, but the reply to MAX is stubbed and the user sees no bot response;
- no sender errors, tracebacks, `401`, `400`, `403`, `404`, or `500` responses were observed in the diagnostic logs.

Current safe state after diagnosis:

- `MAX_SENDER_ENABLED=false`;
- `MAX_WEBHOOK_DEBUG_LOG=false`;
- backend health check: ok;
- no token or webhook secret was printed;
- no raw payload or full real MAX ids were committed;
- no mass sends were performed;
- scheduler, reminders and group assignment jobs were not manually triggered.

Follow-up:

- keep `MAX_SENDER_ENABLED=false` until broader DM/reminder behavior is hardened for permanent sender enablement;
- for visible live chat replies, use short controlled sender-on windows or add a production-safe outbound allowlist/rate-limit guard;
- consider adding clearer operational logs when command responses are skipped because the sender is disabled.

## MAX Task Assignee Mentions — 2026-05-23

Context:

- existing real `message_created` captures showed command text under `message.body.text`;
- no structured mention entity was confirmed in the sanitized sandbox captures used for this MVP step;
- therefore the first implementation treats leading `@mention` tokens in `/задача` text as textual assignee hints.

Supported MVP syntax:

- `/задача @ivan подготовь отчет до пятницы`;
- `/задача @Мария проверить список завтра в 15:00`;
- `reply /задача @ivan`;
- `/задача @ivan @maria подготовить материалы до пятницы`.

Behavior:

- only leading mentions immediately after `/задача` are treated as assignee hints;
- leading mentions are removed from the task source text before deadline parsing;
- mentions are resolved only against active members of the current chat;
- mention matching uses exact `User.max_user_id`, exact `User.username`, or exact `User.display_name`;
- matching is case-insensitive;
- existing pipe syntax with display-name assignees remains unchanged;
- reply `/задача @mention` uses the replied message as task text and the mention as explicit assignee;
- if reply context exists but `/задача @mention` also includes inline task text after the mention, the inline task text wins;
- explicit mentions override the reply self-task fallback;
- multiple assignees are supported through several leading mentions;
- repeated mentions resolving to the same user are deduplicated;
- if some explicit mentions are resolved and some are not, the task is created with the resolved assignees and the bot response includes warnings for unresolved or ambiguous mentions;
- if no explicit mention can be resolved, the task is not created and reply self-task fallback is not applied;
- successful single-assignee response includes `Задача создана.` and `Исполнитель: <display_name>.`;
- successful multi-assignee response includes `Задача создана.` and `Исполнители: Иван, Мария.`;
- unresolved mention response text is `Не удалось найти исполнителя @mention. Уточните исполнителя в WebApp.`;
- ambiguous mention response text is `Нашлось несколько пользователей для @mention. Уточните исполнителя в WebApp.`;

Safety:

- the resolver does not call real MAX APIs;
- unknown mentions are not guessed;
- ambiguous mentions are not guessed;
- when a mention cannot be found among active chat members, the command returns a friendly error;
- when several active chat members match the same mention, the command returns a friendly ambiguity error;
- no real user ids, chat ids, message ids, tokens or webhook secrets are stored in this document.

Remaining gaps:

- real structured MAX mention entities remained unconfirmed at this stage;
- if future sandbox captures include mention entities with target user ids, they should become the preferred source over text matching;
- users must already exist locally, usually from previous MAX webhook identity resolution, before they can be assigned by mention;
- Bitrix24 hierarchy and user sync remain future work for mention-based assignment.

## Real MAX Mention Payload Capture — 2026-05-23

Capture setup:

- `MAX_WEBHOOK_DEBUG_LOG=true` was enabled only for the short capture window;
- `MAX_SENDER_ENABLED=false` remained unchanged;
- test message type: ordinary MAX chat message, not a slash command;
- test message contained an `@` mention selected or typed in the regular message composer;
- debug logging was disabled after capture.

Sanitized capture result:

- webhook received: yes;
- update type: `message_created`;
- text path: `message.body.text`;
- message id path: `message.body.mid`;
- sender path: `message.sender.user_id`;
- chat path: `message.recipient.chat_id`;
- structured markup path observed: `message.body.markup`;
- normalized command: no;
- raw payload, full user ids, full chat ids and full message ids were not committed.

Finding:

- ordinary MAX mention capture produced `message.body.markup`, so mention metadata is not plain text only;
- the current production-safe debug shape intentionally redacts nested list values, so the capture confirmed the structured path but did not expose a specific mentioned `user_id` value in logs;
- backend support now treats structured MAX mention markup as authoritative when it contains `user_id`, `userId`, nested `user.user_id`, `user.id`, `user_link.user_id` or `userLink.userId`;
- if a structured mention does not include a resolvable user id or unique local username/display name, the backend does not guess.

Implemented follow-up:

- `NormalizedBotEvent` now carries sanitized `mentions`;
- pending assignee selection can be completed by an ordinary mention message from the pending action actor;
- the flow uses `message.body.markup` mention data when available;
- a structured mention with external MAX user id maps to `User.max_user_id`;
- if the mentioned MAX user is not local yet, the backend can create a local `User` from the structured mention and add that user as an active chat member;
- plain `@text` without structured mention data does not assign randomly;
- existing bot-driven picker, `/задача @user text` and `reply /задача` self-task behavior remain unchanged.

## Real MAX Structured Mention Assignment Test — 2026-05-23

Environment:

- deployed commit: `68d3ea3 feat: assign tasks from MAX mention reply`;
- app version: `1.1.0-rc.2`;
- `MAX_SENDER_ENABLED=true` and `MAX_WEBHOOK_DEBUG_LOG=true` were enabled only for the controlled backend test window;
- worker was restored with `MAX_SENDER_ENABLED=false` after the test;
- no raw payloads, full ids, bot token or webhook secret were committed.

Live flow:

1. User sent `/задача` with inline task text and no explicit assignee.
2. Bot created a pending assignee-selection action and delivered the picker message.
3. User sent an ordinary MAX message containing an `@` mention.
4. Backend received a non-command `message_created` event with `message.body.markup`.
5. Normalized event included structured mentions.
6. Pending action was completed from the mention message.

Result:

- native MAX `@` list in ordinary message: not directly observed by Codex, but structured `message.body.markup` was received;
- structured mention in `message.body.markup`: yes;
- normalized mention count in debug shape: `2`;
- mentioned user resolved to internal `User.id`: yes;
- resolved user had `User.max_user_id`: yes;
- pending action completed by mention message: yes;
- task created: yes;
- assignee set to mentioned user: yes;
- assignee count: `1`;
- deadline parsed from inline task text: yes;
- plain `@text` guessing avoided: yes by implementation and tests;
- cleanup status for the mention path: `unsupported`, because the mention-reply path is not a callback answer/edit flow;
- `MAX_SENDER_ENABLED=false` after the test: yes;
- `MAX_WEBHOOK_DEBUG_LOG=false` after the test: yes.

Remaining gaps:

- if the product needs visual cleanup of the original picker after mention-message assignment, add a separate edit/delete mechanism for non-callback completion;
- broader participant discovery still depends on local identities from prior webhook interactions or future sync.

## MAX Bot-Driven Assignee Picker — 2026-05-23

Status: superseded for new messages. Legacy `task:assign` callbacks remain supported for already-sent picker messages, but new `/задача` flows use text-only MAX `@mention` selection.

Context:

- real MAX UX does not expose a Telegram-like username/autocomplete flow through the bot API;
- text `@mention` assignment remains supported, but it is an advanced path for users who know an existing local username/display id;
- the older no-assignee `/задача` UX used inline callback buttons before the mention-only flow replaced it.

Supported flow:

1. User sends `/задача подготовить отчет до пятницы`.
2. Bot parses title/deadline but does not create a visible unassigned task.
3. Bot creates a short-lived `BotPendingAction` with action type `task_create_select_assignee`.
4. Bot sends an inline picker with:
   - active known chat members;
   - `Назначить себе`;
   - `Открыть в WebApp`.
5. User clicks an assignee button.
6. Callback `task:assign:<pending_action_id>:<assignee_id>` or `task:assign:<pending_action_id>:self` creates the real task.

Safety behavior:

- picker payloads contain only internal UUIDs for pending action and selected assignee;
- picker payloads do not contain MAX external ids, tokens, webhook secrets or personal data;
- selected assignee must still be an active member of the current chat;
- only the original command actor can complete the pending action in the MVP;
- completed or expired pending actions do not create duplicate tasks;
- unresolved or ambiguous text mentions are not guessed and can fall back to the picker UX;
- `reply /задача` self-task fallback remains unchanged;
- resolved `/задача @username текст` still creates a task directly.

Remaining gaps:

- full MAX chat member discovery/sync is not implemented;
- picker can only show users already known locally through previous webhook identity resolution or manual setup;
- WebApp `assign_<pending_action_id>` route is not implemented yet, so the WebApp button opens the main WebApp as a fallback;
- Bitrix24 hierarchy/users sync remains future work.

## Real MAX Assignee Picker Test — 2026-05-23

Environment:

- deployed feature commit: `581f077 feat: add assignee picker for MAX task commands`;
- deployed follow-up fix: `5090b6e fix: keep callback receipt methods on receipt repository`;
- app version: `1.1.0-rc.2`;
- migration head/current during test: `a4b5c6d7e8f9`;
- test command: `/задача подготовить отчет до пятницы`;
- sender/debug were enabled only for the controlled test window.

Result:

- command webhook received: yes;
- command normalized as a task command: yes;
- pending action created: yes;
- picker message delivered to MAX: yes;
- `Назначить себе` button displayed and active: yes;
- `task:assign` callback webhook received: yes;
- callback routing invoked: yes;
- task created after selection: yes;
- assignee set to the command actor: yes;
- pending action marked completed: yes;
- deadline parsed from `до пятницы`: yes;
- `POST /answers` path did not raise an error during the successful retest;
- full MAX ids, callback ids and raw payloads were not committed.

Duplicate behavior:

- MAX delivered several callback events for the same visible button tap sequence;
- the completed pending action retained one `completed_task_id`;
- the created task had one assignee;
- no duplicate task was created for the completed pending action;
- duplicate callback behavior remains covered by automated tests and by the completed pending-action guard.

Initial retest finding:

- the first deployed picker attempt on `581f077` delivered the picker and received `task:assign`, but returned HTTP 500 after task processing because callback receipt status methods were on the pending-action repository instead of the callback-receipt repository;
- `5090b6e` moved those methods back to `BotCallbackReceiptRepository` and added a regression test;
- backend pytest after the fix: 522 passed;
- ruff after the fix: passed.

Safe final state:

- `MAX_SENDER_ENABLED=false`;
- `MAX_WEBHOOK_DEBUG_LOG=false`;
- backend health check: ok;
- backend and worker healthy;
- no token or webhook secret was printed;
- no raw payload or full real ids were committed;
- no mass sends were performed.

## MAX Reminder And Picker Cleanup Hardening — 2026-05-23

Reminder diagnosis for task `ac05936b-0e4e-42f1-9b64-b229139a0d02`:

- task exists: yes;
- task status during diagnosis: `new`;
- stored deadline: `2026-05-23T18:00:00Z`;
- diagnosis time: `2026-05-23T10:24Z`;
- deadline overdue at diagnosis time: no;
- assignee count: 1;
- assignee has `User.max_user_id`: yes;
- active snooze for the task/assignee: no;
- delivery records for this task: none;
- current safe sender state: `MAX_SENDER_ENABLED=false`;
- root cause for the missing overdue notification at diagnosis time: the task was not overdue in stored UTC time, so the overdue reminder pipeline had not selected it yet.

Additional reminder safety finding:

- broader 24-hour delivery counts showed repeated `notification_deliveries` rows while sender was disabled;
- this was a safety issue in the reminder pipeline: disabled sender still produced delivery attempts every scheduler cycle;
- fix: `notification_deliveries` now stores `reminder_type`;
- fix: sender-disabled reminders are recorded as `skipped` with `sender_disabled` and do not call MAX;
- fix: recent task/user/channel/reminder-type delivery is deduplicated for a short safety window to avoid repeated rows and accidental spam loops;
- users without `max_user_id` remain `dm_unavailable` / `missing_max_user_id`;
- group fallback without `Chat.max_chat_id` remains failed with `missing_max_chat_id`;
- `MAX_SENDER_ENABLED` should remain `false` until broader production reminder behavior is validated with allowlist/rate-limit controls.

Picker chat hygiene:

- MAX edit support is available through callback answers with a replacement message payload;
- the chosen behavior is edit, not delete;
- after successful `task:assign`, the callback answer replaces the picker message with a short summary and sends an empty attachments list to remove stale buttons;
- cleanup result is stored on `BotPendingAction` as `cleanup_status`;
- cleanup failure does not roll back task creation;
- completed/expired pending actions still block duplicate task creation;
- deadline picker cleanup is not applicable yet because the current live flow does not have a separate deadline picker.

## Real MAX Picker Cleanup Deploy Check — 2026-05-23

Post-deploy state:

- deployed application fix commit: `5eea458 fix: harden reminders and clean task picker messages`;
- deployed smoke-script follow-up commits: `4240b2b` and `b6f2f28`;
- app version: `1.1.0-rc.2`;
- VPS Alembic current/head: `b5c6d7e8f901`;
- backend, worker, postgres, redis, webapp, and nginx containers were healthy after deploy;
- HTTPS health check returned ok;
- release smoke result after sender-disabled smoke adjustment: `release_smoke=ok`.

Controlled live picker cleanup check:

- command tested: `/задача` with inline text and no explicit assignee;
- sender/debug were enabled only for the controlled backend test window;
- worker was kept out of the sender-enabled test window to avoid scheduled reminder sends;
- picker message delivered: yes;
- `Назначить себе` callback received: yes;
- task created after selection: yes;
- selected assignee matched the callback actor: yes;
- pending action completed: yes;
- picker message id stored on the pending action: yes;
- picker cleanup status: `edited`;
- picker cleanup error: none;
- callback receipt status: `succeeded`;
- duplicate task created: no;
- `MAX_SENDER_ENABLED=false` after the test: yes;
- `MAX_WEBHOOK_DEBUG_LOG=false` after the test: yes.

Reminder post-deploy checks:

- `notification_deliveries.reminder_type` migration applied: yes;
- sender-disabled reminder behavior observed in smoke: yes;
- with `MAX_SENDER_ENABLED=false`, reminder smoke recorded `skipped` / `sender_disabled` deliveries instead of real MAX sends;
- no unexpected real MAX outbound sends were observed during deploy checks.

## Real MAX rc.3 Acceptance Check — 2026-05-23

Deployment state:

- deployed release commit: `34d799f chore: release 1.1.0-rc.3`;
- deployed tag: `v1.1.0-rc.3`;
- deployed version: `1.1.0-rc.3`;
- VPS Alembic current/head: `b5c6d7e8f901`;
- backend, worker, postgres, redis, webapp, and nginx containers were healthy after deploy;
- HTTPS route checks for `/`, `/tasks`, `/dashboard`, `/group-assignments`, `/settings`, and `/api/health` passed;
- release smoke result: `release_smoke=ok`;
- sender/debug were enabled only for a controlled live backend test window;
- worker was not recreated with sender enabled during acceptance to avoid scheduled reminder sends;
- `MAX_SENDER_ENABLED=false` after the test: yes;
- `MAX_WEBHOOK_DEBUG_LOG=false` after the test: yes.

Controlled live acceptance:

- picker flow: passed;
- `/задача` with inline text and no explicit assignee created a pending action instead of a final unassigned task;
- picker message was delivered;
- `Назначить себе` callback completed the pending action;
- task was created after selection;
- task had exactly one assignee;
- picker message cleanup status was `edited`;
- duplicate task creation was not observed;
- native structured `@mention` flow: passed;
- ordinary MAX mention message completed a pending action;
- structured mention data was normalized without plain-text guessing;
- mentioned user resolved to an internal user;
- task was created with exactly one assignee;
- reply `/задача` flow: passed;
- real `message.link` reply metadata was mapped;
- reply-created task had exactly one assignee;
- reply-created task stored source message context;
- deadline parsing succeeded for the controlled acceptance tasks;
- task callback flow was skipped in this rc.3 acceptance pass because `task:snooze:1h` was already verified in the earlier live E2E check.

Safety notes:

- no raw MAX payloads were committed;
- no full user, chat, message, or callback ids were committed;
- no bot token or webhook secret was printed or committed;
- no mass sends were performed;
- no unexpected MAX outbound sends were observed after sender/debug were returned to `false`.

## MAX WebApp Auth Opening Diagnosis — 2026-05-24

Deployment state:

- deployed code before the fix: `c34626f feat: add WebApp MAX auth bootstrap`;
- backend MAX WebApp session auth was healthy;
- `/api/auth/me` without a session returned `401`;
- `?user_id=...` did not grant access and returned `401`;
- logs did not contain raw `initData`, bot token, webhook secret, or WebApp session secret.

Finding:

- the WebApp was opened through the plain URL `https://maxsecretary.ru`;
- the observed client opened the plain URL in an external browser;
- because the page was not opened inside MAX, frontend did not receive MAX `initData`;
- frontend therefore did not call `POST /api/auth/max-webapp/session`;
- the unauthorized state `Откройте WebApp из MAX` was expected fail-closed behavior.

Fix direction:

- configure `MAX_BOT_USERNAME=secretary_oren_bot` on VPS;
- generate WebApp chat buttons as MAX deep links when the username is configured;
- use `https://max.ru/secretary_oren_bot?startapp=home` for the main WebApp entrypoint;
- keep `https://maxsecretary.ru` only as fallback when `MAX_BOT_USERNAME` is not configured;
- keep `startapp` payloads short and non-secret.

Follow-up after deep-link deploy:

- the deep link opened the WebApp inside an Android WebView;
- nginx observed the URL as `https://maxsecretary.ru/?WebAppStartParam=home`;
- frontend still did not call `POST /api/auth/max-webapp/session`;
- root cause: the WebApp page did not load MAX Bridge, so `window.WebApp.initData` was unavailable;
- fix: load `https://st.max.ru/js/max-web-app.js` before the SPA bundle and keep a sanitized `WebAppData` URL fallback.

## Real MAX WebApp Deep Link Auth Test — 2026-05-24

Deployment state:

- WebApp deep-link commit: `a1598b1 fix: open WebApp through MAX deep links`;
- MAX Bridge commit: `22e130b fix: load MAX WebApp bridge for auth bootstrap`;
- app version: `1.1.0-rc.3`;
- `MAX_BOT_USERNAME=secretary_oren_bot` was configured on VPS;
- `MAX_WEBAPP_AUTH_ENABLED=true`;
- `MAX_SENDER_ENABLED=false` and `MAX_WEBHOOK_DEBUG_LOG=false` after the test.

Controlled test:

- controlled WebApp button messages sent: yes, one before the Bridge fix and one after the Bridge fix;
- mass sends: no;
- generated link: `https://max.ru/secretary_oren_bot?startapp=home`;
- plain URL behavior: opens in an external browser and does not provide MAX `initData`;
- deep link behavior: opens inside MAX WebView;
- observed WebView URL shape: `https://maxsecretary.ru/?WebAppStartParam=home`;
- raw `initData` was not logged or committed.

Auth result after loading MAX Bridge:

- `initData` present to frontend: yes;
- `POST /api/auth/max-webapp/session`: `200`;
- `GET /api/auth/me` after session creation: `200`;
- WebApp API call after session creation: succeeded;
- direct browser/API access without session: blocked with `401`;
- query `user_id` without session: ignored and blocked with `401`;
- frontend no longer sends `user_id` as an inbox-summary query parameter; backend uses the authenticated session user by default.

Safety notes:

- no bot token, webhook secret, WebApp session secret, raw `initData`, cookies, or full user/chat/message ids were committed;
- logs contained no traceback and no raw `initData` leak in the checked window.

## Real MAX `/секретарь` Command Diagnosis — 2026-05-24

Deployment state:

- expected command implementation commit: `0cbd533 feat: add secretary command summary`;
- VPS initially did not contain `0cbd533`; it was still on an earlier `main` commit;
- the VPS was updated to `0cbd533` and backend/worker were rebuilt;
- app version remained `1.1.0-rc.3`;
- `MAX_BOT_USERNAME=secretary_oren_bot` was configured;
- `MAX_SENDER_ENABLED=false` before diagnosis, as expected for the safe default.

Controlled diagnosis:

- `MAX_SENDER_ENABLED=true` and `MAX_WEBHOOK_DEBUG_LOG=true` were enabled only for the controlled check;
- webhook received: yes;
- webhook status: `200`;
- normalized event was a command: yes;
- normalized command text length matched `/секретарь`;
- parser support was confirmed on the deployed backend;
- backend traceback/errors: no;
- MAX sender error logs: no;
- token/secret/raw `initData` leak: no.

Root cause:

- the first no-response observation was caused by the feature not being deployed on the VPS yet;
- with the safe default `MAX_SENDER_ENABLED=false`, command handling can succeed without a visible MAX reply.

After diagnosis:

- `MAX_SENDER_ENABLED=false`;
- `MAX_WEBHOOK_DEBUG_LOG=false`;
- backend and worker healthy;
- `/api/health` returned `ok`.

Remaining check:

- visual confirmation that the `Дьяк` response and buttons are shown in the real MAX chat;
- visual confirmation that the `Открыть Дьяк` button opens the WebApp through the MAX deep link.

## MAX Outbound Guard Split — 2026-05-24

Finding:

- a single `MAX_SENDER_ENABLED` switch was too coarse for the live bot;
- it disabled both safe interactive command replies and higher-risk background notifications;
- with `MAX_SENDER_ENABLED=false`, `/дьяк` and the deprecated `/секретарь` alias can be parsed and handled but no visible MAX reply is sent.

Implemented guard model:

- `MAX_SENDER_ENABLED` remains the transport master switch;
- `MAX_INTERACTIVE_RESPONSES_ENABLED` controls direct user-triggered bot replies and callback answers;
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED` controls reminders, overdue notifications, pings, daily summaries, and group/background sends.

Safe live command mode:

```env
MAX_SENDER_ENABLED=true
MAX_INTERACTIVE_RESPONSES_ENABLED=true
MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false
```

Expected behavior:

- `/дьяк`, `/задача`, assignee picker messages, and callback answers can be visible in MAX;
- reminders and other background sends are skipped with `background_disabled`;
- no mass sends are enabled by this mode.

## 1. Webhook Event For A Normal Text Message

### What Official Docs Indicate

MAX `Update` supports `message_created` events through Webhook or Long Polling.
The `Message` object includes:

- `sender`;
- `recipient`;
- `timestamp`;
- `link`;
- `body`;
- optional stats/url fields depending on chat/channel context.

`User` includes fields such as:

- `user_id`;
- `first_name`;
- `last_name`;
- `username`;
- `is_bot`;
- `last_activity_time`.

`Chat` has `type` values:

- `chat`;
- `channel`;
- `dialog`.

### Sandbox Check Required

Send a normal text message in a test chat and capture raw webhook JSON.

Check actual field paths for:

- `chat_id`;
- `user_id`;
- `message_id`;
- `text`;
- `timestamp`;
- sender profile fields;
- chat type;
- forwarded/replied message metadata.

### Current Finding

Verified in real sandbox on `2026-05-22`; see "Real Sandbox Capture — 2026-05-22".

The real `message_created` payload exposes sender, recipient, timestamp and body. In dialog context, `message.recipient.user_id` is present. In group context captured during reply tests, `message.recipient.user_id` was absent and `message.recipient.chat_type` was present.

## 2. Webhook Event For Reply To Message

### Scenario

1. In a test chat, send:

```text
Иван, подготовь отчет до пятницы
```

2. Reply to that message with:

```text
/задача
```

### What Official Docs Indicate

The `Message` object contains `link`, described as a forwarded or replied message.
`GET /messages/{messageId}` returns a single message by its `mid`, including `sender`, `recipient`, `timestamp`, `link`, and `body`.

### Sandbox Check Required

Capture raw webhook JSON for the reply command and check:

- whether a reply marker is present;
- whether it contains `reply_to_message_id` or equivalent;
- whether the original message text is embedded;
- whether the original message author is embedded;
- whether `GET /messages/{messageId}` can fetch the original message when webhook payload contains only a linked message id;
- whether message permissions differ between group chat, channel and dialog.

### Current Finding

Verified in real sandbox on `2026-05-22`; see "Real Sandbox Capture — 2026-05-22".

Reply metadata is represented through `message.link`. In the tested payloads, the linked message id, text and sender were embedded, so an extra `GET /messages/{messageId}` call was not required for these cases. The backend maps `message.link` into `NormalizedBotEvent.reply_to_*`; reply-created task persistence depends on the MAX external identity mapping described above.

## 3. Callback / Inline Buttons

### What Official Docs Indicate

MAX supports `inline_keyboard` attachments in messages.
Button types include:

- `callback`;
- `link`;
- `request_contact`;
- `request_geo_location`;
- `open_app`;
- `message`;
- `clipboard`.

Docs indicate:

- callback buttons generate `message_callback` events through Webhook or Long Polling;
- callback response is sent through `POST /answers`;
- callback answer can update the message and/or show a one-time notification;
- inline keyboard can contain up to 210 buttons grouped into 30 rows;
- each row can contain up to 7 buttons, or up to 3 buttons for `link`, `open_app`, `request_geo_location`, and `request_contact`;
- link button URL length limit is 2048 characters.

Message edit endpoint exists and can edit bot-sent messages. In dialogs, messages with inline keyboards can be edited regardless of age; other dialog messages are limited by age. In group chats and channels, bot messages can be edited regardless of age according to current docs.

### Sandbox Check Required

Send a task card with inline buttons and capture:

- raw `message_callback` event;
- callback id field path;
- payload field path and payload size behavior;
- user and chat fields in callback event;
- whether callback event includes the original message id;
- whether `POST /answers` updates message text and keyboard;
- behavior when callback payload is too long or malformed.

### Current Finding

Captured in real sandbox on `2026-05-23`; see "Real MAX Callback Capture — 2026-05-23".

The real event shape uses top-level `callback`, `message`, `timestamp`, `update_type`, and `user_locale`. The payload lives at `callback.payload`, and the callback id lives at `callback.callback_id`. The backend now routes this shape into `callback_service`; live task-action verification remains pending after deployment.

## 4. Direct Messages / Personal Reminders

### What Official Docs Indicate

`POST /messages` can target either `chat_id` or `user_id`.
`Update` supports `bot_started` and `bot_stopped`, which suggests there is user-level bot dialog state.

### Sandbox Check Required

Test direct message sending to:

- a user who has started a dialog with the bot;
- a user who is in the group chat but has not started a dialog with the bot;
- a user who stopped the bot;
- an invalid or inaccessible user id.

Capture:

- HTTP status code;
- response JSON;
- whether there is a stable error code or message for DM-unavailable;
- whether `bot_started` is required before personal reminders;
- whether user-level opt-out can be detected.

### Current Finding

Not verified in real sandbox yet.

Expected from docs: direct messages are sent by `user_id`, but availability constraints and exact errors require live tests.

## 5. WebApp Open Button

### What Official Docs Indicate

MAX inline keyboard supports an `open_app` button type.

### Sandbox Check Required

Send a task card with an "Open task" button and verify:

- whether `open_app` can open the max_secretary WebApp from a group chat;
- whether task context can be passed through URL or app parameters;
- whether `task_id`, `chat_id`, and user context can be passed safely;
- maximum payload or URL length;
- behavior on desktop and mobile clients.

### Current Finding

Partially confirmed by official docs, not verified in sandbox.

The implementation should avoid assuming final WebApp auth/user context until sandbox behavior is captured.

## 6. Message Formatting

### What Official Docs Indicate

`POST /messages` supports:

- `text` up to 4000 characters;
- `format=markdown`;
- `format=html`;
- line breaks and basic formatting through supported markup;
- attachments and links.

### Sandbox Check Required

Send test messages with:

- plain text with multiple line breaks;
- bullet list;
- numbered list;
- markdown bold/italic/code/link;
- HTML bold/italic/code/link;
- long text near 4000 characters.

Check rendering in:

- group chat;
- dialog;
- mobile client;
- desktop/web client if available.

### Current Finding

Partially confirmed by official docs, not verified visually in sandbox.

Task card text should stay short and avoid relying on complex formatting until visual behavior is confirmed.

## 7. Rate Limits / Errors

### What Official Docs Indicate

Official docs list common HTTP status codes:

- `200`;
- `400`;
- `401`;
- `404`;
- `405`;
- `429`;
- `503`.

Docs also mention a recommended maximum of 30 requests per second to `platform-api.max.ru`.

Current local `MaxApiClient` treats `429`, `500`, `502`, `503`, and `504` as temporary status codes for retry-safe requests.

### Sandbox Check Required

Run controlled error tests:

- invalid bot token;
- invalid chat id;
- invalid user id;
- missing `chat_id` and `user_id`;
- oversized message;
- unsupported format;
- repeated quick requests to check rate-limit headers.

Capture:

- HTTP status code;
- response body shape;
- whether `Retry-After` or equivalent rate-limit headers are present;
- whether timeout/network errors are distinguishable from API errors.

### Current Finding

Partially confirmed by official docs, not verified in sandbox.

The current retry strategy is conservative, but final behavior should be adjusted after seeing real MAX error payloads.

## Sandbox Evidence Checklist

Before implementing `v1.1.0` code, collect sanitized artifacts:

- normal text message webhook payload;
- reply command webhook payload;
- callback button webhook payload;
- `POST /answers` success response;
- direct message success response;
- direct message unavailable error response;
- deep link / `startapp` button payload and observed client behavior;
- native `open_app` button payload and observed client behavior;
- markdown/html screenshots or written observations;
- rate-limit/error response examples.

Do not commit:

- real bot token;
- webhook secret;
- raw phone numbers;
- personal user data beyond sanitized ids/names;
- production chat ids.

## Implementation Impact

Likely future work after sandbox confirmation:

- rerun real reply-created task flow after MAX external identity mapping deployment;
- add `GET /messages/{messageId}` method to `MaxApiClient`;
- add inline keyboard request schemas;
- add callback event normalization;
- add direct-message fallback rules;
- productionize the WebApp deep-link strategy and add native `open_app` only if the MAX client requires it;
- add natural deadline parser only after reply context is confirmed.

## Sources

- MAX API overview: https://dev.max.ru/docs-api
- `POST /messages`: https://dev.max.ru/docs-api/methods/POST/messages
- `PUT /messages`: https://dev.max.ru/docs-api/methods/PUT/messages
- `GET /messages/{messageId}`: https://dev.max.ru/docs-api/methods/GET/messages/-messageId-
- `POST /answers`: https://dev.max.ru/docs-api/methods/POST/answers
- `GET /subscriptions`: https://dev.max.ru/docs-api/methods/GET/subscriptions
- `POST /subscriptions`: https://dev.max.ru/docs-api/methods/POST/subscriptions
- `Message`: https://dev.max.ru/docs-api/objects/Message
- `Update`: https://dev.max.ru/docs-api/objects/Update
- `User`: https://dev.max.ru/docs-api/objects/User
- `Chat`: https://dev.max.ru/docs-api/objects/Chat

## Real MAX Slash Command Registration — 2026-05-24

### Scope

Controlled registration of native MAX slash-popup bot commands through the bot profile API.

No webhook payloads, user ids, chat ids, tokens, secrets, or Authorization headers were printed or committed.

### Registration

- implementation commit: `6c4f26e feat: add MAX bot command registration script`;
- VPS helper fix commit: `41ae33c fix: support containerized MAX command registration`;
- script: `scripts/max/register_bot_commands.py`;
- API call performed: `PATCH /me`;
- real MAX API calls in this step: only one controlled `PATCH /me`;
- command name format: without slash.

Registered commands:

- `секретарь` — открыть меню и сводку задач;
- `задача` — создать задачу из сообщения или текста;
- `мои_задачи` — показать мои активные задачи;
- `отчет` — отправить отчет по задаче;
- `пинг` — напомнить исполнителю о задаче.

### Result

- VPS dry-run: passed, `max_api_called=no`;
- VPS apply: passed, `max_api_called=yes`;
- native slash-popup visible in MAX: yes;
- visible commands:
  - `/секретарь`: yes;
  - `/задача`: yes;
  - `/мои_задачи`: yes;
  - `/отчет`: yes;
  - `/пинг`: yes.

Parser compatibility:

- native menu uses `/мои_задачи`;
- parser alias `/мои задачи` remains supported for manual typing.

Rebrand update on 2026-05-25:

- external product brand changed to `Дьяк`;
- command registration payload now uses `дьяк` instead of `секретарь`;
- `/секретарь` remains a deprecated parser alias but should not be included in the native slash-popup payload after the next manual `PATCH /me`;
- no real MAX API call was made during the code/docs rebrand task.

### Safety

- token printed: no;
- Authorization header printed: no;
- secrets leaked: no;
- production `.env` changed: no;
- mass sends: no.

## Real MAX Bot Command Center Acceptance — 2026-05-24

### Scope

Controlled live acceptance in one resolved MAX test chat after deploying:

- `c65f0c2 feat: add task ping bot command`;
- `VERSION=1.1.0-rc.3`;
- Alembic current/head: `c6d7e8f90123`.

No raw webhook payloads, tokens, secrets, cookies, initData, full user ids, chat ids, message ids, or callback ids were recorded.

### Safe Live Mode

The VPS backend was running with:

- `MAX_SENDER_ENABLED=true`;
- `MAX_INTERACTIVE_RESPONSES_ENABLED=true`;
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`;
- `MAX_WEBHOOK_DEBUG_LOG=false`;
- `MAX_BOT_USERNAME=secretary_oren_bot`.

This permits interactive command replies while keeping background reminders, summaries, pings, and group sends guarded.

### Command Results

- `/дьяк`: pass, summary and command center buttons visible.
- `/мои_задачи`: pass, active assignee task list shown with `task_ref`.
- `/мои задачи`: pass, text alias behaves like `/мои_задачи`.
- `#number`: pass, task card shown by short task number.
- `/number`: pass, task card shown by short task number.
- `T-number`: pass, task card shown by short task number.
- `/отчет #number`: pass, report command flow works for an allowed assignee test task.
- `/пинг #number`: pass, command is recognized and background delivery is guarded while background notifications are disabled.
- Native slash-popup commands visible: yes.

### Post-Deploy Checks

- containers: backend, worker, webapp, nginx, postgres, redis healthy;
- `GET /api/health`: ok;
- release smoke: `release_smoke=ok`;
- protected unauthenticated endpoints returning `401`: expected pass;
- authenticated smoke: skipped without session/initData fixture;
- logs: no traceback, crash, token leak, secret leak, raw initData leak, or unexpected background sends observed.

### Remaining Gaps

- Background `/пинг` delivery remains intentionally disabled until a separate controlled notification rollout decision.
- WebApp task deep-link routing for `startapp=task_<number>` remains the detailed view path for richer task actions.

## Real MAX Bot Command Center UX Follow-Up — 2026-05-24

### Live Gaps Found

- `/отчёт` with `ё` was not accepted as an alias for `/отчет`.
- Native slash-popup could insert commands as `@secretary_oren_bot <command>`, which the parser did not previously treat as a command.
- `/пинг` on a self-assigned task tried the background notification path instead of returning an immediate interactive self-reminder.
- `/пинг` with background notifications disabled used a technical-ish disabled message.
- Task cards for creators did not surface accept/reject actions when a submitted report was waiting for acceptance.

### Fix Scope

The follow-up fix keeps API/WebApp auth and sender guards unchanged:

- `/отчёт` is accepted wherever `/отчет` is accepted.
- Mention-prefix commands are accepted only for the configured `MAX_BOT_USERNAME`.
- `/пинг` for self-assigned tasks replies in the current chat and creates no background delivery.
- `/пинг` for another assignee still respects `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false` and reports that the assignee did not receive a reminder.
- `#number` task cards show `Принять` / `Отклонить отчет` for creator/chat_admin views when a submitted report is pending acceptance.

No tokens, secrets, raw payloads, full real identifiers, cookies, or initData were added to documentation.

## Bot Command Center Self-Ping Report Flow Follow-Up — 2026-05-25

### Live Gap Found

- `/пинг #number` for a task assigned to the initiator showed an extra `Написать отчет` button.
- The user was already in the chat, so a better flow is to immediately ask for the next message as the report.

### Fix Scope

- Self-task `/пинг` now reuses the same pending report flow as `/отчет #number` without text.
- The bot replies:

```text
Напишите отчет по задаче #1042 одним сообщением.
```

- The next ordinary message from the actor is saved as the task report and completes the pending action.
- The self-task ping response keeps only the `Открыть задачу` WebApp deep-link button.
- No background delivery is created for self-task ping.
- `/пинг` for another assignee still respects background notification guards and cooldown.

No tokens, secrets, raw payloads, full real identifiers, cookies, or initData were added to documentation.

## Pending Action Routing Regression — 2026-05-25

### Live Bug

- A user replied `/задача` to ordinary source text without a recognizable deadline.
- The bot asked to clarify the task deadline.
- The next ordinary message, for example `завтра до 18:00`, was consumed by an older `task_report_submit` pending context.
- The bot incorrectly saved that deadline text as a report for another task.

### Root Cause

- `/задача` without a deadline returned a prompt but did not create an explicit task-creation deadline pending context.
- Non-command message routing checked pending report submission before task-creation follow-up state.
- Stale report pending actions for the same actor/chat could survive after a new explicit `/задача` command.

### Fix Scope

- Added `task_create_set_deadline` pending action for `/задача` flows that need deadline clarification.
- Explicit `/задача` cancels incompatible pending report contexts for the same actor and chat.
- Non-command routing priority is now:
  1. task deadline clarification;
  2. task assignee selection by structured `@mention`;
  3. task report submission.
- A deadline follow-up like `завтра до 18:00` continues task creation, creates assignee-selection pending context for `chat_admin`/`super_admin`, and does not create a `TaskResponse`.
- Existing `/отчет #number` pending report flow remains valid when no more specific task-creation pending action is active.

No production data was modified by this code change. No tokens, secrets, raw payloads, full real identifiers, cookies, or initData were added to documentation.

## Reply Task Inline Deadline Regression — 2026-05-25

### Live Bug

- A user sent a normal chat message with the intended task text.
- The bot command replied to that message with an inline deadline, for example `/задача завтра 15:00`.
- The inline deadline text was incorrectly treated as the task title remainder, so the visible task card could show a time as the title.
- The MAX task card fallback also exposed internal task UUID and raw status enum in user-facing text.

### Fix Scope

- Reply `/задача` now treats the replied message text as the task title/source text.
- Inline text after reply `/задача` is parsed as task parameters such as deadline and leading assignee mentions.
- `завтра 15:00` and `завтра до 18:00` are parsed as full deadline phrases, so the time is not left behind as title text.
- Reply `/задача` with an inline deadline and no assignee continues to assignee selection instead of self-assigning immediately.
- MAX task-card text now uses `task_ref` and localized status labels; internal UUID and raw status enum stay out of user-facing text.
- Read-only production check confirmed the previously affected task exists as `#16` with title `15:00`, status `new`, and one assignee; no production data was changed.

No production data was modified by this code change. No tokens, secrets, raw payloads, full real identifiers, cookies, or initData were added to documentation.

## Real MAX reply /задача inline deadline regression — 2026-05-25

### Deployment

- Deployed commit: `4cf83fb`.
- Version: `1.1.0-rc.3`.
- Backend, worker, webapp, and nginx rebuilt successfully.
- Safe live mode remained:
  - `MAX_SENDER_ENABLED=true`
  - `MAX_INTERACTIVE_RESPONSES_ENABLED=true`
  - `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`
  - `MAX_WEBHOOK_DEBUG_LOG=false`

### Live Results

- `Отпуск2` + reply `/задача завтра 15:00`: pass.
  - Title used replied message text: yes.
  - Deadline parsed and stored: yes.
  - Assignee picker completed and task created: yes.
  - Wrong report creation prevented: yes.
- `Добрый вечер` + reply `/задача завтра до 18:00`: pass.
  - Title used replied message text: yes.
  - Deadline parsed and stored: yes.
  - Assignee picker completed and task created: yes.
  - Wrong report creation prevented: yes.
- Non-reply inline `/задача ... завтра 15:00`: pass.
  - Task title remained the command text before the deadline.
  - Deadline parsed and stored.
- `/отчет #number` pending flow after the regression check: pass.
- Deadline clarification text was not saved as a task report.
- Previously affected task `#16` was left unchanged.
- Release smoke after deployment: `release_smoke=ok`.

### Remaining Gaps

- Existing bad historical task `#16` still has the old incorrect title and requires a separate explicit cleanup decision if the team wants to change production data.

No production data was modified by this validation. No tokens, secrets, raw payloads, full real identifiers, cookies, or initData were added to documentation.

## Chat Deadline Reminders Deploy Check — 2026-05-25

### Deployment

- Deployed commit: `e81023a`.
- Version: `1.1.0-rc.3`.
- Alembic current/head: `d7e8f9012345`.
- Backend, worker, webapp, nginx, postgres, and redis reported healthy after rebuild.
- Safe live mode remained:
  - `MAX_SENDER_ENABLED=true`
  - `MAX_INTERACTIVE_RESPONSES_ENABLED=true`
  - `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`
  - `MAX_WEBHOOK_DEBUG_LOG=false`
  - `MAX_BOT_USERNAME=secretary_oren_bot`

### Safe-Mode Results

- `notification_deliveries` schema includes nullable `chat_id` and nullable `user_id`, so deliveries can be recorded for `channel=max_chat`.
- Existing delivery rows remained readable after migration.
- Worker-created `task_overdue` chat reminders were recorded as `skipped/background_disabled` while background notifications were disabled.
- Controlled single-task service-level check for `task_due_in_1h`: pass.
  - Delivery created as `skipped/background_disabled`.
  - MAX API was not called.
  - Second check for the same task/chat/type did not create a duplicate row.
- Controlled single-task service-level check for `task_overdue`: pass.
  - Delivery created as `skipped/background_disabled`.
  - MAX API was not called.
  - Second check for the same task/chat/type did not create a duplicate row.
- Chat deadline reminder `sent` count remained `0`.
- Release smoke after deployment: `release_smoke=ok`.

### Remaining Gaps

- Controlled live background-enabled chat reminder test remains pending.
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED` should stay `false` until an explicit rollout decision.

No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## Real MAX compact task filters check — 2026-05-26

### Live Visual Check

- Deployed commit: `89c3743`.
- Create/refresh icons visible: yes.
- Create icon is visible to the right of `Дьяк`.
- Refresh icon is visible to the right of `Дьяк`.
- Text buttons no longer take header space.
- Summary buttons compact: yes.
- Summary button text stays on one line.
- Summary row does not break the mobile screen.
- If the summary row overflows, only the summary row scrolls; the whole page does not.
- Summary tap filters the same task list: yes.
- `Сегодня` filters the list: yes.
- `Новые` filters the list: yes.
- `Ждут отчета` filters the list: yes.
- `Ждут приемки` filters the list: yes.
- `Просрочены` filters the list: yes.
- Repeated tap clears the summary filter: yes.
- Active summary item is visually highlighted: yes.
- Filter spoiler works: yes.
- Search is hidden while the filter spoiler is closed.
- `Все чаты` is hidden while the filter spoiler is closed.
- `Участник` is hidden while the filter spoiler is closed.
- Search, chat, and participant controls appear after opening `Фильтр`.
- Opening `Фильтр` does not break layout.
- Reset clears filters: yes.
- Reset clears the summary filter: yes.
- Reset clears search: yes.
- Reset clears chat: yes.
- Reset clears participant: yes.
- `startapp` behavior preserved: yes.
- `startapp=home` works: yes.
- `startapp=my_tasks` works: yes.
- `startapp=task_<number>` works: yes.
- Horizontal page scroll: no.
- Task cards remain readable: yes.
- Top of the screen stays compact: yes.

### Result

- No visual issues reported for compact task filters.

No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## MAX Chat Display Title Diagnosis — 2026-05-26

### Sanitized Data Check

- Recent live tasks that still showed `Чат без названия` were checked with masked identifiers only.
- Stored chat titles for the checked rows were generated MAX fallback names, not real chat names.
- No `source_chat_title_snapshot` or manual alias was present for those old rows.
- The existing MAX sandbox fixture already contains `message.chat.title`, but the normalizer did not persist it before this fix.

### Implementation Notes

- The MAX event normalizer now extracts a chat title from safe title/name fields when present.
- The identity resolver creates new MAX chats with the real title when available.
- If an existing chat still has a generated `MAX chat #...`, `MAX dialog #...`, or `MAX group #...` title, the resolver updates it when a real title arrives.
- Existing non-generated/manual chat titles are not overwritten by generated fallback names.
- New tasks store the source chat title snapshot from the resolved chat.
- WebApp task list and task details use a shared display-title helper:
  - task snapshot;
  - manual alias in `Chat.settings`;
  - non-generated `Chat.title`;
  - `Личный чат` for unnamed dialog;
  - `Чат без названия` otherwise.

### Remaining Gap

Old chats whose real title was never stored still need a manual alias in Дьяк or a future MAX event that includes the title. No production chat titles were mass edited in this task.

No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## Real MAX Chat Display Title Behavior — 2026-05-26

### Deployment

- Deployed commit: `b6b124c`.
- VERSION remained `1.1.0-rc.3`.
- Backend, worker, webapp, nginx, postgres, and redis were healthy after rebuild.
- Alembic current/head remained `e8f901234567`.
- HTTPS health check returned `ok`.

### Behavior Check

- Existing old tasks without stored real chat title still use the safe UI fallback.
- Technical MAX fallback titles are not shown in WebApp task list/details:
  - `MAX dialog #...`;
  - `MAX chat #...`;
  - `MAX group #...`.
- Raw chat identifiers are not shown in the WebApp UI.
- Deployed backend extraction was verified with a sanitized synthetic MAX-like payload containing `message.chat.title`.
- Recent production rows were checked with masked identifiers only:
  - generated chat title rows are still present;
  - no manual alias is currently stored for the checked old chats;
  - old tasks need manual alias or a future MAX event with real chat title to display the real name.

### Remaining Gap

Add a WebApp chat alias management screen so admins can name old chats whose real title was never captured from MAX.

Release smoke after deployment: `release_smoke=ok`.

Tail-log pattern checks showed no traceback/error patterns, no token or secret patterns, no raw initData patterns, and no unexpected send patterns.

No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## MAX Mention-Based Assignee Selection — 2026-05-26

New `/задача` flows no longer send participant-picker buttons in the shared MAX chat.

Behavior:

- `member` behavior is unchanged: after text and deadline are known, the task is created as a self-task.
- `chat_admin` and `super_admin` receive a text prompt to specify one or more assignees through MAX structured `@mentions`.
- The prompt starts with `Укажите исполнителя или исполнителей через @упоминание.` and includes a short hint that mentioning the bot assigns the task to the command author.
- New flow messages do not include `Назначить себе`, participant buttons, or `Открыть в WebApp`.
- A single structured `@mention` creates one assignee.
- Multiple structured `@mentions` create one task with multiple assignees.
- Duplicate structured mentions are deduplicated.
- A plain-text `@name` without structured mention metadata does not create a task and returns a friendly retry prompt.
- Unresolved structured mentions are not guessed.
- Legacy `task:assign` callback handling remains in place for older messages that already contain inline buttons.

Safety:

- Role checks still use internal `ChatMember.role`.
- `member` cannot assign tasks to other participants through mention input.

## Bot Mention Self-Assignment — 2026-05-27

Status: implemented and covered by automated tests; no real MAX API calls were made for this check.

Behavior:

- In the `chat_admin`/`super_admin` assignee-selection step, mentioning `@secretary_oren_bot` means “assign the task to the command author”.
- The bot mention is replaced with the current actor and is not resolved as a separate bot user.
- `@secretary_oren_bot` plus participant mentions creates one multi-assignee task for the actor and the resolved participants.
- Duplicate actor mentions are deduplicated.
- `member` behavior is unchanged: ordinary members still create self-tasks through the normal member flow and cannot use pending assignee selection to gain assignment rights.

Safety:

- `MAX_BOT_USERNAME` remains `secretary_oren_bot`.
- No token, webhook secret, raw payload, full user id, full chat id, or message id is documented here.
- Final task creation cards stay compact and contain only task ref, text, assignee(s), deadline, and the `Открыть задачу` button.
- No production data was changed during this code task.

No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## Real MAX Mention-Based Assignee Selection — 2026-05-26

### Deployment

- Deployed commit: `7295aea`.
- VERSION remained `1.1.0-rc.3`.
- Backend, worker, webapp, nginx, postgres, and redis were healthy after rebuild.
- HTTPS health check returned `ok`.
- Release smoke passed with `release_smoke=ok`.

### Live Acceptance

Controlled MAX test chat verification was completed after deployment:

- New `/задача` flow for a `chat_admin` no longer showed assignee picker buttons.
- The bot prompted for executor selection with `Укажите исполнителя или исполнителей через @упоминание.`
- Buttons such as `Назначить себе`, participant buttons, and `Открыть в WebApp` were not shown in the assignee-selection prompt.
- A single structured `@mention` created a task with one assignee.
- Multiple structured `@mentions` created one task with multiple assignees.
- The final task card used `Исполнитель` for one assignee and `Исполнители` for multiple assignees.
- A no-mention follow-up returned the friendly retry text and did not create a task.
- UUIDs, raw status values, raw payloads, and internal ids were not shown in user-facing task cards.
- `member` self-task behavior was not repeated as a live role switch in this acceptance; it remains covered by regression tests from the same deployed commit.
- Legacy `task:assign` callback support remains available for older messages that already have buttons.

### Logs

Tail-log pattern checks after deployment and smoke showed:

- no traceback/error patterns;
- no token or secret patterns;
- no raw initData patterns;
- no unexpected background-send patterns.

No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## Task Deadline Clarification Role Diagnosis — 2026-05-26

### Sanitized Production Check

The reported live symptom was reproduced around a recent task titled `проверить до 01:00` in a MAX group chat. The production check used sanitized aggregate output only:

- chat found: yes;
- user found: yes;
- chat member found: yes;
- stored role for the task creator in that chat: `member`;
- `is_active`: true;
- source chat member role counts: `member=3`, `chat_admin=0`, `super_admin=0`.

No production roles or tasks were modified.

### Root Cause

The deadline-clarification flow already branches on internal `ChatMember.role`: `member` creates a self-task, while `chat_admin` and `super_admin` continue to assignee selection. The live user was stored as `member` in `Дьяк`, so the bot correctly applied member behavior even if the user is an administrator in the native MAX group.

MAX group-admin status is not automatically synchronized into `ChatMember.role` by the current webhook identity resolver. New MAX chat participants are created as `member` unless promoted inside `Дьяк`.

### Follow-Up

- Keep the safe rule: do not infer `chat_admin` from webhook payloads unless MAX provides a reliable admin field.
- Add or expose a managed flow for assigning `chat_admin` in `Дьяк`.
- Regression tests now cover `member`, `chat_admin`, and `super_admin` behavior after deadline clarification.

No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## Real MAX Chat Admin Role Mapping Check — 2026-05-26

### Deployment

- Deployed commit: `0810aec`.
- VERSION remained `1.1.0-rc.3`.
- Alembic current/head: `e8f901234567`.
- Backend, worker, webapp, nginx, postgres, and redis were healthy after rebuild.
- Release smoke passed with `release_smoke=ok`.

### Role Mapping

The test MAX chat and target user were identified through recent task context with sanitized output only:

- test chat found: yes;
- target user found: yes;
- user was `member` before the update: yes;
- one `ChatMember` row was updated from `member` to `chat_admin`;
- after update, the test chat role counts changed to `chat_admin=1`, `member=2`;
- production role changes were limited to one test chat member.

MAX native group-admin status is still not automatically synchronized into `ChatMember.role`. The internal role in `Дьяк` remains the source of truth for bot RBAC until a managed role assignment/sync flow is added.

### Live Acceptance

After the role update, the controlled live MAX check was completed:

- `/задача проверить до 01:00` triggered deadline clarification;
- after the deadline clarification, the bot showed assignee selection for the `chat_admin`;
- self-task creation was avoided for the promoted test user;
- selected-assignee creation flow was confirmed manually in the test chat;
- `member` self-task behavior remains covered by regression tests.

### Remaining Gap

Add a WebApp/admin role management screen or an explicit MAX-admin synchronization policy so test and production chat admins do not need manual DB role updates.

Tail-log pattern checks showed no traceback/error patterns, no token or secret patterns, no raw initData patterns, and no unexpected background-send patterns.

No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## Worker Healthcheck Timeout Diagnosis — 2026-05-27

### Diagnosis

- The worker container was inspected without printing secret environment values.
- The worker process was running and `RestartCount=0`.
- Docker health history showed healthcheck timeout entries, while the manual heartbeat healthcheck returned success.
- Worker logs showed the scheduler running jobs successfully without traceback or crash-loop patterns.
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED` remained `false`.

### Root Cause

The worker itself was not crashing. The production healthcheck used `python -m app.workers.jobs --healthcheck`, which imports worker and scheduler modules before checking the heartbeat file. Under startup/load conditions that command can exceed the 5 second Docker healthcheck timeout even when the heartbeat is fresh.

### Fix

- Production worker healthcheck now checks the heartbeat file with a lightweight Python one-liner.
- The healthcheck does not import scheduler modules and does not run reminder jobs.
- No production `.env` values were changed.
- No scheduler/reminder command was run manually.

No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## MAX Chat Task Creation Card Boundary — 2026-05-25

### Implementation Check

- The final task creation card in the shared MAX chat was simplified to a short summary.
- The card contains only the user-facing task reference, task text, assignee or assignees, deadline, and one `Открыть задачу` WebApp deep-link button.
- Extended controls are intentionally not shown in the creation card:
  - report submission;
  - report acceptance or rejection;
  - task history;
  - assignee changes or adding assignees;
  - deadline changes;
  - attachment actions.
- Internal UUIDs, raw status enums, source message IDs, chat IDs, organization IDs, and other internal identifiers stay out of creation-card text.
- The `#number` task card keeps contextual quick actions, while full management is owned by WebApp task details.

### WebApp Ownership

WebApp task details should remain the place for:

- report text and report review;
- assignee management;
- deadline changes;
- task history;
- attachments and file metadata.

No live MAX send was performed for this implementation check. No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## Manual `/пинг` Source Chat Delivery Model — 2026-05-25

### Implementation Check

- Manual `/пинг #number` now uses the same destination model as automatic chat deadline reminders.
- The reminder delivery target is the task source MAX chat: `Task.chat_id -> Chat.max_chat_id`.
- The command does not DM assignees in the current model.
- Assignees are mentioned in the source chat with MAX `max://user/<id>` links when available; users without `max_user_id` are shown by display name without a fake mention.
- The shared chat ping includes only the `Открыть задачу` WebApp deep-link button.
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false` records `skipped/background_disabled` and does not call MAX.
- Missing `Chat.max_chat_id` records `missing_max_chat_id`.
- Manual `task_ping` uses `channel=max_chat` and a 30 minute delivery cooldown per task/source chat/type.
- Self-task `/пинг` remains a local report-flow shortcut and does not create background delivery.

No live MAX send was performed for this implementation check. No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## Role Simplification Audit — 2026-05-25

### Implementation Check

- Active business roles are now `member`, `chat_admin`, and `super_admin`.
- Legacy `manager` rows are migrated to `chat_admin` by Alembic revision `e8f901234567`.
- Production pre-migration count was checked with sanitized output only: `manager_count=52`.
- `member` can create self-tasks and submit reports for assigned tasks.
- `member` cannot assign tasks to other users, create group assignments, mutate task participants, or use stale assignment callbacks for other users.
- `chat_admin` keeps assignment, group assignment, participant management, ping, and report acceptance/rejection capabilities in scope.
- `super_admin` remains unrestricted.
- New chat member role values no longer include `manager`.

No production data was changed during this code task. No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## Role Model Simplification Deploy Check — 2026-05-25

### Deployment

- Deployed commit: `e7731d5`.
- VERSION remained `1.1.0-rc.3`.
- Alembic current/head after deployment: `e8f901234567`.
- Backend, worker, webapp, nginx, postgres, and redis were healthy after rebuild.
- HTTPS health check returned `ok`.

### Migration Result

- Pre-upgrade role counts were collected with sanitized aggregate output only:
  - `manager=52`;
  - `member=91`;
  - `chat_admin=0`.
- After `alembic upgrade head`:
  - `manager=0`;
  - `chat_admin=52`;
  - `member=91`.
- Migrated legacy manager rows: `52`.

### Behavior Check

Service-level role guard checks were run inside the deployed backend container without writing production data:

- `member` self-task create guard: pass.
- `member` assigning another user: blocked.
- `chat_admin` assigning another user: allowed.
- legacy `manager` assigning another user: blocked.
- group assignment roles include `chat_admin` and `super_admin`.
- group assignment roles exclude `manager`.
- new chat member role value `manager` is rejected by schema validation.

Release smoke passed with `release_smoke=ok`. Full live MAX role acceptance with real task creation was not run in this deploy check to avoid production data changes; it remains a controlled manual follow-up if needed.

### Logs

Tail-log pattern checks showed:

- no traceback/error patterns;
- no token or secret patterns;
- no raw initData patterns;
- no unexpected background-send patterns.

No tokens, secrets, raw payloads, full real identifiers, cookies, initData, or full MAX user/chat identifiers were added to documentation.

## Task Deadline Timezone Pipeline Check — 2026-05-27

### Sanitized Live Diagnosis

Read-only production diagnosis for tasks `#31` and `#32` showed the deadline shift was already present in stored data:

- `#31` stored deadline UTC: `2026-05-26T00:11:00+00:00`; project-local display from stored value: `2026-05-26T05:11:00+05:00`; backend overdue check: yes.
- `#32` stored deadline UTC: `2026-05-26T00:12:00+00:00`; project-local display from stored value: `2026-05-26T05:12:00+05:00`; backend overdue check: yes.
- Expected storage for local `2026-05-27 00:11/00:12 UTC+5` would be `2026-05-26T19:11/19:12 UTC`.

No full task UUIDs, user ids, chat ids, MAX ids, raw payloads, tokens, cookies, or initData were printed.

### Fix

- Bot deadline parsing now uses project timezone `Asia/Yekaterinburg` (`UTC+5`) for user input such as `сегодня 00:11`, `сегодня до 00:11`, `завтра 15:00`, and `до 01:00`.
- Task creation/update normalizes deadline values to UTC before persistence.
- WebApp task list and task detail format deadlines explicitly in project timezone instead of relying on browser timezone.
- API `due_today` and inbox summary `today` use local project-day boundaries converted to UTC.
- Overdue comparison remains UTC-vs-UTC.

### Production Data Note

Existing tasks `#31` and `#32` were not changed automatically. If they should represent `2026-05-27 00:11/00:12 UTC+5`, they need a separate confirmed manual correction to `2026-05-26T19:11:00Z` and `2026-05-26T19:12:00Z`.

## Real MAX deadline timezone check — 2026-05-27

- Deployed commit: `032016d`.
- Project timezone: `Asia/Yekaterinburg` / `UTC+5`.
- Controlled live task: `#39`.
- New task input local time: `сегодня 00:52` in project timezone.
- Stored UTC converted correctly: yes, `deadline_at_utc=2026-05-26T19:52:00+00:00`.
- Project-local conversion: `2026-05-27T00:52:00+05:00`.
- `due_today` project-day behavior: pass; the deadline is inside `2026-05-27` local day.
- Overdue behavior after deadline: pass; UTC comparison reported overdue after `00:52` local.
- Old tasks `#31` and `#32` remain unchanged and still require separate manual correction if they should represent `27.05 00:11/00:12 UTC+5`.
- No old task data correction was performed.
- No tokens, secrets, raw payloads, full ids, cookies, or initData were added.

## Chat Participants Task Form UX Cleanup — 2026-05-27

Status: implemented as a WebApp-only UX cleanup; no backend behavior and no production data were changed.

- The menu and screen label are now `Задача участникам чата`.
- The create form title is `Новая задача участникам`.
- The organization field is hidden when there is only one/default organization; the internal `organization_id` remains part of the payload.
- `MAX default organization` is not shown as user-facing form text; if multiple organizations are available, it is displayed as `Основная организация`.
- Chat dropdowns and task rows use the shared chat display-title helper.
- Chat UUIDs, `max_chat_id`, and generated technical titles such as `MAX dialog #...` / `MAX chat #...` are not shown in this UI.
- The chat fallback remains `Чат без названия` when no real title or manual alias is available.

No tokens, secrets, raw payloads, full ids, cookies, or initData were added.

## Task Acceptance Rejection Reason Flow — 2026-05-31

Status: implemented and covered by automated tests. No live MAX calls were made for this code change.

What changed:

- The `Ответ ожидает приемки` notification now shows only user-facing actions: `Принять`, `Отклонить`, and `Открыть задачу`.
- The notification text no longer includes callback payloads, UUIDs, `Пользователь #...`, `Группа #...`, or technical actions such as `В работу`, `Ответить`, and `Отложить`.
- `Отклонить` no longer rejects the report immediately. It starts a 30 minute pending flow asking the authorized reviewer to write a rejection reason.
- The rejection reason is saved in task acceptance history and sent to the executor with `Написать отчет` and `Открыть задачу` actions.
- After rejection, a task with an expired deadline returns to `overdue`; a task with a future deadline returns to the working status.
- The executor can submit a new report after the rejection, which moves the task back to `waiting_acceptance`.

Safety notes:

- Only the task creator, chat admin, or super admin can accept or start the rejection flow.
- User-facing text does not expose raw callback payloads or internal identifiers.
- Deadline scheduler selection, per-chat deadline rollout, global deadline flags, and allowlist behavior were not changed.

No tokens, secrets, raw payloads, full ids, cookies, or initData were added.

## Real MAX task acceptance rejection reason check — 2026-05-31

Status: deployed and live-checked in a controlled MAX chat.

- Deployed implementation commit: `e86c380`.
- Follow-up hotfix commit: `96763c2`.
- Waiting acceptance notification is clean: yes.
- User-facing notification hides callback payloads, UUIDs, raw user labels, and raw group labels: yes.
- Actions shown to the reviewer: `Принять`, `Отклонить`, and `Открыть задачу`.
- Initial live check found that `Принять` changed backend state but did not leave a visible chat message; `96763c2` now sends a visible `Ответ по задаче #... принят ✅` message.
- `Принять` live check after hotfix: passed.
- `Отклонить` asks for a rejection reason: yes.
- The assignee receives `Приемка по задаче #... отклонена` with the reviewer reason: yes.
- The controlled overdue rejection check kept the task in `overdue`: yes.
- Repeat report after rejection remains covered by automated regression tests; no raw ids were added to docs.
- Deadline monitoring flags were left unchanged.
- Scheduler selection, per-chat opt-in, global deadline flags, and allowlist logic were not changed.
- Logs after deployment and live check showed no runtime errors, secret leaks, raw payload leaks, or unexpected sends.

No tokens, secrets, raw callback payloads, full ids, cookies, or initData were added.

## Real MAX task rejection reason flow check — 2026-05-31

Status: live controlled check passed.

- Clean waiting acceptance notification: yes.
- Reject button starts reason wizard: yes.
- Rejection reason saved: yes.
- Assignee receives rejection notice with reason: yes.
- Task remains in correct working or overdue state after rejection: yes.
- Repeat report after rejection works: yes.
- No payload, UUID, raw ids, or callback payload appeared in user-facing messages: yes.
- Deadline monitoring was unchanged.

No tokens, secrets, raw callback payloads, full ids, cookies, or initData were added.

## Relative deadline parsing regression — 2026-05-31

Status: fixed in parser and covered by regression tests. Production task `#63` was inspected read-only and was not modified.

Sanitized diagnosis:

- Task `#63` was found with title `Тест ошибка`.
- Stored deadline UTC: `2026-05-31T13:00:00+00:00`.
- Project-local deadline: `2026-05-31T18:00:00+05:00`.
- Created at project local time: `2026-05-31T08:56:51+05:00`.
- The original parsed deadline phrase is not stored with the task.

Root cause:

- The parser supported numeric relative expressions such as `через 2 часа`, but did not support bare `через час`.
- As a result, `сегодня через час` skipped the relative rule, matched the `сегодня` date-only rule, and received the default task deadline time `18:00`.

Fix:

- Relative deadline expressions now have priority over date-only defaults.
- Supported examples include `через час`, `через 1 час`, `через 2 часа`, `через 30 минут`, `через полчаса`, `сегодня через час`, and `сегодня через 30 минут`.
- `сегодня через час` is parsed as project-local `now + 1 hour`, then stored as UTC.
- Conflicting phrases such as `завтра через час` return deadline clarification instead of falling back to `18:00`.
- Past-deadline validation still requires the parsed deadline to be at least 1 minute in the future.

No tokens, secrets, raw payloads, full ids, cookies, or initData were added.

## Past Task Deadline Rejection — 2026-05-31

Implemented a shared production guard for task deadlines after deadline chat reminders were added.

- New task deadlines must be at least 1 minute later than the current time.
- Bot natural-language deadline input is interpreted in project timezone `Asia/Yekaterinburg` and normalized to UTC before comparison.
- Backend API create/update and group assignment paths reject invalid deadlines with `deadline_must_be_in_future`.
- Bot `/задача`, reply `/задача`, member self-task, and chat_admin/super_admin assignment flows keep the user on the deadline step when the deadline is invalid.
- The admin flow does not ask for `@упоминание` until a valid future deadline is provided.
- Wizard user-input cleanup is not triggered on invalid deadlines because no task has been created.
- Existing overdue tasks are not modified by this guard.

No scheduler/reminder jobs, MAX API calls, production env changes, tokens, secrets, raw payloads, full ids, cookies, or initData were used for this change.

## Chat deadline reminders production readiness — 2026-05-29

Status: implemented and covered by automated tests. No real MAX API calls were made during this audit.

Behavior:

- `task_due_in_1h` sends one reminder to the task source MAX chat when the deadline is in the one-hour scheduler window.
- `task_overdue` sends one reminder to the task source MAX chat when the deadline is reached.
- Reminders target `Task.chat_id -> Chat.max_chat_id`; assignee DMs are not used.
- Active assignees are mentioned with MAX mention links when `User.max_user_id` is available; otherwise their display name is plain text.
- Final tasks are skipped.
- Only chats with `Chat.status=active` are eligible. `pending_approval`, `rejected`, and `suspended` chats are skipped.
- Dedup remains one delivery per `task_id`, `chat_id`, `notification_type`, and `channel=max_chat`.
- `TASK_OVERDUE_NOTIFICATION_LOOKBACK_HOURS` limits overdue processing so first rollout cannot notify every old overdue task.

Flags:

- `MAX_SENDER_ENABLED` remains the transport master switch.
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED` remains the background delivery master switch.
- `TASK_DEADLINE_CHAT_REMINDERS_ENABLED` gates only automatic deadline chat reminders and defaults to `false`.

Verification:

- Backend tests cover due-in-one-hour selection, overdue selection, final-task skips, inactive-chat skips, missing `max_chat_id`, background disabled behavior, dedup, assignee mention formatting, plain-name fallback, multiple assignees, and overdue lookback.
- Production `.env` was not changed.
- Background notifications were not enabled.
- No scheduler/reminder run was triggered against live production data.

No tokens, secrets, raw payloads, raw ids, cookies, initData, or MAX responses were added.

## Real MAX overdue reminder controlled test — 2026-05-29

Status: completed as a one-task controlled delivery test after deploying `ef4b21a`.

Pre-check:

- VPS HEAD: `ef4b21a`.
- `VERSION`: `1.1.0-rc.3`.
- Safe flags before the test: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false`.
- `MAX_SENDER_ENABLED=true` and interactive command responses were enabled.
- Backend, worker, nginx, PostgreSQL, Redis, and WebApp were healthy.
- The first attempt did not create a matching test task, so the previous test window was closed without sends.

Controlled task:

- One fresh task was created in an active test MAX chat.
- Task reference: `#53`.
- Chat status: `active`.
- Source chat had `Chat.max_chat_id`: yes.
- Assignees count: 1.
- Assignee had `User.max_user_id`: yes.
- Deadline was already overdue at the controlled send moment.

Safety decision:

- Preflight for the default overdue lookback found 3 eligible overdue candidates.
- To avoid notifying old tasks, global scheduler flags were not opened for this run.
- A one-task controlled call used the same `NotificationDeliveryService` and MAX sender path for task `#53` only.
- No old overdue flood was possible from this test path.

Result:

- `task_overdue` delivery for task `#53`: sent once.
- Delivery count for the task/chat/type/channel after send: 1.
- A second controlled attempt for the same task was skipped by dedup.
- Duplicate notification prevented: yes.
- Final flags after the test: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false`.
- Release smoke: `release_smoke=ok`.
- Logs: no errors, no secret leak, no duplicate sends.

Remaining rollout note:

- Before enabling scheduler-based deadline reminders globally, use a narrower production allowlist/test mode or ensure the overdue lookback window contains only intended fresh test tasks.

No tokens, secrets, raw payloads, raw ids, cookies, initData, or MAX responses were added.

## Deadline reminder scheduler allowlist — 2026-05-30

Status: implemented as a production-safe rollout guard. No production `.env` values were changed and no scheduler/reminder run was triggered.

Problem:

- The real MAX controlled test for task `#53` confirmed delivery and dedup.
- Preflight also showed 3 eligible overdue candidates inside the default lookback window.
- Enabling scheduler-based reminders globally would therefore risk notifying more than the intended test task.

Fix:

- Added `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS`.
- Empty value keeps normal scheduler behavior.
- A single value such as `53` limits scheduler-based `task_due_in_1h` and `task_overdue` reminders to task `#53`.
- A comma-separated value such as `53,54,55` limits processing to those task numbers.
- The allowlist is applied after existing guards: active task, active chat, due/overdue window, overdue lookback, final-task skip, and dedup.
- Tasks excluded by the allowlist do not create notification delivery rows and do not call MAX.
- Invalid allowlist values fail configuration validation instead of silently falling back to mass mode.

Rollout guidance:

- For the next live scheduler test, set `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=true`, and `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=<test_task_number>` only for the controlled window.
- Return the background flags and allowlist to safe values immediately after the test.
- Do not use the allowlist as permanent business logic.

No tokens, secrets, raw payloads, raw ids, cookies, initData, or MAX responses were added.

## Real MAX scheduler deadline reminder allowlist test — 2026-05-30

Status: completed on the production VPS with scheduler-based delivery constrained by task-number allowlist.

Deploy:

- Deployed commit: `68434c9`.
- `VERSION`: `1.1.0-rc.3`.
- Backend, worker, nginx, PostgreSQL, Redis, and WebApp were healthy.
- Alembic current/head matched.

Controlled task:

- Test task ref: `#57`.
- Test chat status: `active`.
- Source chat had `Chat.max_chat_id`: yes.
- Assignees count: 1.
- Assignee had `User.max_user_id`: yes.
- Deadline became overdue during the test window.

Preflight:

- Eligible overdue without allowlist: 5.
- Eligible overdue with allowlist `57`: 1.
- Skipped by allowlist: 4.
- No scheduler window was opened until the allowlist matched only the test task.

Flags:

- Before test: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false`, `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=` empty.
- During test: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=true`, `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=57`.
- After test: flags returned to `false`, allowlist returned to empty.

Result:

- Scheduler sent one `task_overdue` notification for `#57`: yes.
- Source chat delivery: yes.
- Assignee mention path: yes.
- Delivery count for task/chat/type/channel: 1.
- After another scheduler interval, delivery count remained 1.
- Other overdue deliveries since the test task was created: 0.
- Old overdue tasks skipped by allowlist: yes.
- Release smoke: `release_smoke=ok`.
- Logs: no errors, no secret leak, no duplicate sends.
- Mass sends: no.

No tokens, secrets, raw payloads, raw ids, cookies, initData, or MAX responses were added.

## Real MAX due-in-1h reminder allowlist scheduler test — 2026-05-30

Status: completed on the production VPS with scheduler-based delivery constrained by task-number allowlist.

Deploy:

- Deployed code includes commit: `68434c9`.
- Current docs HEAD before this note: `4eea9c8`.
- `VERSION`: `1.1.0-rc.3`.
- Backend, worker, and nginx were healthy before and after the test.

Controlled task:

- Test task ref: `#60`.
- Test task title matched `Тест уведомления за час`.
- Deadline local: `2026-05-31 00:50:00 +05`.
- Deadline UTC: `2026-05-30 19:50:00 UTC`.
- Chat status: `active`.
- Source chat had `Chat.max_chat_id`: yes.
- Assignees count: 1.
- Assignee had `User.max_user_id`: yes.

Preflight:

- Due-in-1h candidates without allowlist: 1.
- Due-in-1h candidates with allowlist `60`: 1.
- Overdue candidates without allowlist: 6.
- Overdue candidates with allowlist `60`: 0.
- Old overdue tasks skipped by allowlist: yes.
- Scheduler window was not opened until the allowlist matched only task `#60`.

Flags:

- Before test: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false`, `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=` empty.
- During test: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=true`, `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=60`.
- After test: flags returned to `false`, allowlist returned to empty.

Result:

- Scheduler sent one `task_due_in_1h` notification for `#60`: yes.
- Source chat delivery: yes.
- Assignee mention path: yes.
- Delivery count for task/chat/type/channel: 1.
- After another scheduler interval, delivery count remained 1.
- Other due-in-1h deliveries: 0.
- Duplicate notification prevented: yes.
- Release smoke: `release_smoke=ok`.
- Logs after the window was closed: no errors, no secret leak, no duplicate sends.
- Mass sends: no.

No tokens, secrets, raw payloads, raw ids, cookies, initData, or MAX responses were added.

## Per-chat deadline reminder rollout gate — 2026-05-31

Status: implemented as a production rollout control. No production `.env` values were changed and no scheduler/reminder run was triggered by this implementation step.

Problem:

- `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS` is safe for one-task controlled tests.
- It is inconvenient for gradual production rollout by chat.
- Existing chats must not start receiving deadline reminders automatically when global flags are enabled.

Fix:

- Added per-chat opt-in stored in `Chat.settings.deadline_reminders_enabled`.
- Default is `false`; existing chats remain disabled until a super-admin turns them on.
- `/super-admin` active chat cards now show a `Дедлайн-уведомления` switch.
- Pending, rejected, and suspended chats show the switch disabled because deadline reminders are available only after connection.
- Added `PATCH /api/super-admin/chats/{chat_id}/settings` for super-admin-only updates.
- Scheduler-based `task_due_in_1h` and `task_overdue` selection now requires an active chat with `deadline_reminders_enabled=true`.
- The delivery service also records a safe skipped delivery with `chat_deadline_reminders_disabled` if a deadline reminder is attempted directly for a disabled chat.
- Global gates remain required: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true` and `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=true`.
- The task-number allowlist remains available as an additional controlled test safety guard.

Verification:

- Automated tests cover default disabled chats, enabled active chats, pending chats even with the setting, disabled-chat delivery skip reason, global feature flag behavior, allowlist behavior, and super-admin toggle access.
- No MAX API calls were made.
- No tokens, secrets, raw payloads, raw ids, cookies, initData, or MAX responses were added.

## Real MAX per-chat deadline reminder rollout check — 2026-05-31

Status: completed on the production VPS after deploying `f74614e`.

Deploy:

- VPS HEAD: `f74614e`.
- `VERSION`: `1.1.0-rc.3`.
- Backend, worker, webapp, nginx, PostgreSQL, and Redis were healthy after rebuild.
- Alembic current/head matched.
- `/super-admin` production bundle included the `Дедлайн-уведомления` switch.

Default state:

- Active chats: 58.
- Chats with `deadline_reminders_enabled=true` before opt-in: 0.
- Global flags before test: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false`, `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=` empty.

Opt-in:

- Super-admin login/API check succeeded without printing credentials or cookies.
- One active test chat was toggled to `deadline_reminders_enabled=true`.
- Enabled active chats after opt-in: 1.
- Other active chats remained disabled.

Controlled task:

- Test task ref: `#61`.
- Test chat status: `active`.
- Test chat had `Chat.max_chat_id`: yes.
- Test chat had `deadline_reminders_enabled=true`: yes.
- Assignees count: 1.
- Assignee had `User.max_user_id`: yes.
- Task deadline was near enough for a short overdue scheduler window.

Scheduler window:

- During test: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=true`, `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=61`.
- Scheduler sent one `task_overdue` notification for `#61`: yes.
- Source chat delivery: yes.
- Delivery count for task/chat/type/channel: 1.
- After another scheduler interval, delivery count remained 1.
- Other overdue sends since test task creation: 0.
- Duplicate notification prevented: yes.

Final state:

- Global flags returned to `false`; allowlist returned to empty.
- Per-chat opt-in remained enabled for the one test chat.
- Enabled active chats after test: 1.
- Release smoke: `release_smoke=ok`.
- Logs: no errors, no secret leak, no unexpected sends, no duplicate sends.
- Mass sends: no.

No tokens, secrets, raw payloads, raw ids, cookies, initData, or MAX responses were added.

## Real MAX per-chat deadline reminder rollout recheck — 2026-05-31

Status: completed on the production VPS with the per-chat opt-in already enabled for the selected active test chat.

State before the scheduler window:

- VPS HEAD: `5f9613b`.
- `VERSION`: `1.1.0-rc.3`.
- Backend, worker, webapp, nginx, PostgreSQL, and Redis were healthy.
- Global flags before test: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false`, `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=` empty.
- Active chats: 58.
- Active chats with `deadline_reminders_enabled=true`: 1.
- Selected chat display title: `Тест ДЬЯК`.
- Selected chat status: `active`.
- Selected chat had `Chat.max_chat_id`: yes.
- Selected chat had `deadline_reminders_enabled=true`: yes.

Controlled task:

- Test task ref: `#73`.
- Task status before send: `new`.
- Task deadline had just become overdue in project local time.
- Assignees count: 1.
- Assignee had `User.max_user_id`: yes.
- Existing `task_overdue` delivery count for the task before the window: 0.

Preflight:

- Eligible overdue candidates before per-chat opt-in/allowlist filtering: 7.
- Eligible overdue candidates with per-chat opt-in: 7.
- Eligible overdue candidates with per-chat opt-in and allowlist `73`: 1.
- Old overdue risk without allowlist: 6.
- Scheduler window was not opened until the allowlist matched only task `#73`.

Scheduler window:

- During test: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=true`, `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=73`.
- Scheduler sent one `task_overdue` notification for `#73`: yes.
- Source chat delivery: yes.
- Assignee mention path: yes; the task assignee had a MAX user id and the chat reminder formatter uses MAX mention links when available.
- Delivery count for task/chat/type/channel: 1.
- After another scheduler interval, delivery count remained 1.
- Other overdue tasks were skipped by the allowlist.
- Duplicate notification prevented: yes.

Final state:

- Global flags returned to `false`; allowlist returned to empty.
- Per-chat opt-in remained enabled for `Тест ДЬЯК`.
- Enabled active chats after test: 1.
- Release smoke: `release_smoke=ok`.
- Logs: no errors, no secret leak, no unexpected sends, no duplicate sends.
- Mass sends: no.

No tokens, secrets, raw payloads, raw ids, cookies, initData, or MAX responses were added.

## Production opt-in deadline reminders rollout — 2026-05-31

Status: started in controlled production mode with global deadline-reminder flags enabled and chat-level opt-in limiting the rollout.

State before enabling:

- VPS HEAD before enabling: `ba1e8f7`.
- `VERSION`: `1.1.0-rc.3`.
- Backend, worker, webapp, nginx, PostgreSQL, and Redis were healthy.
- Active chats: 58.
- Active chats with `deadline_reminders_enabled=true`: 1.
- Enabled chat display title: `Тест ДЬЯК`.
- Active chats with `deadline_reminders_enabled=false` or missing: 57.
- Global flags before enabling: `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false`.
- `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS` before enabling: empty.

Preflight:

- Due-in-1h candidates in active chats: 0.
- Due-in-1h candidates after opt-in chat gate: 0.
- Overdue candidates in active chats inside the configured lookback: 7.
- Overdue candidates after opt-in chat gate: 7.
- Final tasks in the overdue lookback: 0.
- All overdue candidates after the chat gate belonged to the opted-in test chat.
- Two candidates had already received `task_overdue` deliveries during previous controlled tests.
- Five candidates did not yet have overdue deliveries: `#67`, `#64`, `#65`, `#68`, `#66`.
- The operator explicitly confirmed enabling without task-number allowlist and accepting those five sends in `Тест ДЬЯК`.

Production mode enabled:

- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true`.
- `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=true`.
- `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=` empty.
- Backend and worker were force-recreated after the env change.
- Container flags were verified sanitized after restart.

First monitoring window:

- Scheduler sent 5 `task_overdue` notifications.
- Sent task refs: `#67`, `#64`, `#65`, `#68`, `#66`.
- `task_due_in_1h` sent count: 0.
- Delivery chat count: 1.
- Delivery chat title: `Тест ДЬЯК`.
- Deliveries to non-opt-in chats: 0.
- Failed deliveries: 0.
- Delivery rows with errors: 0.
- Duplicate keys after another scheduler interval: 0.
- Existing previously-sent tasks were not duplicated.
- Release smoke: `release_smoke=ok`.
- Logs: no runtime errors, no secret leak, no unexpected sends, no duplicate sends.

Current state after the initial window:

- Global flags remain enabled for opt-in production monitoring.
- `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS` remains empty.
- Per-chat opt-in remains enabled only for `Тест ДЬЯК`.
- 1h / 6h / 24h monitoring checkpoints are pending after this initial rollout note.

No tokens, secrets, raw payloads, raw ids, cookies, initData, or MAX responses were added.

## Super-Admin Chat Approval Web — 2026-05-28

Status: implemented as a separate web control plane, outside MAX WebApp.

Implemented:

- Separate page: `/super-admin`.
- Separate auth: login/password with a dedicated httpOnly super-admin cookie.
- MAX WebApp `initData` is not accepted as super-admin auth.
- Super-admin chat list shows connection status, display title, type, active member count, Dyak chat-admin count, and MAX-admin count when a saved snapshot exists.
- Chat statuses are `pending_approval`, `active`, `rejected`, and `suspended`.
- Existing chats migrate to `active`.
- New group chats created through MAX identity resolution start as `pending_approval`; personal dialogs stay `active`.
- Pending/rejected/suspended chats do not run bot commands and answer with a safe pending-approval message.
- Super-admin can approve/reject/suspend/reactivate chats.
- Super-admin can assign or remove `chat_admin` per chat member.
- Multiple `chat_admin` members are supported.
- The role endpoint does not assign `super_admin`.
- Removing the last active `chat_admin` requires explicit confirmation.
- Status and role changes write audit entries with masked identifiers.

UI safety:

- Raw `chat_id`, `user_id`, `max_chat_id`, `max_user_id`, raw payloads, cookies, tokens, and initData are not shown in the super-admin UI.
- MAX admin marker is informational only; `ChatMember.role` remains the authoritative Dyak permission source.
- Super-admin functions are not added to the mobile MAX WebApp.

Remaining gaps:

- MAX admin marker is `unknown` unless a saved snapshot exists.
- A future controlled sync can fetch MAX admins if the official API path is available and approved.

## MAX admin marker sync — 2026-05-28

Status: implemented for the super-admin web control plane.

Implemented:

- Super-admin can manually sync MAX admin markers for one selected chat.
- Endpoint: `POST /api/super-admin/chats/{chat_id}/sync-max-admins`.
- The UI button is `Обновить роли MAX`.
- Participant rows show `Админ в MAX: Да`, `Админ в MAX: Нет`, or `Админ в MAX: Не проверено`.
- The MAX marker remains informational only.
- `Админ чата в Дьяке` remains a separate checkbox and is the authoritative internal permission.
- Sync does not automatically change `ChatMember.role`.
- The backend stores only a snapshot marker and checked timestamp in chat settings.
- The endpoint returns only safe counters and does not expose raw MAX ids or raw MAX API responses.
- Tests use a fake MAX client; no real MAX API calls were made.

Operational notes:

- Sync is intentionally scoped to one selected chat and is not a bulk background job.
- If MAX API is unavailable or the chat has no MAX id, the super-admin page keeps existing/unknown markers and shows a safe error.

## Super-admin chat approval deploy recovery check — 2026-05-28

Status: completed after resuming from a network interruption during deploy.

Recovery state:

- Execution resumed safely after the network failure.
- VPS HEAD before deploy window: `093e0f4`.
- VPS HEAD after recovery: `12a8c36`.
- `origin/main`: `12a8c36`.
- `VERSION`: `1.1.0-rc.3`.
- Working tree on VPS: clean.
- Super-admin env presence was checked without printing values:
  - login set: yes;
  - password set: yes;
  - session secret set: yes.
- Safe mode remained unchanged:
  - `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`;
  - `MAX_WEBHOOK_DEBUG_LOG=false`.

Deploy and migration:

- Backend, worker, WebApp, and nginx were rebuilt from `12a8c36`.
- Alembic current/head: `f9a0b1c2d3e4`.
- Chat status counts after migration:
  - total: 57;
  - active: 57;
  - pending_approval: 0;
  - rejected: 0;
  - suspended: 0.
- Existing chats are active after migration.

Runtime checks:

- Containers healthy: backend, worker, webapp, nginx, postgres, redis.
- `/api/health`: ok.
- SPA routes `/`, `/tasks`, `/settings`, `/super-admin`: 200.
- Unauthenticated `/api/super-admin/chats`: blocked with 401.
- Login API check: 200, cookie set yes.
- Authenticated super-admin chat list: 200, chats count 57.
- Participants read-only check: members count 2 in the sampled chat; role counts `member=2`, `chat_admin=0`, `super_admin=0`; MAX admin marker `unknown=2`.
- Role checkbox mutation was not exercised on production data; no production roles were changed during recovery.
- Pending chat gate remains covered by backend tests; no new production MAX chat was created for this check.
- Release smoke: `release_smoke=ok`.
- Fresh log scan: no traceback/errors, no secret leak, no raw initData leak, no unexpected background sends.

Remaining gaps:

- Browser visual login and role-checkbox interaction can be checked manually by the service operator using the configured super-admin credentials.

No login, password, session secret, tokens, cookies, raw ids, or raw payloads were added.

## Super-admin login copy-paste fix — 2026-05-28

Status: implemented and prepared for deploy.

Sanitized diagnosis:

- Host `.env` and backend container both had super-admin login, password, and session secret set.
- Host/container value lengths matched.
- Controlled backend login using the configured env values returned `200` and set a session cookie.
- `/api/super-admin/auth/login` is not the route; the correct route is `/api/super-admin/login`.

Root cause:

- The login form and backend comparison accepted copied credentials literally. A leading/trailing space or newline from copying values out of `.env` caused `Invalid login or password`.

Fix:

- Frontend trims leading/trailing whitespace before submitting super-admin login.
- Backend trims leading/trailing whitespace before comparing login/password.
- Internal password characters remain significant; only surrounding copy-paste whitespace is ignored.
- Regression test covers copied credentials with surrounding whitespace.

No login, password, session secret, cookie value, tokens, raw ids, or raw payloads were added.

## Admin task wizard assignee flow check — 2026-05-27

Status: deployed and covered by service-level regression tests. Controlled live MAX command execution was not performed by Codex; no real MAX API calls or mass sends were made during this check.

Sanitized findings:

- The admin assignee-selection fixes were already present in main before this check: yes.
- The admin assignee-selection fixes were already present on VPS before this check: yes.
- VPS was behind `origin/main` only by documentation before the new `/пинг` guard fix.
- Historical tasks `#35` and `#36` were inspected read-only with masked identifiers only.
- For both `#35` and `#36`, the creator is an active `member`, the creator is the only assignee, and the task chat had no active `chat_admin` at inspection time.
- Root cause for the old `#35`/`#36` self-task behavior is consistent with role setup (`member`), not the current admin flow.

Implemented in deploy commit `fb84271`:

- `chat_admin`/`super_admin` task creation without assignees continues to ask for `@упоминание` after text and deadline.
- Task creation does not create an admin self-task before assignee mention.
- `member` `/пинг` is now blocked before task lookup with:

```text
Пинг по задаче доступен только администратору чата.
```

Verification:

- Backend tests: `777 passed`.
- Ruff: passed.
- Smoke: `release_smoke=ok`.
- Worker/backend/webapp/nginx/postgres/redis were healthy after deploy.
- Alembic current/head: `e8f901234567`.
- Logs showed no traceback, no secret leak, and no unexpected background sends.

Remaining manual live check:

- In a controlled test chat where the actor is confirmed `chat_admin`, verify reply `/задача` + deadline and slash-menu `/задача` wizard both ask for `@упоминание` before creating the task.
- Verify one and multiple `@упоминания` create the selected assignee set.
- Member `/пинг` is covered by tests; live member check was skipped.

No tokens, secrets, raw payloads, full ids, cookies, initData, or full MAX user/chat identifiers were added.

## Chat Display Title Alias — 2026-05-27

Status: implemented as backend API plus WebApp Settings UI. Production alias assignment is tracked in the deploy check below.

- Manual chat alias is stored in `Chat.settings.display_title`.
- `PATCH /api/chats/{chat_id}` accepts `display_title`.
- `chat_admin` can update only the current chat from their auth context; `super_admin` can update any chat.
- `member` cannot update chat aliases.
- Chat API responses include `display_title`.
- WebApp Settings contains `Названия чатов` with `Название в Дьяке` fields for editable chats.
- Task list, task detail, chat filters, and `Задача участникам чата` screens use the shared display-title helper.
- Alias is used only inside Дьяк and does not rename the MAX chat.
- Raw chat ids, `max_chat_id`, and generated titles remain hidden from user-facing UI.

No tokens, secrets, raw payloads, full ids, cookies, or initData were added.

## Real MAX chat alias deploy check — 2026-05-27

- Deployed commit: `2df4330`.
- Alias API deployed: yes.
- Selected old live chat was found through sanitized task context: yes.
- Selected chat alias set to `Тест секретарь`: yes.
- Production data changed: yes, exactly one `Chat.settings.display_title` value.
- Alias storage source after update: manual alias.
- Task list uses alias: yes, via shared WebApp chat display-title helper.
- Task detail uses alias: yes, via shared WebApp chat display-title helper.
- Chat filter uses alias: yes.
- `Задача участникам чата` form/details use alias: yes.
- Raw ids hidden in user-facing UI: yes.
- Member access restricted: yes; chat alias edits require `chat_admin` for that chat or `super_admin`.
- Smoke after deploy: `release_smoke=ok`.
- Container health after deploy: backend, worker, webapp, nginx, postgres, redis healthy.
- Remaining gap: authenticated visual confirmation inside the user's MAX WebApp session should be checked on device.

No tokens, secrets, raw payloads, full ids, cookies, or initData were added.

## Task creation wizard message cleanup — 2026-05-29

Status: implemented for new `/задача` flows.

Implemented:

- Task creation now tracks one editable bot wizard message through the text, deadline, assignee, and final-card steps.
- The deadline prompt edits the previous wizard message instead of leaving an additional permanent bot prompt.
- The assignee prompt edits the same wizard message and no longer includes a separate `Срок понял` service line.
- After successful assignee selection or member self-task creation, the wizard message is edited into the final task card.
- The final card remains compact: task ref, task text, assignee/assignees, deadline, and `Открыть задачу`.
- User messages are not deleted or edited: deadline replies, `@mention` replies, and original replied source messages remain intact.
- If MAX message editing fails, the bot sends the final card as a fallback and records cleanup status as failed for diagnostics.
- Legacy `task:assign` callback handling remains supported for old already-sent callback messages.

No tokens, secrets, raw payloads, full ids, cookies, initData, or real MAX API calls in tests were added.

### Live cleanup diagnosis follow-up — 2026-05-29

Status: root cause found and fixed after live MAX showed the deadline prompt still visible.

Sanitized diagnosis:

- Deployed VPS HEAD was confirmed at `456f289`; `VERSION` remained `1.1.0-rc.3`.
- Backend logs had no edit-attempt or edit-failure lines for the live flow.
- Latest task wizard pending action showed `cleanup=failed`, `picker_message_id` missing, and cleanup error `wizard message id is missing`.
- No raw MAX payloads, full message ids, chat ids, user ids, tokens, or cookies were printed.

Root cause:

- The live MAX send response returned the editable message id in a nested response shape not covered by the previous parser.
- Because the wizard message id was not captured, the follow-up handler could not call edit-message and fell back to sending the final task card as a new message.

Fix:

- The MAX sender now extracts message ids from nested response paths such as `message.body.mid`, `body.message_id`, and `result.messageId`, in addition to the existing top-level paths.
- Safe wizard diagnostics now log only whether a message id is present, its length, edit attempt status, and sanitized fallback reason.
- Regression tests cover nested MAX message id extraction and verify that the admin wizard uses the captured nested id for edit calls.

### Task wizard user input cleanup — 2026-05-29

Status: implemented behind an explicit configuration flag.

Behavior:

- Pending task-creation actions track only user-authored wizard input message ids: `/задача`, task text, deadline, and assignee mention.
- The original message used as reply source is preserved and is not added to cleanup ids.
- After successful task creation, if `TASK_WIZARD_DELETE_USER_INPUTS=true`, the bot best-effort deletes tracked user input messages.
- The final task card and editable bot wizard message are preserved.
- Delete failures do not roll back task creation; cleanup result is recorded as `partial` or `failed` for diagnostics.
- The flag defaults to `false` in sample env/deployment docs so production can enable it only after a controlled MAX rights check.

No tokens, secrets, raw payloads, full ids, cookies, initData, or real MAX API calls in tests were added.

### Real MAX task wizard user input cleanup check — 2026-05-29

Status: confirmed in a controlled live MAX flow after deploying commit `801664e`.

Deployment and safety:

- VPS deployed app commit: `801664e`.
- `VERSION` remained `1.1.0-rc.3`.
- Backend, worker, webapp, nginx, postgres, and redis were healthy.
- Release smoke result: `release_smoke=ok`.
- No scheduler/reminder job was started manually.
- No mass sends were performed.

Controlled flag checks:

- With `TASK_WIZARD_DELETE_USER_INPUTS` unset/false, the task wizard still edited the bot wizard message in place, no user-message delete attempts were observed, and user wizard input messages remained visible as expected.
- For the controlled deletion test, `TASK_WIZARD_DELETE_USER_INPUTS=true` was enabled in production `.env` and backend was recreated.
- Backend confirmed the flag as `true` without printing secret values.
- The controlled `/задача` flow visually removed the user wizard service messages and left only the final task card.
- Backend logs showed user-input cleanup completed and no incomplete cleanup markers.
- Delete failures observed: no.
- Final task card preserved: yes.
- Source reply preservation was not part of this visual run; code and tests keep replied source messages out of the cleanup id list.
- Final flag state after the check: `TASK_WIZARD_DELETE_USER_INPUTS=true`.

No tokens, secrets, raw payloads, full ids, message ids, cookies, or initData were added.

## Super-admin pending chat visibility fix — 2026-05-29

Status: implemented as an API/frontend visibility hardening for newly discovered MAX group chats.

Sanitized live diagnosis:

- New MAX group chat was found in the database.
- DB status: `pending_approval`.
- Chat type: `max_chat`.
- Active members count: 1.
- Active role counts: `member:1`, `chat_admin:0`.
- `max_chat_id` presence: yes.
- Tasks in the new chat: 0.
- Commands in the chat were blocked by the pending gate, matching the expected onboarding behavior.
- Super-admin API `/api/super-admin/chats` returned the new pending chat and status counts showed `pending_approval=1`.

Root cause:

- Backend chat creation and pending gate were already correct.
- The super-admin page relied on client-side filtering over the loaded chat list, so a stale browser bundle or an active local search could make the `Ожидают подключения` filter appear empty even when the API had a pending chat.
- SPA routes also lacked explicit no-store cache headers for `index.html`, increasing the chance of an operator seeing an old frontend bundle after deploy.

Fix:

- `GET /api/super-admin/chats` now supports `status=pending_approval`, `active`, `rejected`, and `suspended`.
- Legacy query alias `status=pending` maps to `pending_approval`.
- The super-admin UI requests the selected status from the API instead of relying only on local filtering.
- Switching the status filter clears the search box so pending chats are not hidden by a stale search term.
- Empty state now distinguishes “hidden by search” from “no chats for this status”.
- WebApp nginx serves SPA `index.html`/routes with `Cache-Control: no-store`; hashed assets remain immutable.

No chat was approved or activated during the fix. The new chat remains `pending_approval` until a super-admin explicitly approves or rejects it.

No tokens, secrets, raw payloads, full ids, message ids, cookies, or initData were added.

## Pending MAX chat title fallback — 2026-05-29

Status: implemented as MAX API title lookup plus manual alias UX for pending onboarding.

Sanitized diagnosis:

- The new pending chat had `status=pending_approval`.
- Chat type: `max_chat`.
- `max_chat_id` presence: yes.
- Stored title source: generated technical fallback.
- `settings.display_title`: absent.
- Settings keys only: source/admin snapshot keys.
- Active members count: 1.
- Active role counts: `member:1`.
- Visible display title before fix: `Чат без названия`.

Root cause:

- The webhook event that created the pending chat did not provide a reliable real chat title in the normalized title paths.
- Because a generated fallback title was stored and no manual alias existed, the super-admin UI correctly hid the technical MAX fallback and showed `Чат без названия`.

Fix:

- MAX client now supports read-only `get_chat_info` for one selected chat and normalizes `title`, `name`, `display_name`, and nested chat/result shapes without logging raw responses.
- Identity resolver tries MAX chat info lookup when a new group/max_chat has no real title from webhook and `max_chat_id` is available.
- Existing generated fallback titles can be updated when MAX later returns a real title.
- Manual alias in `Chat.settings.display_title` remains the display priority and is not overwritten.
- Super-admin API adds `POST /api/super-admin/chats/{chat_id}/sync-max-chat-info` with sanitized response fields only.
- Super-admin API adds `PATCH /api/super-admin/chats/{chat_id}/display-title` for manual aliases during onboarding.
- Pending fallback chats show `Название чата в Дьяке`, `Сохранить название`, `Обновить из MAX`, and a warning before approve if the title is still fallback.
- The chat remains `pending_approval` until explicit super-admin approval.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Pending chat title sync deploy recovery check — 2026-05-29

Status: completed after recovery from a network interruption during deploy validation.

Deployment state:

- Deployed commit: `d2caff2`.
- VERSION remained `1.1.0-rc.3`.
- Backend, worker, webapp, nginx, postgres, and redis were healthy.
- `/api/health` returned ok.
- Alembic current/head: `f9a0b1c2d3e4`.
- `/super-admin` route returned 200.

Pending chat title check:

- Before sync, the pending chat was visible with fallback title `Чат без названия`.
- Controlled read-only MAX chat info sync was run once for that selected pending chat.
- Sync result: `title_updated=yes`, `title_source=real`, display title `Тест ДЬЯК`.
- After recovery, the pending chat still had status `pending_approval`.
- After recovery, the pending chat display title remained `Тест ДЬЯК`.
- Display title source after sync: `real`.
- Manual alias was not needed.
- Approve/reject was not performed.
- Raw ids remained hidden in output and docs.

Validation:

- Smoke result: `release_smoke=ok`.
- Logs showed no traceback/errors.
- No secret leak was detected.
- No raw MAX response leak was detected.
- No unexpected sends were detected.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## Live super-admin pending chat flow check — 2026-05-29

Status: confirmed by live super-admin UI check.

Confirmed:

- Pending chat is visible in the `Ожидает подключение` filter: yes.
- Display title: `Тест ДЬЯК`.
- Title source: real title from MAX API sync.
- The chat remains `pending_approval` until explicit approve.
- Super-admin pending chat flow works as expected.
- Approve/reject was not performed during the title sync check.
- No raw ids were exposed.
- No secret leak was observed.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## MAX web slash command fallback — 2026-05-29

Status: implemented as a bot-side fallback for clients that do not show the native slash-popup.

Deployment diagnosis:

- VPS was checked after the first fallback commit and was still at `d2caff2`, while `origin/main` contained `8fa3d10`.
- The initial live `/` symptom was therefore consistent with the fallback not being deployed yet.
- A stronger alias set was added before the next deploy so web MAX users are not dependent on a single slash message.

Registration check:

- `scripts/max/register_bot_commands.py --dry-run` was checked locally with backend dependencies.
- Registered command names are emitted without slash: `дьяк`, `задача`, `мои_задачи`, `отчет`, `пинг`, `помощь`.
- Deprecated `секретарь` is not registered as a native command.
- `max_api_called=no`; no PATCH `/me` call was made during this check.

Observed behavior:

- Previous native/mobile command registration remains the expected path when the MAX client supports slash-popup commands.
- Web MAX may not show the slash-popup on `/`.
- Sending `/` as a regular message now returns a compact `Команды Дьяка` help response.
- Sending `@secretary_oren_bot /` returns the same fallback help.
- Sending `/помощь`, `/help`, `/команды`, `команды`, `дьяк помощь`, or `/дьяк помощь` returns the same fallback help.
- The fallback includes one `Открыть Дьяк` button and does not create tasks, reports, pings, or pending actions.
- Help aliases remain available in `pending_approval` chats and append the standard pending-approval notice; working commands remain blocked.

No tokens, secrets, raw MAX responses, raw payloads, full ids, message ids, cookies, or initData were added.

## WebApp Accessible Chats Listing Fix — 2026-05-27

Status: implemented as a backend access-scope fix for `/api/chats`.

Sanitized diagnosis:

- Task `#38`: task chat exists; chat display source is manual alias; active creator membership exists; creator role is `member`; active members count is 1.
- Task `#41`: task chat exists; chat display source is safe fallback; active creator membership exists; creator role is `member`; active members count is 2.
- Both task chats are valid active memberships for their creator context, so missing group chats in the WebApp dropdown was not caused by missing task/chat data.

Root cause:

- `/api/chats` used `auth_context.chat_id` from the WebApp session as a hard filter.
- When WebApp was launched from a personal dialog, the chat dropdown was narrowed to that launch chat even though the user had active memberships in group chats.

Fix:

- `/api/chats` now returns all active `ChatMember` chats for the authenticated user, optionally narrowed by organization scope.
- `super_admin` still receives all chats.
- The launch chat no longer restricts the WebApp chat dropdown to a single chat.
- Raw chat ids, `max_chat_id`, generated `MAX chat #...` titles, raw payloads, tokens, cookies, and initData remain out of user-facing UI and docs.

## MAX Chat Title Extraction Diagnosis — 2026-05-27

Status: implemented as a webhook normalization and identity resolver hardening. No production data was mass edited.

Sanitized current-data diagnosis:

- Accessible chats checked: 57.
- Chats with manual alias: 1.
- Chats with stored real non-generated title: 52.
- Chats with generated fallback title: 4.
- Chats displayed as safe fallback `Чат без названия`: 4.
- Problematic chats were inspected with masked ids only; each checked row had a chat record, settings keys only, task count, sample `task_ref`, and `max_chat_id` presence checked without raw ids.
- Sample task `#41` belongs to a valid chat with active membership, but the stored chat title is still generated fallback and no manual alias is set.

Root cause:

- Some MAX events store the real chat name outside the previously covered `message.chat.title` path, or do not include a reliable title in the event that created the older chat record.
- The previous title extractor could miss a real sibling field such as `name` when the same object also contained a generated technical `title`.

Fix:

- The webhook normalizer now checks additional safe title paths, including `message.recipient`, `message.body.chat`, top-level `body.chat`, top-level `chat`/`recipient`, `dialog`, `conversation`, and `message_created` variants.
- The extractor ignores generated or identifier-like candidates such as `MAX chat #...`, `MAX dialog #...`, `MAX group #...`, UUID-like strings, numeric-only strings, and message-id-like values.
- If a context object has a generated `title` but a real `name`/`display_name`, the normalizer keeps looking inside that same object before giving up.
- The identity resolver creates new chats with a real title when available and updates existing generated fallback titles when a later real title arrives.
- Manual aliases in `Chat.settings.display_title` remain preserved and are not overwritten by webhook-derived titles.
- Sanitized debug, when explicitly enabled for a short controlled window, logs only candidate path presence, value length, and masked previews; raw payloads and full ids are not logged.

Remaining gap:

- Old chats whose real title was never captured still need a manual alias in Дьяк or a future MAX event that includes the title.

No tokens, secrets, raw payloads, full ids, cookies, or initData were added.

## Manual chat aliases for old tasks — 2026-05-27

Status: completed as a targeted production data update for two selected old task chats.

Sanitized pre-check:

- Task `#37`: found; task chat exists; previous chat display source was manual alias; tasks in the same chat: 5.
- Task `#30`: found; task chat exists; previous chat display source was safe fallback `Чат без названия`; tasks in the same chat: 4.
- Tasks `#37` and `#30` belong to different chats, so the requested aliases are not conflicting.

Applied aliases:

- Task `#37` chat alias set to `Тестовые комменты`.
- Task `#30` chat alias set to `ОВИС и Ко)`.
- Only the selected task chats were updated.
- Existing chat `settings` keys were preserved; only `settings.display_title` was added or replaced.
- No raw ids were exposed in output or docs.
- No mass updates were performed.
- No MAX API calls were made.

Post-check:

- Task `#37` chat display source: manual alias; visible title: `Тестовые комменты`.
- Task `#30` chat display source: manual alias; visible title: `ОВИС и Ко)`.
- WebApp task list, task detail, chat filter, and `Задача участникам чата` display paths use the same `display_title` source.

No tokens, secrets, raw payloads, full ids, cookies, or initData were added.
