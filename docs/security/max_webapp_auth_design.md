# MAX WebApp Auth Design

Status date: 2026-05-24

Project version: `1.1.0-rc.3`

Scope: production-safe authentication for the `max_secretary` WebApp opened inside MAX.

This document started as an architecture design and now also records the implemented backend/frontend auth flow. Runtime `.env`, production configuration, and secrets were not changed.

## 1. Current State

The WebApp now uses MAX session auth in production:

- `webapp/src/auth/AuthContext.tsx` restores existing sessions through `GET /api/auth/me`.
- If no session exists, it reads MAX `initData` and calls `POST /api/auth/max-webapp/session`.
- `webapp/src/api/client.ts` sends API requests with `credentials: "include"`.
- Direct browser opens without a valid session or MAX `initData` show an unauthorized state.
- User-scoped WebApp endpoints derive identity from the session by default; query `user_id` is not used as an auth source.
- Query/dev auth remains available only in Vite dev mode for local diagnostics.
- Since commit `911a1fe`, backend header auth is blocked in production even if `DEV_AUTH_ENABLED=true`; it is still available for local/test/dev flows.

Protected backend routes now depend on `AuthContext`, especially:

- tasks, task comments, files, responses, reminder rules, group reports, and group assignment;
- users;
- chats and chat members;
- organizations;
- task templates and scheduled tasks;
- Bitrix24 integration endpoints.

Current risks:

- Exact current MAX official init-data documentation still should be rechecked against the working reference algorithm.
- Live frontend session flow inside real MAX still needs post-deploy acceptance.
- Browser-supplied query role/chat/organization context remains local/dev only and must not be used in production.

## 2. Target State

Target production flow:

1. User opens `https://maxsecretary.ru` inside MAX through a mini app deep link, for example:

   ```text
   https://max.ru/<bot_username>?startapp=home
   ```

   Current production bot username is configured as `MAX_BOT_USERNAME=secretary_oren_bot`, so chat buttons should use:

   ```text
   https://max.ru/secretary_oren_bot?startapp=home
   ```

   A plain `https://maxsecretary.ru` link opens in an external browser in the observed MAX client and does not provide MAX `initData`.

2. Frontend loads MAX Bridge through `https://st.max.ru/js/max-web-app.js`, then reads signed launch data from `window.WebApp.initData`.
   Compatibility fallback also checks known MAX namespaces and `WebAppData` in the URL fragment/query if a client exposes launch data that way.
3. Frontend sends raw `initData` to backend:

   ```http
   POST /api/auth/max-webapp/session
   ```

4. Backend validates the signature and freshness of `initData` using the configured MAX bot credential.
5. Backend extracts MAX user id from the validated `user` payload.
6. Backend resolves or creates local `User` by `User.max_user_id`.
7. Backend creates a WebApp session and returns current user/profile context.
8. All WebApp API calls use the session, not query `user_id`.
9. Query `user_id`, `chat_id`, `organization_id`, and `roles` remain local/test/dev-only and are not trusted in production.

Desired request model after session creation:

- Browser sends `Cookie: max_secretary_session=...` automatically for same-origin API calls.
- Backend `get_auth_context()` first resolves a valid WebApp session.
- Dev header auth remains a fallback only in local/test/dev, never in production.

## 3. MAX Init Data Validation

Reference evidence:

- `bot_comment_max` sends `window.WebApp.initData` to backend through `X-Max-Init-Data`.
- Its backend validates MAX init data with HMAC-SHA256 using the MAX bot credential.
- Its verifier checks duplicate keys, `hash`, `auth_date`, maximum age, JSON `user` payload, and constant-time signature comparison.
- `docs/integrations/max_bot_comment_reference_analysis.md` records the same behavior.

Reference-confirmed algorithm:

1. Accept raw init data as a query-string-like value.
2. Compatibility handling may unwrap `WebAppData` if MAX provides the launch data in a URL fragment or nested parameter.
3. Parse query parameters with blank values preserved.
4. Reject empty data.
5. Reject duplicate keys.
6. Extract `hash`; reject if missing.
7. Build `data_check_string` from all key/value pairs except `hash`, sorted by key, joined with newline as `key=value`.
8. Build secret key as HMAC-SHA256 with:
   - key: literal `WebAppData`;
   - message: MAX bot credential.
9. Build expected hash as HMAC-SHA256 over `data_check_string` using the derived secret key.
10. Compare expected hash with supplied `hash` using constant-time comparison.
11. Parse `auth_date` and reject if missing, invalid, in the future beyond clock-skew tolerance, or older than configured maximum age.
12. Parse JSON `user` payload and require a stable MAX user id.
13. Parse optional JSON `chat` payload if present, but do not require it.

Important implementation notes:

- The frontend may use `initDataUnsafe` for UI hints only after raw `initData` is sent to the backend. It must not be trusted for authorization.
- The backend must not log raw `initData`, raw hashes, or full MAX user ids.
- Validation failures return `401` with safe messages such as `Invalid MAX WebApp auth`.
- `MAX_BOT_TOKEN` is used only server-side for validation and must never be sent to frontend.

Open confirmation:

- The algorithm above is confirmed by the working reference project, but the exact current MAX official documentation page should be re-checked immediately before implementation.
- Unknowns to confirm: final field names, whether `chat` is always available for group-launched sessions, accepted clock skew, and whether MAX documents replay guidance.

Implemented backend configuration:

- `MAX_WEBAPP_AUTH_ENABLED` enables the backend session exchange endpoint.
- `MAX_WEBAPP_INITDATA_MAX_AGE_SECONDS` controls accepted `auth_date` freshness.
- `MAX_WEBAPP_SESSION_TTL_SECONDS` controls the signed session cookie lifetime.
- `MAX_WEBAPP_SESSION_SECRET` signs WebApp session cookies and is required when WebApp auth is enabled in production.
- `MAX_WEBAPP_SESSION_COOKIE_NAME` defaults to `max_secretary_session`.
- `MAX_WEBAPP_COOKIE_SECURE` and `MAX_WEBAPP_COOKIE_SAMESITE` control cookie transport policy.

## 4. Backend Endpoints

### POST /api/auth/max-webapp/session

Input:

```json
{
  "initData": "<raw MAX WebApp initData>"
}
```

Behavior:

- Validate raw MAX init data.
- Extract MAX user id and optional profile fields.
- Resolve existing `User` by `User.max_user_id`.
- If no user exists, create a local user with:
  - `max_user_id`;
  - safe display name from validated payload if present;
  - username if present;
  - no privileged roles by default.
- Resolve optional chat context if MAX provides chat id and `Chat.max_chat_id` exists.
- Optionally create a default MAX chat only when the design intentionally allows WebApp-driven chat creation. MVP should prefer existing chat membership from bot/webhook history.
- Create and set a session.
- Return sanitized current user context.

Output:

```json
{
  "user": {
    "id": "<internal User.id>",
    "display_name": "Иван Иванов",
    "roles": ["member"]
  },
  "context": {
    "organization_id": "<optional>",
    "chat_id": "<optional>",
    "available_chats": []
  },
  "session_expires_at": "2026-05-24T12:00:00Z"
}
```

Do not return raw MAX ids unless a UI feature explicitly needs masked diagnostics.

### GET /api/auth/me

Behavior:

- Requires a valid WebApp session.
- Returns current user, role context, available organizations/chats, and feature flags.
- Returns `401` if no session exists or the session is expired.

Output fields:

- internal user id;
- display name;
- effective roles;
- selected organization/chat context;
- available chats/orgs;
- feature flags such as `can_create_group_assignment`.

### POST /api/auth/logout

Optional but useful:

- Clears the session cookie.
- Marks server-side session revoked if opaque sessions are used.
- Returns `204`.

## 5. Session Strategy

Recommended MVP strategy: httpOnly secure same-origin cookie with a short-lived signed session.

Why:

- Frontend and backend are served from the same origin, `https://maxsecretary.ru`.
- `httpOnly` keeps the session out of JavaScript, reducing token theft risk from XSS.
- `Secure` ensures the cookie is sent only over HTTPS.
- `SameSite=Lax` works for normal same-site API calls after MAX opens the WebApp and reduces cross-site request risk.
- The API client can use `credentials: "include"` without managing bearer tokens.

Cookie settings:

- name: `max_secretary_session`;
- `HttpOnly`;
- `Secure`;
- `SameSite=Lax`;
- path: `/`;
- max age aligned with `MAX_WEBAPP_SESSION_TTL_SECONDS`.

Session contents:

Option A, stateless signed token:

- signed with `MAX_WEBAPP_SESSION_SECRET`;
- contains internal `user_id`, optional selected `organization_id`/`chat_id`, issued-at, expires-at, session id.

Option B, opaque server-side session:

- cookie stores random session id;
- database stores session hash, user id, context, expires-at, revoked-at;
- easier revocation and audit;
- requires a small migration and cleanup job.

Implementation status:

- The backend MVP uses Option A: a signed stateless httpOnly cookie.
- The session token contains internal `User.id`, `User.max_user_id`, effective roles, optional selected organization/chat context, issued-at, and expires-at.
- The token is signed with `MAX_WEBAPP_SESSION_SECRET`, not the MAX bot credential.
- Prefer Option B before broader production if revocation and audit requirements become important.

CSRF/XSS notes:

- Keep CORS closed to the same origin.
- Check `Origin`/`Referer` on state-changing WebApp session-authenticated requests.
- Add CSRF token header later if cross-origin embedding or non-Lax cookie behavior becomes necessary.
- Do not store session tokens in localStorage.

Bearer-token alternative:

- A short-lived bearer token stored in memory is easier for SPA wiring, but refresh/navigation flows are more fragile and XSS exposure is worse.
- Use bearer only as fallback if MAX WebView blocks same-origin cookies in practice.

## 6. Frontend Changes

Auth bootstrap:

1. On app load, detect MAX bridge object.
2. Read `window.WebApp.initData`.
3. If `initData` exists, call `POST /api/auth/max-webapp/session`.
4. Store returned user/context in React auth state.
5. Configure API client to send same-origin cookie credentials.
6. Call `GET /api/auth/me` on reload to restore session.

User states:

- Loading: show compact loading state while session is created/restored.
- Authorized: render routes normally.
- Missing MAX data in production: show:

  ```text
  Откройте WebApp из MAX.
  ```

- Local/dev: continue supporting query dev auth only when backend permits dev headers.
- Direct browser open in production: show limited landing/unauthorized state, not business data.

API client changes:

- Stop sending `X-User-Id`, `X-Chat-Id`, `X-Organization-Id`, and `X-Roles` in production.
- Add `credentials: "include"` to same-origin `fetch`.
- Keep dev header injection only for local/test/dev builds or when explicitly enabled for local diagnostics.

Deep-link handling:

- Continue using short non-secret `startapp` payloads such as `home` or `task_<id>`.
- Treat `startapp` as navigation hint only.
- After auth, backend authorizes whether the user may view the referenced task.

## 7. Backend Auth Context

Target `get_auth_context()` behavior:

1. If a valid WebApp session cookie exists, return `AuthContext` from the session and database role lookup.
2. If no session exists, allow dev headers only in local/test/dev as currently guarded.
3. Otherwise return `401`.

Role/context resolution:

- Resolve `User` by session internal user id.
- Resolve `ChatMember` rows for available chats and roles.
- If a selected chat is present, derive role from the active `ChatMember`.
- If no selected chat is present, return conservative roles and list available contexts through `/api/auth/me`.
- Super admin must come from trusted backend data, not from frontend launch data.

Compatibility:

- `/api/health` remains public.
- `POST /api/bot/max/webhook` remains on MAX secret validation and does not use WebApp sessions.
- Local/test dev auth tests remain valid.
- Existing WebApp demo URLs can continue in local/dev only.

## 8. Security Requirements

Must:

- Fail closed on missing, invalid, expired, duplicated, or unsigned init data.
- Never trust `initDataUnsafe` for authorization.
- Never trust query `user_id` in production.
- Never log raw `initData`, raw session tokens, raw hashes, or full external MAX ids.
- Use constant-time hash comparison.
- Use a separate session signing secret or opaque server-side session ids; do not reuse the MAX bot credential as the WebApp session secret.
- Enforce session expiration.
- Return `401` for missing/invalid auth and `403` for valid auth without permission.
- Keep auth failure logs sanitized and rate-limited.

Should:

- Include clock-skew tolerance for `auth_date`.
- Add auth failure metrics without raw payloads.
- Add server-side session revocation if using opaque sessions.
- Add cookie `Secure` and `HttpOnly` in every production response.
- Add Origin checks for session-authenticated writes.

## 9. Implementation Plan

P0 backend:

Done in backend implementation:

1. Added MAX init data verifier helper.
2. Added tests for valid hash, invalid hash, missing hash, malformed user payload, expired auth date, session tampering, and safe error text.
3. Added `POST /api/auth/max-webapp/session`.
4. Added `GET /api/auth/me`.
5. Added `POST /api/auth/logout`.
6. Added signed httpOnly session cookie creation and validation.
7. Extended `get_auth_context()` to resolve WebApp session before dev headers.
8. Resolve or autocreate `User` by `User.max_user_id`.
9. Resolve roles from backend chat membership, not frontend-provided roles.

P0 frontend:

Done in frontend implementation:

1. Added MAX WebApp bootstrap in `AuthProvider`.
2. Sends raw `window.WebApp.initData` to backend session endpoint when no existing session is available.
3. Removed production trust in query `user_id`; query/dev header auth remains only in Vite dev mode.
4. Updated API client to use `credentials: "include"`.
5. Added loading, unauthorized/direct-open, auth failure, and network failure states.
6. Added logout through `POST /api/auth/logout`.

P0 docs/ops:

1. Document required runtime variables for WebApp session signing and init-data max age.
2. Document that `DEV_AUTH_ENABLED=true` is forbidden in production.
3. Document how to test direct browser open vs MAX-opened WebApp.

P1:

1. Add opaque session table if not implemented in P0.
2. Add session revocation and cleanup job.
3. Add sanitized auth failure audit logs.
4. Add role/context selector for users in multiple chats/orgs.
5. Restrict or close public OpenAPI/docs if pilot exposure requires it.

## 10. Test Plan

Backend tests:

- valid init data creates session;
- invalid hash returns `401`;
- expired `auth_date` returns `401`;
- missing `initData` returns `401`;
- duplicate init-data keys return `401`;
- missing `hash` returns `401`;
- malformed `user` payload returns `401`;
- existing user is resolved by `User.max_user_id`;
- unknown MAX user is created with safe defaults;
- raw MAX ids and raw init data are not logged or returned unnecessarily;
- direct API call without session returns `401`;
- session cookie authenticates protected endpoints;
- dev auth still works only in local/test/dev;
- production with dev auth enabled still fails fast;
- MAX webhook missing/invalid/valid secret behavior is unchanged.

Frontend tests:

- app bootstraps from MAX `initData`;
- app restores via `GET /api/auth/me`;
- direct production browser open shows unauthorized state;
- dev query auth remains available only for local/dev build mode;
- API client uses cookie credentials in production mode.

Integration/smoke tests:

- open WebApp through MAX deep link;
- verify session endpoint returns current user without exposing raw MAX id;
- verify `/tasks`, `/dashboard`, `/group-assignments`, and `/settings` load through session auth;
- verify direct browser open cannot fetch protected data.

## 11. Open Questions

- Exact current MAX official init-data validation documentation rechecked: no.
- Does MAX always expose `window.WebApp.initData`, or are some clients using a different global object name?
- Does MAX provide reliable chat context in init data for group-launched sessions?
- What is the recommended official max age for `auth_date`?
- Does MAX recommend replay protection beyond `auth_date` and HMAC?
- Should a later production hardening pass replace stateless signed cookies with opaque DB-backed sessions?
- Which `startapp` payloads are needed for task details, group assignment reports, and settings?
- Should WebApp create missing chats from signed init data, or only use chats already created by webhook identity resolver?
- How should users choose active chat/organization if they belong to multiple MAX chats?

## 12. Decision Summary

Recommended MVP:

- Validate MAX `initData` server-side with HMAC-SHA256 using the MAX bot credential.
- Create an httpOnly secure same-origin session cookie.
- Resolve local user by `User.max_user_id`.
- Derive roles and selected context from backend chat membership.
- Keep query/dev auth only for local/test/dev.
- Treat deep-link `startapp` as navigation hint, not authorization.

Implementation status:

- Backend session auth: implemented.
- Frontend session bootstrap: implemented.
- Runtime production enablement and live MAX acceptance: pending deployment task.
