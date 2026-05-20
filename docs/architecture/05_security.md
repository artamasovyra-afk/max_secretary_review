# Security

This document describes the current security model and hardening assumptions for `max_secretary v1.0.x`.

## Secret Handling

Secrets must not be committed to git.

Never commit:

- `.env`;
- tokens;
- passwords;
- webhook URLs containing credentials;
- SSH key files;
- backup files;
- Docker image archives;
- Python wheels or npm caches for closed-contour delivery.

Runtime secrets are provided through:

- `.env` on the VPS or target server;
- GitHub repository secrets for deploy workflow;
- future dedicated secret storage if introduced.

## Production Environment Defaults

Expected production settings:

```env
APP_ENV=production
DEBUG=false
DEV_AUTH_ENABLED=false
AI_ENABLED=false
BITRIX24_ENABLED=false
MAX_SENDER_ENABLED=false
```

External integrations should remain disabled unless a real endpoint and secret management process are configured.

## Authentication State

`v1.0.0` includes RBAC/auth preparation, not full production auth.

Current state:

- backend has `AuthContext`;
- dev/test headers can build auth context;
- production rejects dev headers unless `DEV_AUTH_ENABLED=true`;
- Bitrix24 sync and mapping endpoints are protected by RBAC;
- full MAX WebApp authentication is not implemented yet.

Dev auth headers:

- `X-User-Id`
- `X-Organization-Id`
- `X-Chat-Id`
- `X-Roles`

These headers are a temporary bridge and must not be treated as full production identity.

## RBAC Policy

Roles:

- `member`
- `manager`
- `chat_admin`
- `super_admin`

Key rules:

- executor can submit response only for assigned tasks;
- observer can view but cannot accept result;
- task creator can accept or reject response;
- manager can view and manage tasks in accessible chats;
- chat admin can manage chat-level settings and mappings;
- super admin can perform all policy actions.

See [RBAC policy](../security/rbac_policy.md).

## Network Boundary

Production compose exposes only:

- `nginx` on port `80`.

Internal-only services:

- backend;
- worker;
- webapp;
- PostgreSQL;
- Redis.

PostgreSQL and Redis must not be published externally.

## Nginx Boundary

Nginx routes:

- `/api/*` to backend;
- `/docs` to backend;
- `/openapi.json` to backend;
- frontend routes to WebApp.

The current WebApp routing intentionally supports SPA fallback for frontend routes. Unknown API routes should be handled by backend as API 404.

## Webhook Security

MAX webhook endpoint supports `X-Max-Webhook-Secret`.

Rules:

- if `MAX_WEBHOOK_SECRET` is set, requests must provide the matching header;
- wrong secret returns `401`;
- secret value must not be logged;
- production without webhook secret should be treated as a configuration risk if real webhook traffic is enabled.

## Integration Security

### MAX

- `MAX_BOT_TOKEN` must not be logged or committed.
- `MAX_SENDER_ENABLED=false` keeps sender in logging-only mode.
- Real sending requires explicit configuration.

### Bitrix24

- `BITRIX24_WEBHOOK_URL` is secret if it contains webhook credentials.
- It must not be committed, shown in WebApp or logged.
- `BITRIX24_ENABLED=false` prevents real external HTTP requests.
- Manual sync errors are stored without exposing webhook URL or tokens.

## Backup Security

Backups can contain production data.

Rules:

- backup files must not be committed;
- backup integrity can be checked with `gzip -t`;
- restore tests must use a temporary database or separate environment;
- do not restore over production without explicit approval and rollback plan.

See [Backup and restore](../operations/backup_restore.md).

## Closed Contour

Closed-contour delivery uses offline bundle artifacts:

- Docker image tar files;
- Python wheels;
- checksums;
- manifest;
- offline compose.

The target production server must not download dependencies from the internet. Verify `SHA256SUMS` before installation.

## Known Security Limitations

- Full MAX WebApp auth is not implemented yet.
- Production SSO is not implemented.
- Full observability/security monitoring stack is not included.
- File upload storage is not implemented; file records are metadata only.
- Bitrix24 sync is manual and one-way.
- Closed-contour bundle requires separate infrastructure acceptance.

See [Known limitations](../release/known_limitations_1.0.0.md) and [Security checklist](../release/security_checklist_1.0.0.md).
