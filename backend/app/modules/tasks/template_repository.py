from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.models import Chat
from app.modules.organizations.models import Organization
from app.modules.tasks.models import TaskTemplate
from app.modules.users.models import User


class TaskTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def organization_exists(self, organization_id: UUID) -> bool:
        return await self.session.get(Organization, organization_id) is not None

    async def get_chat(self, chat_id: UUID) -> Optional[Chat]:
        return await self.session.get(Chat, chat_id)

    async def user_exists(self, user_id: UUID) -> bool:
        return await self.session.get(User, user_id) is not None

    async def create_template(
        self,
        *,
        organization_id: UUID,
        chat_id: UUID,
        created_by_user_id: UUID,
        title: str,
        description: Optional[str],
        task_type: str,
        response_required: bool,
        default_deadline_rule: Optional[str],
        audience_type: str,
        exclude_creator: bool,
        settings: Optional[dict[str, Any]],
        is_active: bool,
    ) -> TaskTemplate:
        template = TaskTemplate(
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
            settings=settings,
            is_active=is_active,
        )
        self.session.add(template)
        await self.session.flush()
        return template

    async def list_templates(
        self,
        *,
        organization_id: UUID | None = None,
        chat_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
        is_active: bool | None = True,
    ) -> list[TaskTemplate]:
        query = select(TaskTemplate).order_by(TaskTemplate.created_at.desc())
        if organization_id is not None:
            query = query.where(TaskTemplate.organization_id == organization_id)
        if chat_id is not None:
            query = query.where(TaskTemplate.chat_id == chat_id)
        if created_by_user_id is not None:
            query = query.where(TaskTemplate.created_by_user_id == created_by_user_id)
        if is_active is not None:
            query = query.where(TaskTemplate.is_active == is_active)

        result = await self.session.scalars(query)
        return list(result)

    async def get_template(self, template_id: UUID) -> Optional[TaskTemplate]:
        return await self.session.get(TaskTemplate, template_id)

    async def update_template(
        self,
        template: TaskTemplate,
        *,
        values: Mapping[str, Any],
    ) -> TaskTemplate:
        for field_name in (
            "organization_id",
            "chat_id",
            "created_by_user_id",
            "title",
            "description",
            "task_type",
            "response_required",
            "default_deadline_rule",
            "audience_type",
            "exclude_creator",
            "settings",
            "is_active",
        ):
            if field_name in values:
                setattr(template, field_name, values[field_name])
        await self.session.flush()
        return template

    async def soft_delete_template(self, template: TaskTemplate) -> TaskTemplate:
        template.is_active = False
        await self.session.flush()
        return template
