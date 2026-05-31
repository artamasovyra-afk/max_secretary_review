from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import time
from urllib import parse

from pydantic import SecretStr


class MaxWebAppAuthError(ValueError):
    """Raised when MAX WebApp initData cannot be trusted."""


@dataclass(frozen=True)
class VerifiedMaxWebAppUser:
    max_user_id: str
    display_name: str | None
    username: str | None
    auth_date: int


def parse_init_data(init_data: str) -> dict[str, str]:
    normalized_init_data = _unwrap_webapp_data(init_data.strip())
    params = parse.parse_qsl(normalized_init_data, keep_blank_values=True, strict_parsing=False)
    if not params:
        raise MaxWebAppAuthError("initData has no parameters")

    seen_keys: dict[str, int] = {}
    for key, _value in params:
        seen_keys[key] = seen_keys.get(key, 0) + 1
    duplicates = [key for key, count in seen_keys.items() if count != 1]
    if duplicates:
        raise MaxWebAppAuthError("initData contains duplicate keys")
    return dict(params)


def verify_max_webapp_init_data(
    init_data: str,
    *,
    bot_credential: SecretStr,
    max_age_seconds: int,
    now_ts: int | None = None,
) -> VerifiedMaxWebAppUser:
    if not init_data or not init_data.strip():
        raise MaxWebAppAuthError("initData is required")
    credential = bot_credential.get_secret_value()
    if not credential:
        raise MaxWebAppAuthError("MAX WebApp auth is not configured")

    raw_map = parse_init_data(init_data)
    supplied_hash = raw_map.get("hash")
    if not supplied_hash:
        raise MaxWebAppAuthError("initData hash is missing")

    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted((key, value) for key, value in raw_map.items() if key != "hash")
    )
    secret_key = hmac.new(b"WebAppData", credential.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, supplied_hash):
        raise MaxWebAppAuthError("initData signature mismatch")

    auth_date = _parse_auth_date(raw_map.get("auth_date"))
    current_ts = int(time.time()) if now_ts is None else now_ts
    if auth_date <= 0 or auth_date > current_ts + 60 or current_ts - auth_date > max_age_seconds:
        raise MaxWebAppAuthError("initData is expired")

    user_payload = _parse_user_payload(raw_map.get("user"))
    max_user_id = _extract_max_user_id(user_payload)
    return VerifiedMaxWebAppUser(
        max_user_id=max_user_id,
        display_name=_extract_display_name(user_payload),
        username=_safe_optional_string(user_payload.get("username")),
        auth_date=auth_date,
    )


def _unwrap_webapp_data(init_data: str) -> str:
    if "#" in init_data:
        fragment = init_data.split("#", 1)[1]
        top_level_map = dict(parse.parse_qsl(fragment, keep_blank_values=True))
        return top_level_map.get("WebAppData", "")
    if init_data.startswith("WebAppData="):
        top_level_map = dict(parse.parse_qsl(init_data, keep_blank_values=True))
        return top_level_map.get("WebAppData", "")
    return init_data


def _parse_auth_date(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError as exc:
        raise MaxWebAppAuthError("initData auth_date is invalid") from exc


def _parse_user_payload(value: str | None) -> dict[str, object]:
    if not value:
        raise MaxWebAppAuthError("initData user payload is missing")
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise MaxWebAppAuthError("initData user payload is invalid") from exc
    if not isinstance(payload, dict):
        raise MaxWebAppAuthError("initData user payload is invalid")
    return payload


def _extract_max_user_id(payload: dict[str, object]) -> str:
    for key in ("user_id", "userId", "id"):
        value = _safe_optional_string(payload.get(key))
        if value:
            return value
    raise MaxWebAppAuthError("initData user id is missing")


def _extract_display_name(payload: dict[str, object]) -> str | None:
    for key in ("display_name", "displayName", "name"):
        value = _safe_optional_string(payload.get(key))
        if value:
            return value
    first_name = _safe_optional_string(payload.get("first_name") or payload.get("firstName"))
    last_name = _safe_optional_string(payload.get("last_name") or payload.get("lastName"))
    joined_name = " ".join(part for part in (first_name, last_name) if part)
    if joined_name:
        return joined_name
    return _safe_optional_string(payload.get("username"))


def _safe_optional_string(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
