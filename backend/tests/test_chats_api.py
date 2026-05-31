from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.api.chats import get_chat_service
from app.core.config import get_settings
from app.main import create_app
from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_SUPER_ADMIN
from app.modules.chats.schemas import (
    ChatCreate,
    ChatMemberCreate,
    ChatMemberUpdate,
    ChatUpdate,
)


class ChatRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    max_chat_id: Optional[str]
    title: str
    type: str
    status: str = "active"
    settings: Optional[dict[str, Any]]
    display_title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ChatMemberRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_id: UUID
    user_id: UUID
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FakeChatService:
    def __init__(self) -> None:
        self.chats: dict[UUID, ChatRecord] = {}
        self.members: dict[tuple[UUID, UUID], ChatMemberRecord] = {}

    async def create(self, payload: ChatCreate) -> ChatRecord:
        now = datetime.now(timezone.utc)
        chat = ChatRecord(
            id=uuid4(),
            organization_id=payload.organization_id,
            max_chat_id=payload.max_chat_id,
            title=payload.title,
            type=payload.type,
            status=payload.status.value,
            settings=payload.settings,
            created_at=now,
            updated_at=now,
        )
        self.chats[chat.id] = chat
        return chat

    async def list(self) -> list[ChatRecord]:
        return list(self.chats.values())

    async def list_for_auth_context(self, auth_context: AuthContext) -> list[ChatRecord]:
        if auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN):
            return await self.list()
        chats = [
            self.chats[member.chat_id]
            for member in self.members.values()
            if member.user_id == auth_context.user_id
            and member.is_active
            and member.chat_id in self.chats
        ]
        if auth_context.organization_id is not None:
            chats = [chat for chat in chats if chat.organization_id == auth_context.organization_id]
        return chats

    async def get(self, chat_id: UUID) -> ChatRecord:
        chat = self.chats.get(chat_id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found",
            )
        return chat

    async def update(self, chat_id: UUID, payload: ChatUpdate) -> ChatRecord:
        chat = await self.get(chat_id)
        values = payload.model_dump(exclude_unset=True)
        if "status" in values:
            values["status"] = values["status"].value
        if "display_title" in values:
            display_title = values.pop("display_title")
            settings = dict(values.get("settings") or chat.settings or {})
            if display_title:
                settings["display_title"] = display_title
            else:
                settings.pop("display_title", None)
            values["settings"] = settings or None
            values["display_title"] = display_title
        values["updated_at"] = datetime.now(timezone.utc)
        updated = chat.model_copy(update=values)
        self.chats[chat_id] = updated
        return updated

    async def add_member(self, chat_id: UUID, payload: ChatMemberCreate) -> ChatMemberRecord:
        await self.get(chat_id)
        member_key = (chat_id, payload.user_id)
        if member_key in self.members:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chat member already exists",
            )
        now = datetime.now(timezone.utc)
        member = ChatMemberRecord(
            id=uuid4(),
            chat_id=chat_id,
            user_id=payload.user_id,
            role=payload.role.value,
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
        self.members[member_key] = member
        return member

    async def list_members(self, chat_id: UUID) -> list[ChatMemberRecord]:
        await self.get(chat_id)
        return [
            member
            for (member_chat_id, _user_id), member in self.members.items()
            if member_chat_id == chat_id
        ]

    async def update_member(
        self,
        *,
        chat_id: UUID,
        user_id: UUID,
        payload: ChatMemberUpdate,
    ) -> ChatMemberRecord:
        await self.get(chat_id)
        member_key = (chat_id, user_id)
        member = self.members.get(member_key)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat member not found",
            )
        values = payload.model_dump(exclude_unset=True)
        if "role" in values:
            values["role"] = values["role"].value
        values["updated_at"] = datetime.now(timezone.utc)
        updated = member.model_copy(update=values)
        self.members[member_key] = updated
        return updated


def _auth_headers(
    *,
    user_id: UUID | None = None,
    organization_id: UUID | None = None,
    chat_id: UUID | None = None,
    roles: str = "super_admin",
) -> dict[str, str]:
    headers = {
        "X-User-Id": str(user_id or uuid4()),
        "X-Roles": roles,
    }
    if organization_id is not None:
        headers["X-Organization-Id"] = str(organization_id)
    if chat_id is not None:
        headers["X-Chat-Id"] = str(chat_id)
    return headers


@pytest.fixture()
def chats_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeChatService]:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    app = create_app()
    service = FakeChatService()
    app.dependency_overrides[get_chat_service] = lambda: service
    with TestClient(app, headers=_auth_headers()) as client:
        yield client, service


def create_chat_payload(organization_id: UUID) -> dict[str, Any]:
    return {
        "organization_id": str(organization_id),
        "max_chat_id": None,
        "title": "General",
        "type": "max_group",
        "settings": {"notifications": True},
    }


def test_create_chat(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    organization_id = uuid4()

    response = client.post("/api/chats", json=create_chat_payload(organization_id))

    assert response.status_code == 201
    payload = response.json()
    assert payload["organization_id"] == str(organization_id)
    assert payload["max_chat_id"] is None
    assert payload["title"] == "General"
    assert payload["type"] == "max_group"
    assert payload["settings"] == {"notifications": True}


def test_list_chats_requires_auth(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client

    with TestClient(client.app) as unauthenticated_client:
        response = unauthenticated_client.get("/api/chats")

    assert response.status_code == 401


def test_create_chat_requires_chat_admin(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    organization_id = uuid4()

    response = client.post(
        "/api/chats",
        json=create_chat_payload(organization_id),
        headers=_auth_headers(organization_id=organization_id, roles="member"),
    )

    assert response.status_code == 403


def test_chat_admin_can_add_member(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    organization_id = uuid4()
    created = client.post("/api/chats", json=create_chat_payload(organization_id)).json()
    user_id = uuid4()

    response = client.post(
        f"/api/chats/{created['id']}/members",
        json={"user_id": str(user_id), "role": "member", "is_active": True},
        headers=_auth_headers(
            organization_id=organization_id,
            chat_id=UUID(created["id"]),
            roles="chat_admin",
        ),
    )

    assert response.status_code == 201


def test_non_admin_cannot_add_chat_member(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    organization_id = uuid4()
    created = client.post("/api/chats", json=create_chat_payload(organization_id)).json()

    response = client.post(
        f"/api/chats/{created['id']}/members",
        json={"user_id": str(uuid4()), "role": "member", "is_active": True},
        headers=_auth_headers(
            organization_id=organization_id,
            chat_id=UUID(created["id"]),
            roles="member",
        ),
    )

    assert response.status_code == 403


def test_create_chat_requires_organization_id(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    payload = create_chat_payload(uuid4())
    payload.pop("organization_id")

    response = client.post("/api/chats", json=payload)

    assert response.status_code == 422


def test_list_chats(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    client.post("/api/chats", json=create_chat_payload(uuid4()))
    second_payload = create_chat_payload(uuid4())
    second_payload["title"] = "Operations"
    client.post("/api/chats", json=second_payload)

    response = client.get("/api/chats")

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["General", "Operations"]


def test_list_chats_for_member_returns_only_active_memberships(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    organization_id = uuid4()
    user_id = uuid4()
    accessible = client.post("/api/chats", json=create_chat_payload(organization_id)).json()
    inaccessible_payload = create_chat_payload(organization_id)
    inaccessible_payload["title"] = "Inaccessible"
    client.post("/api/chats", json=inaccessible_payload)
    inactive_payload = create_chat_payload(organization_id)
    inactive_payload["title"] = "Inactive"
    inactive = client.post("/api/chats", json=inactive_payload).json()
    client.post(
        f"/api/chats/{accessible['id']}/members",
        json={"user_id": str(user_id), "role": "member", "is_active": True},
    )
    client.post(
        f"/api/chats/{inactive['id']}/members",
        json={"user_id": str(user_id), "role": "member", "is_active": False},
    )

    response = client.get(
        "/api/chats",
        headers=_auth_headers(
            user_id=user_id,
            organization_id=organization_id,
            roles="member",
        ),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [accessible["id"]]


def test_list_chats_for_member_ignores_launch_chat_scope(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    organization_id = uuid4()
    user_id = uuid4()
    personal_payload = create_chat_payload(organization_id)
    personal_payload["title"] = "Personal"
    personal_chat = client.post("/api/chats", json=personal_payload).json()
    group_payload = create_chat_payload(organization_id)
    group_payload["title"] = "Group"
    group_chat = client.post("/api/chats", json=group_payload).json()
    inaccessible_payload = create_chat_payload(organization_id)
    inaccessible_payload["title"] = "Other"
    client.post("/api/chats", json=inaccessible_payload)
    for chat in (personal_chat, group_chat):
        client.post(
            f"/api/chats/{chat['id']}/members",
            json={"user_id": str(user_id), "role": "member", "is_active": True},
        )

    response = client.get(
        "/api/chats",
        headers=_auth_headers(
            user_id=user_id,
            organization_id=organization_id,
            chat_id=UUID(personal_chat["id"]),
            roles="member",
        ),
    )

    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {personal_chat["id"], group_chat["id"]}


def test_list_chats_for_chat_admin_returns_member_and_admin_chats(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    organization_id = uuid4()
    user_id = uuid4()
    admin_payload = create_chat_payload(organization_id)
    admin_payload["title"] = "Admin chat"
    admin_chat = client.post("/api/chats", json=admin_payload).json()
    member_payload = create_chat_payload(organization_id)
    member_payload["title"] = "Member chat"
    member_chat = client.post("/api/chats", json=member_payload).json()
    client.post(
        f"/api/chats/{admin_chat['id']}/members",
        json={"user_id": str(user_id), "role": "chat_admin", "is_active": True},
    )
    client.post(
        f"/api/chats/{member_chat['id']}/members",
        json={"user_id": str(user_id), "role": "member", "is_active": True},
    )

    response = client.get(
        "/api/chats",
        headers=_auth_headers(
            user_id=user_id,
            organization_id=organization_id,
            chat_id=UUID(admin_chat["id"]),
            roles="chat_admin,member",
        ),
    )

    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {admin_chat["id"], member_chat["id"]}


def test_list_chats_returns_display_title(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    organization_id = uuid4()
    user_id = uuid4()
    created = client.post("/api/chats", json=create_chat_payload(organization_id)).json()
    client.post(
        f"/api/chats/{created['id']}/members",
        json={"user_id": str(user_id), "role": "member", "is_active": True},
    )
    client.patch(
        f"/api/chats/{created['id']}",
        json={"display_title": "Тест Дьяк"},
    )

    response = client.get(
        "/api/chats",
        headers=_auth_headers(
            user_id=user_id,
            organization_id=organization_id,
            chat_id=UUID(created["id"]),
            roles="member",
        ),
    )

    assert response.status_code == 200
    assert response.json()[0]["display_title"] == "Тест Дьяк"


def test_list_chats_super_admin_still_sees_all(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    first = client.post("/api/chats", json=create_chat_payload(uuid4())).json()
    second_payload = create_chat_payload(uuid4())
    second_payload["title"] = "Operations"
    second = client.post("/api/chats", json=second_payload).json()

    response = client.get("/api/chats")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {first["id"], second["id"]}


def test_get_chat(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    created = client.post("/api/chats", json=create_chat_payload(uuid4())).json()

    response = client.get(f"/api/chats/{created['id']}")

    assert response.status_code == 200
    assert response.json()["title"] == "General"


def test_update_chat(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    created = client.post("/api/chats", json=create_chat_payload(uuid4())).json()

    response = client.patch(
        f"/api/chats/{created['id']}",
        json={
            "max_chat_id": "max-chat-1",
            "title": "Updated",
            "type": "max_channel",
            "settings": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["max_chat_id"] == "max-chat-1"
    assert payload["title"] == "Updated"
    assert payload["type"] == "max_channel"
    assert payload["settings"] is None


def test_chat_admin_can_update_own_chat_display_title(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    organization_id = uuid4()
    created = client.post("/api/chats", json=create_chat_payload(organization_id)).json()

    response = client.patch(
        f"/api/chats/{created['id']}",
        json={"display_title": " Тест секретарь "},
        headers=_auth_headers(
            organization_id=organization_id,
            chat_id=UUID(created["id"]),
            roles="chat_admin",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["display_title"] == "Тест секретарь"
    assert payload["settings"]["display_title"] == "Тест секретарь"
    assert payload["title"] == "General"


def test_member_cannot_update_chat_display_title(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    organization_id = uuid4()
    created = client.post("/api/chats", json=create_chat_payload(organization_id)).json()

    response = client.patch(
        f"/api/chats/{created['id']}",
        json={"display_title": "Тест секретарь"},
        headers=_auth_headers(
            organization_id=organization_id,
            chat_id=UUID(created["id"]),
            roles="member",
        ),
    )

    assert response.status_code == 403


def test_chat_admin_cannot_update_other_chat_display_title(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    organization_id = uuid4()
    own_chat = client.post("/api/chats", json=create_chat_payload(organization_id)).json()
    other_payload = create_chat_payload(organization_id)
    other_payload["title"] = "Other"
    other_chat = client.post("/api/chats", json=other_payload).json()

    response = client.patch(
        f"/api/chats/{other_chat['id']}",
        json={"display_title": "Чужой чат"},
        headers=_auth_headers(
            organization_id=organization_id,
            chat_id=UUID(own_chat["id"]),
            roles="chat_admin",
        ),
    )

    assert response.status_code == 403


def test_super_admin_can_update_any_chat_display_title(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    organization_id = uuid4()
    created = client.post("/api/chats", json=create_chat_payload(organization_id)).json()

    response = client.patch(
        f"/api/chats/{created['id']}",
        json={"display_title": "Тест секретарь"},
    )

    assert response.status_code == 200
    assert response.json()["display_title"] == "Тест секретарь"


def test_add_chat_member(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    created = client.post("/api/chats", json=create_chat_payload(uuid4())).json()
    user_id = uuid4()

    response = client.post(
        f"/api/chats/{created['id']}/members",
        json={"user_id": str(user_id), "role": "chat_admin", "is_active": True},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["chat_id"] == created["id"]
    assert payload["user_id"] == str(user_id)
    assert payload["role"] == "chat_admin"
    assert payload["is_active"] is True


def test_chat_member_role_manager_is_rejected(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    created = client.post("/api/chats", json=create_chat_payload(uuid4())).json()

    response = client.post(
        f"/api/chats/{created['id']}/members",
        json={"user_id": str(uuid4()), "role": "manager", "is_active": True},
    )

    assert response.status_code == 422


def test_list_chat_members(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    created = client.post("/api/chats", json=create_chat_payload(uuid4())).json()
    client.post(
        f"/api/chats/{created['id']}/members",
        json={"user_id": str(uuid4()), "role": "member", "is_active": True},
    )
    client.post(
        f"/api/chats/{created['id']}/members",
        json={"user_id": str(uuid4()), "role": "chat_admin", "is_active": True},
    )

    response = client.get(f"/api/chats/{created['id']}/members")

    assert response.status_code == 200
    assert [item["role"] for item in response.json()] == ["member", "chat_admin"]


def test_update_chat_member(chats_client: tuple[TestClient, FakeChatService]) -> None:
    client, _service = chats_client
    created = client.post("/api/chats", json=create_chat_payload(uuid4())).json()
    user_id = uuid4()
    client.post(
        f"/api/chats/{created['id']}/members",
        json={"user_id": str(user_id), "role": "member", "is_active": True},
    )

    response = client.patch(
        f"/api/chats/{created['id']}/members/{user_id}",
        json={"role": "super_admin", "is_active": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "super_admin"
    assert payload["is_active"] is False


def test_chat_member_role_must_be_known(
    chats_client: tuple[TestClient, FakeChatService],
) -> None:
    client, _service = chats_client
    created = client.post("/api/chats", json=create_chat_payload(uuid4())).json()

    response = client.post(
        f"/api/chats/{created['id']}/members",
        json={"user_id": str(uuid4()), "role": "owner", "is_active": True},
    )

    assert response.status_code == 422
