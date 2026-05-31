# MAX DM/Reminder Behavior Audit

Status date: 2026-05-23

Version: `1.1.0-rc.1`

Scope: safe audit only. No real MAX messages were sent during this audit.

## Current state

Confirmed before this audit:

- single-message MAX sender test succeeded;
- outbound recipient mapping uses external `User.max_user_id` and `Chat.max_chat_id`;
- users without `max_user_id` are skipped or marked `dm_unavailable`;
- chats without `max_chat_id` are skipped or marked unavailable;
- `MAX_SENDER_ENABLED` is returned to `false` after controlled tests;
- direct-message behavior is only partially validated, and one earlier real DM scenario returned HTTP `404`;
- reminder jobs exist and can produce outbound notifications automatically.

Current VPS safety state observed during this audit:

- `MAX_SENDER_ENABLED=false`;
- `MAX_WEBHOOK_DEBUG_LOG=false`;
- backend, worker and health endpoint were healthy;
- no production `.env` values were printed.

Worker behavior from code review:

- the worker scheduler runs reminder jobs automatically when `REMINDERS_ENABLED=true`;
- default reminder poll interval is 60 seconds;
- due reminder scans run on every poll;
- daily summary and daily manager summary jobs run on a configured cron time;
- scheduled task creation also runs from the same worker scheduler;
- `MAX_SENDER_ENABLED=false` builds a stub sender and prevents real MAX API sends;
- `MAX_SENDER_ENABLED=true` enables real MAX API sends wherever the worker reaches outbound paths.

Notification delivery behavior:

- personal notifications resolve internal `User.id` to external `User.max_user_id` before sending;
- missing `User.max_user_id` marks the primary delivery as `dm_unavailable` with `missing_max_user_id` and does not call MAX;
- DM unavailable errors can trigger group fallback;
- group fallback resolves internal `Chat.id` to external `Chat.max_chat_id`;
- missing `Chat.max_chat_id` marks fallback delivery failed with `missing_max_chat_id` and does not call MAX;
- one failed recipient should not stop processing other recipients.

## Counts

Safe production counts captured from the VPS database on 2026-05-23 at approximately `06:54 UTC`.

Notification deliveries:

- pending notification deliveries: `0`;
- status/channel counts:
  - `dm_unavailable/max_dm`: `50597`;
  - `failed/max_dm`: `51846`;
  - `sent/max_dm`: `1`.

Identity coverage:

- users total: `111`;
- users with `max_user_id`: `2`;
- users without `max_user_id`: `109`;
- chats total: `35`;
- chats with `max_chat_id`: `35`;
- chats without `max_chat_id`: `0`.

Active task assignment coverage:

- active tasks: `24`;
- active assignees total: `24`;
- active assignees with `max_user_id`: `1`;
- active assignees without `max_user_id`: `23`.

Due reminder snapshot:

- `before_deadline`: `0` tasks, `0` recipient pairs;
- `at_deadline`: `0` tasks, `0` recipient pairs;
- `after_deadline`: `7` tasks, `14` recipient pairs;
- `no_response_after_deadline`: `7` tasks, `14` recipient pairs;
- `waiting_acceptance`: `7` tasks, `14` recipient pairs;
- due reminder unique tasks: `14`;
- due reminder potential recipient pairs: `28`;
- active snooze skips at audit time: `0`;
- due reminder unique recipient users: `14`;
- due reminder recipient users with `max_user_id`: `0`;
- due reminder recipient users without `max_user_id`: `14`.

Summary jobs:

- daily summary candidate users: `26`;
- daily summary candidates with `max_user_id`: `1`;
- daily summary candidates without `max_user_id`: `25`;
- daily manager summary chats: `35`;
- daily manager summary candidate recipients: `34`;
- daily manager summary candidate recipients with `max_user_id`: `0`;
- daily manager summary candidate recipients without `max_user_id`: `34`.

Scheduled tasks:

- due scheduled tasks at audit time: `0`.

Only masked sample ids were inspected during the audit. Full real user, chat, message, token and secret values were not printed or committed.

## Risks

Permanent `MAX_SENDER_ENABLED=true` is not safe yet.

Main risk:

- worker jobs can run automatically and repeatedly;
- due reminder scans currently find real due tasks;
- reminder delivery has no broad dry-run mode, recipient allowlist, rate limit, or per-task/per-user/per-reminder-type send ledger that prevents repeated sends across poll cycles;
- if a due reminder recipient later has `max_user_id`, the worker can send repeated real MAX notifications every poll cycle;
- if direct DM fails for a user with `max_user_id`, group fallback can send to a real MAX chat because all chats currently have `max_chat_id`;
- daily summary has at least one candidate user with `max_user_id`, so a cron window could send a real summary if sender is enabled;
- historical delivery counts already show high churn from repeated delivery attempts.

Current mitigating facts:

- pending delivery count is `0`;
- current due reminder recipients have no `max_user_id`, so enabling sender at the exact audit snapshot would mostly create unavailable delivery rows rather than real DM sends for those due reminders;
- this can change as soon as more real MAX users are resolved;
- single-message sender tests should remain controlled one-off operations, not a signal to keep sender permanently enabled.

## Safe test plan

No live send should happen without a separate explicit confirmation.

Recommended controlled test sequence:

1. Keep `MAX_SENDER_ENABLED=false`.
2. Select exactly one test user with `max_user_id`.
3. Select or create exactly one safe test task assigned to that user.
4. Pause or isolate worker reminder scheduling if possible.
5. Use a one-off script or service call to send one personal notification to the selected user.
6. Do not call `run_due_reminders`, `run_daily_summary`, `run_daily_manager_summaries`, scheduled task jobs, or group assignment broadcast.
7. Verify the delivery row status and sanitized logs.
8. Immediately restore `MAX_SENDER_ENABLED=false`.
9. Confirm no unexpected notification rows were created during the test window.

If reminder behavior itself must be tested live:

- add a temporary recipient allowlist first;
- add dry-run logging first;
- use one test task and one test user;
- run one job invocation manually with the scheduler disabled;
- do not leave the automatic worker sender enabled after the test.

## Required hardening before enabling sender permanently

P0 before permanent sender enablement:

- add a recipient allowlist for MAX outbound pilot mode;
- add dry-run mode for reminder and summary delivery;
- add a send ledger keyed by task, user, reminder type and time bucket to prevent repeated sends every poll;
- add per-run and per-minute rate limits for MAX sender;
- add a hard cap for maximum recipients per worker run;
- add explicit config gates for daily summary, daily manager summary, group fallback and group assignment fan-out;
- add admin-visible counters/logs for skipped, sent, failed and fallback deliveries;
- add tests for repeated reminder polls not sending duplicate notifications.

P1 before broader pilot:

- validate DM unavailable behavior with a controlled test user;
- validate group fallback in one controlled test chat;
- add backoff/retry policy for transient MAX API errors;
- add alerting on high `failed` or `dm_unavailable` delivery volume;
- add operational playbook for disabling sender quickly.

P2 later:

- add MAX API rate-limit telemetry;
- add per-organization/channel delivery budgets;
- add dashboard visibility for notification health.

## Recommended config

Current recommendation:

- keep `MAX_SENDER_ENABLED=false` by default;
- keep `MAX_WEBHOOK_DEBUG_LOG=false`;
- use sender only for short, explicitly controlled tests;
- do not enable broader reminders until dry-run, allowlist and de-duplication hardening exist.

Safe baseline:

```text
MAX_SENDER_ENABLED=false
MAX_WEBHOOK_DEBUG_LOG=false
```

Pilot-only temporary override:

```text
MAX_SENDER_ENABLED=true
```

Use the override only during a planned test window, then force-recreate backend and worker after restoring `false`.
