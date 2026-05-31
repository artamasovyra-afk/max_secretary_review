from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import hashlib
import hmac
import json
import time
from uuid import UUID

from pydantic import SecretStr

from app.core.config import PRODUCTION_APP_ENVS, Settings

DEV_WEBAPP_SESSION_SECRET = "dev-only-max-webapp-session-secret"
SESSION_TOKEN_VERSION = 1


class WebAppSessionError(ValueError):
    """Raised when a WebApp session token cannot be trusted."""


@dataclass(frozen=True)
class SessionPrincipal:
    user_id: UUID
    max_user_id: str
    roles: tuple[str, ...]
    issued_at: int
    expires_at: int
    organization_id: UUID | None = None
    chat_id: UUID | None = None


def get_webapp_session_secret(settings: Settings) -> str:
    secret = settings.max_webapp_session_secret.get_secret_value()
    if secret:
        return secret
    if settings.app_env.strip().lower() in PRODUCTION_APP_ENVS:
        raise WebAppSessionError("MAX WebApp session is not configured")
    return DEV_WEBAPP_SESSION_SECRET


def create_session_token(
    *,
    user_id: UUID,
    max_user_id: str,
    roles: list[str] | tuple[str, ...],
    ttl_seconds: int,
    secret: SecretStr | str,
    organization_id: UUID | None = None,
    chat_id: UUID | None = None,
    now_ts: int | None = None,
) -> str:
    issued_at = int(time.time()) if now_ts is None else now_ts
    expires_at = issued_at + ttl_seconds
    claims = {
        "v": SESSION_TOKEN_VERSION,
        "user_id": str(user_id),
        "max_user_id": max_user_id,
        "roles": list(roles),
        "iat": issued_at,
        "exp": expires_at,
        "organization_id": str(organization_id) if organization_id else None,
        "chat_id": str(chat_id) if chat_id else None,
    }
    payload = _base64url_encode(
        json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = _sign_payload(payload, _secret_value(secret))
    return f"{payload}.{signature}"


def verify_session_token(
    token: str,
    *,
    secret: SecretStr | str,
    now_ts: int | None = None,
) -> SessionPrincipal:
    if not token or "." not in token:
        raise WebAppSessionError("Invalid WebApp session")
    payload, supplied_signature = token.split(".", 1)
    expected_signature = _sign_payload(payload, _secret_value(secret))
    if not hmac.compare_digest(expected_signature, supplied_signature):
        raise WebAppSessionError("Invalid WebApp session")

    claims = _decode_claims(payload)
    current_ts = int(time.time()) if now_ts is None else now_ts
    expires_at = _required_int(claims, "exp")
    if expires_at <= current_ts:
        raise WebAppSessionError("WebApp session expired")
    if claims.get("v") != SESSION_TOKEN_VERSION:
        raise WebAppSessionError("Unsupported WebApp session")

    return SessionPrincipal(
        user_id=_required_uuid(claims, "user_id"),
        max_user_id=_required_string(claims, "max_user_id"),
        roles=tuple(_string_list(claims.get("roles"))),
        issued_at=_required_int(claims, "iat"),
        expires_at=expires_at,
        organization_id=_optional_uuid(claims.get("organization_id")),
        chat_id=_optional_uuid(claims.get("chat_id")),
    )


def _sign_payload(payload: str, secret: str) -> str:
    if not secret:
        raise WebAppSessionError("MAX WebApp session is not configured")
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
        raise WebAppSessionError("Invalid WebApp session") from exc
    if not isinstance(claims, dict):
        raise WebAppSessionError("Invalid WebApp session")
    return claims


def _required_uuid(claims: dict[str, object], key: str) -> UUID:
    value = _required_string(claims, key)
    try:
        return UUID(value)
    except ValueError as exc:
        raise WebAppSessionError("Invalid WebApp session") from exc


def _optional_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(_required_string({"value": value}, "value"))
    except ValueError as exc:
        raise WebAppSessionError("Invalid WebApp session") from exc


def _required_string(claims: dict[str, object], key: str) -> str:
    value = claims.get(key)
    if not isinstance(value, str) or not value:
        raise WebAppSessionError("Invalid WebApp session")
    return value


def _required_int(claims: dict[str, object], key: str) -> int:
    value = claims.get(key)
    if not isinstance(value, int):
        raise WebAppSessionError("Invalid WebApp session")
    return value


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)
