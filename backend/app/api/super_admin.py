from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
import hmac
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.auth.super_admin import (
    SuperAdminAuthError,
    SuperAdminPrincipal,
    create_super_admin_session_token,
    credentials_configured,
    verify_login_password,
    verify_super_admin_session_token,
)
from app.modules.chats.repository import ChatRepository
from app.modules.chats.schemas import ChatConnectionStatus
from app.modules.chats.super_admin_schemas import (
    SuperAdminChatDisplayTitleUpdate,
    SuperAdminChatMemberRead,
    SuperAdminChatMemberRoleUpdate,
    SuperAdminChatRead,
    SuperAdminChatSettingsUpdate,
    SuperAdminMaxChatInfoSyncRead,
    SuperAdminChatStatusUpdate,
    SuperAdminLoginRequest,
    SuperAdminLogoutRead,
    SuperAdminMaxAdminSyncRead,
    SuperAdminSessionRead,
)
from app.modules.chats.super_admin_service import SuperAdminChatService
from app.modules.integrations.max.client import MaxApiClient

logger = logging.getLogger(__name__)
router = APIRouter(tags=["super-admin"])


class SuperAdminStatusRead(BaseModel):
    status: str
    module: str


def get_super_admin_chat_service(
    session: AsyncSession = Depends(get_session),
) -> SuperAdminChatService:
    return SuperAdminChatService(
        repository=ChatRepository(session),
        session=session,
    )


def get_max_api_client(settings: Settings = Depends(get_settings)) -> Iterator[MaxApiClient]:
    with MaxApiClient(settings=settings) as client:
        yield client


def get_super_admin_principal(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> SuperAdminPrincipal:
    session_token = request.cookies.get(settings.super_admin_session_cookie_name)
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Super-admin login required")
    if not settings.super_admin_session_secret.get_secret_value():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Super-admin auth is not configured")
    try:
        return verify_super_admin_session_token(
            session_token,
            secret=settings.super_admin_session_secret,
        )
    except SuperAdminAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid super-admin session") from exc


@router.get("/status", response_model=SuperAdminStatusRead)
def super_admin_status(
    _principal: SuperAdminPrincipal = Depends(get_super_admin_principal),
) -> SuperAdminStatusRead:
    return SuperAdminStatusRead(status="ok", module="super-admin")


@router.post("/login", response_model=SuperAdminSessionRead)
def login_super_admin(
    payload: SuperAdminLoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> SuperAdminSessionRead:
    if not credentials_configured(
        settings.super_admin_login,
        settings.super_admin_password,
        settings.super_admin_session_secret,
    ):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Super-admin auth is not configured")
    supplied_login = payload.login.strip()
    supplied_password = payload.password.strip()
    if not verify_login_password(
        supplied_login,
        supplied_password,
        settings.super_admin_login,
        settings.super_admin_password,
    ):
        _log_super_admin_login_diagnostic(payload, supplied_login, supplied_password, settings)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login or password")
    issued_at = int(datetime.now(tz=UTC).timestamp())
    expires_at = issued_at + settings.super_admin_session_ttl_seconds
    session_token = create_super_admin_session_token(
        login=settings.super_admin_login,
        ttl_seconds=settings.super_admin_session_ttl_seconds,
        secret=settings.super_admin_session_secret,
        now_ts=issued_at,
    )
    _set_super_admin_cookie(response, settings, session_token)
    return SuperAdminSessionRead(
        authenticated=True,
        login=settings.super_admin_login,
        session_expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
    )


@router.get("/session", response_model=SuperAdminSessionRead)
def get_super_admin_session(
    principal: SuperAdminPrincipal = Depends(get_super_admin_principal),
) -> SuperAdminSessionRead:
    return SuperAdminSessionRead(
        authenticated=True,
        login=principal.login,
        session_expires_at=datetime.fromtimestamp(principal.expires_at, tz=UTC),
    )


@router.post("/logout", response_model=SuperAdminLogoutRead)
def logout_super_admin(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> SuperAdminLogoutRead:
    response.delete_cookie(
        key=settings.super_admin_session_cookie_name,
        path="/",
        secure=settings.super_admin_cookie_secure,
        samesite=settings.super_admin_cookie_samesite,
    )
    return SuperAdminLogoutRead(status="ok")


@router.get("/chats", response_model=list[SuperAdminChatRead])
async def list_super_admin_chats(
    status_filter: str | None = Query(default=None, alias="status"),
    _principal: SuperAdminPrincipal = Depends(get_super_admin_principal),
    service: SuperAdminChatService = Depends(get_super_admin_chat_service),
) -> list[SuperAdminChatRead]:
    return await service.list_chats(status_filter=_normalize_chat_status_filter(status_filter))


@router.get("/chats/{chat_id}/members", response_model=list[SuperAdminChatMemberRead])
async def list_super_admin_chat_members(
    chat_id: UUID,
    _principal: SuperAdminPrincipal = Depends(get_super_admin_principal),
    service: SuperAdminChatService = Depends(get_super_admin_chat_service),
) -> list[SuperAdminChatMemberRead]:
    return await service.list_members(chat_id)


@router.patch("/chats/{chat_id}/status", response_model=SuperAdminChatRead)
async def update_super_admin_chat_status(
    chat_id: UUID,
    payload: SuperAdminChatStatusUpdate,
    principal: SuperAdminPrincipal = Depends(get_super_admin_principal),
    service: SuperAdminChatService = Depends(get_super_admin_chat_service),
) -> SuperAdminChatRead:
    return await service.update_status(chat_id=chat_id, payload=payload, actor_login=principal.login)


@router.patch("/chats/{chat_id}/display-title", response_model=SuperAdminChatRead)
async def update_super_admin_chat_display_title(
    chat_id: UUID,
    payload: SuperAdminChatDisplayTitleUpdate,
    principal: SuperAdminPrincipal = Depends(get_super_admin_principal),
    service: SuperAdminChatService = Depends(get_super_admin_chat_service),
) -> SuperAdminChatRead:
    return await service.update_display_title(chat_id=chat_id, payload=payload, actor_login=principal.login)


@router.patch("/chats/{chat_id}/settings", response_model=SuperAdminChatRead)
async def update_super_admin_chat_settings(
    chat_id: UUID,
    payload: SuperAdminChatSettingsUpdate,
    principal: SuperAdminPrincipal = Depends(get_super_admin_principal),
    service: SuperAdminChatService = Depends(get_super_admin_chat_service),
) -> SuperAdminChatRead:
    return await service.update_settings(chat_id=chat_id, payload=payload, actor_login=principal.login)


@router.patch("/chats/{chat_id}/members/{user_id}/role", response_model=SuperAdminChatMemberRead)
async def update_super_admin_chat_member_role(
    chat_id: UUID,
    user_id: UUID,
    payload: SuperAdminChatMemberRoleUpdate,
    principal: SuperAdminPrincipal = Depends(get_super_admin_principal),
    service: SuperAdminChatService = Depends(get_super_admin_chat_service),
) -> SuperAdminChatMemberRead:
    return await service.update_member_role(
        chat_id=chat_id,
        user_id=user_id,
        payload=payload,
        actor_login=principal.login,
    )


@router.post("/chats/{chat_id}/sync-max-admins", response_model=SuperAdminMaxAdminSyncRead)
async def sync_super_admin_chat_max_admins(
    chat_id: UUID,
    principal: SuperAdminPrincipal = Depends(get_super_admin_principal),
    service: SuperAdminChatService = Depends(get_super_admin_chat_service),
    max_client: MaxApiClient = Depends(get_max_api_client),
) -> SuperAdminMaxAdminSyncRead:
    return await service.sync_max_admins(chat_id=chat_id, actor_login=principal.login, max_client=max_client)


@router.post("/chats/{chat_id}/sync-max-chat-info", response_model=SuperAdminMaxChatInfoSyncRead)
async def sync_super_admin_chat_max_info(
    chat_id: UUID,
    principal: SuperAdminPrincipal = Depends(get_super_admin_principal),
    service: SuperAdminChatService = Depends(get_super_admin_chat_service),
    max_client: MaxApiClient = Depends(get_max_api_client),
) -> SuperAdminMaxChatInfoSyncRead:
    return await service.sync_max_chat_info(chat_id=chat_id, actor_login=principal.login, max_client=max_client)


def _log_super_admin_login_diagnostic(
    payload: SuperAdminLoginRequest,
    supplied_login: str,
    supplied_password: str,
    settings: Settings,
) -> None:
    if not settings.super_admin_login_diagnostic:
        return

    env_password = settings.super_admin_password.get_secret_value()
    login_matches = hmac.compare_digest(payload.login, settings.super_admin_login)
    password_matches = hmac.compare_digest(payload.password, env_password)
    trimmed_login_matches = hmac.compare_digest(supplied_login, settings.super_admin_login)
    trimmed_password_matches = hmac.compare_digest(supplied_password, env_password)

    logger.warning(
        "event=super_admin_login_failed_diagnostic "
        "input_login_len=%s input_password_len=%s "
        "env_login_len=%s env_password_len=%s "
        "login_matches_env=%s password_matches_env=%s "
        "trimmed_login_matches_env=%s trimmed_password_matches_env=%s",
        len(payload.login),
        len(payload.password),
        len(settings.super_admin_login),
        len(env_password),
        _bool_label(login_matches),
        _bool_label(password_matches),
        _bool_label(trimmed_login_matches),
        _bool_label(trimmed_password_matches),
        extra={
            "event": "super_admin_login_failed_diagnostic",
            "input_login_len": len(payload.login),
            "input_password_len": len(payload.password),
            "env_login_len": len(settings.super_admin_login),
            "env_password_len": len(env_password),
            "login_matches_env": login_matches,
            "password_matches_env": password_matches,
            "trimmed_login_matches_env": trimmed_login_matches,
            "trimmed_password_matches_env": trimmed_password_matches,
        },
    )


def _bool_label(value: bool) -> str:
    return "true" if value else "false"


def _normalize_chat_status_filter(value: str | None) -> ChatConnectionStatus | None:
    if value is None or not value.strip() or value == "all":
        return None
    normalized = value.strip()
    if normalized == "pending":
        normalized = ChatConnectionStatus.pending_approval.value
    try:
        return ChatConnectionStatus(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid chat status filter") from exc


def _set_super_admin_cookie(
    response: Response,
    settings: Settings,
    session_token: str,
) -> None:
    response.set_cookie(
        key=settings.super_admin_session_cookie_name,
        value=session_token,
        max_age=settings.super_admin_session_ttl_seconds,
        path="/",
        httponly=True,
        secure=settings.super_admin_cookie_secure,
        samesite=settings.super_admin_cookie_samesite,
    )
