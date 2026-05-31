from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.task_templates import get_task_template_service
from app.core.config import get_settings
from app.main import create_app
from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_MEMBER
from app.modules.tasks.enums import TaskTemplateAudienceType, TaskType
from app.modules.tasks.template_schemas import (
    TaskTemplateCreate,
    TaskTemplateRead,
    TaskTemplateUpdate,
)


class FakeTaskTemplateService:
    def __init__(self) -> None:
        self.templates: dict[UUID, TaskTemplateRead] = {}
        self.last_create_payload: Optional[TaskTemplateCreate] = None
        self.last_create_context: Optional[AuthContext] = None
        self.last_list_context: Optional[AuthContext] = None
        self.last_get_context: Optional[AuthContext] = None
        self.last_update_payload: Optional[TaskTemplateUpdate] = None
        self.last_delete_context: Optional[AuthContext] = None

    async def create(
        self,
        payload: TaskTemplateCreate,
        auth_context: AuthContext,
    ) -> TaskTemplateRead:
        self.last_create_payload = payload
        self.last_create_context = auth_context
        template = _template_read(
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            created_by_user_id=payload.created_by_user_id,
            title=payload.title,
            description=payload.description,
            task_type=payload.task_type,
            response_required=payload.response_required,
            default_deadline_rule=payload.default_deadline_rule,
            audience_type=payload.audience_type,
            exclude_creator=payload.exclude_creator,
            settings=payload.settings,
            is_active=payload.is_active,
        )
        self.templates[template.id] = template
        return template

    async def list(
        self,
        *,
        auth_context: AuthContext,
        organization_id: UUID | None = None,
        chat_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
        is_active: bool | None = True,
    ) -> list[TaskTemplateRead]:
        self.last_list_context = auth_context
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

    async def get(self, template_id: UUID, auth_context: AuthContext) -> TaskTemplateRead:
        self.last_get_context = auth_context
        return self.templates[template_id]

    async def update(
        self,
        template_id: UUID,
        payload: TaskTemplateUpdate,
        auth_context: AuthContext,
    ) -> TaskTemplateRead:
        self.last_update_payload = payload
        template = self.templates[template_id]
        values = payload.model_dump(exclude_unset=True)
        updated = template.model_copy(update=values)
        self.templates[template_id] = updated
        self.last_get_context = auth_context
        return updated

    async def delete(self, template_id: UUID, auth_context: AuthContext) -> TaskTemplateRead:
        self.last_delete_context = auth_context
        template = self.templates[template_id].model_copy(update={"is_active": False})
        self.templates[template_id] = template
        return template


def _template_read(
    *,
    organization_id: UUID,
    chat_id: UUID,
    created_by_user_id: UUID,
    title: str = "Еженедельный отчет",
    description: str | None = "Сдать отчет",
    task_type: TaskType = TaskType.GROUP_ASSIGNMENT,
    response_required: bool = True,
    default_deadline_rule: str | None = "friday_18",
    audience_type: TaskTemplateAudienceType = TaskTemplateAudienceType.ALL_CHAT_MEMBERS,
    exclude_creator: bool = True,
    settings: dict[str, object] | None = None,
    is_active: bool = True,
) -> TaskTemplateRead:
    now = datetime.now(timezone.utc)
    return TaskTemplateRead(
        id=uuid4(),
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=created_by_user_id,
        title=title,
        description=description,
        task_type=task_type,
        response_required=response_required,
        default_deadline_rule=default_deadline_rule,
        audience_type=audience_type,
        exclude_creator=exclude_creator,
        settings=settings or {"tags": ["demo"]},
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def task_templates_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeTaskTemplateService]:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    app = create_app()
    service = FakeTaskTemplateService()
    app.dependency_overrides[get_task_template_service] = lambda: service
    with TestClient(app) as client:
        yield client, service


def _payload(
    *,
    organization_id: UUID,
    chat_id: UUID,
    created_by_user_id: UUID,
) -> dict[str, object]:
    return {
        "organization_id": str(organization_id),
        "chat_id": str(chat_id),
        "created_by_user_id": str(created_by_user_id),
        "title": "Еженедельный отчет",
        "description": "Сдать отчет",
        "task_type": TaskType.GROUP_ASSIGNMENT.value,
        "response_required": True,
        "default_deadline_rule": "friday_18",
        "audience_type": TaskTemplateAudienceType.ALL_CHAT_MEMBERS.value,
        "exclude_creator": True,
        "settings": {"tags": ["demo"]},
        "is_active": True,
    }


def _auth_headers(
    *,
    user_id: UUID,
    organization_id: UUID,
    chat_id: UUID,
    roles: str = ROLE_MEMBER,
) -> dict[str, str]:
    return {
        "X-User-Id": str(user_id),
        "X-Organization-Id": str(organization_id),
        "X-Chat-Id": str(chat_id),
        "X-Roles": roles,
    }


def test_create_task_template(task_templates_client: tuple[TestClient, FakeTaskTemplateService]) -> None:
    client, service = task_templates_client
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()

    response = client.post(
        "/api/task-templates",
        json=_payload(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=user_id,
        ),
        headers=_auth_headers(
            user_id=user_id,
            organization_id=organization_id,
            chat_id=chat_id,
        ),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Еженедельный отчет"
    assert payload["task_type"] == TaskType.GROUP_ASSIGNMENT.value
    assert payload["audience_type"] == TaskTemplateAudienceType.ALL_CHAT_MEMBERS.value
    assert service.last_create_payload is not None
    assert service.last_create_context is not None
    assert service.last_create_context.user_id == user_id


def test_list_task_templates(task_templates_client: tuple[TestClient, FakeTaskTemplateService]) -> None:
    client, service = task_templates_client
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    template = _template_read(
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=user_id,
    )
    service.templates[template.id] = template

    response = client.get(
        "/api/task-templates",
        params={"organization_id": str(organization_id)},
        headers=_auth_headers(
            user_id=user_id,
            organization_id=organization_id,
            chat_id=chat_id,
            roles=ROLE_CHAT_ADMIN,
        ),
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(template.id)
    assert service.last_list_context is not None
    assert service.last_list_context.roles == [ROLE_CHAT_ADMIN]


def test_get_update_and_delete_task_template(
    task_templates_client: tuple[TestClient, FakeTaskTemplateService],
) -> None:
    client, service = task_templates_client
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()
    template = _template_read(
        organization_id=organization_id,
        chat_id=chat_id,
        created_by_user_id=user_id,
    )
    service.templates[template.id] = template
    headers = _auth_headers(
        user_id=user_id,
        organization_id=organization_id,
        chat_id=chat_id,
    )

    get_response = client.get(f"/api/task-templates/{template.id}", headers=headers)
    update_response = client.patch(
        f"/api/task-templates/{template.id}",
        json={
            "title": "Новый шаблон",
            "audience_type": TaskTemplateAudienceType.SELECTED_MEMBERS.value,
        },
        headers=headers,
    )
    delete_response = client.delete(f"/api/task-templates/{template.id}", headers=headers)

    assert get_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Новый шаблон"
    assert update_response.json()["audience_type"] == TaskTemplateAudienceType.SELECTED_MEMBERS.value
    assert service.last_update_payload is not None
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False
    assert service.last_delete_context is not None


def test_task_template_endpoints_require_auth(
    task_templates_client: tuple[TestClient, FakeTaskTemplateService],
) -> None:
    client, service = task_templates_client
    organization_id = uuid4()
    chat_id = uuid4()
    user_id = uuid4()

    response = client.post(
        "/api/task-templates",
        json=_payload(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=user_id,
        ),
    )

    assert response.status_code == 401
    assert service.last_create_payload is None
