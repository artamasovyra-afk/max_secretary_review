#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 127
    fi
}

log() {
    printf '\n== %s ==\n' "$1"
}

request() {
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

expect_status() {
    local method="$1"
    local path="$2"
    local expected_status="$3"
    local payload="${4:-}"

    request "$method" "$path" "$expected_status" "$payload" >/dev/null
    echo "OK $method $path -> $expected_status"
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

printf 'Release smoke target: %s\n' "$BASE_URL"

log "Public API smoke"
HEALTH="$(request GET /api/health 200)"
assert_json "$HEALTH" '.status == "ok"' "health endpoint must return status=ok"
echo "public_api_smoke=ok"

log "Public WebApp smoke"
for path in \
    / \
    /tasks \
    /dashboard \
    /group-assignments \
    /settings \
    /site.webmanifest \
    /favicon.ico
do
    expect_status GET "$path" 200
done
echo "public_webapp_smoke=ok"

log "Protected API unauthenticated smoke"
ORG_PAYLOAD="$(jq -n '{name: "Release Smoke Unauthorized Org", status: "active"}')"
expect_status POST /api/organizations 401 "$ORG_PAYLOAD"
expect_status GET /api/tasks 401
expect_status GET /api/tasks/inbox/summary 401
expect_status GET /api/users 401
expect_status GET /api/chats 401
expect_status GET /api/auth/me 401
echo "protected_unauth_smoke=ok"

log "Authenticated API smoke"
echo "authenticated_smoke=skipped:no_session"
echo "auth_session_smoke=skipped:no_initdata"

log "MAX sender smoke"
if [[ "${MAX_SENDER_ENABLED:-false}" == "true" ]]; then
    MAX_SENDER_SMOKE_STATUS="skipped:requires_explicit_allowlist"
else
    MAX_SENDER_SMOKE_STATUS="skipped:disabled"
fi
echo "max_sender_smoke=$MAX_SENDER_SMOKE_STATUS"

log "Bitrix24 smoke"
echo "bitrix24_smoke=skipped:auth_disabled"

log "Reminders smoke"
echo "reminders_smoke=skipped:no_authenticated_context"

log "Summary"
echo "release_smoke=ok"
echo "base_url=$BASE_URL"
echo "public_smoke=ok"
echo "protected_unauth_smoke=ok"
echo "authenticated_smoke=skipped:no_session"
echo "max_sender_smoke=$MAX_SENDER_SMOKE_STATUS"
echo "bitrix24_smoke=skipped:auth_disabled"
echo "reminders_smoke=skipped:no_authenticated_context"
