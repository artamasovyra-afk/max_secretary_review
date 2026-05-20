# Data Model

`max_secretary` uses PostgreSQL and SQLAlchemy 2.x async models. Models are registered through the backend metadata so Alembic can generate and apply schema migrations.

## Core Entities

### Organization

Top-level tenant boundary for chats, tasks and integration settings.

Key fields:

- `id`
- `name`
- `status`
- timestamps

### User

Local user record. A user can later be linked to MAX and Bitrix24 identities.

Key fields:

- `id`
- `max_user_id`
- `display_name`
- `username`
- `phone`
- `email`
- timestamps

### Chat

Working chat inside an organization.

Key fields:

- `id`
- `organization_id`
- `max_chat_id`
- `title`
- `type`
- `settings`
- timestamps

### ChatMember

Membership and role of a user inside a chat.

Supported roles:

- `member`
- `manager`
- `chat_admin`
- `super_admin`

## Task Model

`Task` is the central aggregate. A task always belongs to an organization and chat.

Important rule: `Task` does not have a single `responsible_user_id`; multiple assignees are stored in `TaskAssignee`.

Task fields include:

- `organization_id`
- `chat_id`
- `source_message_id`
- `title`
- `description`
- `created_by_user_id`
- `deadline_at`
- `status`
- `priority`
- `completion_rule`
- `submitted_at`
- `completed_at`
- `cancelled_at`
- timestamps

Task statuses:

- `new`
- `in_progress`
- `waiting_response`
- `waiting_acceptance`
- `done`
- `overdue`
- `rejected`
- `cancelled`

Task priorities:

- `low`
- `normal`
- `high`
- `urgent`

Completion rules:

- `any_assignee_response`
- `all_assignees_response`
- `manual_submit`

## Task Relations

### TaskAssignee

Stores all assignees for a task.

Key behavior:

- one row per assigned user;
- status tracks assignee progress;
- `responded_at` is filled after assignee response;
- duplicate assignees are rejected at API/service level.

### TaskObserver

Stores observers for a task. Observers can view the task but cannot accept or reject the result unless they also have a higher role through RBAC policy.

### TaskComment

Stores comments and optional reply chains through `reply_to_comment_id`.

### TaskFile

Stores file metadata only. Real file storage/upload is not implemented in the pilot baseline.

### TaskResponse

Stores assignee responses.

Response statuses:

- `submitted`
- `accepted`
- `rejected`

### TaskAcceptance

Stores requester decision for a response.

Decisions:

- `accepted`
- `rejected`

### TaskStatusHistory

Stores status transitions and optional user that caused the transition.

### TaskReminderRule

Stores task-level or chat-level reminder settings.

Reminder types:

- `before_deadline`
- `at_deadline`
- `after_deadline`
- `no_response_after_deadline`
- `waiting_acceptance`
- `daily_summary`

### AuditLog

Stores selected audit events such as assignee/observer changes.

## Integration Models

### IntegrationAccount

Stores integration account metadata at organization level.

Credentials are expected to be encrypted or stored externally. Secrets must not be placed into public fields.

### BitrixTaskLink

Tracks local task synchronization with Bitrix24.

Key fields:

- `task_id`
- `organization_id`
- `bitrix_portal_url`
- `bitrix_task_id`
- `sync_status`
- `last_sync_at`
- `last_error`

`sync_status` values:

- `pending`
- `synced`
- `error`
- `disabled`

There should be at most one active Bitrix link per local task.

### BitrixUserMapping

Maps a local `User` to a Bitrix24 user id.

Key rules:

- `bitrix_user_id` is stored as string;
- one active mapping per local user inside an organization;
- mapping source can be `manual`, `email`, `phone` or `import`;
- MVP creates mappings manually through API.

## Migration Model

Alembic migrations are part of the backend image:

```text
backend/alembic.ini
backend/alembic/
```

Production migration command:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

Offline migration command:

```bash
docker compose -f docker-compose.offline.yml exec backend alembic upgrade head
```
