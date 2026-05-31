from __future__ import annotations

import hashlib
import hmac
import json
from urllib import parse
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.modules.auth.max_webapp import (
    MaxWebAppAuthError,
    parse_init_data,
    verify_max_webapp_init_data,
)
from app.modules.auth.session import (
    WebAppSessionError,
    create_session_token,
    verify_session_token,
)

TEST_BOT_TOKEN = "test-bot-token"
TEST_SESSION_SECRET = "test-session-secret"


def test_valid_init_data_verifies_max_user() -> None:
    init_data = _build_init_data(
        credential=TEST_BOT_TOKEN,
        user={"user_id": "max-user-001", "first_name": "Ivan", "last_name": "Petrov", "username": "ivan"},
        auth_date=2_000,
    )

    verified = verify_max_webapp_init_data(
        init_data,
        bot_credential=SecretStr(TEST_BOT_TOKEN),
        max_age_seconds=600,
        now_ts=2_100,
    )

    assert verified.max_user_id == "max-user-001"
    assert verified.display_name == "Ivan Petrov"
    assert verified.username == "ivan"
    assert verified.auth_date == 2_000


def test_init_data_can_be_unwrapped_from_webapp_data_fragment() -> None:
    inner_init_data = _build_init_data(
        credential=TEST_BOT_TOKEN,
        user={"id": "max-user-001"},
        auth_date=2_000,
    )
    wrapped_init_data = f"https://maxsecretary.ru#WebAppData={parse.quote(inner_init_data, safe='')}"

    parsed = parse_init_data(wrapped_init_data)

    assert parsed["auth_date"] == "2000"
    assert json.loads(parsed["user"])["id"] == "max-user-001"


def test_invalid_init_data_hash_is_rejected() -> None:
    init_data = _build_init_data(
        credential=TEST_BOT_TOKEN,
        user={"user_id": "max-user-001"},
        auth_date=2_000,
    ).replace("max-user-001", "max-user-002")

    with pytest.raises(MaxWebAppAuthError, match="signature mismatch"):
        verify_max_webapp_init_data(
            init_data,
            bot_credential=SecretStr(TEST_BOT_TOKEN),
            max_age_seconds=600,
            now_ts=2_100,
        )


def test_missing_init_data_hash_is_rejected() -> None:
    with pytest.raises(MaxWebAppAuthError, match="hash is missing"):
        verify_max_webapp_init_data(
            "auth_date=2000&user=%7B%22user_id%22%3A%22max-user-001%22%7D",
            bot_credential=SecretStr(TEST_BOT_TOKEN),
            max_age_seconds=600,
            now_ts=2_100,
        )


def test_expired_init_data_is_rejected() -> None:
    init_data = _build_init_data(
        credential=TEST_BOT_TOKEN,
        user={"user_id": "max-user-001"},
        auth_date=1_000,
    )

    with pytest.raises(MaxWebAppAuthError, match="expired"):
        verify_max_webapp_init_data(
            init_data,
            bot_credential=SecretStr(TEST_BOT_TOKEN),
            max_age_seconds=600,
            now_ts=2_000,
        )


def test_malformed_user_json_is_rejected() -> None:
    params = {"auth_date": "2000", "user": "{not-json"}
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", TEST_BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    with pytest.raises(MaxWebAppAuthError, match="user payload is invalid"):
        verify_max_webapp_init_data(
            parse.urlencode(params),
            bot_credential=SecretStr(TEST_BOT_TOKEN),
            max_age_seconds=600,
            now_ts=2_100,
        )


def test_init_data_error_does_not_include_bot_token() -> None:
    with pytest.raises(MaxWebAppAuthError) as exc_info:
        verify_max_webapp_init_data(
            "auth_date=2000",
            bot_credential=SecretStr(TEST_BOT_TOKEN),
            max_age_seconds=600,
            now_ts=2_100,
        )

    assert TEST_BOT_TOKEN not in str(exc_info.value)


def test_session_token_round_trip() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    chat_id = uuid4()

    token = create_session_token(
        user_id=user_id,
        max_user_id="max-user-001",
        roles=["member"],
        organization_id=organization_id,
        chat_id=chat_id,
        ttl_seconds=600,
        secret=TEST_SESSION_SECRET,
        now_ts=1_000,
    )
    principal = verify_session_token(token, secret=TEST_SESSION_SECRET, now_ts=1_100)

    assert principal.user_id == user_id
    assert principal.max_user_id == "max-user-001"
    assert principal.roles == ("member",)
    assert principal.organization_id == organization_id
    assert principal.chat_id == chat_id
    assert principal.issued_at == 1_000
    assert principal.expires_at == 1_600


def test_expired_session_token_is_rejected() -> None:
    token = create_session_token(
        user_id=uuid4(),
        max_user_id="max-user-001",
        roles=["member"],
        ttl_seconds=10,
        secret=TEST_SESSION_SECRET,
        now_ts=1_000,
    )

    with pytest.raises(WebAppSessionError, match="expired"):
        verify_session_token(token, secret=TEST_SESSION_SECRET, now_ts=1_011)


def test_tampered_session_token_is_rejected() -> None:
    token = create_session_token(
        user_id=uuid4(),
        max_user_id="max-user-001",
        roles=["member"],
        ttl_seconds=600,
        secret=TEST_SESSION_SECRET,
        now_ts=1_000,
    )
    tampered_token = token.replace("a", "b", 1)

    with pytest.raises(WebAppSessionError, match="Invalid WebApp session"):
        verify_session_token(tampered_token, secret=TEST_SESSION_SECRET, now_ts=1_100)


def test_session_error_does_not_include_secret() -> None:
    with pytest.raises(WebAppSessionError) as exc_info:
        verify_session_token("invalid", secret=TEST_SESSION_SECRET, now_ts=1_100)

    assert TEST_SESSION_SECRET not in str(exc_info.value)


def _build_init_data(
    *,
    credential: str,
    user: dict[str, object],
    auth_date: int,
) -> str:
    params = {
        "auth_date": str(auth_date),
        "user": json.dumps(user, sort_keys=True, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", credential.encode("utf-8"), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return parse.urlencode(params)
