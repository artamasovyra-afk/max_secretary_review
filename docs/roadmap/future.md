# Future Roadmap

This document captures post-pilot direction after `v1.0.x`.

## Authentication And Access Control

- Implement full MAX WebApp authentication.
- Replace temporary dev auth/query user context.
- Expand RBAC enforcement across task, chat, organization and integration endpoints.
- Add production-grade session/user identity handling.

## MAX Integration

- Validate real MAX webhook payloads on a staging environment.
- Support task creation from reply messages if MAX payloads provide reliable source message context.
- Add native task cards and inline actions when UX and API details are confirmed.
- Improve mapping between external MAX users/chats and local entities.

## Bitrix24 Integration

- Add optional automatic sync triggers after duplicate-protection rules are finalized.
- Add safe update/status sync flows.
- Validate comments/messages sync with real Bitrix24 API behavior.
- Consider import and two-way sync only after pilot feedback.
- Add external Bitrix24 task URL display when safe URL construction is defined.

## Files

- Add real file storage.
- Add upload/download access control.
- Add antivirus or content checks if required by deployment contour.
- Preserve metadata-only mode for closed-contour deployments where file storage is external.

## WebApp

- Improve task filtering and saved views.
- Add role-aware UI states.
- Add richer Dashboard summaries.
- Add accessibility and keyboard-flow polish.
- Add browser-level acceptance tests.

## Operations

- Add regular backup scheduling.
- Add restore drills on test environments.
- Add structured logs and metrics.
- Add alerting and dashboards.
- Improve deploy workflow with migrations and smoke checks.
- Expand CI to cover WebApp build, compose config, shell scripts and release gate.

## Closed Contour

- Validate offline bundle in a real closed-contour environment.
- Add internal registry workflows if needed.
- Add internal Python/npm registry guidance if needed.
- Add formal dependency update and approval records.
- Add checksum verification to operator runbooks.

## Product Discovery

- Pilot feedback should decide priority for:
  - automatic reminders configuration UX;
  - task templates;
  - delegation and substitution;
  - chat-level policies;
  - cross-organization administration;
  - reporting and exports.
