# MAX Official Docs Alignment

## Source

- `documentation_gov.pdf`

The PDF is the official MAX partner-platform guide for government organizations. It covers platform onboarding, bot creation, bot moderation, where to obtain the bot token, mini app setup, deep links, and channel management.

Important limitation: this PDF does not contain the low-level Bot API reference for `/subscriptions`, webhook request headers, update object schemas, or webhook payload examples. Those API-level details still need to be confirmed against the MAX Bot API reference and real sandbox traffic.

## Authorization

What the PDF says:

- after bot moderation, the bot token becomes available;
- the bot token is found in the partner platform at `Чат-боты -> Интеграция -> Получить токен`;
- the PDF does not specify the HTTP authorization header format for Bot API calls;
- the PDF does not distinguish whether the value is a bot token, access token, integration token, or another credential type for `/subscriptions`.

Current max_secretary behavior:

- `MaxApiClient` sends the configured bot credential in the `Authorization` header as-is;
- previous safe VPS checks tried the as-is value and also tested common prefixed variants without printing the credential;
- MAX API still returned `401`, code `verify.token`, with an invalid credential message.

Alignment status:

- token source in the project docs matches the PDF: use the platform section `Чат-боты -> Интеграция -> Получить токен`;
- exact Bot API authorization format is not confirmed by the PDF;
- the current `401` invalid credential response means the deployed credential is still not accepted by the `/subscriptions` API or the credential type/header format differs from what this PDF explains.

## Subscriptions

What the PDF says:

- no `/subscriptions` endpoint is described;
- no `GET /subscriptions` or `POST /subscriptions` request/response format is described;
- no `update_types` list is described;
- no subscription `secret` field is described;
- no subscription delete/update behavior is described.

What current project docs and code expect from the Bot API reference:

- webhook URL: `https://maxsecretary.ru/api/bot/max/webhook`;
- subscription creation is done through `POST /subscriptions`;
- expected body shape:

```json
{
  "url": "https://maxsecretary.ru/api/bot/max/webhook",
  "update_types": ["message_created", "bot_started", "message_callback"],
  "secret": "<MAX_WEBHOOK_SECRET from VPS .env>"
}
```

- `MAX_WEBHOOK_SECRET` must match `^[a-zA-Z0-9_-]{5,256}$` before it can be used as an official subscription secret.

Current mismatch:

- the PDF cannot validate or invalidate the subscription body because it does not document `/subscriptions`;
- latest VPS check showed that the deployed webhook secret is set but does not match the official subscription secret pattern;
- because `GET /subscriptions` still returns a `401` invalid credential response, `POST /subscriptions` should not be retried until the credential is accepted.

## Webhook Secret

What the PDF says:

- no webhook secret header is documented;
- no webhook signature mechanism is documented;
- no behavior for missing secret is documented.

Current backend implementation:

- `MAX_WEBHOOK_ENABLED=false` disables `POST /api/bot/max/webhook` with HTTP `404`;
- production with `MAX_WEBHOOK_ENABLED=true` and empty `MAX_WEBHOOK_SECRET` returns HTTP `503` before payload handling;
- official header `X-Max-Bot-Api-Secret` is accepted;
- legacy/internal header `X-Max-Webhook-Secret` is temporarily accepted;
- missing or invalid secret header returns HTTP `401`;
- secret comparison uses constant-time comparison;
- debug logging records only sanitized structure and masked identifiers.

Alignment status:

- backend is aligned with the Bot API reference expectation for `X-Max-Bot-Api-Secret`;
- the PDF does not independently confirm this header;
- legacy `X-Max-Webhook-Secret` should remain internal-only and can be removed after all tests/tooling use the official header.

## Webhook Payload

What the PDF says:

- no webhook payload schema is described;
- no `message_created`, `message_callback`, `bot_started`, or reply payload structure is described;
- no paths for `message_id`, `chat_id`, `user_id`, reply metadata, or callback payload are described.

What current code supports:

- normalized/mock events with `chat_id`, `user_id`, `message_id`, and `text`;
- MAX-like raw message payloads using paths such as `message.recipient.chat_id`, `message.sender.user_id`, and `message.body.mid`;
- unsupported events such as `bot_started` are safely ignored;
- debug logging is sanitized when enabled.

What remains pending:

- real text-message payload capture;
- real reply payload capture;
- real callback payload capture;
- direct-message behavior;
- WebApp/open-app button behavior;
- rate-limit and error response shapes.

## Mini App

What the PDF says:

- mini apps are configured in the partner platform under `Чат-боты -> Чат-бот и мини-приложение -> Настроить`;
- the mini app URL is pasted into the URL field;
- mini app URL must use `https://`;
- after connecting the mini app, MAX shows a visible button in the chat with the bot;
- direct mini app links use the form `https://max.ru/<botName>?startapp=<payload>`;
- `payload` is optional, up to 512 characters, and may contain latin letters, digits, underscore, and hyphen;
- start parameters are available to the mini app through MAX Bridge.

Current max_secretary setup:

- mini app URL: `https://maxsecretary.ru`;
- webhook URL: `https://maxsecretary.ru/api/bot/max/webhook`;
- these are separate concepts and should not be conflated.

Alignment status:

- the mini app URL configured in the MAX partner UI is correct for WebApp opening;
- the PDF confirms that the mini app URL field is not the webhook subscription URL;
- the PDF does not provide webhook subscription setup.

## Required Changes

### P0 Before Rechecking `/subscriptions`

1. Re-check the credential source in the MAX partner platform: `Чат-боты -> Интеграция -> Получить токен`.
2. Confirm whether `/subscriptions` expects exactly that token or another access credential not described in `documentation_gov.pdf`.
3. Replace `MAX_WEBHOOK_SECRET` on the VPS with a generated value that matches `^[a-zA-Z0-9_-]{5,256}$`.
4. Recreate backend and worker containers after `.env` changes.
5. Re-run `GET /subscriptions` without printing the credential.

### P1 Before Real Sandbox Capture

1. Create or update the webhook subscription only after `GET /subscriptions` succeeds.
2. Use the official `X-Max-Bot-Api-Secret` validation path.
3. Keep `MAX_WEBHOOK_DEBUG_LOG=true` only for the short capture window.
4. Capture and document sanitized payloads for normal message, reply message, callback, direct message, and WebApp/open-app scenarios.

### P2 Later

1. Remove legacy `X-Max-Webhook-Secret` support after internal tooling and tests move fully to `X-Max-Bot-Api-Secret`.
2. Add a small admin-safe script for `/subscriptions` checks that redacts credential and secret values by default.
3. Add a docs note distinguishing partner-platform setup from Bot API setup.

## Recommended Next Command

Run this on the VPS only after manually replacing the credential and setting a MAX-compatible webhook secret in `.env`. It prints only statuses and sanitized response previews.

```bash
cd /opt/max_secretary/app
python3 - <<'PY'
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

env = {}
for line in Path(".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    env[key.strip()] = value.strip().strip('"').strip("'")

base = env.get("MAX_API_BASE_URL", "https://platform-api.max.ru").rstrip("/")
credential = env.get("MAX_BOT_TOKEN", "")
secret = env.get("MAX_WEBHOOK_SECRET", "")
webhook_url = "https://maxsecretary.ru/api/bot/max/webhook"

print("credential_set=" + str(bool(credential)))
print("credential_length=" + str(len(credential)))
print("secret_set=" + str(bool(secret)))
print("secret_length=" + str(len(secret)))
print("secret_pattern_ok=" + str(bool(re.fullmatch(r"[A-Za-z0-9_-]{5,256}", secret))))

if not credential or not secret:
    raise SystemExit(2)
if not re.fullmatch(r"[A-Za-z0-9_-]{5,256}", secret):
    raise SystemExit(3)

def request_json(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        f"{base}{path}",
        data=data,
        headers={
            "Authorization": credential,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"{method} {path} status={resp.status}")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"{method} {path} status={exc.code}")
    except URLError as exc:
        print(f"{method} {path} url_error={type(exc).__name__}")
        raise SystemExit(1)
    print("body_preview=" + body.replace(secret, "<SECRET_REDACTED>")[:1500])
    return body

body = request_json("GET", "/subscriptions")
if "invalid credential" in body.lower():
    raise SystemExit(4)

payload = {
    "url": webhook_url,
    "update_types": ["message_created", "bot_started", "message_callback"],
    "secret": secret,
}
request_json("POST", "/subscriptions", payload)
request_json("GET", "/subscriptions")
PY
```

Do not enable shell tracing. Do not print `.env`. Do not paste the credential or webhook secret into chat, docs, shell history notes, screenshots, or commit messages.
