# Task Numbering

## Summary

Each task has a short user-facing number in addition to its internal UUID.

- Database field: `tasks.task_number`
- API fields: `task_number` and `task_ref`
- User format: `#1042`
- Internal UUID routes remain unchanged.

## Numbering Strategy

Task numbers are unique within an organization:

```text
UNIQUE (organization_id, task_number)
```

This keeps numbers short for users while allowing independent organizations to have their own `#1`, `#2`, and so on.

The current generator uses `max(task_number) + 1` inside the task creation transaction. The database unique constraint protects the invariant. If high-concurrency task creation becomes common, this can be replaced with an organization counter table without changing the public API shape.

## Migration Behavior

The migration backfills existing tasks deterministically:

1. Group tasks by `organization_id`.
2. Order each group by `created_at ASC, id ASC`.
3. Assign `1, 2, 3, ...` within each organization.
4. Mark `task_number` as not null.
5. Add the organization-scoped uniqueness constraint.

## API Behavior

Task list/detail responses include:

```json
{
  "id": "internal-uuid",
  "task_number": 1042,
  "task_ref": "#1042"
}
```

The UUID remains the canonical internal identifier for existing endpoints:

- `GET /api/tasks/{task_id}`
- `PATCH /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/cancel`
- task comments, files, responses, reminders, and callbacks

## Search

Task list search supports user-facing references:

- `1042`
- `#1042`
- `T-1042`
- `t-1042`

The list endpoint also accepts an explicit `task_number` query parameter.

Text search remains available for non-reference search strings and checks task title/description.

## Bot And WebApp UX

Bot responses and WebApp task lists should show `task_ref` whenever a user needs to recognize a task. UUIDs can still be shown in technical detail screens or copied for support/debugging.

Future command examples:

- `/отчет #1042`
- `/пинг #1042`
- `/статус #1042`
- plain `#1042` lookup

## Notes

Bitrix24 IDs and MAX message IDs remain separate external identifiers. `task_number` is a local user-facing reference, not an integration ID.
