#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%d%H%M%S)}"
AUTH_HEADER_ARGS=()

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

log() {
    printf '\n== %s ==\n' "$1"
}

check_head() {
    local path="$1"
    local expected_status="$2"
    local response_headers
    local status_code

    response_headers="$(mktemp)"
    status_code="$(
        curl -sS \
            -I \
            -o "$response_headers" \
            -w '%{http_code}' \
            "$BASE_URL$path"
    )"

    if [[ "$status_code" != "$expected_status" ]]; then
        echo "HEAD $path failed: expected $expected_status, got $status_code" >&2
        echo "Response headers:" >&2
        cat "$response_headers" >&2
        rm -f "$response_headers"
        exit 1
    fi

    rm -f "$response_headers"
    echo "OK $path -> $status_code"
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

log "WebApp routes"
check_head / 200
check_head /dashboard 200
check_head /tasks 200

log "Backend routes through nginx"
check_head /api/health 200
check_head /openapi.json 200

log "Create smoke data for Task Details"
ORG="$(api POST /api/organizations 201 "$(jq -n \
    --arg name "WebApp Smoke Org $RUN_ID" \
    '{name: $name, status: "active"}')")"
ORG_ID="$(jq -r '.id' <<<"$ORG")"

USER="$(api POST /api/users 201 "$(jq -n \
    --arg display_name "WebApp Smoke User $RUN_ID" \
    --arg username "webapp_smoke_user_$RUN_ID" \
    '{display_name: $display_name, username: $username}')")"
USER_ID="$(jq -r '.id' <<<"$USER")"

CHAT="$(api POST /api/chats 201 "$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg title "WebApp Smoke Chat $RUN_ID" \
    --arg max_chat_id "webapp-smoke-chat-$RUN_ID" \
    '{
        organization_id: $organization_id,
        max_chat_id: $max_chat_id,
        title: $title,
        type: "group",
        settings: {smoke_test: true}
    }')")"
CHAT_ID="$(jq -r '.id' <<<"$CHAT")"
AUTH_HEADER_ARGS=(
    -H "X-User-Id: $USER_ID"
    -H "X-Organization-Id: $ORG_ID"
    -H "X-Chat-Id: $CHAT_ID"
    -H "X-Roles: chat_admin"
)

api POST "/api/chats/$CHAT_ID/members" 201 "$(jq -n \
    --arg user_id "$USER_ID" \
    '{user_id: $user_id, role: "chat_admin", is_active: true}')" >/dev/null

TASK="$(api POST /api/tasks 201 "$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg chat_id "$CHAT_ID" \
    --arg created_by_user_id "$USER_ID" \
    --arg assignee_id "$USER_ID" \
    --arg title "WebApp Smoke Task $RUN_ID" \
    '{
        organization_id: $organization_id,
        chat_id: $chat_id,
        title: $title,
        description: "Smoke task for WebApp route and Bitrix24 status checks",
        created_by_user_id: $created_by_user_id,
        priority: "normal",
        completion_rule: "any_assignee_response",
        assignee_ids: [$assignee_id],
        observer_ids: []
    }')")"
TASK_ID="$(jq -r '.id' <<<"$TASK")"
echo "task_id=$TASK_ID"

log "Task Details route"
check_head "/tasks/$TASK_ID?user_id=$USER_ID" 200

log "Bitrix24 sync status API"
BITRIX_STATUS_FILE="$(mktemp)"
BITRIX_STATUS_CODE="$(
    curl -sS \
        -o "$BITRIX_STATUS_FILE" \
        -w '%{http_code}' \
        -X GET \
        "${AUTH_HEADER_ARGS[@]}" \
        "$BASE_URL/api/integrations/bitrix24/tasks/$TASK_ID/status"
)"
BITRIX_STATUS="$(cat "$BITRIX_STATUS_FILE")"
rm -f "$BITRIX_STATUS_FILE"

if [[ "$BITRIX_STATUS_CODE" == "200" ]]; then
    assert_json "$BITRIX_STATUS" \
        '.sync_status == "disabled" or .sync_status == "pending" or .sync_status == "synced" or .sync_status == "error"' \
        "Bitrix24 sync status must be one of disabled/pending/synced/error"
    echo "bitrix_sync_status=$(jq -r '.sync_status' <<<"$BITRIX_STATUS")"
elif [[ "$BITRIX_STATUS_CODE" == "401" ]] \
    && jq -e '.detail == "Header auth is disabled"' >/dev/null <<<"$BITRIX_STATUS"; then
    echo "bitrix_sync_status=auth_disabled"
    echo "Protected Bitrix24 status check skipped because dev header auth is disabled."
else
    echo "HTTP GET /api/integrations/bitrix24/tasks/$TASK_ID/status failed: expected 200 or auth-disabled 401, got $BITRIX_STATUS_CODE" >&2
    echo "Response body:" >&2
    echo "$BITRIX_STATUS" >&2
    exit 1
fi

log "Smoke test completed"
