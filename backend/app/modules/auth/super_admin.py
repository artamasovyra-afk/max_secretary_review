from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import hashlib
import hmac
import json
import time

from pydantic import SecretStr

SESSION_TOKEN_VERSION = 1


class SuperAdminAuthError(ValueError):
    """Raised when a super-admin session cannot be trusted."""


@dataclass(frozen=True)
class SuperAdminPrincipal:
    login: str
    issued_at: int
    expires_at: int


def create_super_admin_session_token(
    *,
    login: str,
    ttl_seconds: int,
    secret: SecretStr | str,
    now_ts: int | None = None,
) -> str:
    issued_at = int(time.time()) if now_ts is None else now_ts
    expires_at = issued_at + ttl_seconds
    claims = {
        "v": SESSION_TOKEN_VERSION,
        "login": login,
        "iat": issued_at,
        "exp": expires_at,
    }
    payload = _base64url_encode(
        json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = _sign_payload(payload, _secret_value(secret))
    return f"{payload}.{signature}"


def verify_super_admin_session_token(
    token: str,
    *,
    secret: SecretStr | str,
    now_ts: int | None = None,
) -> SuperAdminPrincipal:
    if not token or "." not in token:
        raise SuperAdminAuthError("Invalid super-admin session")
    payload, supplied_signature = token.split(".", 1)
    expected_signature = _sign_payload(payload, _secret_value(secret))
    if not hmac.compare_digest(expected_signature, supplied_signature):
        raise SuperAdminAuthError("Invalid super-admin session")

    claims = _decode_claims(payload)
    current_ts = int(time.time()) if now_ts is None else now_ts
    expires_at = _required_int(claims, "exp")
    if expires_at <= current_ts:
        raise SuperAdminAuthError("Super-admin session expired")
    if claims.get("v") != SESSION_TOKEN_VERSION:
        raise SuperAdminAuthError("Unsupported super-admin session")
    return SuperAdminPrincipal(
        login=_required_string(claims, "login"),
        issued_at=_required_int(claims, "iat"),
        expires_at=expires_at,
    )


def credentials_configured(login: str, password: SecretStr, secret: SecretStr) -> bool:
    return bool(login.strip() and password.get_secret_value() and secret.get_secret_value())


def verify_login_password(
    supplied_login: str,
    supplied_password: str,
    expected_login: str,
    expected_password: SecretStr,
) -> bool:
    return hmac.compare_digest(supplied_login, expected_login) and hmac.compare_digest(
        supplied_password,
        expected_password.get_secret_value(),
    )


def _sign_payload(payload: str, secret: str) -> str:
    if not secret:
        raise SuperAdminAuthError("Super-admin session is not configured")
    digest = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return _base64url_encode(digest)


def _secret_value(secret: SecretStr | str) -> str:
    if isinstance(secret, SecretStr):
        return secret.get_secret_value()
    return secret


def _decode_claims(payload: str) -> dict[str, object]:
    try:
        decoded = _base64url_decode(payload)
        claims = json.loads(decoded)
    except (binascii.Error, ValueError, json.JSONDecodeError) as exc:
        raise SuperAdminAuthError("Invalid super-admin session") from exc
    if not isinstance(claims, dict):
        raise SuperAdminAuthError("Invalid super-admin session")
    return claims


def _required_string(claims: dict[str, object], key: str) -> str:
    value = claims.get(key)
    if not isinstance(value, str) or not value:
        raise SuperAdminAuthError("Invalid super-admin session")
    return value


def _required_int(claims: dict[str, object], key: str) -> int:
    value = claims.get(key)
    if not isinstance(value, int):
        raise SuperAdminAuthError("Invalid super-admin session")
    return value


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)
