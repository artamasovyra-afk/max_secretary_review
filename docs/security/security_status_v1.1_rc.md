# Security Status — v1.1.0-rc.1

Status date: 2026-05-21

Audited version: `1.1.0-rc.1`

Audited branch: `main`

Audited baseline: `5edb085 chore: release 1.1.0-rc.1`

Security hardening commits included:

- `73a7317 fix: require MAX webhook secret in production`
- `6298469 fix: harden MAX webhook secret validation`

Public URLs:

- WebApp: `https://maxsecretary.ru`
- MAX webhook: `https://maxsecretary.ru/api/bot/max/webhook`

Scope checked:

- `docker-compose.prod.yml`
- `infra/nginx/nginx.conf`
- backend auth dependency and RBAC policy layer
- MAX webhook endpoint
- `DEV_AUTH_ENABLED` behavior
- group assignment endpoints
- task template and scheduled task endpoints
- scheduled task worker path
- notification delivery and MAX sender path
- `.env.example`
- `docs/deployment/05_server_env.md`

No real MAX API calls were executed during this audit. No runtime secrets were added or inspected.

## 1. Already implemented

### Deployment and network boundary

- Production Docker Compose publishes Docker nginx only on `127.0.0.1:8080:80`.
- Public HTTPS is terminated by host nginx and proxied to Docker nginx.
- PostgreSQL and Redis are not published outside the Docker network.
- Production Compose has healthchecks for backend, worker, webapp, nginx, postgres and redis.
- Backend and worker wait for healthy postgres and redis before startup.
- `.env` is external to git and is loaded through Compose `env_file`.

### Environment defaults

- `APP_ENV=production` and `DEBUG=false` are documented as the production baseline.
- `DEV_AUTH_ENABLED=false` is the documented production default.
- `MAX_SENDER_ENABLED=false` is the documented default until real MAX credentials are configured.
- `MAX_WEBHOOK_DEBUG_LOG=false` is the documented default.
- `BITRIX24_ENABLED=false` and `AI_ENABLED=false` are documented safe defaults.
- Backend requires PostgreSQL async driver format for `DATABASE_URL`; SQLite fallback is not accepted.
- Bitrix24 runtime helper refuses enabled Bitrix24 mode without configured Bitrix24 webhook secret.

### MAX webhook security baseline

- MAX webhook endpoint supports shared-secret validation through the official `X-Max-Bot-Api-Secret` header.
- The legacy `X-Max-Webhook-Secret` header is accepted temporarily for internal compatibility.
- `MAX_WEBHOOK_ENABLED=false` disables `POST /api/bot/max/webhook` with HTTP `404`.
- In production, `MAX_WEBHOOK_ENABLED=true` without `MAX_WEBHOOK_SECRET` returns HTTP `503` before payload handling.
- Secret comparison uses constant-time comparison.
- If the webhook secret is configured, missing or invalid header returns `401`.
- If the webhook secret is configured and `X-Max-Bot-Api-Secret` is valid, the request is accepted and normal event handling starts.
- If the legacy `X-Max-Webhook-Secret` header is valid, the request is also accepted during the compatibility window.
- Safe webhook debug mode logs raw payload shape and masked normalized identifiers instead of full values.
- Production startup logs a warning when the MAX webhook secret is not configured.
- MAX sender remains disabled unless explicitly enabled by configuration.

Expected VPS `.env` shape for real sandbox connection:

```env
MAX_WEBHOOK_ENABLED=true
MAX_SENDER_ENABLED=true
MAX_API_BASE_URL=https://platform-api.max.ru
MAX_WEBHOOK_DEBUG_LOG=false
```

Real bot credential and webhook secret must be stored only in the VPS `.env` or a protected secret store. They must not be committed, pasted into documentation, sent in chat, or included in screenshots.

### Auth and RBAC foundation

- `AuthContext` exists as the backend dependency for protected endpoints.
- In production, header-based dev auth is disabled unless `DEV_AUTH_ENABLED=true`.
- Protected endpoints return `401` when header auth is disabled or missing.
- RBAC policy service covers task view/create/update/response/accept/reject, Bitrix24 sync and mapping rules.
- Bitrix24 sync and mapping endpoints are protected by RBAC from earlier hardening.

### v1.1 protected features

- Group assignment creation requires `chat_admin` or `super_admin`.
- Group assignment creator must match the authenticated user unless the caller is super admin.
- Group assignment scope checks `organization_id` and `chat_id`.
- Group assignment recipients are active members of the selected chat, not all bot users.
- Group assignment reports require creator, chat admin or super admin access.
- Group assignment stores concrete creator attribution snapshots for auditability.
- Task templates and scheduled tasks use `AuthContext` and service-level access checks.
- Scheduled task execution has a `ScheduledTaskRun` ledger and unique planned-run protection.
- Scheduled task failures store controlled `last_error` strings.

### Notification and integration safety

- Personal notification delivery records explicit statuses: pending, sent, failed and DM unavailable.
- Notification delivery error messages redact common secret-bearing patterns before storage.
- MAX outbound delivery must resolve internal `User.id` / `Chat.id` to `User.max_user_id` / `Chat.max_chat_id` before calling the MAX API.
- Users or chats without external MAX ids are skipped with safe delivery-unavailable statuses instead of sending internal UUIDs.
- MAX sender stub mode avoids real MAX API calls when sender is disabled.
- MAX client isolates outgoing Bot API calls behind one adapter and requires a configured bot credential before real sending.

## 2. Required before real MAX bot

1. Configure a strong MAX webhook secret only in the VPS environment or a protected secret store.
2. Configure webhook delivery through the official MAX `/subscriptions` API and validate that MAX sends the expected `X-Max-Bot-Api-Secret` header.
3. Keep `MAX_WEBHOOK_DEBUG_LOG=false` by default; enable it only for short sandbox capture windows.
4. Run real sandbox capture for:
   - normal text message payloads;
   - reply payloads;
   - callback/action payloads;
   - direct message behavior;
   - WebApp open-button behavior;
   - formatting and error/rate-limit behavior.
5. Add inbound webhook idempotency using MAX `message_id` or equivalent event identifier before relying on live events for task creation.
6. Add a payload-size limit for `/api/bot/max/webhook` at host nginx and/or application layer.
7. Decide how webhook replay protection should work if MAX supports signatures, timestamps or event ids.
8. Confirm that callback payload length and encoding match real MAX limits.
9. Review logging before enabling sender: task titles and reminder texts may contain business information and should not be logged as full message bodies.
10. Enable real MAX sender only after sandbox send tests confirm DM unavailable errors and fallback behavior.

Sandbox validation sequence:

1. Add the real MAX bot credential and webhook secret only to the VPS `.env`.
2. Restart backend and worker.
3. Configure the webhook in the MAX control panel.
4. Send a normal sandbox chat message.
5. Send `/задача` as a reply to a sandbox message.
6. Check callback behavior.
7. Check direct messages and fallback behavior.
8. Update `docs/integrations/max_sandbox_audit.md` with sanitized results.

## 3. Required before production pilot

1. Replace dev/query WebApp auth with verified MAX WebApp authentication.
2. Do not enable `DEV_AUTH_ENABLED=true` in production except for a short controlled diagnostic window.
3. Protect legacy MVP endpoints that still accept unauthenticated requests:
   - organizations;
   - users;
   - chats and members;
   - base task create/list/detail/update/cancel;
   - comments, files, responses and acceptance;
   - reminder-rule endpoints;
   - inbox summary query access.
4. Close or restrict public `/docs` and `/openapi.json` before non-internal production use.
5. Add host nginx deny rules for dotfiles and common scanner paths so requests like `/.env` do not return the SPA shell with HTTP 200.
6. Add rate limiting for public API routes, especially the MAX webhook and write endpoints.
7. Review CORS policy before opening the product beyond the current domain.
8. Add backup encryption and retention policy for production pilot data.
9. Add audit logging for privileged actions:
   - group assignment creation;
   - scheduled task creation/update/delete;
   - template changes;
   - acceptance/rejection;
   - integration settings changes.
10. Define incident playbooks for leaked bot credential, leaked webhook secret and database restore.

## 4. Recommended / nice-to-have

- Add security headers in host nginx: HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` or a CSP-compatible frame policy for the WebApp context.
- Add response compression and cache controls intentionally rather than relying only on default nginx behavior.
- Add structured log redaction filters globally for common secret names and credential-shaped values.
- Add a CI secret scan job over diffs and full repository history for release branches.
- Add dependency vulnerability scanning for Python, npm and Docker base images.
- Add database least-privilege roles for application runtime and migrations if the deployment model permits it.
- Consider removing hard-coded `container_name` values in Compose for easier blue/green or parallel environments.
- Add monitoring alerts for repeated webhook failures, high 401/403 rates and worker healthcheck failures.
- Add a dedicated admin-only API route inventory document for release reviews.

## 5. Security risks

### P0 risks

- Several legacy MVP endpoints remain unauthenticated. This is acceptable only for controlled demo/internal validation and must be fixed before production pilot.
- Real MAX bot cannot be safely enabled without a configured webhook secret and real payload validation.
- Webhook idempotency is not yet confirmed for live MAX events; duplicate webhook delivery could create duplicate local actions.

### P1 risks

- Public `/docs` and `/openapi.json` expose API shape to the internet.
- Requests for dotfiles can be served by the SPA fallback as HTTP 200, which is not a data leak by itself but creates noisy security scanner results and should be denied explicitly.
- Sender stub logging may include full notification text in structured logging extras depending on logging configuration.
- Real MAX direct-message and callback error semantics are unknown until sandbox capture.

### P2 risks

- No full production SSO or MAX WebApp auth is available yet.
- No production-grade observability stack is included.
- Security headers are not documented as verified for the host nginx layer.
- Offline bundle security review is documentation-based and still needs separate infrastructure acceptance.

## 6. Proposed backlog P0/P1/P2

### P0

1. Require and configure MAX webhook secret before connecting the real bot.
2. Capture and verify real MAX sandbox payloads before enabling live task creation.
3. Add inbound MAX event idempotency keyed by real event/message identifiers.
4. Protect legacy MVP endpoints with `AuthContext` and RBAC.
5. Replace query/dev WebApp auth with verified MAX WebApp auth for pilot users.
6. Add nginx/application payload-size and rate limits for public write endpoints.
7. Deny dotfiles and known scanner paths at host nginx.

### P1

1. Restrict or disable public `/docs` and `/openapi.json` outside internal validation.
2. Add audit logging for group assignment, templates, scheduled tasks and acceptance actions.
3. Redact or remove full notification message text from normal production logs.
4. Add security headers to host nginx and document the deployed config.
5. Add CI secret scanning and dependency vulnerability checks.
6. Add backup encryption and restore-test cadence to operations docs.
7. Add alerting for worker health, webhook failures and repeated auth failures.

### P2

1. Review Docker image hardening: non-root users, read-only filesystems where feasible, and resource limits.
2. Add dedicated route-level security matrix for all FastAPI endpoints.
3. Add external penetration-test checklist before wider rollout.
4. Add automated verification for host nginx config in deployment smoke.
5. Add offline bundle security checklist for closed-contour delivery acceptance.
