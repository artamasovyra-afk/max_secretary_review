from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class AuthContext:
    user_id: UUID
    organization_id: UUID | None = None
    chat_id: UUID | None = None
    roles: list[str] = field(default_factory=list)
    is_super_admin: bool = False
    max_user_id: str | None = None
    session_expires_at: int | None = None

    @property
    def role_values(self) -> frozenset[str]:
        return frozenset(_role_value(role) for role in self.roles)

    def has_role(self, role: str) -> bool:
        return role in self.role_values

    def has_any_role(self, roles: set[str] | frozenset[str]) -> bool:
        return bool(self.role_values & roles)


def _role_value(role: Any) -> str:
    return str(getattr(role, "value", role))
