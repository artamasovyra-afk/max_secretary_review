# Task Notifications Policy

## Chat Deadline Reminders

For MAX-created tasks with a deadline and active assignees, the worker creates chat-level deadline reminders:

| Reminder type | When | Destination | Dedup |
|---|---|---|---|
| `task_due_in_1h` | About 1 hour before `deadline_at` | Source task chat | Once per task/chat/type |
| `task_overdue` | After `deadline_at` has passed | Source task chat | Once per task/chat/type |
| `task_ping` | Manual `/пинг #number` from an allowed actor | Source task chat | 30 minutes per task/chat/type |

The message uses `task_ref` (`#1042`) and never shows the internal UUID. Assignees are mentioned with MAX `max://user/<id>` links when `User.max_user_id` is available; otherwise their display name is shown as plain text.

Manual `/пинг` follows the same source-chat model as deadline reminders. It does not send DMs in the current policy. The initiator receives an interactive confirmation, while the reminder itself is a background `PING` to `Task.chat_id -> Chat.max_chat_id`.

Self-task `/пинг` is the exception: if the task is assigned to the initiator, the bot does not create a background delivery and starts the pending report flow instead.

## Guard Behavior

These reminders and manual chat pings are background notifications. Real MAX delivery requires:

```env
MAX_SENDER_ENABLED=true
MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true
```

If background notifications are disabled, the worker or bot command records `notification_deliveries` with `channel=max_chat`, `status=skipped`, and `error_code=background_disabled`, and does not call MAX.

If the source chat has no `Chat.max_chat_id`, delivery is skipped with `missing_max_chat_id`.

## Delivery Records

Chat reminders and manual chat pings are deduplicated by:

- `task_id`;
- `chat_id`;
- `channel=max_chat`;
- `reminder_type`.

This prevents repeated scheduler runs from posting the same due-in-1h or overdue reminder multiple times. Manual `task_ping` uses the same key with a 30 minute cooldown window.

## Deployment Check

The `e81023a` deploy check on 2026-05-25 confirmed the safe-mode path:

- migration head `d7e8f9012345` applied successfully;
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`;
- `task_due_in_1h` and `task_overdue` controlled checks created `skipped/background_disabled` deliveries;
- repeated checks did not create duplicate deliveries;
- MAX API was not called;
- release smoke remained `release_smoke=ok`.

Background-enabled live delivery remains a separate controlled rollout step.
