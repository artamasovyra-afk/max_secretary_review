from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_MEMBER, ROLE_SUPER_ADMIN
from app.modules.tasks.enums import TaskTemplateAudienceType, TaskType
from app.modules.tasks.template_schemas import TaskTemplateCreate, TaskTemplateUpdate
from app.modules.tasks.template_service import TaskTemplateService


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _instance: object) -> None:
        return None


class FakeTaskTemplateRepository:
    def __init__(self, *, organization_id: UUID, chat_id: UUID, user_id: UUID) -> None:
        self.organization_id = organization_id
        self.chat_id = chat_id
        self.user_id = user_id
        self.template_id = uuid4()
        self.created_values: dict[str, object] = {}
        self.templates: dict[UUID, SimpleNamespace] = {}

    async def organization_exists(self, organization_id: UUID) -> bool:
        return organization_id == self.organization_id

    async def get_chat(self, chat_id: UUID) -> SimpleNamespace | None:
        if chat_id != self.chat_id:
            return None
        return SimpleNamespace(id=chat_id, organization_id=self.organization_id)

    async def user_exists(self, user_id: UUID) -> bool:
        return user_id == self.user_id

    async def create_template(self, **values: object) -> SimpleNamespace:
        self.created_values = values
        template = _template(
            template_id=self.template_id,
            organization_id=values["organization_id"],
            chat_id=values["chat_id"],
            created_by_user_id=values["created_by_user_id"],
            title=values["title"],
            task_type=values["task_type"],
            audience_type=values["audience_type"],
            is_active=values["is_active"],
        )
        self.templates[template.id] = template
        return template

    async def list_templates(
        self,
        *,
        organization_id: UUID | None = None,
        chat_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
        is_active: bool | None = True,
    ) -> list[SimpleNamespace]:
        templates = list(self.templates.values())
        if organization_id is not None:
            templates = [item for item in templates if item.organization_id == organization_id]
        if chat_id is not None:
            templates = [item for item in templates if item.chat_id == chat_id]
        if created_by_user_id is not None:
            templates = [item for item in templates if item.created_by_user_id == created_by_user_id]
        if is_active is not None:
            templates = [item for item in templates if item.is_active is is_active]
        return templates

    async def get_template(self, template_id: UUID) -> SimpleNamespace | None:
        return self.templates.get(template_id)

    async def update_template(
        self,
        template: SimpleNamespace,
        *,
        values: dict[str, object],
    ) -> SimpleNamespace:
        for field_name, value in values.items():
            setattr(template, field_name, value)
        return template

    async def soft_delete_template(self, template: SimpleNamespace) -> SimpleNamespace:
        template.is_active = False
        return template


def _template(
    *,
    template_id: UUID,
    organization_id: object,
    chat_id: object,
    created_by_user_id: object,
    title: object = "Еженедельный отчет",
    task_type: object = TaskType.GROUP_ASSIGNMENT.value,
    audience_type: object = TaskTemplateAudienceType.ALL_CHAT_MEMBERS.value,
    is_active: object = True,
) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=template_id,
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=created_by_user_id,
        title=title,
        description="Сдать отчет",
        task_type=task_type,
        response_required=True,
        default_deadline_rule="friday_18",
        audience_type=audience_type,
        exclude_creator=True,
        settings={"tags": ["demo"]},
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def _payload(
    *,
    organization_id: UUID,
    chat_id: UUID,
    created_by_user_id: UUID,
) -> TaskTemplateCreate:
    return TaskTemplateCreate(
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=created_by_user_id,
        title="Еженедельный отчет",
        description="Сдать отчет",
        default_deadline_rule="friday_18",
        settings={"tags": ["demo"]},
    )


@pytest.mark.anyio
async def test_task_template_service_creator_can_create_template() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    repository = FakeTaskTemplateRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=user_id,
    )
    session = FakeSession()
    service = TaskTemplateService(repository=repository, session=session)

    result = await service.create(
        _payload(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=user_id,
        ),
        AuthContext(user_id=user_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_MEMBER]),
    )

    assert result.id == repository.template_id
    assert repository.created_values["task_type"] == TaskType.GROUP_ASSIGNMENT.value
    assert repository.created_values["audience_type"] == TaskTemplateAudienceType.ALL_CHAT_MEMBERS.value
    assert repository.created_values["response_required"] is True
    assert repository.created_values["exclude_creator"] is True
    assert session.committed is True


@pytest.mark.anyio
async def test_task_template_service_rejects_creator_impersonation() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    repository = FakeTaskTemplateRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=user_id,
    )
    service = TaskTemplateService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.create(
            _payload(
                organization_id=organization_id,
                chat_id=chat_id,
                created_by_user_id=user_id,
            ),
            AuthContext(user_id=uuid4(), organization_id=organization_id, chat_id=chat_id, roles=[ROLE_MEMBER]),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_task_template_service_chat_admin_can_access_scoped_templates() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    admin_id = uuid4()
    repository = FakeTaskTemplateRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
    )
    template = _template(
        template_id=repository.template_id,
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=creator_id,
    )
    repository.templates[template.id] = template
    service = TaskTemplateService(repository=repository, session=FakeSession())

    result = await service.get(
        template.id,
        AuthContext(user_id=admin_id, organization_id=organization_id, chat_id=chat_id, roles=[ROLE_CHAT_ADMIN]),
    )

    assert result.id == template.id


@pytest.mark.anyio
async def test_task_template_service_filters_list_by_rbac() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    other_user_id = uuid4()
    repository = FakeTaskTemplateRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
    )
    own_template = _template(
        template_id=uuid4(),
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=creator_id,
    )
    other_template = _template(
        template_id=uuid4(),
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=other_user_id,
    )
    repository.templates = {own_template.id: own_template, other_template.id: other_template}
    service = TaskTemplateService(repository=repository, session=FakeSession())

    result = await service.list(
        auth_context=AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id),
    )

    assert [item.id for item in result] == [own_template.id]


@pytest.mark.anyio
async def test_task_template_service_outsider_forbidden() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    repository = FakeTaskTemplateRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
    )
    template = _template(
        template_id=repository.template_id,
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=creator_id,
    )
    repository.templates[template.id] = template
    service = TaskTemplateService(repository=repository, session=FakeSession())

    with pytest.raises(HTTPException) as exc_info:
        await service.get(
            template.id,
            AuthContext(user_id=uuid4(), organization_id=organization_id, chat_id=chat_id, roles=[ROLE_MEMBER]),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_task_template_service_update_and_soft_delete() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    repository = FakeTaskTemplateRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
    )
    template = _template(
        template_id=repository.template_id,
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=creator_id,
    )
    repository.templates[template.id] = template
    session = FakeSession()
    service = TaskTemplateService(repository=repository, session=session)
    context = AuthContext(user_id=creator_id, organization_id=organization_id, chat_id=chat_id)

    updated = await service.update(
        template.id,
        TaskTemplateUpdate(
            title="Новый шаблон",
            audience_type=TaskTemplateAudienceType.SELECTED_MEMBERS,
        ),
        context,
    )
    deleted = await service.delete(template.id, context)

    assert updated.title == "Новый шаблон"
    assert updated.audience_type == TaskTemplateAudienceType.SELECTED_MEMBERS.value
    assert deleted.is_active is False
    assert session.committed is True


@pytest.mark.anyio
async def test_task_template_service_super_admin_can_change_creator() -> None:
    organization_id = uuid4()
    chat_id = uuid4()
    creator_id = uuid4()
    repository = FakeTaskTemplateRepository(
        organization_id=organization_id,
        chat_id=chat_id,
        user_id=creator_id,
    )
    template = _template(
        template_id=repository.template_id,
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=uuid4(),
    )
    repository.templates[template.id] = template
    service = TaskTemplateService(repository=repository, session=FakeSession())

    result = await service.update(
        template.id,
        TaskTemplateUpdate(created_by_user_id=creator_id),
        AuthContext(user_id=uuid4(), roles=[ROLE_SUPER_ADMIN], is_super_admin=True),
    )

    assert result.created_by_user_id == creator_id
