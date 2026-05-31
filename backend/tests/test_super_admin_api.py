from __future__ import annotations

from datetime import datetime, timezone
import logging
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from httpx import Response

from app.api.super_admin import get_max_api_client, get_super_admin_chat_service
from app.core.config import get_settings
from app.main import create_app
from app.modules.chats.super_admin_service import SuperAdminChatService
from app.modules.chats.schemas import ChatConnectionStatus, ChatMemberRole
from app.modules.chats.super_admin_schemas import (
    SuperAdminChatDisplayTitleUpdate,
    SuperAdminChatMemberRead,
    SuperAdminChatMemberRoleUpdate,
    SuperAdminChatRead,
    SuperAdminChatSettingsUpdate,
    SuperAdminMaxChatInfoSyncRead,
    SuperAdminChatStatusUpdate,
)
from app.modules.integrations.max.exceptions import MaxApiHTTPError


class FakeSuperAdminChatService:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.chat_id = uuid4()
        self.second_chat_id = uuid4()
        self.user_id = uuid4()
        self.second_user_id = uuid4()
        self.chats: dict[UUID, SuperAdminChatRead] = {
            self.chat_id: SuperAdminChatRead(
                id=self.chat_id,
                display_title="Тест Дьяк",
                display_title_source="fallback",
                status=ChatConnectionStatus.pending_approval,
                type="max_group",
                deadline_reminders_enabled=False,
                members_count=2,
                chat_admins_count=0,
                max_admins_count=None,
                created_at=now,
                updated_at=now,
            ),
            self.second_chat_id: SuperAdminChatRead(
                id=self.second_chat_id,
                display_title="Подключенный чат",
                display_title_source="real",
                status=ChatConnectionStatus.active,
                type="max_group",
                deadline_reminders_enabled=False,
                members_count=1,
                chat_admins_count=1,
                max_admins_count=None,
                created_at=now,
                updated_at=now,
            ),
        }
        self.members: dict[UUID, list[SuperAdminChatMemberRead]] = {
            self.chat_id: [
                SuperAdminChatMemberRead(
                    id=uuid4(),
                    user_id=self.user_id,
                    display_name="Иван Иванов",
                    username="ivan",
                    role_in_dyak=ChatMemberRole.member,
                    is_active=True,
                    is_max_chat_admin=None,
                    has_max_user_id=True,
                    updated_at=now,
                ),
                SuperAdminChatMemberRead(
                    id=uuid4(),
                    user_id=self.second_user_id,
                    display_name="Мария Петрова",
                    username=None,
                    role_in_dyak=ChatMemberRole.member,
                    is_active=True,
                    is_max_chat_admin=True,
                    has_max_user_id=True,
                    updated_at=now,
                ),
            ],
            self.second_chat_id: [
                SuperAdminChatMemberRead(
                    id=uuid4(),
                    user_id=self.user_id,
                    display_name="Иван Иванов",
                    username="ivan",
                    role_in_dyak=ChatMemberRole.chat_admin,
                    is_active=True,
                    is_max_chat_admin=None,
                    has_max_user_id=True,
                    updated_at=now,
                )
            ],
        }

    async def list_chats(
        self,
        *,
        status_filter: ChatConnectionStatus | None = None,
    ) -> list[SuperAdminChatRead]:
        chats = list(self.chats.values())
        if status_filter is not None:
            chats = [chat for chat in chats if chat.status == status_filter]
        return chats

    async def list_members(self, chat_id: UUID) -> list[SuperAdminChatMemberRead]:
        return self.members.get(chat_id, [])

    async def update_status(
        self,
        *,
        chat_id: UUID,
        payload: SuperAdminChatStatusUpdate,
        actor_login: str,
    ) -> SuperAdminChatRead:
        chat = self.chats[chat_id]
        updated = chat.model_copy(update={"status": payload.status})
        self.chats[chat_id] = updated
        return updated

    async def update_display_title(
        self,
        *,
        chat_id: UUID,
        payload: SuperAdminChatDisplayTitleUpdate,
        actor_login: str,
    ) -> SuperAdminChatRead:
        chat = self.chats[chat_id]
        updated = chat.model_copy(
            update={
                "display_title": payload.display_title or "Чат без названия",
                "display_title_source": "manual" if payload.display_title else "fallback",
            }
        )
        self.chats[chat_id] = updated
        return updated

    async def update_settings(
        self,
        *,
        chat_id: UUID,
        payload: SuperAdminChatSettingsUpdate,
        actor_login: str,
    ) -> SuperAdminChatRead:
        chat = self.chats[chat_id]
        if chat.status != ChatConnectionStatus.active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Deadline reminders can be changed only for active chats",
            )
        updated = chat.model_copy(update={"deadline_reminders_enabled": payload.deadline_reminders_enabled})
        self.chats[chat_id] = updated
        return updated

    async def update_member_role(
        self,
        *,
        chat_id: UUID,
        user_id: UUID,
        payload: SuperAdminChatMemberRoleUpdate,
        actor_login: str,
    ) -> SuperAdminChatMemberRead:
        if payload.role == "member" and not payload.allow_remove_last_admin:
            chat = self.chats[chat_id]
            if chat.chat_admins_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot remove the last chat admin without confirmation",
                )
        members = self.members[chat_id]
        member = next(item for item in members if item.user_id == user_id)
        updated = member.model_copy(update={"role_in_dyak": ChatMemberRole(payload.role)})
        self.members[chat_id] = [updated if item.user_id == user_id else item for item in members]
        return updated

    async def sync_max_admins(
        self,
        *,
        chat_id: UUID,
        actor_login: str,
        max_client: object,
    ):
        members = self.members[chat_id]
        updated_members = []
        for index, member in enumerate(members):
            updated_members.append(member.model_copy(update={"is_max_chat_admin": index == 0}))
        self.members[chat_id] = updated_members
        chat = self.chats[chat_id]
        self.chats[chat_id] = chat.model_copy(update={"max_admins_count": 1})
        return {
            "checked_members_count": len(members),
            "max_admins_count": 1,
            "matched_admins_count": 1,
            "unknown_count": 0,
            "checked_at": datetime.now(timezone.utc),
        }

    async def sync_max_chat_info(
        self,
        *,
        chat_id: UUID,
        actor_login: str,
        max_client: object,
    ) -> SuperAdminMaxChatInfoSyncRead:
        chat = self.chats[chat_id]
        if chat.display_title_source == "manual":
            return SuperAdminMaxChatInfoSyncRead(
                title_updated=False,
                title_source="manual",
                display_title=chat.display_title,
            )
        updated = chat.model_copy(update={"display_title": "Название из MAX", "display_title_source": "real"})
        self.chats[chat_id] = updated
        return SuperAdminMaxChatInfoSyncRead(
            title_updated=True,
            title_source="max_api",
            display_title=updated.display_title,
        )


class FakeMaxApiClient:
    def get_chat_admins(self, chat_id: str) -> list[dict[str, str | None]]:
        return [{"max_user_id": "max-user-1"}]

    def get_chat_info(self, chat_id: str) -> dict[str, str | None]:
        return {"title": "Название из MAX", "type": "chat"}


@pytest.fixture()
def super_admin_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeSuperAdminChatService]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SUPER_ADMIN_LOGIN", "root")
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "correct-password")
    monkeypatch.setenv("SUPER_ADMIN_SESSION_SECRET", "super-admin-session-secret")
    monkeypatch.setenv("SUPER_ADMIN_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    service = FakeSuperAdminChatService()
    app = create_app()
    app.dependency_overrides[get_super_admin_chat_service] = lambda: service
    app.dependency_overrides[get_max_api_client] = lambda: FakeMaxApiClient()
    client = TestClient(app)
    return client, service


def test_super_admin_login_sets_http_only_cookie(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client

    response = _login(client)

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert "max_secretary_super_admin=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_super_admin_login_rejects_invalid_password(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client

    response = client.post("/api/super-admin/login", json={"login": "root", "password": "wrong"})

    assert response.status_code == 401


def test_super_admin_login_rejects_invalid_login(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client

    response = client.post("/api/super-admin/login", json={"login": "wrong", "password": "correct-password"})

    assert response.status_code == 401


def test_super_admin_login_trims_copied_credentials(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client

    response = client.post(
        "/api/super-admin/login",
        json={"login": " root ", "password": " correct-password\n"},
    )

    assert response.status_code == 200
    assert response.cookies.get("max_secretary_super_admin") is not None


def test_super_admin_login_diagnostic_disabled_by_default(
    caplog: pytest.LogCaptureFixture,
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client
    caplog.set_level(logging.WARNING, logger="app.api.super_admin")

    response = client.post("/api/super-admin/login", json={"login": "root", "password": "wrong"})

    assert response.status_code == 401
    assert "super_admin_login_failed_diagnostic" not in caplog.text


def test_super_admin_login_diagnostic_logs_safe_mismatch_fields(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client
    monkeypatch.setenv("SUPER_ADMIN_LOGIN_DIAGNOSTIC", "true")
    get_settings.cache_clear()
    caplog.set_level(logging.WARNING, logger="app.api.super_admin")

    response = client.post(
        "/api/super-admin/login",
        json={"login": " root ", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "event=super_admin_login_failed_diagnostic" in caplog.text
    assert "input_login_len=6" in caplog.text
    assert "input_password_len=14" in caplog.text
    assert "env_login_len=4" in caplog.text
    assert "env_password_len=16" in caplog.text
    assert "login_matches_env=false" in caplog.text
    assert "password_matches_env=false" in caplog.text
    assert "trimmed_login_matches_env=true" in caplog.text
    assert "trimmed_password_matches_env=false" in caplog.text
    assert "wrong-password" not in caplog.text
    assert "correct-password" not in caplog.text
    assert " root " not in caplog.text

    record = next(item for item in caplog.records if getattr(item, "event", "") == "super_admin_login_failed_diagnostic")
    assert record.input_login_len == 6
    assert record.input_password_len == 14
    assert record.env_login_len == 4
    assert record.env_password_len == 16
    assert record.login_matches_env is False
    assert record.password_matches_env is False
    assert record.trimmed_login_matches_env is True
    assert record.trimmed_password_matches_env is False


def test_member_without_super_admin_session_cannot_list_chats(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client

    response = client.get("/api/super-admin/chats")

    assert response.status_code == 401


def test_super_admin_can_list_chats(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client
    _login(client)

    response = client.get("/api/super-admin/chats")

    assert response.status_code == 200
    payload = response.json()
    assert {item["display_title"] for item in payload} == {"Тест Дьяк", "Подключенный чат"}
    assert payload[0]["status"] in {"pending_approval", "active"}


def test_super_admin_can_filter_pending_chats(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client
    _login(client)

    response = client.get("/api/super-admin/chats?status=pending_approval")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["display_title"] == "Тест Дьяк"
    assert payload[0]["status"] == "pending_approval"


def test_super_admin_pending_status_alias_is_supported(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client
    _login(client)

    response = client.get("/api/super-admin/chats?status=pending")

    assert response.status_code == 200
    assert response.json()[0]["status"] == "pending_approval"


def test_super_admin_rejects_unknown_status_filter(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, _service = super_admin_client
    _login(client)

    response = client.get("/api/super-admin/chats?status=awaiting")

    assert response.status_code == 422


def test_super_admin_can_list_chat_members(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)

    response = client.get(f"/api/super-admin/chats/{service.chat_id}/members")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["display_name"] == "Иван Иванов"
    assert payload[0]["role_in_dyak"] == "member"
    assert payload[0]["is_max_chat_admin"] is None


def test_super_admin_can_approve_reject_and_suspend_chat(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)

    approve = client.patch(
        f"/api/super-admin/chats/{service.chat_id}/status",
        json={"status": "active"},
    )
    reject = client.patch(
        f"/api/super-admin/chats/{service.chat_id}/status",
        json={"status": "rejected"},
    )
    suspend = client.patch(
        f"/api/super-admin/chats/{service.second_chat_id}/status",
        json={"status": "suspended"},
    )

    assert approve.status_code == 200
    assert reject.status_code == 200
    assert suspend.status_code == 200
    assert reject.json()["status"] == "rejected"
    assert suspend.json()["status"] == "suspended"


def test_super_admin_can_update_pending_chat_display_title(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)

    response = client.patch(
        f"/api/super-admin/chats/{service.chat_id}/display-title",
        json={"display_title": "Отдел кадров"},
    )

    assert response.status_code == 200
    assert response.json()["display_title"] == "Отдел кадров"
    assert response.json()["display_title_source"] == "manual"


def test_super_admin_can_toggle_active_chat_deadline_reminders(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)

    enabled = client.patch(
        f"/api/super-admin/chats/{service.second_chat_id}/settings",
        json={"deadline_reminders_enabled": True},
    )
    disabled = client.patch(
        f"/api/super-admin/chats/{service.second_chat_id}/settings",
        json={"deadline_reminders_enabled": False},
    )

    assert enabled.status_code == 200
    assert enabled.json()["deadline_reminders_enabled"] is True
    assert disabled.status_code == 200
    assert disabled.json()["deadline_reminders_enabled"] is False


def test_super_admin_cannot_toggle_pending_chat_deadline_reminders(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)

    response = client.patch(
        f"/api/super-admin/chats/{service.chat_id}/settings",
        json={"deadline_reminders_enabled": True},
    )

    assert response.status_code == 409


def test_super_admin_chat_settings_update_requires_session(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client

    response = client.patch(
        f"/api/super-admin/chats/{service.second_chat_id}/settings",
        json={"deadline_reminders_enabled": True},
    )

    assert response.status_code == 401


def test_super_admin_can_assign_multiple_chat_admins(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)

    first = client.patch(
        f"/api/super-admin/chats/{service.chat_id}/members/{service.user_id}/role",
        json={"role": "chat_admin"},
    )
    second = client.patch(
        f"/api/super-admin/chats/{service.chat_id}/members/{service.second_user_id}/role",
        json={"role": "chat_admin"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["role_in_dyak"] == "chat_admin"
    assert second.json()["role_in_dyak"] == "chat_admin"


def test_super_admin_can_remove_chat_admin_with_confirmation(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)

    blocked = client.patch(
        f"/api/super-admin/chats/{service.second_chat_id}/members/{service.user_id}/role",
        json={"role": "member"},
    )
    allowed = client.patch(
        f"/api/super-admin/chats/{service.second_chat_id}/members/{service.user_id}/role",
        json={"role": "member", "allow_remove_last_admin": True},
    )

    assert blocked.status_code == 409
    assert allowed.status_code == 200
    assert allowed.json()["role_in_dyak"] == "member"


def test_cannot_assign_super_admin_via_chat_member_role_endpoint(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)

    response = client.patch(
        f"/api/super-admin/chats/{service.chat_id}/members/{service.user_id}/role",
        json={"role": "super_admin"},
    )

    assert response.status_code == 422


def test_super_admin_can_sync_max_admin_markers(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)

    response = client.post(f"/api/super-admin/chats/{service.chat_id}/sync-max-admins")
    members = client.get(f"/api/super-admin/chats/{service.chat_id}/members")
    chats = client.get("/api/super-admin/chats")

    assert response.status_code == 200
    assert response.json()["checked_members_count"] == 2
    assert response.json()["max_admins_count"] == 1
    assert response.json()["matched_admins_count"] == 1
    assert response.json()["unknown_count"] == 0
    assert members.status_code == 200
    assert [item["is_max_chat_admin"] for item in members.json()] == [True, False]
    assert chats.status_code == 200
    synced_chat = next(item for item in chats.json() if item["id"] == str(service.chat_id))
    assert synced_chat["max_admins_count"] == 1


def test_super_admin_can_sync_max_chat_info(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)

    response = client.post(f"/api/super-admin/chats/{service.chat_id}/sync-max-chat-info")
    chats = client.get("/api/super-admin/chats?status=pending_approval")

    assert response.status_code == 200
    assert response.json() == {
        "title_updated": True,
        "title_source": "max_api",
        "display_title": "Название из MAX",
    }
    assert chats.json()[0]["display_title"] == "Название из MAX"
    assert chats.json()[0]["display_title_source"] == "real"


def test_super_admin_sync_max_chat_info_preserves_manual_alias(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client
    _login(client)
    client.patch(
        f"/api/super-admin/chats/{service.chat_id}/display-title",
        json={"display_title": "Ручной alias"},
    )

    response = client.post(f"/api/super-admin/chats/{service.chat_id}/sync-max-chat-info")

    assert response.status_code == 200
    assert response.json() == {
        "title_updated": False,
        "title_source": "manual",
        "display_title": "Ручной alias",
    }


def test_super_admin_sync_max_admins_requires_session(
    super_admin_client: tuple[TestClient, FakeSuperAdminChatService],
) -> None:
    client, service = super_admin_client

    response = client.post(f"/api/super-admin/chats/{service.chat_id}/sync-max-admins")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_sync_max_admins_maps_snapshot_without_changing_dyak_roles() -> None:
    repository = FakeSuperAdminRepository()
    service = SuperAdminChatService(repository=repository, session=FakeSession())
    max_client = FakeSyncMaxClient(
        [
            {"max_user_id": "max-admin-1"},
            {"max_user_id": "max-admin-extra"},
        ]
    )

    result = await service.sync_max_admins(
        chat_id=repository.chat.id,
        actor_login="root",
        max_client=max_client,
    )

    assert result.checked_members_count == 3
    assert result.max_admins_count == 2
    assert result.matched_admins_count == 1
    assert result.unknown_count == 1
    assert repository.chat.settings["max_chat_admin_user_ids"] == ["max-admin-1", "max-admin-extra"]
    assert "max_chat_admin_checked_at" in repository.chat.settings
    assert [member.role for member in repository.members] == ["member", "member", "chat_admin"]
    assert repository.audit_payload["matched_admins_count"] == 1


@pytest.mark.anyio
async def test_update_chat_settings_toggles_deadline_reminders() -> None:
    repository = FakeSuperAdminRepository()
    service = SuperAdminChatService(repository=repository, session=FakeSession())

    enabled = await service.update_settings(
        chat_id=repository.chat.id,
        payload=SuperAdminChatSettingsUpdate(deadline_reminders_enabled=True),
        actor_login="root",
    )
    disabled = await service.update_settings(
        chat_id=repository.chat.id,
        payload=SuperAdminChatSettingsUpdate(deadline_reminders_enabled=False),
        actor_login="root",
    )

    assert enabled.deadline_reminders_enabled is True
    assert disabled.deadline_reminders_enabled is False
    assert repository.chat.settings["deadline_reminders_enabled"] is False
    assert repository.audit_payload["deadline_reminders_old"] is True
    assert repository.audit_payload["deadline_reminders_new"] is False


@pytest.mark.anyio
async def test_update_chat_settings_rejects_inactive_chat() -> None:
    repository = FakeSuperAdminRepository()
    repository.chat.status = "pending_approval"
    service = SuperAdminChatService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.update_settings(
            chat_id=repository.chat.id,
            payload=SuperAdminChatSettingsUpdate(deadline_reminders_enabled=True),
            actor_login="root",
        )

    assert exc_info.value.status_code == 409
    assert "deadline_reminders_enabled" not in repository.chat.settings


@pytest.mark.anyio
async def test_sync_max_admins_returns_safe_error_on_max_api_failure() -> None:
    repository = FakeSuperAdminRepository()
    service = SuperAdminChatService(repository=repository, session=FakeSession())
    max_client = FakeFailingMaxClient()

    with pytest.raises(HTTPException) as exc_info:
        await service.sync_max_admins(
            chat_id=repository.chat.id,
            actor_login="root",
            max_client=max_client,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Failed to sync MAX admin roles"
    assert "raw" not in str(exc_info.value.detail).lower()


@pytest.mark.anyio
async def test_sync_max_chat_info_updates_generated_title() -> None:
    repository = FakeSuperAdminRepository()
    repository.chat.title = "MAX chat #12345678"
    repository.chat.status = "pending_approval"
    service = SuperAdminChatService(repository=repository, session=FakeSession())
    max_client = FakeSyncMaxClient([], chat_info={"title": "Название из MAX", "type": "chat"})

    result = await service.sync_max_chat_info(
        chat_id=repository.chat.id,
        actor_login="root",
        max_client=max_client,
    )

    assert result.title_updated is True
    assert result.title_source == "max_api"
    assert result.display_title == "Название из MAX"
    assert repository.chat.title == "Название из MAX"
    assert repository.audit_payload["title_updated"] is True
    assert repository.audit_payload["title_len"] == len("Название из MAX")


@pytest.mark.anyio
async def test_sync_max_chat_info_preserves_manual_alias() -> None:
    repository = FakeSuperAdminRepository()
    repository.chat.title = "MAX chat #12345678"
    repository.chat.settings = {"display_title": "Ручной alias"}
    service = SuperAdminChatService(repository=repository, session=FakeSession())
    max_client = FakeSyncMaxClient([], chat_info={"title": "Название из MAX", "type": "chat"})

    result = await service.sync_max_chat_info(
        chat_id=repository.chat.id,
        actor_login="root",
        max_client=max_client,
    )

    assert result.title_updated is True
    assert result.title_source == "manual"
    assert result.display_title == "Ручной alias"
    assert repository.chat.title == "Название из MAX"
    assert repository.chat.settings["display_title"] == "Ручной alias"


@pytest.mark.anyio
async def test_sync_max_chat_info_returns_fallback_when_title_missing() -> None:
    repository = FakeSuperAdminRepository()
    repository.chat.title = "MAX chat #12345678"
    service = SuperAdminChatService(repository=repository, session=FakeSession())
    max_client = FakeSyncMaxClient([], chat_info={"title": None, "type": "chat"})

    result = await service.sync_max_chat_info(
        chat_id=repository.chat.id,
        actor_login="root",
        max_client=max_client,
    )

    assert result.title_updated is False
    assert result.title_source == "fallback"
    assert result.display_title == "Чат без названия"
    assert repository.chat.title == "MAX chat #12345678"


@pytest.mark.anyio
async def test_sync_max_chat_info_returns_safe_error_on_max_api_failure() -> None:
    repository = FakeSuperAdminRepository()
    service = SuperAdminChatService(repository=repository, session=FakeSession())
    max_client = FakeFailingMaxClient()

    with pytest.raises(HTTPException) as exc_info:
        await service.sync_max_chat_info(
            chat_id=repository.chat.id,
            actor_login="root",
            max_client=max_client,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Failed to sync MAX chat info"
    assert "raw" not in str(exc_info.value.detail).lower()


def _login(client: TestClient) -> Response:
    return client.post(
        "/api/super-admin/login",
        json={"login": "root", "password": "correct-password"},
    )


class FakeSuperAdminRepository:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(
            id=uuid4(),
            organization_id=uuid4(),
            max_chat_id="max-chat-1",
            title="Тест Дьяк",
            type="max_group",
            status="active",
            settings={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.members = [
            SimpleNamespace(
                id=uuid4(),
                user_id=uuid4(),
                role="member",
                is_active=True,
                updated_at=datetime.now(timezone.utc),
                user=SimpleNamespace(
                    display_name="MAX admin",
                    username="max_admin",
                    max_user_id="max-admin-1",
                ),
                chat=self.chat,
            ),
            SimpleNamespace(
                id=uuid4(),
                user_id=uuid4(),
                role="member",
                is_active=True,
                updated_at=datetime.now(timezone.utc),
                user=SimpleNamespace(
                    display_name="Regular member",
                    username="member",
                    max_user_id="max-member-2",
                ),
                chat=self.chat,
            ),
            SimpleNamespace(
                id=uuid4(),
                user_id=uuid4(),
                role="chat_admin",
                is_active=True,
                updated_at=datetime.now(timezone.utc),
                user=SimpleNamespace(
                    display_name="No MAX id",
                    username=None,
                    max_user_id=None,
                ),
                chat=self.chat,
            ),
        ]
        self.audit_payload: dict[str, object] = {}

    async def get_chat(self, chat_id: UUID):
        return self.chat if chat_id == self.chat.id else None

    async def list_members(self, chat_id: UUID):
        return self.members if chat_id == self.chat.id else []

    async def update_chat(self, chat, *, values):
        for key, value in values.items():
            setattr(chat, key, value)
        return chat

    async def create_audit_log(self, *, organization_id, entity_type, entity_id, action, payload=None):
        self.audit_payload = payload or {}
        return SimpleNamespace(id=uuid4())

    async def count_active_members(self, chat_id: UUID) -> int:
        return sum(1 for member in self.members if member.is_active)

    async def count_active_chat_admins(self, chat_id: UUID) -> int:
        return sum(1 for member in self.members if member.is_active and member.role == "chat_admin")


class FakeSession:
    async def commit(self) -> None:
        return None

    async def refresh(self, _entity) -> None:
        return None


class FakeSyncMaxClient:
    def __init__(
        self,
        admins: list[dict[str, str | None]],
        *,
        chat_info: dict[str, str | None] | None = None,
    ) -> None:
        self.admins = admins
        self.chat_info = chat_info or {"title": None, "type": None}

    def get_chat_admins(self, chat_id: str) -> list[dict[str, str | None]]:
        return self.admins

    def get_chat_info(self, chat_id: str) -> dict[str, str | None]:
        return self.chat_info


class FakeFailingMaxClient:
    def get_chat_admins(self, chat_id: str) -> list[dict[str, str | None]]:
        raise MaxApiHTTPError("MAX API returned HTTP 403.", status_code=403, response_text="raw response")

    def get_chat_info(self, chat_id: str) -> dict[str, str | None]:
        raise MaxApiHTTPError("MAX API returned HTTP 403.", status_code=403, response_text="raw response")
