# Bot Command Center

## Purpose

Bot Command Center describes the short MAX chat commands for `Дьяк`.

The bot is for fast actions inside a MAX chat: create, find, summarize, report, and remind. The WebApp is for details, filters, history, attachments, and extended management. Commands should be short, forgiving, and easy to remember.

User-facing bot UX must use `task_number` and `task_ref`, not internal UUIDs. Internal UUIDs remain API and callback identifiers, but users should work with references like `#1042`.

## Prerequisite: Short Task Numbers

Tasks have an organization-scoped short number:

```text
#1042
```

Supported user input:

- `1042`
- `#1042`
- `T-1042`
- `/1042`, if MAX allows slash-like numeric commands in chat input

UUID remains internal. API responses already expose `task_number` and `task_ref`, and search supports `1042`, `#1042`, and `T-1042`.

## Command: /дьяк

`/дьяк` shows a compact summary for the current actor and current MAX chat.
The old `/секретарь` command remains as a deprecated alias for the transition period, but all responses use the new `Дьяк` brand.

Implementation status: backend command parser and summary response are implemented. The command center response uses one WebApp deep-link button for `home`; task filters, group assignments, and extended task management live inside the WebApp or in separate bot commands.

## Group Assignment Backend Rules

`Задача участникам чата` is a WebApp-owned flow backed by `POST /api/tasks/group-assignment`.

- `member` cannot create group assignments.
- `chat_admin` can create group assignments only in active chats where the actor is an active chat admin.
- `super_admin` can create group assignments in any active chat.
- Pending, rejected, suspended, and MAX-disconnected chats are rejected.
- The API requires a future deadline in the project timezone flow; backend validation remains authoritative.
- Explicit selected `assignee_ids` are supported, deduplicated, and must belong to active members of the selected chat.
- If `assignee_ids` are omitted, the existing behavior assigns all active chat members, with `exclude_creator=true` removing the actor.
- Successful creation sends one clean summary message to the source MAX chat with display names, task ref, deadline, report requirement, and one `Открыть Дьяк` button.
- User-facing messages never include UUIDs, raw chat/user/task ids, MAX ids, or callback payloads.

Live production check on `2026-05-31` after deploying `095b94b` confirmed that the WebApp screen is role-aware, loads allowed active chats and active participants, supports explicit participant selection, honors `exclude_creator`, creates tasks successfully, and sends one clean final MAX-chat summary without raw ids or payloads.

The actor is resolved from MAX external identity:

```text
callback/message user_id -> User.max_user_id -> internal User.id
```

The summary must be scoped by RBAC and access policy. It must not include tasks the actor cannot see.

Response text:

```text
Дьяк

Всего задач: N
В этом чате: N
Просрочено: N
Ждут вашего ответа: N
```

If the actor is a creator/chat_admin and tasks are waiting for acceptance, add:

```text
Ждут приемки: N
```

Buttons:

- `Открыть Дьяк`

The WebApp button uses a MAX deep link:

```text
https://max.ru/<bot_username>?startapp=home
```

## Native MAX Slash Menu

MAX can show bot commands in the native slash-popup after the bot profile is patched with a `commands` list.

Registration is a manual operator action:

```bash
python scripts/max/register_bot_commands.py --dry-run
python scripts/max/register_bot_commands.py --apply
```

The API payload uses command names without `/`:

| Native name | User-visible command | Description |
|---|---|---|
| `дьяк` | `/дьяк` | Open summary and command center. |
| `задача` | `/задача` | Create a task from text or reply context. |
| `мои_задачи` | `/мои_задачи` | Show active tasks assigned to me. |
| `отчет` | `/отчет` | Submit a task report. |
| `пинг` | `/пинг` | Remind an assignee about a task. |
| `помощь` | `/помощь` | Show the command list. |

The parser also accepts `/мои задачи` as an alias for human typing, but the native MAX command menu uses `мои_задачи` because command names with spaces are unsafe for registration.
The native menu should register `дьяк`, not the deprecated `секретарь` alias.

MAX clients may insert native slash-popup commands as a bot mention prefix, for example `@secretary_oren_bot дьяк`.
The parser accepts this mention-prefix format only for the configured `MAX_BOT_USERNAME`, and keeps ordinary words like `дьяк` without slash/mention as normal chat text. The technical MAX username stays `secretary_oren_bot`; only the external product brand changes.

The native/mobile MAX client can show the slash-popup when it supports registered bot commands. The web MAX client may not show that popup on `/`. If the popup does not open, the user can send `/`, `/помощь`, `/help`, `/команды`, `помощь`, `help`, `команды`, `дьяк помощь`, or `/дьяк помощь` as a regular message and the bot returns a compact command list with the `Открыть Дьяк` button.

Help aliases do not create tasks, reports, pings, or pending actions. In a pending onboarding chat, help remains available and appends the standard “chat is not connected yet” notice; working commands remain blocked until approval.

## MAX Chat vs WebApp Task Management

The shared MAX chat is for short final cards and minimal quick actions. Extended task management belongs to the WebApp task details screen.

After task creation, the final MAX chat card must contain only:

- `task_ref`, for example `#1042`;
- task text;
- assignee or assignees;
- deadline, or `не указан`;
- one `Открыть задачу` WebApp deep-link button.

Canonical final card:

```text
Задача #1042 создана ✅

Текст: Отпуск2
Исполнитель: Иван Иванов
Срок: завтра, 18:00
```

For multiple assignees, use `Исполнители: Иван Иванов, Мария Петрова`.

New task-creation flows use one editable bot wizard message. The bot can show intermediate prompts such as `/задача · Напишите текст задачи`, `/задача · Укажите срок задачи`, and `/задача · Укажите исполнителя`, but after the task is created that same bot message is edited into the final task card. Intermediate bot prompts should not remain as separate visible messages.

If MAX message editing fails, cleanup is best-effort: the task stays created, the bot sends the final card as a fallback message, and the pending action records the cleanup failure for diagnostics.
The sender accepts MAX message ids from both top-level and nested response shapes so the wizard can edit the same service message in live MAX.
When `TASK_WIZARD_DELETE_USER_INPUTS=true`, successful task creation also best-effort deletes user-authored wizard input messages (`/задача`, task text, deadline, and assignee mention). The replied source message and final task card are preserved. Delete failures are diagnostic only and do not roll back task creation.
The production live check on 2026-05-29 confirmed that, after enabling the flag for a controlled MAX flow, the user wizard service messages disappeared visually and only the final task card remained.

Task creation and deadline updates reject deadlines that are already past or less than 1 minute in the future. The check uses UTC comparison after interpreting bot input in the project timezone `Asia/Yekaterinburg`. If a bot wizard deadline is invalid, the pending action stays open on the deadline step, the task is not created, assignee selection is not shown yet, and the existing wizard message is edited with a user-facing error.

Validation errors inside the active task wizard use the same editable wizard message instead of adding new bot service messages. With `TASK_WIZARD_DELETE_USER_INPUTS=true`, the invalid user input message is deleted best-effort after it is processed. Cleanup is exact-id only: it uses the message ids saved for the current actor and pending action, never a timestamp range or "everything between" sweep, so unrelated messages from other participants remain visible.

Natural deadline parsing treats relative phrases as higher priority than date-only defaults. Examples such as `через час`, `через 30 минут`, and `сегодня через час` are parsed as project-local `now + delta`; `сегодня через час` must not fall back to `сегодня 18:00`. Conflicting mixed phrases such as `завтра через час` stay on the deadline clarification step.

The final creation card must not include report controls, history, assignee changes, deadline changes, accept/reject actions, attachment actions, UUIDs, raw status enums, source message IDs, chat IDs, organization IDs, or other internal identifiers.

The `#number` command remains a compact task card and may show contextual actions:

- assignee view: `Написать отчет`, `Отложить на 1 час`, `Открыть задачу`;
- creator/chat_admin view with a pending report: `Принять`, `Отклонить отчет`, `Открыть задачу`;
- other extended actions should route through WebApp.

The WebApp task details screen owns extended management:

- reports and report review;
- current assignees, assignee changes, and adding assignees;
- current deadline and deadline changes;
- task history;
- attachment metadata and file access when supported.

## Command: /мои задачи / /мои_задачи

`/мои задачи` and `/мои_задачи` show active tasks where the actor is an assignee.

The native MAX slash-popup registers `/мои_задачи`; `/мои задачи` remains a human-friendly text alias.

Default limit: 7 tasks.

Sorting:

1. Overdue tasks.
2. Nearest deadline.
3. Tasks without deadline.
4. Newest active tasks.

Final statuses are excluded from the chat response: done, cancelled, and rejected tasks are not shown.

Task card format:

```text
#1042 · Просрочена
Подготовить отчет
Срок: сегодня 18:00
Постановщик: Иван Иванов
```

If more than 7 active assignee tasks exist, the response adds:

```text
Еще N задач — откройте WebApp.
```

If there are no active assignee tasks:

```text
У вас нет активных задач.

Создать задачу можно командой /задача в этом чате.
```

Button:

- `Открыть все в WebApp`

Deep link payload:

```text
startapp=my_tasks
```

## Command: #1042 / /1042

Plain task reference lookup returns a compact task card.

Supported forms:

- `#1042`
- `/1042`
- `T-1042`

Access check is mandatory. If the actor cannot access the task, the bot must not disclose whether the task exists:

```text
Задача #1042 не найдена или у вас нет доступа.
```

Task card format:

```text
#1042 · В работе

Подготовить отчет
Срок: пятница, 18:00
Постановщик: Иван Иванов
Исполнитель: Мария Петрова
Статус: В работе
```

Buttons:

- `Написать отчет`
- `Отложить`
- `Открыть в WebApp`

The WebApp button should use:

```text
https://max.ru/<bot_username>?startapp=task_1042
```

The deep link must not include tokens, secrets, raw user IDs, chat IDs, or UUIDs.

## Command: /отчет #1042

`/отчет #1042` submits a report for a task. The parser also accepts the common spelling `/отчёт`.

Examples:

```text
/отчет #1042 готово, доступы проверены
/отчёт #1042 готово, доступы проверены
/отчет #1042
```

If report text is present in the command, save it immediately.

```text
Отчет по задаче #1042 отправлен ✅
```

If report text is missing, create a pending action:

```text
task_report_submit
```

Bot response:

```text
Напишите отчет по задаче #1042 одним сообщением.
```

The next ordinary message from the same actor in the same chat becomes the report. The pending context expires after 30 minutes.

The task card button `Написать отчет` uses callback payload `task:report:start:<task_uuid>` and starts the same pending report context. UUID stays inside the callback payload and is not shown in user-facing text.

After successful report submission, the bot shows a short confirmation and a single `Открыть задачу` WebApp button with `startapp=task_1042`.

Attachments are out of scope for the text MVP. If the user needs files, the bot should direct them to the WebApp; raw attachment payloads must not be logged.

Permissions:

- Assignee can submit a report.
- Creator does not submit a report for the assignee by default.
- chat_admin/super_admin behavior should be implemented only through explicit policy.

If the task is done, cancelled, or rejected:

```text
Задача #1042 уже завершена.
```

## Command: /пинг #1042

`/пинг #1042` reminds assignees that a task needs attention.

Allowed actors:

- chat_admin
- super_admin
- `member` users cannot run manual ping, even for self-assigned tasks. The response is:

```text
Пинг по задаче доступен только администратору чата.
```

The manual ping is delivered to the task source MAX chat, not to assignee DMs.
Assignees are mentioned in that chat:

```text
По задаче #1042 требуется отчет.

@Иван Иванов, нужен отчет.
Срок: пятница, 18:00
```

Buttons:

- `Открыть задачу`

Cooldown:

- At most once per 30 minutes for the same task, source chat, channel, and `task_ping` type.
- If cooldown is active:

```text
Напоминание уже отправлялось недавно. Попробуйте позже.
```

Self-task behavior:

- If the task is assigned to a `chat_admin` or `super_admin` actor, `/пинг` does not create a background delivery and does not show the extra `Написать отчет` button.
- It starts the same pending report flow as `/отчет #1042` without text:

```text
Напишите отчет по задаче #1042 одним сообщением.
```

- The next ordinary message from the actor is saved as the report.
- The response may include only `Открыть задачу` as a WebApp deep link.

Delivery behavior:

- Interactive command replies use the interactive outbound category. The safe live mode is:

```env
MAX_SENDER_ENABLED=true
MAX_INTERACTIVE_RESPONSES_ENABLED=true
MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false
```

- If `MAX_SENDER_ENABLED=false`, all real MAX outbound calls are skipped with `sender_disabled`.
- If `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`, reminders, pings, summaries, and group sends are skipped with `background_disabled` and do not call MAX.
- If the actor pings another assignee while background notifications are disabled, the response is: `Фоновые уведомления сейчас отключены. Напоминание в чат задачи не отправлено.`
- If the task source chat has no `Chat.max_chat_id`, mark delivery skipped with `missing_max_chat_id` and respond: `Не удалось отправить напоминание: чат задачи недоступен для отправки.`
- If an assignee has no `User.max_user_id`, show their display name as plain text and do not create a fake mention.

Deadline reminders:

- `task_due_in_1h` and `task_overdue` are sent to the source MAX chat, not to assignee DMs.
- `task_due_in_1h` fires once when the deadline is in the scheduler window around `now + 1 hour`.
- `task_overdue` fires once when the deadline is reached, but only inside the configured overdue lookback window so first rollout does not ping old backlog tasks.
- Final tasks such as `done`, `cancelled`, `rejected`, and closed/accepted states are not selected.
- Only tasks from `active` chats are eligible. `pending_approval`, `rejected`, and `suspended` chats are skipped.
- Each active chat must also opt in with `Chat.settings.deadline_reminders_enabled=true`; the default is `false` for every chat.
- The message uses `task_ref`, task text, local project-time deadline, and active assignees. MAX mentions use `max://user/<id>` links when `User.max_user_id` is available; otherwise the assignee display name is plain text.
- Dedup is one delivery per task/chat/reminder type on `channel=max_chat`.
- Sending requires all three gates: `MAX_SENDER_ENABLED=true`, `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true`, and `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=true`.
- With `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false` or `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false`, MAX API is not called for automatic deadline chat reminders.
- Super-admin controls the per-chat opt-in from `/super-admin`; allowlist remains a controlled test safety feature.
- If `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS` is set, scheduler-based deadline reminders process only matching task numbers after all normal guards are applied. Excluded tasks do not create delivery rows or MAX calls.

Rollout note:

- If preflight shows multiple eligible overdue tasks inside `TASK_OVERDUE_NOTIFICATION_LOOKBACK_HOURS`, do not open the global scheduler window for a live test without `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS`. The allowlist is for controlled rollout/test mode, not permanent business logic.
- A production scheduler test on 2026-05-30 used allowlist `57`: preflight saw 5 overdue candidates without allowlist, 1 with allowlist, the scheduler sent one `task_overdue` notification for `#57`, and no old overdue tasks were notified.
- A production scheduler test on 2026-05-30 used allowlist `60`: preflight saw 1 due-in-1h candidate without allowlist, 1 with allowlist, 6 overdue candidates reduced to 0 by allowlist, the scheduler sent one `task_due_in_1h` notification for `#60`, and no duplicate or unrelated deadline notifications were sent.
- A production per-chat rollout recheck on 2026-05-31 used active opt-in chat `Тест ДЬЯК` and allowlist `73`: preflight saw 7 overdue candidates with per-chat opt-in and 1 after allowlist, the scheduler sent one `task_overdue` notification for `#73`, other overdue tasks were skipped by allowlist, and no duplicate was sent after another scheduler interval.
- Production opt-in mode was started on 2026-05-31 with global deadline-reminder flags enabled, empty task allowlist, and exactly one active opt-in chat: `Тест ДЬЯК`. The initial monitoring window sent overdue notifications only to that chat for `#67`, `#64`, `#65`, `#68`, and `#66`; no non-opt-in chat delivery or duplicate delivery was observed.

## Notification Destination

Manual `/пинг`, `task_due_in_1h`, and `task_overdue` all use the same destination model: the source MAX chat of the task.

`/пинг` does not send DMs in the current model. The command initiator receives an interactive confirmation, while the reminder itself is a background `PING` to `Task.chat_id -> Chat.max_chat_id`.

The sender must always use external MAX identifiers:

- assignee mention links: `User.max_user_id`
- chat delivery target: `Chat.max_chat_id`

Internal UUIDs must never be sent to MAX API as recipients.

## Pending Actions

Pending contexts allow the bot to wait for the next user action without creating incomplete visible tasks.

Required pending action types:

- `task_create_select_assignee` - waits for one or more structured MAX `@mentions` after task text/deadline are known
- `task_create_set_text` - waits for task text after an empty `/задача` command
- `task_create_set_deadline` - waits for a deadline after `/задача` when the task text is known but the deadline is missing or ambiguous
- `task_report_submit` - waits for report text after `/отчет #1042`

Common fields:

- `actor_user_id`
- `task_id`
- `chat_id`
- `source_message_id`, when available
- `expires_at`
- `status`

Statuses:

- `pending`
- `completed`
- `expired`
- `cancelled`

Completed or expired pending actions must not execute again.

Pending routing rules:

- Explicit slash commands are parsed before any pending action can consume the message.
- Empty `/задача` starts a task wizard: first `task_create_set_text`, then `task_create_set_deadline`, then self-task creation for `member` or assignee selection for `chat_admin`/`super_admin`.
- `/задача` creates or updates task-creation pending context and supersedes stale report or task-creation pending context for the same actor and chat.
- Reply `/задача` uses the replied message text as the task title. Inline text after the command is parsed only as parameters such as deadline and assignee.
- Reply `/задача завтра 15:00` therefore keeps the replied message as the task text, parses `завтра 15:00` as the deadline, and continues to assignee selection when no assignee is provided.
- Assignee selection for new `/задача` flows is text-only: the bot asks the user to mention one or more executors through MAX `@mentions`.
- New assignee-selection prompts do not include participant buttons, `Назначить себе`, or `Открыть в WebApp`; legacy `task:assign` callbacks remain accepted only for old messages that already have buttons.
- Multiple structured `@mentions` are supported and create one task with multiple assignees. Duplicate mentions are deduplicated.
- During assignee selection, `@Дьяк` or `@secretary_oren_bot` means “assign to myself” for the current `chat_admin`/`super_admin`. If the bot and participants are mentioned together, assignees are the actor plus the resolved participants.
- Bot mention has priority over help aliases while `task_create_select_assignee` is active: `@secretary_oren_bot /` and `@secretary_oren_bot помощь` are treated as self-assignee input in that step. Outside that pending flow, the same mention-prefix help forms still return the command list.
- `task_create_set_text` and `task_create_set_deadline` have priority over `task_report_submit`; task text or deadline clarification must never be saved as a report.
- Assignee selection by structured `@mention` has priority over report submission while task creation is pending.
- Validation errors for deadline or assignee input edit the current task wizard message, keep the pending action open, and may delete only the current actor's saved wizard input message when user-input cleanup is enabled.
- `task_report_submit` consumes ordinary text only when no more specific task-creation pending action is active.

Bot role checks use the internal `ChatMember.role` value for the resolved chat. MAX group-admin status is not treated as `chat_admin` unless it has been synchronized or assigned in `Дьяк`; this avoids guessing privileges from webhook payloads that do not carry a reliable admin flag.

## Buttons And Deep Links

Use MAX callback buttons with:

```json
{
  "type": "callback",
  "text": "Button text",
  "payload": "safe:payload",
  "intent": "default"
}
```

Use MAX deep links for WebApp navigation:

```text
https://max.ru/<bot_username>?startapp=task_1042
```

Allowed `startapp` examples:

- `home`
- `my_tasks`
- `task_1042`
- `report_1042`

Do not put the following in callback payloads or deep links:

- tokens
- secrets
- full external user IDs
- full external chat IDs
- internal UUIDs unless the payload is internal-only and never user-visible

## Error Texts

No task number:

```text
Укажите номер задачи, например #1042.
```

Task number not recognized:

```text
Не удалось распознать номер задачи. Используйте формат #1042.
```

Task not found or no access:

```text
Задача не найдена или у вас нет доступа.
```

Report text expected:

```text
Напишите отчет по задаче #1042 одним сообщением.
```

Cannot ping:

```text
Вы не можете отправить напоминание по этой задаче.
```

Cooldown active:

```text
Напоминание уже отправлялось недавно. Попробуйте позже.
```

Sender disabled:

```text
Напоминание записано, но отправка в MAX сейчас отключена.
```

Completed/cancelled task:

```text
Задача уже завершена или отменена.
```

## Security

All commands must resolve the actor through MAX identity mapping:

```text
MAX external user_id -> User.max_user_id -> internal User.id
```

Task lookup by number must go through the same access policy as UUID routes. Users cannot enumerate or access чужие задачи by guessing `#1042`.

Security rules:

- Never reveal whether a task exists if the actor has no access.
- Do not show raw UUIDs in bot UX.
- Do not trust query `user_id` as auth.
- Do not send internal UUIDs to MAX as recipients.
- Respect `MAX_SENDER_ENABLED` and outbound guards.
- Rate-limit `/пинг`.
- Keep shared chat cleanup strict: no stale active picker buttons after completion.
- Do not log raw payloads, tokens, secrets, cookies, or raw initData.

## Implementation Plan

A. Command parser for task references

- Parse `#1042`, `T-1042`, and `/1042` when the reference is the whole message.
- Reuse the existing task reference normalizer.
- Keep UUID routes unchanged.

B. `/дьяк` summary

- Add scoped task counts for actor and chat.
- Add summary response and WebApp buttons.

C. `/мои задачи`

- Add assignee task list query.
- Limit to 5 to 7 active tasks.
- Add WebApp deep link to full list.

D. Task card by number

- Lookup by `organization_id + task_number`.
- Apply access policy.
- Return compact card and action buttons.

E. `/отчет` flow

- Parse task reference.
- Enforce assignee permission.
- Save inline report text or create `task_report_submit` pending action.
- Use one editable report wizard message for `/отчет #номер` without text and for the `Написать отчет` callback.
- Edit the report wizard prompt into `Отчет по задаче #... отправлен ✅` after successful submission.
- With `TASK_WIZARD_DELETE_USER_INPUTS=true`, best-effort delete only the actor's exact saved report wizard input message ids: the `/отчет #номер` command and the report text.
- Preserve other users' chat messages, source task messages, final bot messages, and waiting-acceptance notifications; do not use timestamp or range cleanup.
- Keep empty report text in the pending flow and edit the wizard message with a friendly validation error.
- Support attachment metadata or WebApp fallback.
- Live MAX check on 2026-05-31 confirmed `/отчет #номер`, inline report text, callback `Написать отчет`, prompt-to-final edit, exact user input cleanup, preserved unrelated messages, and clean waiting-acceptance notification.

F. Acceptance flow

- Send `Ответ ожидает приемки` to the task creator with `Принять`, `Отклонить`, and `Открыть задачу`.
- Keep callback payloads and internal ids out of user-facing message text.
- `Принять` is available to the creator, chat admin, and super admin.
- `Принять` sends a visible confirmation message and finalizes the response decision; stale incompatible buttons cannot later reject the same accepted response.
- `Отклонить` starts a `task_acceptance_reject_reason` pending action and asks for a non-empty reason.
- Save the rejection reason in acceptance history and notify the executor with `Написать отчет` and `Открыть задачу`.
- After rejection, overdue tasks stay `overdue`; non-overdue tasks return to the working status and can receive a repeat `/отчет`.
- Live MAX check on 2026-05-31 confirmed the rejection reason wizard, saved reason, assignee notice, correct post-rejection task state, and repeat report flow without exposing raw ids or callback payloads.

G. `/пинг` flow

- Enforce creator/chat_admin/super_admin permission.
- Use `NotificationDeliveryService` with `reminder_type=task_ping`.
- Apply a 30 minute delivery-ledger cooldown per task, source chat, channel, and ping type.
- Send the assignee mention notification as background `PING` to the source chat, while the command initiator receives an interactive reply.
- Do not add `Написать отчет` to the shared chat ping; use only `Открыть задачу`.

H. WebApp deep link to task details

- Support `startapp=task_1042`.
- Route WebApp to task details after auth bootstrap.
- Keep direct browser access unauthorized without a valid session.

## Tests Plan

Parser:

- parse `#1042`
- parse `T-1042`
- parse `/1042`
- do not treat arbitrary references inside ordinary text as lookup commands
- reject invalid references

`/дьяк`:

- counts are scoped to actor permissions
- chat count is scoped to current chat
- inaccessible tasks are excluded

`/мои задачи`:

- only assignee tasks are shown
- done/cancelled tasks are excluded by default
- ordering prioritizes overdue and nearest deadline

Task card:

- authorized actor can open `#1042`
- unauthorized actor gets generic not-found/no-access text
- no raw UUID appears in response
- action buttons include `Написать отчет`, `Отложить на 1 час`, and `Открыть в WebApp`
- creator/chat_admin views of `waiting_acceptance` tasks with a submitted report show `Принять`, `Отклонить`, and `Открыть в WebApp`

`/отчет`:

- parse `/отчёт` as an alias for `/отчет`
- assignee can submit inline report
- inline report command cleans its own command message when wizard input cleanup is enabled
- missing text creates pending report action and sends one editable wizard prompt
- next report message edits the wizard prompt into the final submitted message
- callback `Написать отчет` starts the same report wizard
- empty report edits the wizard validation error and keeps pending
- report cleanup deletes only exact saved actor input message ids and preserves unrelated messages
- non-assignee cannot submit report
- completed/cancelled task returns friendly no-op

Acceptance:

- waiting acceptance notification contains only `Принять`, `Отклонить`, and `Открыть задачу`
- waiting acceptance notification does not contain raw payloads, UUIDs, or technical fallback labels
- authorized reject click creates pending reason flow
- empty reason keeps pending
- saved reason is sent to the executor
- overdue task remains overdue after rejection
- executor can submit a repeat report after rejection
- accepted and rejected responses cannot be decided again through stale callback buttons

`/пинг`:

- parse `/пинг #1042`, `/пинг 1042`, and `/пинг T-1042`
- only `chat_admin`/`super_admin` can ping
- `member` users cannot ping, including self-assigned tasks
- final tasks cannot be pinged
- cooldown prevents spam
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false` records skipped delivery without a MAX API call
- source chat without `max_chat_id` records `missing_max_chat_id`
- assignee without `max_user_id` is shown as plain display name
- ping notification includes assignee mentions and only the `Открыть задачу` button
- self-task ping creates pending report context only for `chat_admin`/`super_admin`, includes only `Открыть задачу`, and does not create background delivery

Deep links:

- generated links use `max.ru/<bot_username>`
- payload is URL-encoded
- no token, secret, raw user ID, chat ID, or UUID leaks into the URL
