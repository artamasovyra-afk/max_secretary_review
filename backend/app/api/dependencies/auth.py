from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException, Request, status

from app.core.config import get_settings
from app.modules.auth.context import AuthContext
from app.modules.auth.session import (
    WebAppSessionError,
    get_webapp_session_secret,
    verify_session_token,
)

HEADER_AUTH_ALWAYS_ALLOWED_ENVS = frozenset({"local", "test"})
HEADER_AUTH_OPT_IN_ENVS = frozenset({"dev", "development"})


def get_auth_context(
    request: Request,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_chat_id: Annotated[str | None, Header(alias="X-Chat-Id")] = None,
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-Id")] = None,
    x_roles: Annotated[str | None, Header(alias="X-Roles")] = None,
) -> AuthContext:
    settings = get_settings()
    session_context = _get_webapp_session_context(request)
    if session_context is not None:
        return session_context

    if not _dev_header_auth_allowed(settings.app_env, settings.dev_auth_enabled):
        raise _unauthorized("Header auth is disabled")
    if not x_user_id:
        raise _unauthorized("Authentication context is required")

    roles = _parse_roles_header(x_roles)
    return AuthContext(
        user_id=_parse_uuid_header("X-User-Id", x_user_id),
        organization_id=_parse_optional_uuid_header("X-Organization-Id", x_organization_id),
        chat_id=_parse_optional_uuid_header("X-Chat-Id", x_chat_id),
        roles=roles,
        is_super_admin="super_admin" in roles,
    )


def _get_webapp_session_context(request: Request) -> AuthContext | None:
    settings = get_settings()
    if not settings.max_webapp_auth_enabled:
        return None
    session_token = request.cookies.get(settings.max_webapp_session_cookie_name)
    if not session_token:
        return None
    try:
        principal = verify_session_token(
            session_token,
            secret=get_webapp_session_secret(settings),
        )
    except WebAppSessionError as exc:
        raise _unauthorized("Invalid WebApp session") from exc
    roles = list(principal.roles)
    return AuthContext(
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        chat_id=principal.chat_id,
        roles=roles,
        is_super_admin="super_admin" in roles,
        max_user_id=principal.max_user_id,
        session_expires_at=principal.expires_at,
    )


def _dev_header_auth_allowed(app_env: str, dev_auth_enabled: bool) -> bool:
    normalized_env = app_env.strip().lower()
    return normalized_env in HEADER_AUTH_ALWAYS_ALLOWED_ENVS or (
        dev_auth_enabled and normalized_env in HEADER_AUTH_OPT_IN_ENVS
    )


def _parse_optional_uuid_header(header_name: str, value: str | None) -> UUID | None:
    if not value:
        return None
    return _parse_uuid_header(header_name, value)


def _parse_uuid_header(header_name: str, value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise _unauthorized(f"{header_name} must be a valid UUID") from exc


def _parse_roles_header(value: str | None) -> list[str]:
    if not value:
        return []
    return [role.strip() for role in value.split(",") if role.strip()]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
