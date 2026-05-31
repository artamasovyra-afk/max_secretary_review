#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%d%H%M%S)}"
DEADLINE="${DEADLINE:-$(date -u +%Y-%m-%d)}"

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

webhook_event() {
    local chat_id="$1"
    local user_id="$2"
    local text="$3"
    local message_id="smoke-bot-$RUN_ID-$4"

    jq -n \
        --arg chat_id "$chat_id" \
        --arg user_id "$user_id" \
        --arg message_id "$message_id" \
        --arg text "$text" \
        '{
            chat_id: $chat_id,
            user_id: $user_id,
            message_id: $message_id,
            text: $text
        }'
}

require_command curl
require_command jq

log "Target"
echo "BASE_URL=$BASE_URL"

log "Healthcheck"
HEALTH="$(api GET /api/health 200)"
assert_json "$HEALTH" '.status == "ok"' "health endpoint must return status=ok"

log "Create test organization"
ORG_PAYLOAD="$(jq -n \
    --arg name "Smoke Bot Org $RUN_ID" \
    '{name: $name, status: "active"}')"
ORG="$(api POST /api/organizations 201 "$ORG_PAYLOAD")"
ORG_ID="$(jq -r '.id' <<<"$ORG")"
echo "organization_id=$ORG_ID"

log "Create test users"
REQUESTER_NAME="Smoke Bot Requester $RUN_ID"
ASSIGNEE_1_NAME="Smoke Bot Assignee 1 $RUN_ID"
ASSIGNEE_2_NAME="Smoke Bot Assignee 2 $RUN_ID"
OBSERVER_NAME="Smoke Bot Observer $RUN_ID"

REQUESTER="$(create_user "$REQUESTER_NAME" "smoke_bot_requester_$RUN_ID")"
ASSIGNEE_1="$(create_user "$ASSIGNEE_1_NAME" "smoke_bot_assignee_1_$RUN_ID")"
ASSIGNEE_2="$(create_user "$ASSIGNEE_2_NAME" "smoke_bot_assignee_2_$RUN_ID")"
OBSERVER="$(create_user "$OBSERVER_NAME" "smoke_bot_observer_$RUN_ID")"

REQUESTER_ID="$(jq -r '.id' <<<"$REQUESTER")"
ASSIGNEE_1_ID="$(jq -r '.id' <<<"$ASSIGNEE_1")"
ASSIGNEE_2_ID="$(jq -r '.id' <<<"$ASSIGNEE_2")"
OBSERVER_ID="$(jq -r '.id' <<<"$OBSERVER")"
echo "requester_id=$REQUESTER_ID"
echo "assignee_1_id=$ASSIGNEE_1_ID"
echo "assignee_2_id=$ASSIGNEE_2_ID"
echo "observer_id=$OBSERVER_ID"

log "Create test chat"
CHAT_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg title "Smoke Bot Chat $RUN_ID" \
    --arg max_chat_id "smoke-bot-chat-$RUN_ID" \
    '{
        organization_id: $organization_id,
        max_chat_id: $max_chat_id,
        title: $title,
        type: "group",
        settings: {smoke_test: true, source: "bot_webhook"}
    }')"
CHAT="$(api POST /api/chats 201 "$CHAT_PAYLOAD")"
CHAT_ID="$(jq -r '.id' <<<"$CHAT")"
echo "chat_id=$CHAT_ID"

log "Add test users to chat"
add_chat_member "" "" chat_admin
add_chat_member "$CHAT_ID" "$ASSIGNEE_1_ID" member
add_chat_member "$CHAT_ID" "$ASSIGNEE_2_ID" member
add_chat_member "$CHAT_ID" "$OBSERVER_ID" member
echo "members_added=4"

log "Webhook /задача"
CREATE_TEXT="/задача Smoke Bot Task $RUN_ID | $ASSIGNEE_1_NAME, $ASSIGNEE_2_NAME | $DEADLINE | наблюдатели: $OBSERVER_NAME"
CREATE_EVENT="$(webhook_event "$CHAT_ID" "$REQUESTER_ID" "$CREATE_TEXT" create-task)"
CREATE_RESPONSE="$(api POST /api/bot/max/webhook 200 "$CREATE_EVENT")"
assert_json "$CREATE_RESPONSE" '.ok == true and .command.type == "create_task"' "/задача must be parsed and executed"
assert_json "$CREATE_RESPONSE" '.outbound.method == "send_task_card" and .outbound.sent == false' "MAX sender must stay stubbed"
TASK_ID="$(jq -r '.outbound.task.id' <<<"$CREATE_RESPONSE")"
if [[ "$TASK_ID" == "null" || -z "$TASK_ID" ]]; then
    echo "Assertion failed: /задача response must include outbound.task.id" >&2
    echo "$CREATE_RESPONSE" | jq . >&2
    exit 1
fi
echo "task_id=$TASK_ID"

log "Verify task was created"
TASK="$(api GET "/api/tasks/$TASK_ID" 200)"
assert_json_arg "$TASK" task_id "$TASK_ID" '.id == $task_id' "created task must be fetchable"
assert_json "$TASK" '.status == "new"' "created task must start as new"
assert_json "$TASK" '.assignees | length == 2' "created task must have two assignees"
assert_json "$TASK" '.observers | length == 1' "created task must have one observer"

log "Webhook /задачи"
LIST_EVENT="$(webhook_event "$CHAT_ID" "$REQUESTER_ID" "/задачи" list-tasks)"
LIST_RESPONSE="$(api POST /api/bot/max/webhook 200 "$LIST_EVENT")"
assert_json "$LIST_RESPONSE" '.ok == true and .command.type == "list_tasks"' "/задачи must be parsed and executed"
assert_json_arg "$LIST_RESPONSE" task_id "$TASK_ID" '.response_text | contains($task_id)' "/задачи must include created task"

log "Webhook /мои_задачи"
MY_TASKS_EVENT="$(webhook_event "$CHAT_ID" "$ASSIGNEE_1_ID" "/мои_задачи" my-tasks)"
MY_TASKS_RESPONSE="$(api POST /api/bot/max/webhook 200 "$MY_TASKS_EVENT")"
assert_json "$MY_TASKS_RESPONSE" '.ok == true and .command.type == "my_tasks"' "/мои_задачи must be parsed and executed"
assert_json_arg "$MY_TASKS_RESPONSE" task_id "$TASK_ID" '.response_text | contains($task_id)' "/мои_задачи must include created task for assignee"

log "Webhook /ответ"
ANSWER_TEXT="/ответ $TASK_ID Smoke bot response is ready"
ANSWER_EVENT="$(webhook_event "$CHAT_ID" "$ASSIGNEE_1_ID" "$ANSWER_TEXT" answer)"
ANSWER_RESPONSE="$(api POST /api/bot/max/webhook 200 "$ANSWER_EVENT")"
assert_json "$ANSWER_RESPONSE" '.ok == true and .command.type == "task_response"' "/ответ must be parsed and executed"

TASK_AFTER_RESPONSE="$(api GET "/api/tasks/$TASK_ID" 200)"
assert_json "$TASK_AFTER_RESPONSE" '.status == "waiting_acceptance"' "task must move to waiting_acceptance after /ответ"
assert_json_arg "$TASK_AFTER_RESPONSE" user_id "$ASSIGNEE_1_ID" '.responses | map(select(.user_id == $user_id)) | length >= 1' "task must include assignee response"
RESPONSE_ID="$(jq -r --arg user_id "$ASSIGNEE_1_ID" '.responses | map(select(.user_id == $user_id)) | .[-1].id' <<<"$TASK_AFTER_RESPONSE")"
echo "response_id=$RESPONSE_ID"

log "Webhook /принять"
ACCEPT_TEXT="/принять $TASK_ID $RESPONSE_ID"
ACCEPT_EVENT="$(webhook_event "$CHAT_ID" "$REQUESTER_ID" "$ACCEPT_TEXT" accept)"
ACCEPT_RESPONSE="$(api POST /api/bot/max/webhook 200 "$ACCEPT_EVENT")"
assert_json "$ACCEPT_RESPONSE" '.ok == true and .command.type == "accept_response"' "/принять must be parsed and executed"

log "Verify final task status"
TASK_AFTER_ACCEPT="$(api GET "/api/tasks/$TASK_ID" 200)"
assert_json "$TASK_AFTER_ACCEPT" '.status == "done"' "task must move to done after /принять"
assert_json "$TASK_AFTER_ACCEPT" '.completed_at != null' "done task must have completed_at"
echo "final_status=$(jq -r '.status' <<<"$TASK_AFTER_ACCEPT")"

log "Bot webhook smoke test passed"
cat <<EOF
run_id=$RUN_ID
organization_id=$ORG_ID
chat_id=$CHAT_ID
task_id=$TASK_ID
response_id=$RESPONSE_ID
final_status=$(jq -r '.status' <<<"$TASK_AFTER_ACCEPT")
EOF
