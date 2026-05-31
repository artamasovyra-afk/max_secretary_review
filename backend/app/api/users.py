from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_auth_context
from app.db.session import get_session
from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate, UserRead, UserStatus, UserUpdate
from app.modules.users.service import UserService

router = APIRouter(tags=["users"], dependencies=[Depends(get_auth_context)])


def get_user_service(
    session: AsyncSession = Depends(get_session),
) -> UserService:
    return UserService(
        repository=UserRepository(session),
        session=session,
    )


@router.get("/status", response_model=UserStatus)
def users_status() -> UserStatus:
    return UserStatus(status="ok", module="users")


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> UserRead:
    _ensure_admin(auth_context)
    return await service.create(payload)


@router.get("", response_model=list[UserRead])
async def list_users(
    service: UserService = Depends(get_user_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> list[UserRead]:
    _ensure_admin(auth_context)
    return await service.list()


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    service: UserService = Depends(get_user_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> UserRead:
    _ensure_self_or_admin(auth_context, user_id)
    return await service.get(user_id)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    service: UserService = Depends(get_user_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> UserRead:
    _ensure_self_or_admin(auth_context, user_id)
    return await service.update(user_id, payload)


ADMIN_ROLES = frozenset({ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN})


def _is_admin(auth_context: AuthContext) -> bool:
    return auth_context.is_super_admin or auth_context.has_any_role(ADMIN_ROLES)


def _ensure_admin(auth_context: AuthContext) -> None:
    if not _is_admin(auth_context):
        raise _forbidden("Admin role is required")


def _ensure_self_or_admin(auth_context: AuthContext, user_id: UUID) -> None:
    if _is_admin(auth_context) or auth_context.user_id == user_id:
        return
    raise _forbidden("User scope mismatch")


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
