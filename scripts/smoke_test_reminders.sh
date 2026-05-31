#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
WORKER_SERVICE="${WORKER_SERVICE:-worker}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%d%H%M%S)}"
PAST_DEADLINE="${PAST_DEADLINE:-2000-01-01T00:00:00Z}"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

log() {
    printf '\n== %s ==\n' "$1"
}

api() {
    local method="$1"
    local path="$2"
    local expected_status="$3"
    local payload="${4:-}"
    local response_file
    local status_code

    response_file="$(mktemp)"
    if [[ -n "$payload" ]]; then
        status_code="$(
            curl -sS \
                -o "$response_file" \
                -w '%{http_code}' \
                -X "$method" \
                "$BASE_URL$path" \
                -H 'Content-Type: application/json' \
                --data "$payload"
        )"
    else
        status_code="$(
            curl -sS \
                -o "$response_file" \
                -w '%{http_code}' \
                -X "$method" \
                "$BASE_URL$path"
        )"
    fi

    if [[ "$status_code" != "$expected_status" ]]; then
        echo "HTTP $method $path failed: expected $expected_status, got $status_code" >&2
        echo "Response body:" >&2
        cat "$response_file" >&2
        rm -f "$response_file"
        exit 1
    fi

    cat "$response_file"
    rm -f "$response_file"
}

assert_json() {
    local json="$1"
    local filter="$2"
    local message="$3"

    if ! jq -e "$filter" >/dev/null <<<"$json"; then
        echo "Assertion failed: $message" >&2
        echo "$json" | jq . >&2
        exit 1
    fi
}

run_worker_python() {
    docker compose -f "$COMPOSE_FILE" exec -T "$WORKER_SERVICE" python -
}

create_user() {
    local display_name="$1"
    local username="$2"
    local payload

    payload="$(jq -n \
        --arg display_name "$display_name" \
        --arg username "$username" \
        '{display_name: $display_name, username: $username}')"
    api POST /api/users 201 "$payload"
}

add_chat_member() {
    local chat_id="$1"
    local user_id="$2"
    local role="$3"
    local payload

    payload="$(jq -n \
        --arg user_id "$user_id" \
        --arg role "$role" \
        '{user_id: $user_id, role: $role, is_active: true}')"
    api POST "/api/chats/$chat_id/members" 201 "$payload" >/dev/null
}

require_command curl
require_command docker
require_command jq

log "Target"
echo "BASE_URL=$BASE_URL"
echo "COMPOSE_FILE=$COMPOSE_FILE"

log "Healthcheck"
HEALTH="$(api GET /api/health 200)"
assert_json "$HEALTH" '.status == "ok"' "health endpoint must return status=ok"

log "Create organization"
ORG_PAYLOAD="$(jq -n \
    --arg name "Smoke Reminders Org $RUN_ID" \
    '{name: $name, status: "active"}')"
ORG="$(api POST /api/organizations 201 "$ORG_PAYLOAD")"
ORG_ID="$(jq -r '.id' <<<"$ORG")"
echo "organization_id=$ORG_ID"

log "Create users"
REQUESTER="$(create_user "Smoke Reminders Requester $RUN_ID" "smoke_reminders_requester_$RUN_ID")"
ASSIGNEE="$(create_user "Smoke Reminders Assignee $RUN_ID" "smoke_reminders_assignee_$RUN_ID")"
REQUESTER_ID="$(jq -r '.id' <<<"$REQUESTER")"
ASSIGNEE_ID="$(jq -r '.id' <<<"$ASSIGNEE")"
echo "requester_id=$REQUESTER_ID"
echo "assignee_id=$ASSIGNEE_ID"

log "Create chat"
CHAT_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg title "Smoke Reminders Chat $RUN_ID" \
    --arg max_chat_id "smoke-reminders-chat-$RUN_ID" \
    '{
        organization_id: $organization_id,
        max_chat_id: $max_chat_id,
        title: $title,
        type: "group",
        settings: {smoke_test: true, source: "reminders"}
    }')"
CHAT="$(api POST /api/chats 201 "$CHAT_PAYLOAD")"
CHAT_ID="$(jq -r '.id' <<<"$CHAT")"
echo "chat_id=$CHAT_ID"

log "Add users to chat"
add_chat_member "" "" chat_admin
add_chat_member "$CHAT_ID" "$ASSIGNEE_ID" member
echo "members_added=2"

log "Create overdue candidate task"
OVERDUE_TASK_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg chat_id "$CHAT_ID" \
    --arg title "Smoke Overdue Task $RUN_ID" \
    --arg created_by_user_id "$REQUESTER_ID" \
    --arg assignee_id "$ASSIGNEE_ID" \
    --arg deadline_at "$PAST_DEADLINE" \
    '{
        organization_id: $organization_id,
        chat_id: $chat_id,
        title: $title,
        description: "Smoke test task for reminder overdue job",
        created_by_user_id: $created_by_user_id,
        deadline_at: $deadline_at,
        priority: "normal",
        completion_rule: "any_assignee_response",
        assignee_ids: [$assignee_id],
        observer_ids: []
    }')"
OVERDUE_TASK="$(api POST /api/tasks 201 "$OVERDUE_TASK_PAYLOAD")"
OVERDUE_TASK_ID="$(jq -r '.id' <<<"$OVERDUE_TASK")"
assert_json "$OVERDUE_TASK" '.status == "new"' "overdue candidate must start with status=new"
echo "overdue_task_id=$OVERDUE_TASK_ID"

log "Run mark_overdue_tasks in worker container"
MARK_RESULT="$(
    run_worker_python <<'PY'
import asyncio
import json
from dataclasses import asdict

from app.modules.reminders.jobs import mark_overdue_tasks

print(json.dumps(asdict(asyncio.run(mark_overdue_tasks())), sort_keys=True))
PY
)"
echo "$MARK_RESULT" | jq .
assert_json "$MARK_RESULT" '.tasks_marked_overdue >= 1' "mark_overdue_tasks must mark at least one task"

log "Verify task became overdue"
OVERDUE_TASK_AFTER="$(api GET "/api/tasks/$OVERDUE_TASK_ID" 200)"
assert_json "$OVERDUE_TASK_AFTER" '.status == "overdue"' "past-deadline task must become overdue"
echo "overdue_task_status=$(jq -r '.status' <<<"$OVERDUE_TASK_AFTER")"

log "Create waiting_acceptance task"
WAITING_TASK_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg chat_id "$CHAT_ID" \
    --arg title "Smoke Waiting Acceptance Task $RUN_ID" \
    --arg created_by_user_id "$REQUESTER_ID" \
    --arg assignee_id "$ASSIGNEE_ID" \
    '{
        organization_id: $organization_id,
        chat_id: $chat_id,
        title: $title,
        description: "Smoke test task for waiting_acceptance reminder",
        created_by_user_id: $created_by_user_id,
        priority: "normal",
        completion_rule: "any_assignee_response",
        assignee_ids: [$assignee_id],
        observer_ids: []
    }')"
WAITING_TASK="$(api POST /api/tasks 201 "$WAITING_TASK_PAYLOAD")"
WAITING_TASK_ID="$(jq -r '.id' <<<"$WAITING_TASK")"
WAITING_PATCH_PAYLOAD="$(jq -n '{status: "waiting_acceptance"}')"
WAITING_TASK_UPDATED="$(api PATCH "/api/tasks/$WAITING_TASK_ID" 200 "$WAITING_PATCH_PAYLOAD")"
assert_json "$WAITING_TASK_UPDATED" '.status == "waiting_acceptance"' "task must be moved to waiting_acceptance"
echo "waiting_acceptance_task_id=$WAITING_TASK_ID"

log "Run run_due_reminders in worker container"
DUE_RESULT="$(
    run_worker_python <<'PY'
import asyncio
import json
from dataclasses import asdict

from app.modules.reminders.jobs import run_due_reminders

print(json.dumps(asdict(asyncio.run(run_due_reminders())), sort_keys=True))
PY
)"
echo "$DUE_RESULT" | jq .
assert_json "$DUE_RESULT" '.tasks_processed >= 1' "run_due_reminders must process at least one reminder task"

MAX_SENDER_ENABLED="$(
    run_worker_python <<'PY'
from app.core.config import get_settings

print(str(get_settings().max_sender_enabled).lower())
PY
)"
echo "max_sender_enabled=$MAX_SENDER_ENABLED"

if [[ "$MAX_SENDER_ENABLED" == "true" ]]; then
    assert_json "$DUE_RESULT" '.reminders_sent >= 1' "run_due_reminders must send at least one reminder when MAX sender is enabled"
else
    assert_json "$DUE_RESULT" '.reminders_sent == 0' "run_due_reminders must not count skipped reminders as sent when MAX sender is disabled"
    log "Verify sender-disabled delivery is recorded safely"
    SENDER_DISABLED_DELIVERY_COUNT="$(
        run_worker_python <<PY
import asyncio
from uuid import UUID

from sqlalchemy import text

from app.db.session import get_session_factory

task_id = UUID("$WAITING_TASK_ID")


async def main() -> None:
    async with get_session_factory()() as session:
        count = await session.scalar(
            text(
                """
                select count(*)
                from notification_deliveries
                where task_id = :task_id
                  and status = 'skipped'
                  and error_code = 'sender_disabled'
                  and reminder_type = 'waiting_acceptance'
                """
            ),
            {"task_id": task_id},
        )
        print(count or 0)


asyncio.run(main())
PY
    )"
    echo "sender_disabled_delivery_count=$SENDER_DISABLED_DELIVERY_COUNT"
    if [[ "$SENDER_DISABLED_DELIVERY_COUNT" -lt 1 ]]; then
        echo "Assertion failed: run_due_reminders must record sender_disabled delivery when MAX sender is disabled" >&2
        exit 1
    fi
fi

log "Verify waiting_acceptance task is still visible through API"
WAITING_TASK_AFTER="$(api GET "/api/tasks/$WAITING_TASK_ID" 200)"
assert_json "$WAITING_TASK_AFTER" '.status == "waiting_acceptance"' "due reminder job must not change waiting_acceptance status"

log "Reminder smoke test completed"
echo "ok=true"
