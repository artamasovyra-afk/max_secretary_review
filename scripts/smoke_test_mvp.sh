#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%d%H%M%S)}"

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

assert_contains_task() {
    local json="$1"
    local section="$2"
    local task_id="$3"
    local message="$4"

    if ! jq -e --arg task_id "$task_id" --arg section "$section" '.[$section] | any(.id == $task_id)' >/dev/null <<<"$json"; then
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

require_command curl
require_command jq

log "Target"
echo "BASE_URL=$BASE_URL"

log "Healthcheck"
HEALTH="$(api GET /api/health 200)"
assert_json "$HEALTH" '.status == "ok"' "health endpoint must return status=ok"

log "Create organization"
ORG_PAYLOAD="$(jq -n \
    --arg name "Smoke Org $RUN_ID" \
    '{name: $name, status: "active"}')"
ORG="$(api POST /api/organizations 201 "$ORG_PAYLOAD")"
ORG_ID="$(jq -r '.id' <<<"$ORG")"
echo "organization_id=$ORG_ID"

log "Create users"
REQUESTER="$(create_user "Smoke Requester $RUN_ID" "smoke_requester_$RUN_ID")"
ASSIGNEE_1="$(create_user "Smoke Assignee 1 $RUN_ID" "smoke_assignee_1_$RUN_ID")"
ASSIGNEE_2="$(create_user "Smoke Assignee 2 $RUN_ID" "smoke_assignee_2_$RUN_ID")"
OBSERVER="$(create_user "Smoke Observer $RUN_ID" "smoke_observer_$RUN_ID")"
REQUESTER_ID="$(jq -r '.id' <<<"$REQUESTER")"
ASSIGNEE_1_ID="$(jq -r '.id' <<<"$ASSIGNEE_1")"
ASSIGNEE_2_ID="$(jq -r '.id' <<<"$ASSIGNEE_2")"
OBSERVER_ID="$(jq -r '.id' <<<"$OBSERVER")"
echo "requester_id=$REQUESTER_ID"
echo "assignee_1_id=$ASSIGNEE_1_ID"
echo "assignee_2_id=$ASSIGNEE_2_ID"
echo "observer_id=$OBSERVER_ID"

log "Create chat"
CHAT_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg title "Smoke Chat $RUN_ID" \
    --arg max_chat_id "smoke-chat-$RUN_ID" \
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
for member in \
    "$REQUESTER_ID:chat_admin" \
    "$ASSIGNEE_1_ID:member" \
    "$ASSIGNEE_2_ID:member" \
    "$OBSERVER_ID:member"
do
    user_id="${member%%:*}"
    role="${member##*:}"
    MEMBER_PAYLOAD="$(jq -n \
        --arg user_id "$user_id" \
        --arg role "$role" \
        '{user_id: $user_id, role: $role, is_active: true}')"
    api POST "/api/chats/$CHAT_ID/members" 201 "$MEMBER_PAYLOAD" >/dev/null
done
echo "members_added=4"

log "Create task"
TASK_PAYLOAD="$(jq -n \
    --arg organization_id "$ORG_ID" \
    --arg chat_id "$CHAT_ID" \
    --arg title "Smoke Task $RUN_ID" \
    --arg created_by_user_id "$REQUESTER_ID" \
    --arg assignee_1_id "$ASSIGNEE_1_ID" \
    --arg assignee_2_id "$ASSIGNEE_2_ID" \
    --arg observer_id "$OBSERVER_ID" \
    '{
        organization_id: $organization_id,
        chat_id: $chat_id,
        title: $title,
        description: "Smoke test task created by scripts/smoke_test_mvp.sh",
        created_by_user_id: $created_by_user_id,
        priority: "normal",
        completion_rule: "any_assignee_response",
        assignee_ids: [$assignee_1_id, $assignee_2_id],
        observer_ids: [$observer_id]
    }')"
TASK="$(api POST /api/tasks 201 "$TASK_PAYLOAD")"
TASK_ID="$(jq -r '.id' <<<"$TASK")"
assert_json "$TASK" '.status == "new"' "new task must start with status=new"
assert_json "$TASK" '.assignees | length == 2' "task must have two assignees"
assert_json "$TASK" '.observers | length == 1' "task must have one observer"
echo "task_id=$TASK_ID"

log "Get task card"
TASK_CARD="$(api GET "/api/tasks/$TASK_ID" 200)"
assert_json "$TASK_CARD" '.id != null and .comments == [] and .files == [] and .responses == []' "task card must include empty detail collections"

log "Add comment"
COMMENT_PAYLOAD="$(jq -n \
    --arg user_id "$REQUESTER_ID" \
    '{user_id: $user_id, text: "Smoke comment from requester"}')"
COMMENT="$(api POST "/api/tasks/$TASK_ID/comments" 201 "$COMMENT_PAYLOAD")"
COMMENT_ID="$(jq -r '.id' <<<"$COMMENT")"
echo "comment_id=$COMMENT_ID"

log "Add file metadata"
FILE_PAYLOAD="$(jq -n \
    --arg uploaded_by_user_id "$REQUESTER_ID" \
    --arg comment_id "$COMMENT_ID" \
    --arg file_storage_key "smoke/$RUN_ID/spec.txt" \
    '{
        uploaded_by_user_id: $uploaded_by_user_id,
        comment_id: $comment_id,
        file_name: "spec.txt",
        file_storage_key: $file_storage_key,
        mime_type: "text/plain",
        size_bytes: 128
    }')"
FILE="$(api POST "/api/tasks/$TASK_ID/files" 201 "$FILE_PAYLOAD")"
FILE_ID="$(jq -r '.id' <<<"$FILE")"
echo "file_id=$FILE_ID"

log "Submit response from assignee 1"
RESPONSE_PAYLOAD="$(jq -n \
    --arg user_id "$ASSIGNEE_1_ID" \
    '{user_id: $user_id, text: "Smoke result submitted", source_message_id: "smoke-response"}')"
RESPONSE="$(api POST "/api/tasks/$TASK_ID/responses" 201 "$RESPONSE_PAYLOAD")"
RESPONSE_ID="$(jq -r '.id' <<<"$RESPONSE")"
assert_json "$RESPONSE" '.status == "submitted"' "task response must be submitted"
echo "response_id=$RESPONSE_ID"

log "Check waiting_acceptance transition"
TASK_AFTER_RESPONSE="$(api GET "/api/tasks/$TASK_ID" 200)"
assert_json "$TASK_AFTER_RESPONSE" '.status == "waiting_acceptance"' "task must move to waiting_acceptance after first assignee response"
assert_json "$TASK_AFTER_RESPONSE" '.responses | length == 1' "task must include one response"
echo "task_status=$(jq -r '.status' <<<"$TASK_AFTER_RESPONSE")"

log "Accept response by requester"
ACCEPT_PAYLOAD="$(jq -n \
    --arg accepted_by_user_id "$REQUESTER_ID" \
    '{accepted_by_user_id: $accepted_by_user_id, comment: "Smoke acceptance"}')"
ACCEPTANCE="$(api POST "/api/tasks/$TASK_ID/responses/$RESPONSE_ID/accept" 201 "$ACCEPT_PAYLOAD")"
assert_json "$ACCEPTANCE" '.decision == "accepted"' "acceptance decision must be accepted"
ACCEPTANCE_ID="$(jq -r '.id' <<<"$ACCEPTANCE")"
echo "acceptance_id=$ACCEPTANCE_ID"

log "Check done transition"
TASK_AFTER_ACCEPT="$(api GET "/api/tasks/$TASK_ID" 200)"
assert_json "$TASK_AFTER_ACCEPT" '.status == "done"' "task must move to done after acceptance"
assert_json "$TASK_AFTER_ACCEPT" '.completed_at != null' "done task must have completed_at"
echo "task_status=$(jq -r '.status' <<<"$TASK_AFTER_ACCEPT")"

log "Check inbox summary for assignee 1"
ASSIGNEE_SUMMARY="$(api GET "/api/tasks/inbox/summary?user_id=$ASSIGNEE_1_ID&organization_id=$ORG_ID" 200)"
assert_contains_task "$ASSIGNEE_SUMMARY" my_tasks "$TASK_ID" "assignee summary must include task in my_tasks"
if jq -e --arg task_id "$TASK_ID" '.waiting_my_response | any(.id == $task_id)' >/dev/null <<<"$ASSIGNEE_SUMMARY"; then
    echo "Assertion failed: responded assignee should not have this task in waiting_my_response" >&2
    echo "$ASSIGNEE_SUMMARY" | jq . >&2
    exit 1
fi

log "Check inbox summary for requester"
REQUESTER_SUMMARY="$(api GET "/api/tasks/inbox/summary?user_id=$REQUESTER_ID&organization_id=$ORG_ID" 200)"
assert_contains_task "$REQUESTER_SUMMARY" created_by_me "$TASK_ID" "requester summary must include task in created_by_me"
if jq -e --arg task_id "$TASK_ID" '.waiting_my_acceptance | any(.id == $task_id)' >/dev/null <<<"$REQUESTER_SUMMARY"; then
    echo "Assertion failed: done task should not stay in waiting_my_acceptance" >&2
    echo "$REQUESTER_SUMMARY" | jq . >&2
    exit 1
fi

log "Smoke test passed"
cat <<EOF
run_id=$RUN_ID
organization_id=$ORG_ID
chat_id=$CHAT_ID
task_id=$TASK_ID
response_id=$RESPONSE_ID
final_status=$(jq -r '.status' <<<"$TASK_AFTER_ACCEPT")
EOF
