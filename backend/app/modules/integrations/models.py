from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.integrations.enums import BitrixSyncStatus, BitrixUserMatchSource

if TYPE_CHECKING:
    from app.modules.organizations.models import Organization
    from app.modules.tasks.models import Task
    from app.modules.users.models import User


class IntegrationAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_accounts"

    organization_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    auth_type: Mapped[str] = mapped_column(String(50), nullable=False)
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
    )

    organization: Mapped["Organization"] = relationship(back_populates="integration_accounts")


class BitrixTaskLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bitrix_task_links"
    __table_args__ = (
        Index(
            "uq_bitrix_task_links_active_task_id",
            "task_id",
            unique=True,
            postgresql_where=text("sync_status != 'disabled'"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bitrix_portal_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bitrix_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    sync_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=BitrixSyncStatus.PENDING.value,
        server_default=BitrixSyncStatus.PENDING.value,
        index=True,
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="bitrix_task_links")
    task: Mapped["Task"] = relationship(back_populates="bitrix_task_links")


class BitrixUserMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bitrix_user_mappings"
    __table_args__ = (
        Index(
            "uq_bitrix_user_mappings_active_org_user",
            "organization_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bitrix_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    match_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=BitrixUserMatchSource.MANUAL.value,
        server_default=BitrixUserMatchSource.MANUAL.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
    )

    organization: Mapped["Organization"] = relationship(back_populates="bitrix_user_mappings")
    user: Mapped["User"] = relationship(back_populates="bitrix_user_mappings")
