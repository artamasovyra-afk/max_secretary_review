from __future__ import annotations

from app.core.config import Settings, get_settings
from app.modules.integrations.max.client import MaxApiClient
from app.modules.notifications.max_sender import MaxSender


def build_max_sender(settings: Settings | None = None) -> MaxSender:
    settings = settings or get_settings()
    if not settings.max_sender_enabled:
        return MaxSender(
            enabled=False,
            interactive_enabled=settings.max_interactive_responses_enabled,
            background_enabled=settings.max_background_notifications_enabled,
        )

    client_options = {
        "base_url": settings.max_api_base_url,
        "bot_token": settings.max_bot_token,
        "timeout_seconds": settings.max_request_timeout_seconds,
    }
    client = MaxApiClient(**client_options)
    return MaxSender(
        client=client,
        enabled=True,
        interactive_enabled=settings.max_interactive_responses_enabled,
        background_enabled=settings.max_background_notifications_enabled,
    )
