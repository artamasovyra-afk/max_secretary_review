from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.modules.auth.policy import ROLE_MEMBER
from app.modules.chats.schemas import ChatConnectionStatus
from app.modules.bot.identity_resolver import (
    DEFAULT_MAX_ORGANIZATION_NAME,
    MaxIdentityResolver,
)
from app.modules.bot.schemas import NormalizedBotEvent
from app.modules.integrations.max.exceptions import MaxApiHTTPError


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


class FakeOrganizationRepository:
    def __init__(self) -> None:
        self.organizations_by_name: dict[str, SimpleNamespace] = {}
        self.create_count = 0

    async def get_by_name(self, name: str) -> SimpleNamespace | None:
        return self.organizations_by_name.get(name)

    async def create(self, *, name: str, status: str) -> SimpleNamespace:
        self.create_count += 1
        organization = SimpleNamespace(id=uuid4(), name=name, status=status)
        self.organizations_by_name[name] = organization
        return organization


class FakeUserRepository:
    def __init__(self) -> None:
        self.users_by_max_id: dict[str, SimpleNamespace] = {}
        self.users_by_id: dict[UUID, SimpleNamespace] = {}
        self.create_count = 0

    async def get(self, user_id: UUID) -> SimpleNamespace | None:
        return self.users_by_id.get(user_id)

    async def get_by_max_user_id(self, max_user_id: str) -> SimpleNamespace | None:
        return self.users_by_max_id.get(max_user_id)

    async def create(
        self,
        *,
        display_name: str,
        max_user_id: str | None = None,
        username: str | None = None,
        phone: str | None = None,
        email: str | None = None,
    ) -> SimpleNamespace:
        self.create_count += 1
        user = SimpleNamespace(
            id=uuid4(),
            max_user_id=max_user_id,
            display_name=display_name,
            username=username,
            phone=phone,
            email=email,
        )
        assert max_user_id is not None
        self.users_by_max_id[max_user_id] = user
        self.users_by_id[user.id] = user
        return user

    async def update(self, user: SimpleNamespace, *, values: dict[str, object]) -> SimpleNamespace:
        for key, value in values.items():
            setattr(user, key, value)
        return user


class FakeChatRepository:
    def __init__(self) -> None:
        self.chats_by_key: dict[tuple[UUID, str], SimpleNamespace] = {}
        self.chats_by_id: dict[UUID, SimpleNamespace] = {}
        self.members_by_key: dict[tuple[UUID, UUID], SimpleNamespace] = {}
        self.create_count = 0

    async def get_chat(self, chat_id: UUID) -> SimpleNamespace | None:
        return self.chats_by_id.get(chat_id)

    async def get_chat_by_max_chat_id(
        self,
        *,
        organization_id: UUID,
        max_chat_id: str,
    ) -> SimpleNamespace | None:
        return self.chats_by_key.get((organization_id, max_chat_id))

    async def create_chat(
        self,
        *,
        organization_id: UUID,
        title: str,
        type: str,
        max_chat_id: str | None = None,
        status: str = "active",
        settings: dict[str, object] | None = None,
    ) -> SimpleNamespace:
        self.create_count += 1
        chat = SimpleNamespace(
            id=uuid4(),
            organization_id=organization_id,
            max_chat_id=max_chat_id,
            title=title,
            type=type,
            status=status,
            settings=settings,
        )
        assert max_chat_id is not None
        self.chats_by_key[(organization_id, max_chat_id)] = chat
        self.chats_by_id[chat.id] = chat
        return chat

    async def update_chat(self, chat: SimpleNamespace, *, values: dict[str, object]) -> SimpleNamespace:
        for key, value in values.items():
            setattr(chat, key, value)
        return chat

    async def get_member(self, *, chat_id: UUID, user_id: UUID) -> SimpleNamespace | None:
        return self.members_by_key.get((chat_id, user_id))

    async def create_member(
        self,
        *,
        chat_id: UUID,
        user_id: UUID,
        role: str,
        is_active: bool,
    ) -> SimpleNamespace:
        member = SimpleNamespace(chat_id=chat_id, user_id=user_id, role=role, is_active=is_active)
        self.members_by_key[(chat_id, user_id)] = member
        return member

    async def update_member(self, member: SimpleNamespace, *, values: dict[str, object]) -> SimpleNamespace:
        for key, value in values.items():
            setattr(member, key, value)
        return member


class FakeMaxChatInfoClient:
    def __init__(
        self,
        responses: dict[str, dict[str, str | None]] | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.responses = responses or {}
        self.fail = fail
        self.calls: list[str] = []

    def get_chat_info(self, chat_id: str) -> dict[str, str | None]:
        self.calls.append(chat_id)
        if self.fail:
            raise MaxApiHTTPError("MAX API returned HTTP 404.", status_code=404)
        return self.responses.get(chat_id, {"title": None, "type": None})


@pytest.fixture()
def resolver_context() -> dict[str, object]:
    session = FakeSession()
    user_repository = FakeUserRepository()
    chat_repository = FakeChatRepository()
    organization_repository = FakeOrganizationRepository()
    resolver = MaxIdentityResolver(
        user_repository=user_repository,  # type: ignore[arg-type]
        chat_repository=chat_repository,  # type: ignore[arg-type]
        organization_repository=organization_repository,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
    )
    return {
        "resolver": resolver,
        "session": session,
        "user_repository": user_repository,
        "chat_repository": chat_repository,
        "organization_repository": organization_repository,
    }


def make_event(
    *,
    user_id: str = "max-user-001",
    chat_id: str = "max-chat-001",
    sender_display_name: str | None = "Иван Петров",
    sender_username: str | None = "ivan",
    chat_type: str | None = "dialog",
    chat_title: str | None = None,
) -> NormalizedBotEvent:
    return NormalizedBotEvent(
        chat_id=chat_id,
        user_id=user_id,
        message_id="mock-message-001",
        text="/задачи",
        chat_type=chat_type,
        chat_title=chat_title,
        sender_display_name=sender_display_name,
        sender_username=sender_username,
    )


@pytest.mark.anyio
async def test_resolve_new_max_user_chat_and_default_organization(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]
    user_repository = resolver_context["user_repository"]
    chat_repository = resolver_context["chat_repository"]
    organization_repository = resolver_context["organization_repository"]

    identity = await resolver.resolve_event(make_event())

    assert identity.organization.name == DEFAULT_MAX_ORGANIZATION_NAME
    assert identity.user.max_user_id == "max-user-001"
    assert identity.user.display_name == "Иван Петров"
    assert identity.user.username == "ivan"
    assert identity.chat.max_chat_id == "max-chat-001"
    assert identity.chat.organization_id == identity.organization.id
    assert identity.chat.type == "max_dialog"
    assert identity.chat.status == ChatConnectionStatus.active.value
    assert chat_repository.members_by_key[(identity.chat.id, identity.user.id)].role == ROLE_MEMBER
    assert user_repository.create_count == 1
    assert chat_repository.create_count == 1
    assert organization_repository.create_count == 1


@pytest.mark.anyio
async def test_resolve_existing_max_user_and_chat_without_duplicates(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]
    user_repository = resolver_context["user_repository"]
    chat_repository = resolver_context["chat_repository"]

    first = await resolver.resolve_event(make_event())
    second = await resolver.resolve_event(make_event())

    assert second.user.id == first.user.id
    assert second.chat.id == first.chat.id
    assert user_repository.create_count == 1
    assert chat_repository.create_count == 1
    assert len(chat_repository.members_by_key) == 1


@pytest.mark.anyio
async def test_resolve_new_max_chat_uses_real_chat_title(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]

    identity = await resolver.resolve_event(
        make_event(
            chat_id="max-chat-with-title",
            chat_type="group",
            chat_title="Тестовый чат",
        )
    )

    assert identity.chat.title == "Тестовый чат"
    assert identity.chat.type == "max_group"
    assert identity.chat.status == ChatConnectionStatus.pending_approval.value


@pytest.mark.anyio
async def test_resolve_new_max_chat_uses_max_api_title_when_webhook_title_missing(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]
    max_client = FakeMaxChatInfoClient({"max-chat-api-title": {"title": "Название из MAX API", "type": "chat"}})
    resolver.max_chat_info_client = max_client

    identity = await resolver.resolve_event(make_event(chat_id="max-chat-api-title", chat_type="group"))

    assert identity.chat.title == "Название из MAX API"
    assert identity.chat.status == ChatConnectionStatus.pending_approval.value
    assert max_client.calls == ["max-chat-api-title"]


@pytest.mark.anyio
async def test_resolve_new_max_chat_keeps_generated_title_when_max_api_fails(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]
    max_client = FakeMaxChatInfoClient(fail=True)
    resolver.max_chat_info_client = max_client

    identity = await resolver.resolve_event(make_event(chat_id="max-chat-api-fail", chat_type="group"))

    assert identity.chat.title.startswith("MAX chat #")
    assert max_client.calls == ["max-chat-api-fail"]


@pytest.mark.anyio
async def test_resolve_existing_generated_chat_updates_from_max_api_title(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]

    first = await resolver.resolve_event(make_event(chat_id="max-chat-api-title-later", chat_type="group"))
    max_client = FakeMaxChatInfoClient(
        {"max-chat-api-title-later": {"title": "Позднее название из MAX", "type": "chat"}}
    )
    resolver.max_chat_info_client = max_client
    second = await resolver.resolve_event(make_event(chat_id="max-chat-api-title-later", chat_type="group"))

    assert first.chat.id == second.chat.id
    assert second.chat.title == "Позднее название из MAX"
    assert max_client.calls == ["max-chat-api-title-later"]


@pytest.mark.anyio
async def test_resolve_updates_generated_chat_title_when_real_title_arrives(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]

    first = await resolver.resolve_event(
        make_event(chat_id="max-chat-title-later", chat_type="group")
    )
    second = await resolver.resolve_event(
        make_event(
            chat_id="max-chat-title-later",
            chat_type="group",
            chat_title="Чат отдела кадров",
        )
    )

    assert first.chat.id == second.chat.id
    assert first.chat.title == "Чат отдела кадров"
    assert second.chat.title == "Чат отдела кадров"


@pytest.mark.anyio
async def test_resolve_does_not_overwrite_manual_chat_title_with_generated_fallback(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]

    first = await resolver.resolve_event(
        make_event(
            chat_id="max-chat-manual-title",
            chat_type="group",
            chat_title="Ручное название",
        )
    )
    first.chat.title = "Переименовано в Дьяке"
    second = await resolver.resolve_event(make_event(chat_id="max-chat-manual-title", chat_type="group"))

    assert second.chat.title == "Переименовано в Дьяке"


@pytest.mark.anyio
async def test_resolve_preserves_manual_display_title_alias(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]

    first = await resolver.resolve_event(make_event(chat_id="max-chat-alias", chat_type="group"))
    first.chat.settings = {"source": "max_webhook", "display_title": "Тест секретарь"}
    second = await resolver.resolve_event(
        make_event(
            chat_id="max-chat-alias",
            chat_type="group",
            chat_title="Реальное название из MAX",
        )
    )

    assert second.chat.title == "Реальное название из MAX"
    assert second.chat.settings["display_title"] == "Тест секретарь"


@pytest.mark.anyio
async def test_resolve_does_not_overwrite_real_chat_title_with_generated_fallback(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]

    first = await resolver.resolve_event(
        make_event(
            chat_id="max-chat-real-title",
            chat_type="group",
            chat_title="Тест Дьяк",
        )
    )
    second = await resolver.resolve_event(
        make_event(
            chat_id="max-chat-real-title",
            chat_type="group",
            chat_title="MAX chat #47009261",
        )
    )

    assert first.chat.id == second.chat.id
    assert second.chat.title == "Тест Дьяк"


@pytest.mark.anyio
async def test_resolve_ignores_identifier_like_chat_title(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]

    identity = await resolver.resolve_event(
        make_event(
            chat_id="max-chat-uuid-title",
            chat_type="group",
            chat_title="236c375a-155c-455e-97b1-ad3d366b2d3d",
        )
    )

    assert identity.chat.title.startswith("MAX chat #")


@pytest.mark.anyio
async def test_default_max_organization_is_reused_once(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]
    organization_repository = resolver_context["organization_repository"]

    await resolver.resolve_event(make_event(user_id="max-user-001", chat_id="max-chat-001"))
    await resolver.resolve_event(make_event(user_id="max-user-002", chat_id="max-chat-002"))

    assert organization_repository.create_count == 1


@pytest.mark.anyio
async def test_resolve_missing_sender_display_name_uses_safe_fallback(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]

    identity = await resolver.resolve_event(
        make_event(
            user_id="max-user-without-name",
            sender_display_name=None,
            sender_username=None,
        )
    )

    assert identity.user.display_name == "Пользователь #out-name"


@pytest.mark.anyio
async def test_inactive_chat_member_is_reactivated(resolver_context: dict[str, object]) -> None:
    resolver = resolver_context["resolver"]
    chat_repository = resolver_context["chat_repository"]

    identity = await resolver.resolve_event(make_event())
    member = chat_repository.members_by_key[(identity.chat.id, identity.user.id)]
    member.is_active = False

    await resolver.resolve_event(make_event())

    assert member.is_active is True


@pytest.mark.anyio
async def test_resolve_mixed_internal_chat_and_external_user(
    resolver_context: dict[str, object],
) -> None:
    resolver = resolver_context["resolver"]
    chat_repository = resolver_context["chat_repository"]
    organization_repository = resolver_context["organization_repository"]
    organization = await organization_repository.create(
        name=DEFAULT_MAX_ORGANIZATION_NAME,
        status="active",
    )
    chat = await chat_repository.create_chat(
        organization_id=organization.id,
        max_chat_id="max-chat-existing",
        title="Existing chat",
        type="max_chat",
    )

    identity = await resolver.resolve_event(make_event(chat_id=str(chat.id), user_id="max-user-002"))

    assert identity.chat.id == chat.id
    assert identity.user.max_user_id == "max-user-002"
    assert chat_repository.create_count == 1
