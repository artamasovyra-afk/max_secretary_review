#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%d%H%M%S)}"
AUTH_HEADER_ARGS=(-H "X-Smoke-Test: max_secretary")

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
                "${AUTH_HEADER_ARGS[@]}" \
                -H 'Content-Type: application/json' \
                --data "$payload"
        )"
    else
        status_code="$(
            curl -sS \
                -o "$response_file" \
                -w '%{http_code}' \
                -X "$method" \
                "${AUTH_HEADER_ARGS[@]}" \
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

require_command curl
require_command jq

log "Target"
echo "BASE_URL=$BASE_URL"

log "Healthcheck"
HEALTH="$(api GET /api/health 200)"
assert_json "$HEALTH" '.status == "ok"' "health endpoint must return status=ok"

log "Create organization"
ORG_PAYLOAD="$(jq -n \
    --arg name "Bitrix Connector Smoke Org $RUN_ID" \
    '{name: $name, status: "active"}')"
ORG="$(api POST /api/organizations 201 "$ORG_PAYLOAD")"
ORG_ID="$(jq -r '.id' <<<"$ORG")"
echo "organization_id=$ORG_ID"

log "Create requester"
REQUESTER_PAYLOAD="$(jq -n \
    --arg display_name "Bitrix Smoke Requester $RUN_ID" \
    --arg username "bitrix_smoke_requester_$RUN_ID" \
    '{display_name: $display_name, username: $username}')"
REQUESTER="$(api POST /api/users 201 "$REQUESTER_PAYLOAD")"
REQUESTER_ID="$(jq -r '.id' <<<"$REQUESTER")"
echo "requester_id=$REQUESTER_ID"
AUTH_HEADER_ARGS=(
    -H "X-Smoke-Test: max_secretary"
    -H "X-User-Id: $REQUESTER_ID"
    -H "X-Organization-Id: $ORG_ID"
    -H "X-Roles: chat_admin"
)

log "Create assignee"
ASSIGNEE_PAYLOAD="$(jq -n \
    --arg display_name "Bitrix Smoke Assignee $RUN_ID" \
    --arg username "bitrix_smoke_assignee_$RUN_ID" \
    '{display_name: $display_name, username: $username}')"
ASSIGNEE="$(api POST /api/users 201 "$ASSIGNEE_PAYLOAD")"
ASSIGNEE_ID="$(jq -r '.id' <<<"$ASSIGNEE")"
echo "assignee_id=$ASSIGNEE_ID"

log "Create Bitrix24 user mapping for assignee"
MAPPING_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg user_id "$ASSIGNEE_ID" \
    '{
        organization_id: $organization_id,
        user_id: $user_id,
        bitrix_user_id: "123",
        match_source: "manual",
        is_active: true
    }')"
MAPPING_RESPONSE_FILE="$(mktemp)"
MAPPING_STATUS_CODE="$(
    curl -sS \
        -o "$MAPPING_RESPONSE_FILE" \
        -w '%{http_code}' \
        -X POST \
        "$BASE_URL/api/integrations/bitrix24/user-mappings" \
        "${AUTH_HEADER_ARGS[@]}" \
        -H 'Content-Type: application/json' \
        --data "$MAPPING_PAYLOAD"
)"
MAPPING="$(cat "$MAPPING_RESPONSE_FILE")"
rm -f "$MAPPING_RESPONSE_FILE"

if [[ "$MAPPING_STATUS_CODE" == "401" ]] \
    && jq -e '.detail == "Header auth is disabled"' >/dev/null <<<"$MAPPING"; then
    log "Summary"
    echo "bitrix24_connector_smoke=skipped_auth_disabled"
    echo "reason=dev header auth is disabled on this environment"
    echo "organization_id=$ORG_ID"
    echo "requester_id=$REQUESTER_ID"
    echo "assignee_id=$ASSIGNEE_ID"
    exit 0
fi

if [[ "$MAPPING_STATUS_CODE" != "201" ]]; then
    echo "HTTP POST /api/integrations/bitrix24/user-mappings failed: expected 201 or auth-disabled 401, got $MAPPING_STATUS_CODE" >&2
    echo "Response body:" >&2
    echo "$MAPPING" >&2
    exit 1
fi

MAPPING_ID="$(jq -r '.id' <<<"$MAPPING")"
assert_json "$MAPPING" '.is_active == true and .bitrix_user_id == "123"' \
    "assignee mapping must be active"
echo "mapping_id=$MAPPING_ID"

log "Create chat"
CHAT_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg title "Bitrix Connector Smoke Chat $RUN_ID" \
    --arg max_chat_id "bitrix-connector-smoke-chat-$RUN_ID" \
    '{
        organization_id: $organization_id,
        max_chat_id: $max_chat_id,
        title: $title,
        type: "group",
        settings: {smoke_test: true}
    }')"
CHAT="$(api POST /api/chats 201 "$CHAT_PAYLOAD")"
CHAT_ID="$(jq -r '.id' <<<"$CHAT")"
echo "chat_id=$CHAT_ID"

log "Add chat members"
for member in "$REQUESTER_ID:chat_admin" "$ASSIGNEE_ID:member"; do
    user_id="${member%%:*}"
    role="${member##*:}"
    MEMBER_PAYLOAD="$(jq -n \
        --arg user_id "$user_id" \
        --arg role "$role" \
        '{user_id: $user_id, role: $role, is_active: true}')"
    api POST "/api/chats/$CHAT_ID/members" 201 "$MEMBER_PAYLOAD" >/dev/null
done
echo "members_added=2"

log "Create task"
TASK_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg chat_id "$CHAT_ID" \
    --arg title "Bitrix Connector Smoke Task $RUN_ID" \
    --arg created_by_user_id "$REQUESTER_ID" \
    --arg assignee_id "$ASSIGNEE_ID" \
    '{
        organization_id: $organization_id,
        chat_id: $chat_id,
        title: $title,
        description: "Smoke task for Bitrix24 disabled-mode sync",
        created_by_user_id: $created_by_user_id,
        priority: "normal",
        completion_rule: "any_assignee_response",
        assignee_ids: [$assignee_id],
        observer_ids: []
    }')"
TASK="$(api POST /api/tasks 201 "$TASK_PAYLOAD")"
TASK_ID="$(jq -r '.id' <<<"$TASK")"
assert_json "$TASK" '.status == "new"' "task must start with status=new"
echo "task_id=$TASK_ID"

log "Manual Bitrix24 sync in disabled mode"
SYNC_RESULT="$(api POST "/api/integrations/bitrix24/tasks/$TASK_ID/sync" 200)"
assert_json "$SYNC_RESULT" '.sync_status == "disabled"' \
    "sync must return disabled when BITRIX24_ENABLED=false"
echo "sync_status=$(jq -r '.sync_status' <<<"$SYNC_RESULT")"

log "Get Bitrix24 sync status"
STATUS_RESULT="$(api GET "/api/integrations/bitrix24/tasks/$TASK_ID/status" 200)"
assert_json "$STATUS_RESULT" '.sync_status == "disabled"' \
    "status endpoint must return disabled after disabled sync"
echo "status_sync_status=$(jq -r '.sync_status' <<<"$STATUS_RESULT")"

log "Summary"
echo "bitrix24_connector_smoke=ok"
echo "mode=disabled"
echo "organization_id=$ORG_ID"
echo "requester_id=$REQUESTER_ID"
echo "assignee_id=$ASSIGNEE_ID"
echo "mapping_id=$MAPPING_ID"
echo "chat_id=$CHAT_ID"
echo "task_id=$TASK_ID"
