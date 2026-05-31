# API Access Matrix

## Summary

Audit date: 2026-05-24.

Source scope:

- `backend/app/main.py`
- `backend/app/api/*.py`
- `backend/app/api/dependencies/auth.py`
- `backend/app/modules/**/service.py`
- `webapp/src/api/*`
- `webapp/src/auth/*`
- `docs/product/webapp_mvp.md`
- `docs/security/security_status_v1.1_rc.md`
- `docs/security/webapp_auth_preparation.md`

Update note:

- This matrix was created as a read-only audit, updated while committing the first core API security fix, and re-audited after MAX WebApp session auth went live.
- Core `tasks`, `users`, `chats`, and `organizations` routers now have route-level `Depends(get_auth_context)`.
- Baseline API-layer ownership/RBAC checks were added for the most sensitive task, user, chat, and organization paths.
- Backend MAX WebApp session auth, frontend bootstrap, MAX deep-link opening, and session-based inbox summary are implemented and live-validated.
- Separate `/super-admin` web auth uses login/password plus a dedicated httpOnly cookie and is not backed by MAX WebApp `initData`.
- Remaining production risk is mostly P1 service-boundary policy hardening, broader DM/reminder rollout controls, and production docs/openapi exposure policy.

Route inventory:

- FastAPI/Starlette route entries found: 74.
- Method/path variants found: 78.
- Unique method/path variants found: 76.
- API `APIRoute` entries found: 70.
- Public endpoint method/path pairs: 10.
- Webhook endpoints: 1.
- Auth/session endpoints: 3.
- Protected core API route entries: 54.
- Integration API route entries: 8.
- Internal/admin API route entries: 8.
- Protected business/integration route entries with missing route auth: 0.
- Standard user-auth exceptions: public health/docs/openapi/redoc, MAX WebApp session exchange, logout cookie clearing, and MAX webhook secret validation.
- Core route-level auth gap status: closed for tasks, users, chats, and organizations.
- DEV_AUTH production guard status: closed.
- MAX WebApp query `user_id` auth risk: closed at backend and frontend bootstrap level.
- Remaining P0 high-risk endpoint groups: 0.
- Remaining high-risk themes: broader route-policy coverage, DM/reminder rollout controls, production docs/openapi exposure policy, and official MAX initData schema confirmation.

## Legend

Current auth values:

- `none`: no route auth dependency.
- `get_auth_context`: backend auth dependency that first resolves a signed WebApp session cookie; dev headers are accepted only in local/test/dev allowed modes.
- `MAX initData`: MAX WebApp launch data signature validation before setting a session cookie.
- `WebApp session`: signed httpOnly session cookie resolved by `get_auth_context`.
- `Super-admin session`: separate signed httpOnly cookie for `/super-admin`; MAX WebApp `initData` is not accepted as super-admin auth.
- `MAX secret`: official `X-Max-Bot-Api-Secret` check, with legacy `X-Max-Webhook-Secret` still accepted.
- `service RBAC`: additional service or handler authorization beyond route auth.

Risk values:

- `OK`: acceptable exception or already has appropriate route auth plus scoped checks.
- `P0`: must be fixed before non-internal release or pilot exposure.
- `P1`: important hardening after P0.
- `P2`: cleanup or policy decision.

## Endpoint Matrix

| Method | Path | Module | Handler | Category | Current auth | Required auth | Role | Risk | Recommendation | Tests |
|---|---|---|---|---|---|---|---|---|---|---|
| GET, HEAD | `/openapi.json` | FastAPI default / `backend/app/main.py` | `openapi`, `openapi_head` | public | none | production policy | n/a | P1 | Decide whether OpenAPI stays public; close or restrict before external pilot if needed. | indirect smoke |
| GET, HEAD | `/docs` | FastAPI default / `backend/app/main.py` | `swagger_ui_html`, `docs_head` | public | none | production policy | n/a | P1 | Decide whether Swagger UI stays public; close or restrict before external pilot if needed. | indirect smoke |
| GET, HEAD | `/docs/oauth2-redirect` | FastAPI default | `swagger_ui_redirect` | public | none | production policy | n/a | P2 | Keep only if `/docs` remains enabled. | none |
| GET, HEAD | `/redoc` | FastAPI default | `redoc_html` | public | none | production policy | n/a | P2 | Keep only if public API docs are intentional. | none |
| GET | `/api/health` | `backend/app/api/health.py` | `health` | public | none | public | n/a | OK | Keep public for uptime checks. | smoke |
| HEAD | `/api/health` | `backend/app/api/health.py` | `health_head` | public | none | public | n/a | OK | Keep public for uptime checks. | smoke |
| POST | `/api/auth/max-webapp/session` | `backend/app/api/auth.py` | `create_max_webapp_session` | auth | `MAX initData` | signed MAX initData | MAX WebApp user | OK | Frontend should call this after MAX opens the WebApp; do not log raw initData. | auth API tests |
| GET | `/api/auth/me` | `backend/app/api/auth.py` | `get_current_user` | auth | `WebApp session` / `get_auth_context` | valid session | authenticated | OK | Use for WebApp bootstrap/restore; direct browser call without session returns `401`. | auth API tests |
| POST | `/api/auth/logout` | `backend/app/api/auth.py` | `logout` | auth | none | session clear only | n/a | OK | Clears session cookie; no business data returned. | auth API tests |
| POST | `/api/super-admin/login` | `backend/app/api/super_admin.py` | `login_super_admin` | internal/admin | login/password | configured super-admin credentials | super_admin operator | OK | Separate from MAX WebApp auth; password stays server-side and is never logged. | super-admin API tests |
| GET | `/api/super-admin/session` | `backend/app/api/super_admin.py` | `get_super_admin_session` | internal/admin | `Super-admin session` | super-admin session cookie | super_admin operator | OK | Restores super-admin UI session; MAX initData is not accepted. | super-admin API tests |
| POST | `/api/super-admin/logout` | `backend/app/api/super_admin.py` | `logout_super_admin` | internal/admin | none | session clear only | n/a | OK | Clears only the super-admin cookie and returns no business data. | super-admin API tests |
| GET | `/api/super-admin/status` | `backend/app/api/super_admin.py` | `super_admin_status` | internal/admin | `Super-admin session` | super-admin session cookie | super_admin operator | OK | Keep protected because the whole super-admin API prefix is private. | super-admin API tests |
| GET | `/api/super-admin/chats` | `backend/app/api/super_admin.py` | `list_super_admin_chats` | internal/admin | `Super-admin session` | super-admin session cookie | super_admin operator | OK | Lists chat connection status and counts without raw MAX ids. Supports `status=pending_approval/active/rejected/suspended` and legacy alias `status=pending`. | super-admin API tests |
| GET | `/api/super-admin/chats/{chat_id}/members` | `backend/app/api/super_admin.py` | `list_super_admin_chat_members` | internal/admin | `Super-admin session` | super-admin session cookie | super_admin operator | OK | Lists display names, Dyak roles, and saved MAX-admin marker only. | super-admin API tests |
| POST | `/api/super-admin/chats/{chat_id}/sync-max-chat-info` | `backend/app/api/super_admin.py` | `sync_super_admin_chat_max_info` | internal/admin | `Super-admin session` + MAX bot token server-side | super-admin session cookie | super_admin operator | OK | Manually syncs title/type display info for one selected chat only, returns sanitized source/update flags, stores no raw MAX response, and does not approve the chat. | super-admin API tests |
| POST | `/api/super-admin/chats/{chat_id}/sync-max-admins` | `backend/app/api/super_admin.py` | `sync_super_admin_chat_max_admins` | internal/admin | `Super-admin session` + MAX bot token server-side | super-admin session cookie | super_admin operator | OK | Manually syncs MAX admin markers for one selected chat only, stores snapshot counters, returns no raw MAX ids/responses, and does not change Dyak roles. | super-admin API tests |
| PATCH | `/api/super-admin/chats/{chat_id}/display-title` | `backend/app/api/super_admin.py` | `update_super_admin_chat_display_title` | internal/admin | `Super-admin session` | super-admin session cookie | super_admin operator | OK | Sets or clears manual chat alias in `settings.display_title` for onboarding; does not expose raw ids and does not rename MAX chat. | super-admin API tests |
| PATCH | `/api/super-admin/chats/{chat_id}/status` | `backend/app/api/super_admin.py` | `update_super_admin_chat_status` | internal/admin | `Super-admin session` | super-admin session cookie | super_admin operator | OK | Approve/reject/suspend/reactivate chat; writes audit log. | super-admin API tests |
| PATCH | `/api/super-admin/chats/{chat_id}/members/{user_id}/role` | `backend/app/api/super_admin.py` | `update_super_admin_chat_member_role` | internal/admin | `Super-admin session` | super-admin session cookie | super_admin operator | OK | Can set `member`/`chat_admin`, cannot assign `super_admin`; last-admin removal requires confirmation. | super-admin API tests |
| GET | `/api/organizations/status` | `backend/app/api/organizations.py` | `organizations_status` | protected | `get_auth_context` | user auth | authenticated | P1 | Status can stay protected or be removed from public surface. | partial |
| POST | `/api/organizations` | `backend/app/api/organizations.py` | `create_organization` | protected | `get_auth_context` + role check | user auth + RBAC | `super_admin` | OK | Keep super-admin-only organization creation. | API tests |
| GET | `/api/organizations` | `backend/app/api/organizations.py` | `list_organizations` | protected | `get_auth_context` + scope filter | user auth + scope | scoped user/admin | OK | Keep scoped listing. | API tests |
| GET | `/api/organizations/{organization_id}` | `backend/app/api/organizations.py` | `get_organization` | protected | `get_auth_context` + scope check | user auth + scope | org scoped user/admin | OK | Keep organization scope check. | API tests |
| PATCH | `/api/organizations/{organization_id}` | `backend/app/api/organizations.py` | `update_organization` | protected | `get_auth_context` + role check | user auth + RBAC | `super_admin` | OK | Keep super-admin-only organization updates. | API tests |
| GET | `/api/chats/status` | `backend/app/api/chats.py` | `chats_status` | protected | `get_auth_context` | user auth | authenticated | P1 | Status can stay protected or be removed. | partial |
| POST | `/api/chats` | `backend/app/api/chats.py` | `create_chat` | protected | `get_auth_context` + role/scope check | user auth + RBAC | chat_admin/super_admin | OK | Keep scoped chat-admin creation. | API tests |
| GET | `/api/chats` | `backend/app/api/chats.py` | `list_chats` | protected | `get_auth_context` + active membership filter | user auth + membership scope | active chat member/super_admin | OK | WebApp launch chat must not narrow the dropdown to one chat; return all active member chats in org scope, super_admin all chats. | API tests |
| GET | `/api/chats/{chat_id}` | `backend/app/api/chats.py` | `get_chat` | protected | `get_auth_context` + scope check | user auth + scope | chat scoped user/admin | OK | Keep chat scope check. | API tests |
| PATCH | `/api/chats/{chat_id}` | `backend/app/api/chats.py` | `update_chat` | protected | `get_auth_context` + per-chat role check | user auth + RBAC | chat_admin of this chat/super_admin | OK | Keep admin-only updates; `display_title` alias is stored in chat settings and must not expose raw ids. | API tests |
| POST | `/api/chats/{chat_id}/reminder-rules` | `backend/app/api/chats.py` | `create_chat_reminder_rule` | protected | `get_auth_context` + role/scope check | user auth + RBAC | chat_admin/super_admin | OK | Keep admin-only reminder policy mutation. | reminder API tests |
| GET | `/api/chats/{chat_id}/reminder-rules` | `backend/app/api/chats.py` | `list_chat_reminder_rules` | protected | `get_auth_context` + scope check | user auth + scope | chat scoped user/admin | OK | Keep chat scope check. | reminder API tests |
| POST | `/api/chats/{chat_id}/members` | `backend/app/api/chats.py` | `add_chat_member` | protected | `get_auth_context` + role/scope check | user auth + RBAC | chat_admin/super_admin | OK | Keep membership writes admin-only. | API tests |
| GET | `/api/chats/{chat_id}/members` | `backend/app/api/chats.py` | `list_chat_members` | protected | `get_auth_context` + scope check | user auth + scope | chat scoped user/admin | OK | Keep chat scope check. | API tests |
| PATCH | `/api/chats/{chat_id}/members/{user_id}` | `backend/app/api/chats.py` | `update_chat_member` | protected | `get_auth_context` + role/scope check | user auth + RBAC | chat_admin/super_admin | OK | Keep membership edits admin-only. | API tests |
| GET | `/api/users/status` | `backend/app/api/users.py` | `users_status` | protected | `get_auth_context` | user auth | authenticated | P1 | Status can stay protected or be removed. | partial |
| POST | `/api/users` | `backend/app/api/users.py` | `create_user` | protected | `get_auth_context` + role check | user auth + RBAC | chat_admin/super_admin | OK | Keep user creation admin-controlled; keep bot identity creation in bot service. | API tests |
| GET | `/api/users` | `backend/app/api/users.py` | `list_users` | protected | `get_auth_context` + role check | user auth + scope | chat_admin/super_admin | OK | Keep global user listing admin-only until richer scoped directory exists. | API tests |
| GET | `/api/users/{user_id}` | `backend/app/api/users.py` | `get_user` | protected | `get_auth_context` + self/admin check | user auth + scope | self/admin | OK | Keep self/admin access rule. | API tests |
| PATCH | `/api/users/{user_id}` | `backend/app/api/users.py` | `update_user` | protected | `get_auth_context` + self/admin check | user auth + RBAC | self/admin | OK | Keep self/admin access rule; tighten external-id edits in follow-up if needed. | API tests |
| GET | `/api/tasks/status` | `backend/app/api/tasks.py` | `tasks_status` | protected | `get_auth_context` | user auth | authenticated | P1 | Status can stay protected or be removed. | partial |
| POST | `/api/tasks` | `backend/app/api/tasks.py` | `create_task` | protected | `get_auth_context` + creator/scope check | user auth + task policy | member self-task/chat_admin/super_admin | OK | Keep `created_by_user_id` bound to auth context unless `super_admin`; enforce chat/org scope. | API tests |
| POST | `/api/tasks/group-assignment` | `backend/app/api/tasks.py` | `create_group_assignment` | protected | `get_auth_context` + handler role check + service checks | user auth + RBAC | chat_admin of active source chat/super_admin | OK | Requires future deadline, active chat with `max_chat_id`, active assignees in selected chat, and one clean MAX chat summary message. | API/service tests |
| GET | `/api/tasks` | `backend/app/api/tasks.py` | `list_tasks` | protected | `get_auth_context` + visibility filter | user auth + task visibility policy | owner/assignee/observer/chat_admin | OK | Keep `PolicyService.can_view_task` filtering for search, chat, participant, and quick-status filters; consider service-boundary enforcement in follow-up. | API tests |
| GET | `/api/tasks/inbox/summary` | `backend/app/api/tasks.py` | `get_task_inbox_summary` | protected | `get_auth_context` + auth-context user default; optional `user_id` must match auth context unless super-admin | user auth + self/scope | self/admin | OK | Keep deriving the WebApp default user from session; do not use query `user_id` as auth. | smoke/API tests |
| GET | `/api/tasks/{task_id}` | `backend/app/api/tasks.py` | `get_task` | protected | `get_auth_context` + `can_view_task` | user auth + `can_view_task` | owner/assignee/observer/chat_admin | OK | Keep task visibility check before returning details. | API tests |
| GET | `/api/tasks/{task_id}/group-report` | `backend/app/api/tasks.py` | `get_group_assignment_report` | protected | `get_auth_context` + service checks | user auth + RBAC | creator/chat_admin/super_admin | OK | Keep; add unauth/wrong-scope regression tests. | API tests exist |
| PATCH | `/api/tasks/{task_id}` | `backend/app/api/tasks.py` | `update_task` | protected | `get_auth_context` + `can_update_task` | user auth + `can_update_task` | creator/chat_admin/super_admin | OK | Keep task update policy. | API tests |
| POST | `/api/tasks/{task_id}/cancel` | `backend/app/api/tasks.py` | `cancel_task` | protected | `get_auth_context` + `can_update_task` | user auth + `can_update_task` | creator/chat_admin/super_admin | OK | Keep cancellation policy. | API tests |
| POST | `/api/tasks/{task_id}/reminder-rules` | `backend/app/api/tasks.py` | `create_task_reminder_rule` | protected | `get_auth_context` + `can_update_task` | user auth + task policy | creator/chat_admin/super_admin | OK | Keep reminder-rule mutations behind task update policy. | reminder API tests |
| GET | `/api/tasks/{task_id}/reminder-rules` | `backend/app/api/tasks.py` | `list_task_reminder_rules` | protected | `get_auth_context` + `can_view_task` | user auth + task visibility | owner/assignee/observer/chat_admin | OK | Keep task visibility restriction. | reminder API tests |
| PATCH | `/api/tasks/{task_id}/reminder-rules/{rule_id}` | `backend/app/api/tasks.py` | `update_task_reminder_rule` | protected | `get_auth_context` + `can_update_task` | user auth + task policy | creator/chat_admin/super_admin | OK | Keep reminder-rule updates behind task update policy. | reminder API tests |
| DELETE | `/api/tasks/{task_id}/reminder-rules/{rule_id}` | `backend/app/api/tasks.py` | `delete_task_reminder_rule` | protected | `get_auth_context` + `can_update_task` | user auth + task policy | creator/chat_admin/super_admin | OK | Keep reminder-rule deletion behind task update policy. | reminder API tests |
| POST | `/api/tasks/{task_id}/assignees` | `backend/app/api/tasks.py` | `add_task_assignee` | protected | `get_auth_context` + participant role/scope check | user auth + task policy | chat_admin/super_admin | OK | Keep participant changes behind task update policy. | API tests |
| DELETE | `/api/tasks/{task_id}/assignees/{user_id}` | `backend/app/api/tasks.py` | `remove_task_assignee` | protected | `get_auth_context` + participant role/scope check | user auth + task policy | chat_admin/super_admin | OK | Keep participant changes behind task update policy. | API tests |
| POST | `/api/tasks/{task_id}/observers` | `backend/app/api/tasks.py` | `add_task_observer` | protected | `get_auth_context` + participant role/scope check | user auth + task policy | chat_admin/super_admin | OK | Keep observer changes behind task update policy. | API tests |
| DELETE | `/api/tasks/{task_id}/observers/{user_id}` | `backend/app/api/tasks.py` | `remove_task_observer` | protected | `get_auth_context` + participant role/scope check | user auth + task policy | chat_admin/super_admin | OK | Keep observer changes behind task update policy. | API tests |
| POST | `/api/tasks/{task_id}/comments` | `backend/app/api/tasks.py` | `add_task_comment` | protected | `get_auth_context` + actor match + `can_view_task` | user auth + task visibility | visible participant | OK | Keep comment author bound to auth context and task visibility. | API tests |
| GET | `/api/tasks/{task_id}/comments` | `backend/app/api/tasks.py` | `list_task_comments` | protected | `get_auth_context` + `can_view_task` | user auth + task visibility | visible participant | OK | Keep task visibility restriction. | API tests |
| POST | `/api/tasks/{task_id}/files` | `backend/app/api/tasks.py` | `add_task_file` | protected | `get_auth_context` + actor match + `can_view_task` | user auth + task visibility | visible participant | OK | Keep uploader bound to auth context and task visibility. | API tests |
| GET | `/api/tasks/{task_id}/files` | `backend/app/api/tasks.py` | `list_task_files` | protected | `get_auth_context` + `can_view_task` | user auth + task visibility | visible participant | OK | Keep task visibility restriction. | API tests |
| POST | `/api/tasks/{task_id}/responses` | `backend/app/api/tasks.py` | `submit_task_response` | protected | `get_auth_context` + actor match + `can_submit_response` | user auth + `can_submit_response` | assignee | OK | Keep response user bound to auth context and enforce assignee policy. | API tests |
| POST | `/api/tasks/{task_id}/responses/{response_id}/accept` | `backend/app/api/tasks.py` | `accept_task_response` | protected | `get_auth_context` + actor match + `can_accept_task` | user auth + `can_accept_task` | creator/admin | OK | Keep accepter bound to auth context and enforce creator/admin. | API tests |
| POST | `/api/tasks/{task_id}/responses/{response_id}/reject` | `backend/app/api/tasks.py` | `reject_task_response` | protected | `get_auth_context` + actor match + `can_reject_task` | user auth + `can_reject_task` | creator/admin | OK | Keep rejecter bound to auth context and enforce creator/admin. | API tests |
| POST | `/api/task-templates` | `backend/app/api/task_templates.py` | `create_task_template` | protected | `get_auth_context` + service checks | user auth + scope | creator/admin | OK | Keep; add route-level unauth tests if missing. | API tests exist |
| GET | `/api/task-templates` | `backend/app/api/task_templates.py` | `list_task_templates` | protected | `get_auth_context` + service filtering | user auth + scope | creator/chat_admin/super_admin | OK | Keep scoped service filtering. | API tests exist |
| GET | `/api/task-templates/{template_id}` | `backend/app/api/task_templates.py` | `get_task_template` | protected | `get_auth_context` + service checks | user auth + scope | creator/chat_admin/super_admin | OK | Keep. | API tests exist |
| PATCH | `/api/task-templates/{template_id}` | `backend/app/api/task_templates.py` | `update_task_template` | protected | `get_auth_context` + service checks | user auth + scope | creator/chat_admin/super_admin | OK | Keep. | API tests exist |
| DELETE | `/api/task-templates/{template_id}` | `backend/app/api/task_templates.py` | `delete_task_template` | protected | `get_auth_context` + service checks | user auth + scope | creator/chat_admin/super_admin | OK | Keep. | API tests exist |
| POST | `/api/scheduled-tasks` | `backend/app/api/scheduled_tasks.py` | `create_scheduled_task` | protected | `get_auth_context` + service checks | user auth + scope | creator/chat_admin/super_admin | OK | Keep. | API tests exist |
| GET | `/api/scheduled-tasks` | `backend/app/api/scheduled_tasks.py` | `list_scheduled_tasks` | protected | `get_auth_context` + service filtering | user auth + scope | creator/chat_admin/super_admin | OK | Keep scoped service filtering. | API tests exist |
| GET | `/api/scheduled-tasks/{scheduled_task_id}` | `backend/app/api/scheduled_tasks.py` | `get_scheduled_task` | protected | `get_auth_context` + service checks | user auth + scope | creator/chat_admin/super_admin | OK | Keep. | API tests exist |
| PATCH | `/api/scheduled-tasks/{scheduled_task_id}` | `backend/app/api/scheduled_tasks.py` | `update_scheduled_task` | protected | `get_auth_context` + service checks | user auth + scope | creator/chat_admin/super_admin | OK | Keep. | API tests exist |
| DELETE | `/api/scheduled-tasks/{scheduled_task_id}` | `backend/app/api/scheduled_tasks.py` | `delete_scheduled_task` | protected | `get_auth_context` + service checks | user auth + scope | creator/chat_admin/super_admin | OK | Keep. | API tests exist |
| POST | `/api/bot/max/webhook` | `backend/app/api/bot_max.py` | `max_bot_webhook` | webhook | `MAX secret` | official MAX secret | n/a | OK | Keep outside user auth; enforce body size/rate limits at edge. | webhook tests exist |
| POST | `/api/integrations/bitrix24/user-mappings` | `backend/app/api/integrations_bitrix24.py` | `create_bitrix_user_mapping` | integration | `get_auth_context` + service RBAC | user auth + RBAC | chat_admin/super_admin | OK | Keep; ensure production auth source is not dev query. | API tests exist |
| GET | `/api/integrations/bitrix24/user-mappings` | `backend/app/api/integrations_bitrix24.py` | `list_bitrix_user_mappings` | integration | `get_auth_context` + service RBAC | user auth + RBAC | scoped chat_admin/super_admin | OK | Keep. | API tests exist |
| GET | `/api/integrations/bitrix24/user-mappings/{mapping_id}` | `backend/app/api/integrations_bitrix24.py` | `get_bitrix_user_mapping` | integration | `get_auth_context` + service RBAC | user auth + RBAC | scoped chat_admin/super_admin | OK | Keep. | API tests exist |
| PATCH | `/api/integrations/bitrix24/user-mappings/{mapping_id}` | `backend/app/api/integrations_bitrix24.py` | `update_bitrix_user_mapping` | integration | `get_auth_context` + service RBAC | user auth + RBAC | scoped chat_admin/super_admin | OK | Keep. | API tests exist |
| DELETE | `/api/integrations/bitrix24/user-mappings/{mapping_id}` | `backend/app/api/integrations_bitrix24.py` | `delete_bitrix_user_mapping` | integration | `get_auth_context` + service RBAC | user auth + RBAC | scoped chat_admin/super_admin | OK | Keep. | API tests exist |
| POST | `/api/integrations/bitrix24/tasks/{task_id}/sync` | `backend/app/api/integrations_bitrix24.py` | `sync_bitrix_task_create` | integration | `get_auth_context` + `can_run_bitrix_sync` | user auth + task policy | creator/chat_admin/super_admin | OK | Keep. | API tests exist |
| GET | `/api/integrations/bitrix24/tasks/{task_id}/status` | `backend/app/api/integrations_bitrix24.py` | `get_bitrix_task_sync_status` | integration | `get_auth_context` + `can_view_task` | user auth + task policy | visible participant/admin | OK | Keep. | API tests exist |
| POST | `/api/integrations/bitrix24/retry-failed` | `backend/app/api/integrations_bitrix24.py` | `retry_failed_bitrix_sync` | integration | `get_auth_context` + role check | user auth + RBAC | chat_admin/super_admin | OK | Keep; consider `super_admin` only for broad retry. | API tests exist |

## P0 Findings

### Resolved. Core API route-level auth is committed

Covered routes:

- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/inbox/summary`
- `GET /api/tasks/{task_id}`
- `PATCH /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/cancel`
- task reminder-rule routes
- task participant/comment/file/response routes
- organization CRUD routes
- chat CRUD/member/reminder-rule routes
- user CRUD routes

Current status:

- Core `tasks`, `users`, `chats`, and `organizations` routers require `get_auth_context`.
- Unauthenticated regression tests expect `401`.
- `/api/health` remains public.
- MAX webhook remains outside normal user auth and continues to use MAX secret validation.

### P1. Task API policy coverage needs continued hardening

Affected routes:

- task create/list/detail/update/cancel;
- task participants;
- task comments/files;
- task responses and response acceptance/rejection;
- task reminder rules;
- inbox summary.

Why this still matters:

- API routes now apply baseline task visibility/update checks and bind actor fields to `AuthContext` for the sensitive write paths.
- Some checks still live at the API layer rather than deeper service boundaries.
- Further hardening should keep internal callers and future routes from bypassing the same policy rules.

Next hardening:

- Move or duplicate critical task policy enforcement into service boundaries where appropriate.
- Keep `PolicyService.can_view_task`, `can_update_task`, `can_submit_response`, `can_accept_task`, and `can_reject_task` covered by regression tests.
- Keep actor fields such as comment author, file uploader, response user, and accepter bound to `AuthContext.user_id` unless a `super_admin` override is explicitly allowed.

### P1. Users, chats, and organizations need deeper membership policy

Affected routes:

- organization create/list/detail/update;
- chat create/list/detail/update/member management;
- user create/list/detail/update.

Why this still matters:

- API routes now include baseline super-admin, admin-role, self, organization-scope, and chat-scope checks.
- The current scope model still relies on the dev-auth headers until production WebApp auth is implemented.
- Future member sync and richer role semantics should tighten "same organization/chat" visibility.

Next hardening:

- Expand membership-aware authorization beyond header scope.
- Restrict external identifier updates such as MAX ids behind admin/system-only flows.
- Add more negative tests for cross-organization and cross-chat access.
- Decide and implement an explicit admin sync/assignment flow for MAX group admins. Current bot RBAC uses internal `ChatMember.role`; a MAX group admin who is still stored as `member` is intentionally treated as `member` until promoted in `Дьяк`.

### Resolved. Frontend WebApp bootstrap uses MAX session auth

Affected surface:

- WebApp pages under `/tasks`, `/dashboard`, `/group-assignments`, `/settings`.
- API client headers `X-User-Id`, `X-Organization-Id`, `X-Chat-Id`, `X-Roles`.

Current status:

- Frontend now restores session through `GET /api/auth/me`.
- If no session exists, frontend reads MAX `initData` and calls `POST /api/auth/max-webapp/session`.
- API calls use same-origin cookies through `credentials: "include"`.
- Query/dev header auth remains only for Vite dev mode.
- `get_auth_context` accepts dev headers only in local/test, or in dev/development when dev auth is explicitly enabled.
- The backend now fails fast if `APP_ENV=production` and `DEV_AUTH_ENABLED=true`.
- Live MAX validation passed after switching WebApp buttons to `https://max.ru/<bot_username>?startapp=home` deep links and loading the MAX WebApp bridge.
- Direct browser/API access without a session returns `401`, and `?user_id=...` does not authenticate the user.
- WebApp inbox summary no longer sends `user_id` in the query; the backend uses the session user by default.

Remaining work:

- Keep `DEV_AUTH_ENABLED=false` in production; backend startup fails if it is set to `true`.
- Add automated frontend regression coverage for direct browser open, MAX-opened WebApp, and session restore.

## Webhook Exceptions

MAX webhook must not use normal user auth.

Current behavior:

- Endpoint: `POST /api/bot/max/webhook`.
- Current auth: `verify_max_webhook_access`.
- Official header: `X-Max-Bot-Api-Secret`.
- Legacy/internal header: `X-Max-Webhook-Secret`.
- Secret comparison uses constant-time comparison.
- Missing/invalid secret returns `401`.
- Disabled webhook returns `404`.
- Production with enabled webhook and missing configured secret returns `503`.

Required hardening:

- Keep current webhook tests.
- Add edge/body-size limits and rate limiting before broader exposure.
- Continue avoiding raw payload logs unless explicitly enabled and sanitized.

## Public Exceptions

Allowed public endpoints:

- `GET /api/health`.
- `HEAD /api/health`.

Production policy decision needed:

- `GET/HEAD /docs`.
- `GET/HEAD /openapi.json`.
- `GET/HEAD /redoc`.
- `GET/HEAD /docs/oauth2-redirect`.

Recommendation:

- Keep health public.
- Restrict or disable docs/openapi/redoc for non-internal production use, or explicitly accept the information-disclosure risk during the internal pilot.

## WebApp Auth Risk

Current WebApp behavior:

- `webapp/src/auth/AuthContext.tsx` first restores an existing WebApp session through `/api/auth/me`.
- If no session exists, it reads MAX `initData` and exchanges it through `/api/auth/max-webapp/session`.
- `webapp/src/api/client.ts` sends `credentials: "include"` on API calls.
- Query-derived dev auth is gated to Vite dev mode and is not used by production builds.
- WebApp deep-link buttons use `https://max.ru/<bot_username>?startapp=...` when `MAX_BOT_USERNAME` is configured; plain `https://maxsecretary.ru` remains a fallback and opens outside MAX without initData.

Risk status:

- Direct browser open without a valid session or MAX `initData` shows an unauthorized state and does not mount data pages.
- If `DEV_AUTH_ENABLED=true` in production, the backend refuses to start.
- Live MAX validation confirmed `POST /api/auth/max-webapp/session -> 200`, `GET /api/auth/me -> 200`, and protected pages load from the session.
- Query `user_id` is ignored as an auth source and returns `401` without a valid session.

Required future hardening:

- Add automated frontend tests for direct browser open, MAX-opened WebApp, and session restore.
- Confirm the exact MAX initData algorithm against official MAX documentation if/when it is published; current implementation is reference-confirmed.
- Consider Origin/Referer checks for session-authenticated state-changing requests.

## Recommended Fix Plan

Done. Commit route-level auth for core APIs.

- Tasks, users, chats, and organizations now require committed `get_auth_context`.
- Regression tests cover no headers -> `401` on the core routes.

P1. Continue task API service-boundary policy hardening.

- Keep `AuthContext` checks on task list/detail/update/cancel/participants/comments/files/responses/reminders.
- Move critical checks deeper into services where future internal callers may bypass route handlers.
- Add more tests: wrong user -> `403`; creator/assignee/observer/chat_admin/super_admin -> allowed as appropriate.

P1. Continue users/chats/organizations scope/RBAC hardening.

- Keep route-level role/scope checks.
- Add membership-aware policy that does not depend on browser-supplied dev auth scope.
- Protect membership and external-id mutations with deeper service tests.

Done. Keep `DEV_AUTH_ENABLED` production guard.

- Production default must remain false.
- Backend settings validation rejects `APP_ENV=production` with `DEV_AUTH_ENABLED=true`.

Done. Implement backend MAX WebApp init-data auth.

- Backend verifies reference-confirmed MAX initData signatures.
- Backend issues signed httpOnly WebApp session cookies.
- `get_auth_context` reads WebApp session cookies before dev headers.
- Query `user_id` is still not a production identity source.

Done. Implement frontend MAX WebApp auth bootstrap.

- Sends `window.WebApp.initData` to `/api/auth/max-webapp/session`.
- Uses `GET /api/auth/me` to restore sessions.
- Removes production query/dev header identity flow from the WebApp.
- Shows an unauthorized direct-open state instead of business data.
- Live MAX validation passed after loading the MAX WebApp bridge and opening through MAX deep links.
- User-scoped WebApp calls derive identity from the session by default; `GET /api/tasks/inbox/summary` no longer needs a `user_id` query.

P1. Decide OpenAPI/docs production policy.

- Close, restrict, or explicitly accept public docs for pilot.

P1. Add route-level auth regression tests.

- Unauthenticated -> `401`.
- Authenticated wrong role/scope -> `403`.
- Valid role/scope -> allowed.
- MAX webhook missing/invalid secret -> `401`.
- Health remains public.

## Suggested Tests

Route-auth regression tests:

- `GET /api/tasks` without headers -> `401`.
- `POST /api/tasks` without headers -> `401`.
- `GET /api/users` without headers -> `401`.
- `GET /api/chats` without headers -> `401`.
- `GET /api/organizations` without headers -> `401`.

Task policy tests:

- User who is not creator/assignee/observer/chat_admin cannot `GET /api/tasks/{task_id}`.
- User who is not creator/chat_admin/super_admin cannot `PATCH /api/tasks/{task_id}`.
- Non-assignee cannot `POST /api/tasks/{task_id}/responses`.
- Non-creator cannot accept/reject a response.
- Comment/file actor IDs are taken from auth context, not request body.

Scope tests:

- Ordinary user cannot list all organizations.
- Ordinary user cannot list all users.
- Chat member can see own chat only.
- Chat admin can manage members only inside allowed chat/organization scope.

Webhook tests:

- MAX webhook missing official secret -> `401`.
- MAX webhook invalid official secret -> `401`.
- MAX webhook valid official secret -> accepted.
- Webhook disabled -> `404`.

Public tests:

- `GET /api/health` -> `200` without auth.
- `HEAD /api/health` -> `200` without auth.

WebApp auth tests:

- `POST /api/auth/max-webapp/session` with valid synthetic initData -> `200` and session cookie.
- Invalid or expired initData -> `401`.
- `GET /api/auth/me` without session -> `401`.
- `GET /api/auth/me?user_id=<uuid>` without session -> `401`.
- `GET /api/tasks/inbox/summary` uses the session user when `user_id` is omitted.
- Production settings reject `APP_ENV=production` with `DEV_AUTH_ENABLED=true`.
