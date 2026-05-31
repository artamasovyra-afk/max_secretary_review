from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserStatus(BaseModel):
    status: str
    module: str


class UserCreate(BaseModel):
    max_user_id: Optional[str] = Field(default=None, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    username: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=64)
    email: Optional[str] = Field(default=None, max_length=255)


class UserUpdate(BaseModel):
    max_user_id: Optional[str] = Field(default=None, max_length=255)
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    username: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=64)
    email: Optional[str] = Field(default=None, max_length=255)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            raise ValueError("display_name cannot be null")
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    max_user_id: Optional[str]
    display_name: str
    username: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    created_at: datetime
    updated_at: datetime
