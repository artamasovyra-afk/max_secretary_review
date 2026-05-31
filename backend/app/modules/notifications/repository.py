from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.models import Chat
from app.modules.notifications.enums import DeliveryStatus
from app.modules.notifications.models import NotificationDelivery
from app.modules.tasks.models import Task
from app.modules.users.models import User


class NotificationDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_task(self, task_id: UUID) -> Task | None:
        return await self.session.get(Task, task_id)

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_chat(self, chat_id: UUID) -> Chat | None:
        return await self.session.get(Chat, chat_id)

    async def create_delivery(
        self,
        *,
        task_id: UUID,
        user_id: UUID | None = None,
        chat_id: UUID | None = None,
        channel: str,
        reminder_type: str | None = None,
        status: DeliveryStatus = DeliveryStatus.PENDING,
    ) -> NotificationDelivery:
        delivery = NotificationDelivery(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            channel=channel,
            reminder_type=reminder_type,
            status=status.value,
        )
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    async def find_recent_delivery(
        self,
        *,
        task_id: UUID,
        user_id: UUID | None = None,
        chat_id: UUID | None = None,
        channel: str,
        reminder_type: str | None,
        since: datetime | None,
    ) -> NotificationDelivery | None:
        query = (
            select(NotificationDelivery)
            .where(NotificationDelivery.task_id == task_id)
            .where(NotificationDelivery.channel == channel)
            .order_by(NotificationDelivery.created_at.desc())
            .limit(1)
        )
        if user_id is None:
            query = query.where(NotificationDelivery.user_id.is_(None))
        else:
            query = query.where(NotificationDelivery.user_id == user_id)
        if chat_id is None:
            query = query.where(NotificationDelivery.chat_id.is_(None))
        else:
            query = query.where(NotificationDelivery.chat_id == chat_id)
        if since is not None:
            query = query.where(NotificationDelivery.created_at >= since)
        if reminder_type is None:
            query = query.where(NotificationDelivery.reminder_type.is_(None))
        else:
            query = query.where(NotificationDelivery.reminder_type == reminder_type)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_delivery(
        self,
        delivery: NotificationDelivery,
        *,
        status: DeliveryStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        sent_at: datetime | None = None,
    ) -> NotificationDelivery:
        delivery.status = status.value
        delivery.error_code = error_code
        delivery.error_message = error_message
        delivery.sent_at = sent_at
        await self.session.flush()
        return delivery
