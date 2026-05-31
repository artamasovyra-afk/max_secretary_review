from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_auth_context
from app.db.session import get_session
from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN
from app.modules.chats.repository import ChatRepository
from app.modules.chats.schemas import (
    ChatCreate,
    ChatMemberCreate,
    ChatMemberRead,
    ChatMemberUpdate,
    ChatRead,
    ChatStatus,
    ChatUpdate,
)
from app.modules.chats.service import ChatService
from app.modules.reminders.repository import ReminderRepository
from app.modules.reminders.schemas import ReminderRuleCreate, ReminderRuleRead
from app.modules.reminders.service import ReminderService

router = APIRouter(tags=["chats"], dependencies=[Depends(get_auth_context)])


def get_chat_service(
    session: AsyncSession = Depends(get_session),
) -> ChatService:
    return ChatService(
        repository=ChatRepository(session),
        session=session,
    )


def get_reminder_service(
    session: AsyncSession = Depends(get_session),
) -> ReminderService:
    return ReminderService(
        repository=ReminderRepository(session),
        session=session,
    )


@router.get("/status", response_model=ChatStatus)
def chats_status() -> ChatStatus:
    return ChatStatus(status="ok", module="chats")


@router.post("", response_model=ChatRead, status_code=status.HTTP_201_CREATED)
async def create_chat(
    payload: ChatCreate,
    service: ChatService = Depends(get_chat_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ChatRead:
    _ensure_chat_admin(auth_context)
    _ensure_organization_scope(auth_context, payload.organization_id)
    return await service.create(payload)


@router.get("", response_model=list[ChatRead])
async def list_chats(
    service: ChatService = Depends(get_chat_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> list[ChatRead]:
    return await service.list_for_auth_context(auth_context)


@router.get("/{chat_id}", response_model=ChatRead)
async def get_chat(
    chat_id: UUID,
    service: ChatService = Depends(get_chat_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ChatRead:
    chat = await service.get(chat_id)
    _ensure_chat_scope(auth_context, chat.id, chat.organization_id)
    return chat


@router.patch("/{chat_id}", response_model=ChatRead)
async def update_chat(
    chat_id: UUID,
    payload: ChatUpdate,
    service: ChatService = Depends(get_chat_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ChatRead:
    chat = await service.get(chat_id)
    _ensure_chat_manager(auth_context, chat.id)
    return await service.update(chat_id, payload)


@router.post(
    "/{chat_id}/reminder-rules",
    response_model=ReminderRuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_reminder_rule(
    chat_id: UUID,
    payload: ReminderRuleCreate,
    service: ReminderService = Depends(get_reminder_service),
    chat_service: ChatService = Depends(get_chat_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ReminderRuleRead:
    chat = await chat_service.get(chat_id)
    _ensure_chat_admin(auth_context)
    _ensure_chat_scope(auth_context, chat.id, chat.organization_id)
    return await service.create_chat_rule(chat_id, payload)


@router.get("/{chat_id}/reminder-rules", response_model=list[ReminderRuleRead])
async def list_chat_reminder_rules(
    chat_id: UUID,
    service: ReminderService = Depends(get_reminder_service),
    chat_service: ChatService = Depends(get_chat_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> list[ReminderRuleRead]:
    chat = await chat_service.get(chat_id)
    _ensure_chat_scope(auth_context, chat.id, chat.organization_id)
    return await service.list_chat_rules(chat_id)


@router.post(
    "/{chat_id}/members",
    response_model=ChatMemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_chat_member(
    chat_id: UUID,
    payload: ChatMemberCreate,
    service: ChatService = Depends(get_chat_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ChatMemberRead:
    chat = await service.get(chat_id)
    _ensure_chat_admin(auth_context)
    _ensure_chat_scope(auth_context, chat.id, chat.organization_id)
    return await service.add_member(chat_id, payload)


@router.get("/{chat_id}/members", response_model=list[ChatMemberRead])
async def list_chat_members(
    chat_id: UUID,
    service: ChatService = Depends(get_chat_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> list[ChatMemberRead]:
    chat = await service.get(chat_id)
    _ensure_chat_scope(auth_context, chat.id, chat.organization_id)
    return await service.list_members(chat_id)


@router.patch("/{chat_id}/members/{user_id}", response_model=ChatMemberRead)
async def update_chat_member(
    chat_id: UUID,
    user_id: UUID,
    payload: ChatMemberUpdate,
    service: ChatService = Depends(get_chat_service),
    auth_context: AuthContext = Depends(get_auth_context),
) -> ChatMemberRead:
    chat = await service.get(chat_id)
    _ensure_chat_admin(auth_context)
    _ensure_chat_scope(auth_context, chat.id, chat.organization_id)
    return await service.update_member(
        chat_id=chat_id,
        user_id=user_id,
        payload=payload,
    )


CHAT_ADMIN_ROLES = frozenset({ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN})
CHAT_VIEW_ROLES = frozenset({ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN})


def _is_super_admin(auth_context: AuthContext) -> bool:
    return auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN)


def _ensure_chat_admin(auth_context: AuthContext) -> None:
    if _is_super_admin(auth_context) or auth_context.has_any_role(CHAT_ADMIN_ROLES):
        return
    raise _forbidden("Chat admin role is required")


def _ensure_organization_scope(auth_context: AuthContext, organization_id: UUID) -> None:
    if _is_super_admin(auth_context):
        return
    if auth_context.organization_id is not None and auth_context.organization_id == organization_id:
        return
    raise _forbidden("Organization scope mismatch")


def _ensure_chat_scope(auth_context: AuthContext, chat_id: UUID, organization_id: UUID) -> None:
    if _is_super_admin(auth_context):
        return
    if auth_context.chat_id is not None and auth_context.chat_id == chat_id:
        return
    if (
        auth_context.organization_id is not None
        and auth_context.organization_id == organization_id
        and auth_context.has_any_role(CHAT_VIEW_ROLES)
    ):
        return
    raise _forbidden("Chat scope mismatch")


def _ensure_chat_manager(auth_context: AuthContext, chat_id: UUID) -> None:
    if _is_super_admin(auth_context):
        return
    if auth_context.chat_id == chat_id and auth_context.has_role(ROLE_CHAT_ADMIN):
        return
    raise _forbidden("Chat admin role is required for this chat")


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
