from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.context import AuthContext
from app.modules.auth.policy import ROLE_CHAT_ADMIN, ROLE_SUPER_ADMIN
from app.modules.tasks.models import TaskTemplate
from app.modules.tasks.template_repository import TaskTemplateRepository
from app.modules.tasks.template_schemas import TaskTemplateCreate, TaskTemplateUpdate


class TaskTemplateService:
    def __init__(self, repository: TaskTemplateRepository, session: AsyncSession) -> None:
        self.repository = repository
        self.session = session

    async def create(
        self,
        payload: TaskTemplateCreate,
        auth_context: AuthContext,
    ) -> TaskTemplate:
        self._ensure_can_create(payload, auth_context)
        await self._validate_template_relations(
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            created_by_user_id=payload.created_by_user_id,
        )
        template = await self.repository.create_template(
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            created_by_user_id=payload.created_by_user_id,
            title=payload.title,
            description=payload.description,
            task_type=payload.task_type.value,
            response_required=payload.response_required,
            default_deadline_rule=payload.default_deadline_rule,
            audience_type=payload.audience_type.value,
            exclude_creator=payload.exclude_creator,
            settings=payload.settings,
            is_active=payload.is_active,
        )
        await self.session.commit()
        await self.session.refresh(template)
        return template

    async def list(
        self,
        *,
        auth_context: AuthContext,
        organization_id: UUID | None = None,
        chat_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
        is_active: bool | None = True,
    ) -> list[TaskTemplate]:
        templates = await self.repository.list_templates(
            organization_id=organization_id,
            chat_id=chat_id,
            created_by_user_id=created_by_user_id,
            is_active=is_active,
        )
        return [template for template in templates if self._can_access(template, auth_context)]

    async def get(self, template_id: UUID, auth_context: AuthContext) -> TaskTemplate:
        template = await self.repository.get_template(template_id)
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task template not found",
            )
        self._ensure_can_access(template, auth_context)
        return template

    async def update(
        self,
        template_id: UUID,
        payload: TaskTemplateUpdate,
        auth_context: AuthContext,
    ) -> TaskTemplate:
        template = await self.get(template_id, auth_context)
        values = self._normalize_update_values(payload)
        if values:
            target_organization_id = values.get("organization_id", template.organization_id)
            target_chat_id = values.get("chat_id", template.chat_id)
            target_created_by_user_id = values.get("created_by_user_id", template.created_by_user_id)
            if "created_by_user_id" in values and not self._is_super_admin(auth_context):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only super_admin can change template creator",
                )
            self._ensure_scope_matches(
                organization_id=target_organization_id,
                chat_id=target_chat_id,
                auth_context=auth_context,
            )
            await self._validate_template_relations(
                organization_id=target_organization_id,
                chat_id=target_chat_id,
                created_by_user_id=target_created_by_user_id,
            )
            template = await self.repository.update_template(template, values=values)
            await self.session.commit()
            await self.session.refresh(template)
        return template

    async def delete(self, template_id: UUID, auth_context: AuthContext) -> TaskTemplate:
        template = await self.get(template_id, auth_context)
        template = await self.repository.soft_delete_template(template)
        await self.session.commit()
        await self.session.refresh(template)
        return template

    def _ensure_can_create(
        self,
        payload: TaskTemplateCreate,
        auth_context: AuthContext,
    ) -> None:
        if not self._is_super_admin(auth_context) and payload.created_by_user_id != auth_context.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Task template creator must match authenticated user",
            )
        self._ensure_scope_matches(
            organization_id=payload.organization_id,
            chat_id=payload.chat_id,
            auth_context=auth_context,
        )

    def _ensure_can_access(self, template: TaskTemplate, auth_context: AuthContext) -> None:
        if self._can_access(template, auth_context):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Task template requires creator, chat_admin or super_admin role",
        )

    def _can_access(self, template: TaskTemplate, auth_context: AuthContext) -> bool:
        if self._is_super_admin(auth_context):
            return True
        if template.created_by_user_id == auth_context.user_id:
            return True
        return auth_context.has_role(ROLE_CHAT_ADMIN) and self._scope_matches_template(
            template,
            auth_context,
        )

    def _scope_matches_template(self, template: TaskTemplate, auth_context: AuthContext) -> bool:
        if auth_context.chat_id is not None:
            return auth_context.chat_id == template.chat_id
        if auth_context.organization_id is not None:
            return auth_context.organization_id == template.organization_id
        return False

    def _ensure_scope_matches(
        self,
        *,
        organization_id: Any,
        chat_id: Any,
        auth_context: AuthContext,
    ) -> None:
        if self._is_super_admin(auth_context):
            return
        if auth_context.organization_id is not None and auth_context.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Task template organization scope mismatch",
            )
        if auth_context.chat_id is not None and auth_context.chat_id != chat_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Task template chat scope mismatch",
            )

    async def _validate_template_relations(
        self,
        *,
        organization_id: UUID,
        chat_id: UUID,
        created_by_user_id: UUID,
    ) -> None:
        if not await self.repository.organization_exists(organization_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
        chat = await self.repository.get_chat(chat_id)
        if chat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found",
            )
        if chat.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chat does not belong to organization",
            )
        if not await self.repository.user_exists(created_by_user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Creator user not found",
            )

    def _normalize_update_values(self, payload: TaskTemplateUpdate) -> dict[str, Any]:
        values = payload.model_dump(exclude_unset=True)
        if "task_type" in values:
            values["task_type"] = values["task_type"].value
        if "audience_type" in values:
            values["audience_type"] = values["audience_type"].value
        return values

    def _is_super_admin(self, auth_context: AuthContext) -> bool:
        return auth_context.is_super_admin or auth_context.has_role(ROLE_SUPER_ADMIN)
