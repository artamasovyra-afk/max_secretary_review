# MAX Webhook Security Audit

Status date: 2026-05-21

Version: `v1.1.0-rc.1`

Branch: `main`

Security hardening commits included:

- `73a7317 fix: require MAX webhook secret in production`
- `6298469 fix: harden MAX webhook secret validation`

Public URLs:

- WebApp: `https://maxsecretary.ru`
- MAX webhook: `https://maxsecretary.ru/api/bot/max/webhook`

Scope:

- `backend/app/api/bot_max.py`
- `backend/app/modules/integrations/max/`
- `backend/app/modules/bot/`
- `backend/app/core/config.py`
- `.env.example`
- `docs/integrations/max.md`
- `docs/integrations/max_webhook_setup.md`
- `docs/security/security_status_v1.1_rc.md`
- `backend/tests/*max*`
- `backend/tests/*bot*`

No real MAX API calls were executed. No real credentials were added or inspected.

## Current Behavior

### Endpoint

The MAX webhook is accepted by:

- `POST /api/bot/max/webhook`

The router is mounted in `backend/app/main.py` under:

- `/api/bot/max`

The endpoint receives an arbitrary JSON object, optionally logs safe debug shape data, normalizes the event, and passes the normalized event to `MaxBotWebhookService.handle_event()`.

### Webhook Secret Check

The endpoint uses dependency `verify_max_webhook_access()` in `backend/app/api/bot_max.py`.

Current logic:

1. If `MAX_WEBHOOK_ENABLED=false`, return `404` before payload handling.
2. Read the configured webhook secret from runtime settings.
3. If `APP_ENV=production`, `MAX_WEBHOOK_ENABLED=true`, and the configured secret is empty, return `503 MAX webhook is not configured` before payload handling.
4. In local/test environments, an empty configured secret is accepted for testability.
5. If the configured value is present and request header `X-Max-Webhook-Secret` is absent, return `401`.
6. If the configured value is present and request header `X-Max-Webhook-Secret` is invalid, return `401`.
7. If the configured value is present and request header matches, allow the request.

The comparison uses `secrets.compare_digest()`.

Expected header:

```text
X-Max-Webhook-Secret: <secret from VPS .env>
```

### Behavior Matrix

| Case | Current behavior |
| --- | --- |
| Webhook flag is false | Endpoint returns `404` and does not process or log the event payload. |
| Production webhook flag is true and configured secret is empty | Endpoint returns `503` with `MAX webhook is not configured` and does not process or log the event payload. |
| Local/test webhook flag is true and configured secret is empty | Request is accepted for local/test development. |
| Configured secret is present and request header is missing | Request is rejected with `401`. |
| Configured secret is present and request header is wrong | Request is rejected with `401`. |
| Configured secret is present and request header is correct | Request is accepted. |

### Startup Behavior

In production, if the webhook is enabled and the webhook secret is empty, application startup logs a warning:

- MAX webhook secret is not configured in production.

This is useful visibility, but it does not block startup. The endpoint itself returns `503` until the secret is configured or the webhook is disabled.

### Debug Logging

`MAX_WEBHOOK_DEBUG_LOG` exists and defaults to false.

When enabled, the endpoint logs:

- raw event top-level keys;
- raw event value shapes, not raw values;
- normalized event source;
- ignored state and reason;
- masked chat/user/message identifiers;
- text length and command flag.

The debug helper does not log full message text from normalized events. For raw payloads it records types and object keys, not values.

### MAX Sender

Outgoing MAX sender is disabled by default. Real outgoing MAX calls require sender enabled and a configured bot credential. This audit did not execute real outbound calls.

## Test Coverage Observed

Existing tests in `backend/tests/test_bot_max_webhook.py` cover:

- local mode without configured webhook secret works;
- correct secret works;
- missing secret header returns `401` when a secret is configured;
- wrong secret returns `401`;
- expected secret does not appear in response body or logs for missing/invalid header;
- secret comparison uses constant-time comparison;
- debug logging is disabled by default;
- debug logging masks values and does not log private payload content;
- raw MAX-like message event normalization;
- unsupported event handling;
- empty text handling;
- invalid normalized event validation.

Related tests also cover:

- MAX event normalization;
- mock MAX fixtures;
- callback payload validation;
- MAX API client configuration and error behavior.

## Gaps

### No Request Size Limit at Application Layer

The endpoint accepts a JSON body without an endpoint-specific size guard. Any size enforcement depends on upstream nginx or server defaults.

Impact:

- Large webhook payloads could create unnecessary load.

### No Inbound Event Idempotency

The webhook path does not yet enforce idempotency based on real MAX event/message identifiers.

Impact:

- Real webhook retries could create duplicate local actions after real payload mapping is enabled.

### Real MAX Header Compatibility Is Pending

The backend expects `X-Max-Webhook-Secret`. It is not yet confirmed that the MAX control panel can send this exact header or that MAX provides an official signature/timestamp scheme.

Impact:

- The verification mechanism may need adjustment after real sandbox validation.

### Debug Mode Still Needs Operational Controls

Debug logging appears safe by implementation, but it should only be enabled for short sandbox sessions and then disabled.

Impact:

- Even shape logs can reveal object structure and operational metadata.

## Risks

### P0

- Missing inbound idempotency may duplicate actions under real webhook retries.

### P1

- No application-level request size limit.
- Real MAX signature/header semantics are unverified.
- Public docs and OpenAPI remain accessible unless restricted at deployment level.

### P2

- Debug logging needs an operational checklist for enable/capture/disable.
- Global log redaction would reduce risk if future code logs integration errors.

## Required Fixes Before Real MAX Bot

1. Configure a strong webhook secret in the VPS runtime environment before setting `MAX_WEBHOOK_ENABLED=true`.
2. Configure the real bot credential only in the VPS runtime environment or protected secret store.
3. Validate the real MAX webhook verification mechanism in sandbox.
4. Add inbound event idempotency using real MAX event/message identifiers.
5. Add request body size limits at host nginx and/or backend layer.
6. Keep debug logging disabled except during short sandbox capture windows.

Never commit the MAX bot credential or webhook secret, paste them into README/docs, send them in chat, or include them in screenshots.

Sandbox validation sequence:

1. Add the real MAX bot credential and webhook secret only to the VPS `.env`.
2. Restart backend and worker.
3. Configure the webhook in the MAX control panel.
4. Send a normal sandbox chat message.
5. Send `/задача` as a reply to a sandbox message.
6. Check callback behavior.
7. Check direct messages and fallback behavior.
8. Update `docs/integrations/max_sandbox_audit.md` with sanitized results.

## Recommended Tests

Add or confirm tests for:

1. Production mode, webhook flag false: endpoint returns `404`, does not call the handler and does not emit debug logs.
2. Production mode, webhook flag true, configured secret empty: returns `503` and does not call the handler or emit debug logs.
3. Production mode, configured secret present, missing header: returns `401`.
4. Production mode, configured secret present, wrong header: returns `401`.
5. Production mode, configured secret present, correct header: returns success.
6. Debug logging enabled: no raw text, names, credential-like values, or full identifiers appear in logs.
7. Oversized payload: request is rejected before normalization.
8. Duplicate real-like event id: second event is skipped or treated idempotently.

## Files to Change

Likely implementation files:

- `backend/app/api/bot_max.py`
- `backend/app/core/config.py`, only if stricter startup/runtime validation is added
- `backend/tests/test_bot_max_webhook.py`
- `infra/nginx/nginx.conf`, if request-size limits or route restrictions are added inside Docker nginx
- host nginx config on VPS, if route restrictions are applied at the host proxy
- `docs/integrations/max.md`
- `docs/integrations/max_webhook_setup.md`
- `docs/security/security_status_v1.1_rc.md`

## Readiness Summary

The webhook endpoint has a basic shared-secret check, safe debug logging, an application-level disabled state for `MAX_WEBHOOK_ENABLED=false`, and a production misconfiguration guard for enabled webhook without secret. It is not ready for a real MAX bot until the secret is configured, live payload idempotency is added, request size limits are defined and real MAX sandbox verification confirms the incoming payload and verification scheme.
