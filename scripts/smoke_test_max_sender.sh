#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%d%H%M%S)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKEND_SERVICE="${BACKEND_SERVICE:-backend}"
WORKER_SERVICE="${WORKER_SERVICE:-worker}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-}"

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
    local curl_args=()

    response_file="$(mktemp)"
    if [[ -n "$payload" ]]; then
        curl_args=(-X "$method" "$BASE_URL$path" -H "Content-Type: application/json" --data "$payload")
    else
        curl_args=(-X "$method" "$BASE_URL$path")
    fi

    if [[ -n "$WEBHOOK_SECRET" && "$path" == "/api/bot/max/webhook" ]]; then
        curl_args+=(-H "X-Max-Webhook-Secret: $WEBHOOK_SECRET")
    fi

    status_code="$(curl -sS -o "$response_file" -w "%{http_code}" "${curl_args[@]}")"
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

docker_compose_available() {
    command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]
}

require_command curl
require_command jq

log "Target"
echo "BASE_URL=$BASE_URL"

log "Healthcheck"
HEALTH="$(api GET /api/health 200)"
assert_json "$HEALTH" '.status == "ok"' "health endpoint must return status=ok"
echo "$HEALTH" | jq .

log "Create test organization"
ORG_PAYLOAD="$(jq -n \
    --arg name "Smoke MAX Sender Org $RUN_ID" \
    '{name: $name, status: "active"}')"
ORG="$(api POST /api/organizations 201 "$ORG_PAYLOAD")"
ORG_ID="$(jq -r '.id' <<<"$ORG")"
echo "organization_id=$ORG_ID"

log "Create test chat"
CHAT_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg title "Smoke MAX Sender Chat $RUN_ID" \
    --arg max_chat_id "smoke-max-sender-chat-$RUN_ID" \
    '{
        organization_id: $organization_id,
        max_chat_id: $max_chat_id,
        title: $title,
        type: "group",
        settings: {smoke_test: true, source: "max_sender"}
    }')"
CHAT="$(api POST /api/chats 201 "$CHAT_PAYLOAD")"
CHAT_ID="$(jq -r '.id' <<<"$CHAT")"
echo "chat_id=$CHAT_ID"

log "Send webhook command in disabled sender mode"
WEBHOOK_PAYLOAD="$(jq -n \
    --arg chat_id "$CHAT_ID" \
    --arg user_id "00000000-0000-0000-0000-000000000000" \
    --arg message_id "smoke-max-sender-$RUN_ID" \
    '{
        chat_id: $chat_id,
        user_id: $user_id,
        message_id: $message_id,
        text: "/задачи"
    }')"
WEBHOOK_RESPONSE="$(api POST /api/bot/max/webhook 200 "$WEBHOOK_PAYLOAD")"
echo "$WEBHOOK_RESPONSE" | jq .

assert_json "$WEBHOOK_RESPONSE" '.ok == true' "webhook must return ok=true"
assert_json "$WEBHOOK_RESPONSE" '.is_command == true and .command.type == "list_tasks"' "webhook must parse /задачи"
assert_json "$WEBHOOK_RESPONSE" '.action == "reply_prepared"' "webhook must prepare a reply"
assert_json "$WEBHOOK_RESPONSE" '.outbound.method == "send_message"' "webhook must use send_message"
assert_json "$WEBHOOK_RESPONSE" '.outbound.sent == false' "MAX sender must not send real messages in disabled mode"
assert_json "$WEBHOOK_RESPONSE" '.outbound.reason | contains("disabled")' "MAX sender reason must confirm disabled mode"

log "Check container logs when Docker Compose is available"
if docker_compose_available; then
    if docker compose -f "$COMPOSE_FILE" logs --tail=200 "$BACKEND_SERVICE" 2>/dev/null | grep -q "MAX sender stub message"; then
        echo "backend_logs=stub_message_found"
    else
        echo "backend_logs=stub_message_not_found"
        echo "The response already confirmed outbound.sent=false; inspect backend logs manually if needed."
    fi

    if docker compose -f "$COMPOSE_FILE" ps "$WORKER_SERVICE" >/dev/null 2>&1; then
        docker compose -f "$COMPOSE_FILE" logs --tail=50 "$WORKER_SERVICE" >/dev/null 2>&1 \
            && echo "worker_logs=available" \
            || echo "worker_logs=not_available"
    else
        echo "worker_logs=service_not_found"
    fi
else
    echo "Docker Compose is not available here; skipped backend/worker log inspection."
fi

log "MAX sender disabled smoke test passed"
cat <<EOF
run_id=$RUN_ID
organization_id=$ORG_ID
chat_id=$CHAT_ID
sender_sent=$(jq -r '.outbound.sent' <<<"$WEBHOOK_RESPONSE")
sender_reason=$(jq -r '.outbound.reason' <<<"$WEBHOOK_RESPONSE")
EOF
