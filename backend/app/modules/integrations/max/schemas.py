from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TextFormat = Literal["markdown", "html"]


class MaxSendMessageRequest(BaseModel):
    text: Optional[str] = Field(default=None, max_length=4000)
    attachments: Optional[list[dict[str, Any]]] = None
    link: Optional[dict[str, Any]] = None
    notify: bool = True
    format: Optional[TextFormat] = None


class MaxSendMessageResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: Optional[dict[str, Any]] = None


class MaxBotInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: Optional[int] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    username: Optional[str] = None
    is_bot: Optional[bool] = None


class MaxTaskCard(BaseModel):
    id: Optional[str] = None
    title: str
    status: Optional[str] = None
    deadline_at: Optional[str] = None
