from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.integrations.enums import BitrixSyncStatus, BitrixUserMatchSource


class BitrixUserMappingCreate(BaseModel):
    organization_id: UUID
    user_id: UUID
    bitrix_user_id: str = Field(min_length=1, max_length=255)
    match_source: BitrixUserMatchSource
    is_active: bool = True


class BitrixUserMappingUpdate(BaseModel):
    organization_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    bitrix_user_id: Optional[str] = Field(default=None, min_length=1, max_length=255)
    match_source: Optional[BitrixUserMatchSource] = None
    is_active: Optional[bool] = None

    @field_validator("organization_id", "user_id", "bitrix_user_id", "match_source", "is_active")
    @classmethod
    def reject_mapping_field_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class BitrixUserMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    bitrix_user_id: str
    match_source: BitrixUserMatchSource
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BitrixTaskLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    organization_id: UUID
    bitrix_portal_url: Optional[str]
    bitrix_task_id: Optional[str]
    sync_status: BitrixSyncStatus
    last_sync_at: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class BitrixTaskSyncRead(BaseModel):
    task_id: UUID
    organization_id: UUID
    sync_status: BitrixSyncStatus
    action: str
    detail: str
    bitrix_task_id: Optional[str] = None
    last_error: Optional[str] = None
    link: Optional[BitrixTaskLinkRead] = None


class BitrixTaskSyncStatusRead(BaseModel):
    task_id: UUID
    sync_status: BitrixSyncStatus
    detail: str
    link: Optional[BitrixTaskLinkRead] = None


class BitrixRetryFailedSyncRead(BaseModel):
    limit: int
    results: list[BitrixTaskSyncRead]
