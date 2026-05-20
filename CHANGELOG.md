# Changelog

## Unreleased

## 1.0.1 — 2026-05-20

### Added

- Added documentation audit for v1.0.0.
- Added 1.0.1 hardening backlog.
- Added project roadmap documentation.
- Added release verification reports for API routes, backup/restore and test inventory.
- Added hardening verification report.
- Filled task lifecycle documentation.
- Filled roles and permissions documentation.
- Updated MAX integration guide.

### Changed

- Aligned offline bundle defaults with v1.0.x.
- Synchronized offline Docker Compose healthchecks with production compose.
- Updated offline deployment documentation for the v1.0.x release line.
- Updated README and deployment documentation for the pilot release state.

### Infrastructure

- Offline compose now renders backend and WebApp images using RELEASE_VERSION=1.0.0 by default.
- Production and offline compose config checks were verified on VPS.
- Added/updated ignore rules for editor lock and temporary files.

### Security

- Rechecked documentation and hardening diffs for secrets.
- Confirmed that temporary/editor files are ignored.
- Confirmed that protected production endpoints keep secure behavior when dev auth is disabled.

### Notes

- No application feature changes.
- v1.0.1 is a hardening and documentation cleanup release after v1.0.0 pilot stable.

## 1.0.0 — 2026-05-19

### Added

- Pilot scope documentation.
- Production deployment checklist.
- Pilot acceptance scenarios.
- Known limitations document.
- Operator guide.
- Backup and restore scripts.
- Release smoke script.
- Security checklist for pilot deployment.

### Changed

- Project is now documented as pilot-ready baseline.

### Security

- Added operational security checklist for deployment.

### Operations

- Added backup/restore guidance and scripts.
- Added release smoke procedure.

### Limitations

- 1.0.0 is a pilot-stable version, not full production certification.

## 0.9.0 — 2026-05-19

### Added

- Offline delivery policy documentation.
- Python wheelhouse build script.
- Docker image save/load scripts.
- Offline Docker Compose file.
- Release manifest and SHA256 checksum tooling.
- Offline bundle build script.
- Closed contour installation guide.
- Manual dependency update policy.

### Changed

- Deployment documentation now includes closed-contour installation path.

### Security

- Offline bundle avoids downloading dependencies on production servers.
- Added checksum generation for release artifacts.

### Limitations

- Offline bundle build requires Docker on the build machine.
- External MAX/Bitrix24 integrations remain disabled unless explicitly configured in the target contour.

## 0.8.0 — 2026-05-19

### Added

- RBAC policy documentation.
- Backend permission enums and policy service.
- AuthContext dependency for protected endpoints.
- Dev auth mode through request headers.
- RBAC protection for Bitrix24 sync and mapping endpoints.
- WebApp AuthContext preparation.
- Dev auth warning in WebApp.
- WebApp documentation for future MAX auth integration.

### Security

- Started replacing query-based user_id usage with explicit auth context.
- Bitrix24 sync and mapping endpoints are protected by RBAC.

### Limitations

- Full MAX WebApp authentication is not implemented yet.
- Dev auth headers are temporary and must be disabled in production unless explicitly enabled.

## 0.7.0 — 2026-05-19

### Added

- Added Bitrix24 integration settings.
- Added IntegrationAccount model.
- Added BitrixTaskLink model.
- Added BitrixUserMapping model and CRUD API.
- Added Bitrix24 REST client adapter.
- Added Bitrix24 task mapper.
- Added Bitrix24 manual sync service.
- Added manual Bitrix24 task sync endpoint.
- Added Bitrix24 sync status endpoint.
- Added Bitrix24 retry failed endpoint.
- Added Bitrix24 sync status tracking through BitrixTaskLink.
- Added Bitrix24 connector smoke test in disabled mode.
- Added Bitrix24 sync status card in WebApp task details.
- Added manual Bitrix24 sync action in WebApp task details.

### Changed

- Bitrix24 integration remains manually triggered in MVP to avoid duplicate external tasks.
- WebApp task details page now displays Bitrix24 sync state.
- Bitrix24 sync status is intentionally limited to task details page in MVP.

### Security

- Bitrix24 webhook URL is treated as secret and must not be logged or committed.
- Bitrix24 sync errors are stored without exposing webhook URLs or tokens.
- Real Bitrix24 HTTP requests are disabled unless BITRIX24_ENABLED=true and webhook URL is configured.

### Limitations

- MVP supports one-way sync: max_secretary -> Bitrix24.
- Automatic Bitrix24 sync triggers are not implemented yet.
- Two-way Bitrix24 sync is not implemented.
- Bitrix24 task import is not implemented.
- Bitrix24 task deletion is not performed.
- Bitrix24 sync status is shown only on task details page.
- Task list Bitrix24 sync column requires a future batch status endpoint.
- Real Bitrix24 task comments/chat messages require separate API validation.

## 0.6.0 — 2026-05-19

### Added

- MAX Bot API client adapter.
- Switchable MaxSender implementation.
- MAX webhook event normalization layer.
- MAX webhook secret validation.
- MAX bot setup documentation.
- MAX sender smoke test.

### Changed

- MaxSender can now run in placeholder mode or real MAX API mode.
- Bot webhook endpoint supports both normalized test events and MAX-like raw events.

### Security

- Added optional webhook secret validation.
- Prevented MAX token logging.

### Fixed

- Added WebApp `/dashboard` route alias so direct Dashboard URLs render the dashboard page.

### Limitations

- Real MAX task cards/buttons are not implemented yet.
- send_task_card currently sends text representation.
- User matching remains temporary for MVP.

## 0.5.0 — 2026-05-19

### Added

- WebApp MVP based on React, TypeScript, Vite and Ant Design.
- Dashboard with inbox summary from multiple chats.
- Tasks page with filters.
- Task creation form.
- Task details page.
- Comments UI.
- File metadata UI.
- Assignee response UI.
- Requester accept/reject UI.
- WebApp Dockerfile.
- WebApp production Docker Compose service.
- WebApp smoke test.
- WebApp MVP documentation.

### Changed

- Nginx now serves WebApp frontend and proxies API requests to backend.
- Deploy workflow restarts nginx after compose updates to reload routing config.
- Health, docs and OpenAPI routes support HEAD checks used by smoke tests.

### Limitations

- MAX WebApp authentication is not implemented yet.
- user_id is temporarily passed through query parameters.
- File upload stores metadata only.

## 0.4.0 — 2026-05-19

### Added

- Reminder service for task deadlines.
- Reminder rules API for tasks and chats.
- Overdue task detection.
- Waiting acceptance reminder flow.
- No-response-after-deadline reminder flow.
- Daily summary builder.
- Reminder worker using scheduler.
- Logging MaxSender for reminder notifications.
- Reminder smoke test.
- Reminder product documentation.

### Changed

- Worker container now runs reminder scheduler when enabled.

### Limitations

- Real MAX notification sending is not enabled yet.
- Reminder delivery is logged through MaxSender placeholder.

## 0.3.0 — 2026-05-18

### Added

- Added MVP API smoke test script and documentation.
- MAX Bot webhook adapter.
- Normalized bot event schema.
- Bot command parser.
- Task creation command.
- Task list command.
- My tasks command.
- Assignee response command.
- Requester accept/reject commands.
- Bot command documentation.
- Bot webhook smoke test.

### Changed

- Connected bot command layer to backend task service.

### Fixed

- Fixed async SQLAlchemy session dependency used by API routes.

### Limitations

- Real MAX Bot API sender is not enabled yet.
- MVP user matching by display_name is temporary.

## 0.2.0 — 2026-05-18

### Added

- Backend MVP data model.
- Organizations API.
- Users API.
- Chats and chat members API.
- Tasks API with multiple assignees and observers.
- Task comments API.
- Task files metadata API.
- Assignee response workflow.
- Requester acceptance and rejection workflow.
- Inbox summary API.
- Alembic migrations for MVP schema.

### Changed

- Extended backend structure for modular monolith architecture.

### Infrastructure

- Verified Docker Compose compatibility with backend MVP.

## 0.1.2 — 2026-05-18

### Changed

- Hardened nginx fallback behavior: unknown routes now return 404.

### Added

- Added VPS runtime tuning documentation.
- Added Redis vm.overcommit_memory guidance.
- Added documentation for checking unexpected open ports.

### Infrastructure

- Documented Redis runtime tuning for production VPS.
- Documented investigation steps for unexpected host ports.

## 0.1.1 — 2026-05-18

### Added

- Deployment documentation for VPS.
- Production Docker Compose setup.
- Nginx reverse proxy configuration.
- Backend Dockerfile.
- Environment example for production.
- GitHub Actions Backend CI workflow.
- GitHub Actions manual Deploy to VPS workflow.
- Manual deploy instructions.
- Closed contour offline deployment notes.

### Security

- SSH key based deployment documented.
- Deploy user usage documented.
- Secrets and .env excluded from repository.

### Infrastructure

- Added initial VPS deployment path using Docker Compose.

0.1.0 — initial documentation structure.
