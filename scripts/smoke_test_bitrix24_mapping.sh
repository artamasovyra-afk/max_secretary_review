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

assert_json_arg() {
    local json="$1"
    local arg_name="$2"
    local arg_value="$3"
    local filter="$4"
    local message="$5"

    if ! jq -e --arg "$arg_name" "$arg_value" "$filter" >/dev/null <<<"$json"; then
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
    --arg name "Bitrix Mapping Smoke Org $RUN_ID" \
    '{name: $name, status: "active"}')"
ORG="$(api POST /api/organizations 201 "$ORG_PAYLOAD")"
ORG_ID="$(jq -r '.id' <<<"$ORG")"
echo "organization_id=$ORG_ID"

log "Create user"
USER_PAYLOAD="$(jq -n \
    --arg display_name "Bitrix Mapping Smoke User $RUN_ID" \
    --arg username "bitrix_mapping_smoke_$RUN_ID" \
    '{display_name: $display_name, username: $username}')"
USER="$(api POST /api/users 201 "$USER_PAYLOAD")"
USER_ID="$(jq -r '.id' <<<"$USER")"
echo "user_id=$USER_ID"
AUTH_HEADER_ARGS=(
    -H "X-Smoke-Test: max_secretary"
    -H "X-User-Id: $USER_ID"
    -H "X-Organization-Id: $ORG_ID"
    -H "X-Roles: chat_admin"
)

log "Create Bitrix24 user mapping"
MAPPING_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg user_id "$USER_ID" \
    '{
        organization_id: $organization_id,
        user_id: $user_id,
        bitrix_user_id: "123",
        match_source: "manual",
        is_active: true
    }')"
MAPPING="$(api POST /api/integrations/bitrix24/user-mappings 201 "$MAPPING_PAYLOAD")"
MAPPING_ID="$(jq -r '.id' <<<"$MAPPING")"
assert_json "$MAPPING" '.bitrix_user_id == "123" and .match_source == "manual" and .is_active == true' \
    "created mapping must be active and manual"
echo "mapping_id=$MAPPING_ID"

log "List mappings by organization"
MAPPINGS="$(api GET "/api/integrations/bitrix24/user-mappings?organization_id=$ORG_ID" 200)"
assert_json_arg "$MAPPINGS" "mapping_id" "$MAPPING_ID" 'any(.id == $mapping_id)' \
    "list must include created mapping"

log "Get mapping by id"
MAPPING_BY_ID="$(api GET "/api/integrations/bitrix24/user-mappings/$MAPPING_ID" 200)"
assert_json_arg "$MAPPING_BY_ID" "mapping_id" "$MAPPING_ID" '.id == $mapping_id' \
    "get by id must return created mapping"

log "Reject duplicate active mapping"
DUPLICATE_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg user_id "$USER_ID" \
    '{
        organization_id: $organization_id,
        user_id: $user_id,
        bitrix_user_id: "456",
        match_source: "manual",
        is_active: true
    }')"
DUPLICATE_RESPONSE="$(api POST /api/integrations/bitrix24/user-mappings 409 "$DUPLICATE_PAYLOAD")"
assert_json "$DUPLICATE_RESPONSE" '.detail == "Active Bitrix24 user mapping already exists"' \
    "duplicate active mapping must return conflict"

log "Patch mapping"
PATCH_PAYLOAD="$(jq -n '{bitrix_user_id: "789", match_source: "email"}')"
PATCHED="$(api PATCH "/api/integrations/bitrix24/user-mappings/$MAPPING_ID" 200 "$PATCH_PAYLOAD")"
assert_json "$PATCHED" '.bitrix_user_id == "789" and .match_source == "email" and .is_active == true' \
    "patched mapping must keep active=true and update fields"

log "Soft delete mapping"
DELETED="$(api DELETE "/api/integrations/bitrix24/user-mappings/$MAPPING_ID" 200)"
assert_json "$DELETED" '.is_active == false' "delete must soft-delete mapping"

log "Verify mapping still exists and is inactive"
INACTIVE="$(api GET "/api/integrations/bitrix24/user-mappings/$MAPPING_ID" 200)"
assert_json "$INACTIVE" '.is_active == false and .bitrix_user_id == "789"' \
    "mapping must remain readable and inactive after delete"

log "Result"
echo "bitrix24_mapping_smoke=ok"
echo "organization_id=$ORG_ID"
echo "user_id=$USER_ID"
echo "mapping_id=$MAPPING_ID"
