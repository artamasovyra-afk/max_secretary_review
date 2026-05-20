# API Overview

The backend exposes a FastAPI API under `/api` plus OpenAPI documentation under `/docs` and `/openapi.json`.

The current `1.0.x` application exposes route groups for health, organizations, users, chats, tasks, reminders, MAX webhook and Bitrix24 integration.

## Public Technical Endpoints

- `GET /api/health`
- `HEAD /api/health`
- `GET /docs`
- `GET /openapi.json`

`/api/health` is used by Docker healthchecks and deployment smoke checks.

## Organizations

Base path:

```text
/api/organizations
```

Main operations:

- create organization;
- list organizations;
- get organization by id;
- patch organization.

## Users

Base path:

```text
/api/users
```

Main operations:

- create local user;
- list users;
- get user by id;
- patch user.

`display_name` is required. External MAX/Bitrix identities are optional in MVP.

## Chats And Members

Base path:

```text
/api/chats
```

Main operations:

- create chat;
- list chats;
- get chat by id;
- patch chat;
- add/list/update chat members;
- create/list chat-level reminder rules.

Chat member roles:

- `member`
- `manager`
- `chat_admin`
- `super_admin`

## Tasks

Base path:

```text
/api/tasks
```

Main operations:

- create task;
- list tasks with filters and pagination;
- get full task details;
- patch task;
- cancel task;
- manage assignees;
- manage observers;
- create/list comments;
- create/list file metadata;
- submit assignee response;
- accept/reject response;
- create/list/update/delete task reminder rules.

Task list supports filters such as organization, chat, status, creator, assignee, observer and deadline range.

## Inbox Summary

Endpoint:

```text
GET /api/tasks/inbox/summary
```

Returns user-centered task buckets:

- `my_tasks`
- `created_by_me`
- `observed_by_me`
- `waiting_my_response`
- `waiting_my_acceptance`
- `overdue`
- `today`

In the pilot WebApp, `user_id` can still be passed through query parameters for dev/MVP flows. New protected endpoints should use `AuthContext` headers instead.

## MAX Bot Webhook

Endpoint:

```text
POST /api/bot/max/webhook
```

Supports:

- normalized test event format;
- MAX-like raw event normalization;
- command parsing;
- optional `X-Max-Webhook-Secret` validation.

MVP commands include:

- `/задача`
- `/задачи`
- `/мои_задачи`
- `/ответ`
- `/готово`
- `/принять`
- `/отклонить`

Real MAX sending is controlled by `MAX_SENDER_ENABLED`.

## Bitrix24 Integration

Base path:

```text
/api/integrations/bitrix24
```

User mapping endpoints:

- `POST /user-mappings`
- `GET /user-mappings`
- `GET /user-mappings/{mapping_id}`
- `PATCH /user-mappings/{mapping_id}`
- `DELETE /user-mappings/{mapping_id}`

Manual sync endpoints:

- `POST /tasks/{task_id}/sync`
- `GET /tasks/{task_id}/status`
- `POST /retry-failed`

These endpoints are protected by RBAC/auth context. In MVP, integration is disabled by default and manual sync returns `disabled` when `BITRIX24_ENABLED=false`.

## Auth Context

Protected endpoints use `get_auth_context()` and headers:

- `X-User-Id`
- `X-Organization-Id`
- `X-Chat-Id`
- `X-Roles`

In production, dev headers are disabled unless `DEV_AUTH_ENABLED=true`. Full MAX WebApp auth is future work.

## OpenAPI Tags

Router tags include:

- `health`
- `organizations`
- `users`
- `chats`
- `tasks`
- `integrations`
- `bitrix24`

## Smoke Checks

Release smoke scripts call:

- health;
- WebApp routes;
- MVP task workflow;
- reminders;
- Bitrix24 disabled mode.

See [Release smoke](../release/release_smoke.md) and [Operator guide](../operations/operator_guide.md).
