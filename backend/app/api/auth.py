from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_auth_context
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.auth.context import AuthContext
from app.modules.auth.max_webapp import MaxWebAppAuthError, verify_max_webapp_init_data
from app.modules.auth.session import (
    WebAppSessionError,
    create_session_token,
    get_webapp_session_secret,
)
from app.modules.auth.webapp_service import (
    MaxWebAppAuthService,
    WebAppAuthenticatedUser,
    WebAppAuthServiceError,
)
from app.modules.chats.repository import ChatRepository
from app.modules.users.repository import UserRepository

router = APIRouter(tags=["auth"])


class MaxWebAppSessionCreate(BaseModel):
    init_data: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_init_data_alias(cls, data: object) -> object:
        if isinstance(data, dict) and "initData" in data and "init_data" not in data:
            normalized_data = dict(data)
            normalized_data["init_data"] = normalized_data["initData"]
            return normalized_data
        return data


class AuthUserRead(BaseModel):
    id: UUID
    display_name: str
    username: str | None
    roles: list[str]


class AuthChatRead(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    role: str


class AuthContextRead(BaseModel):
    organization_id: UUID | None
    chat_id: UUID | None
    available_chats: list[AuthChatRead]


class AuthSessionRead(BaseModel):
    user: AuthUserRead
    context: AuthContextRead
    session_expires_at: datetime | None = None


class AuthLogoutRead(BaseModel):
    status: str


def get_max_webapp_auth_service(
    session: AsyncSession = Depends(get_session),
) -> MaxWebAppAuthService:
    return MaxWebAppAuthService(
        user_repository=UserRepository(session),
        chat_repository=ChatRepository(session),
        session=session,
    )


@router.post("/max-webapp/session", response_model=AuthSessionRead)
async def create_max_webapp_session(
    payload: MaxWebAppSessionCreate,
    response: Response,
    settings: Settings = Depends(get_settings),
    service: MaxWebAppAuthService = Depends(get_max_webapp_auth_service),
) -> AuthSessionRead:
    if not settings.max_webapp_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MAX WebApp auth is disabled",
        )
    try:
        verified_user = verify_max_webapp_init_data(
            payload.init_data,
            bot_credential=settings.max_bot_token,
            max_age_seconds=settings.max_webapp_initdata_max_age_seconds,
        )
        authenticated_user = await service.resolve_verified_user(verified_user)
        session_secret = get_webapp_session_secret(settings)
    except MaxWebAppAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except WebAppSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MAX WebApp session is not configured",
        ) from exc

    issued_at = int(datetime.now(tz=UTC).timestamp())
    expires_at = issued_at + settings.max_webapp_session_ttl_seconds
    signed_session = create_session_token(
        user_id=authenticated_user.user.id,
        max_user_id=verified_user.max_user_id,
        roles=authenticated_user.roles,
        organization_id=authenticated_user.organization_id,
        chat_id=authenticated_user.chat_id,
        ttl_seconds=settings.max_webapp_session_ttl_seconds,
        secret=session_secret,
        now_ts=issued_at,
    )
    _set_session_cookie(
        response=response,
        settings=settings,
        signed_session=signed_session,
        max_age=settings.max_webapp_session_ttl_seconds,
    )
    return _build_session_response(
        authenticated_user,
        session_expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
    )


@router.get("/me", response_model=AuthSessionRead)
async def get_current_user(
    auth_context: AuthContext = Depends(get_auth_context),
    service: MaxWebAppAuthService = Depends(get_max_webapp_auth_service),
) -> AuthSessionRead:
    try:
        authenticated_user = await service.get_authenticated_user(auth_context.user_id)
    except WebAppAuthServiceError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WebApp session") from exc
    session_expires_at = (
        datetime.fromtimestamp(auth_context.session_expires_at, tz=UTC)
        if auth_context.session_expires_at
        else None
    )
    return _build_session_response(authenticated_user, session_expires_at=session_expires_at)


@router.post("/logout", response_model=AuthLogoutRead)
def logout(response: Response, settings: Settings = Depends(get_settings)) -> AuthLogoutRead:
    response.delete_cookie(
        key=settings.max_webapp_session_cookie_name,
        path="/",
        secure=settings.max_webapp_cookie_secure,
        samesite=settings.max_webapp_cookie_samesite,
    )
    return AuthLogoutRead(status="ok")


def _set_session_cookie(
    *,
    response: Response,
    settings: Settings,
    signed_session: str,
    max_age: int,
) -> None:
    response.set_cookie(
        key=settings.max_webapp_session_cookie_name,
        value=signed_session,
        max_age=max_age,
        path="/",
        httponly=True,
        secure=settings.max_webapp_cookie_secure,
        samesite=settings.max_webapp_cookie_samesite,
    )


def _build_session_response(
    authenticated_user: WebAppAuthenticatedUser,
    *,
    session_expires_at: datetime | None,
) -> AuthSessionRead:
    return AuthSessionRead(
        user=AuthUserRead(
            id=authenticated_user.user.id,
            display_name=authenticated_user.user.display_name,
            username=authenticated_user.user.username,
            roles=authenticated_user.roles,
        ),
        context=AuthContextRead(
            organization_id=authenticated_user.organization_id,
            chat_id=authenticated_user.chat_id,
            available_chats=[
                AuthChatRead(
                    id=chat.id,
                    organization_id=chat.organization_id,
                    title=chat.title,
                    role=chat.role,
                )
                for chat in authenticated_user.available_chats
            ],
        ),
        session_expires_at=session_expires_at,
    )
