from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


DEFAULT_DAILY_SUMMARY_TIME = "09:00"


@dataclass(frozen=True)
class ChatDailySummarySettings:
    daily_summary_enabled: bool = False
    daily_summary_time: str = DEFAULT_DAILY_SUMMARY_TIME
    daily_summary_recipients: tuple[UUID, ...] = ()


def parse_chat_daily_summary_settings(settings: dict | None) -> ChatDailySummarySettings:
    settings = settings or {}
    return ChatDailySummarySettings(
        daily_summary_enabled=bool(settings.get("daily_summary_enabled", False)),
        daily_summary_time=_parse_summary_time(settings.get("daily_summary_time")),
        daily_summary_recipients=_parse_recipients(settings.get("daily_summary_recipients")),
    )


def _parse_summary_time(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return DEFAULT_DAILY_SUMMARY_TIME
    parts = value.strip().split(":")
    if len(parts) != 2:
        return DEFAULT_DAILY_SUMMARY_TIME
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return DEFAULT_DAILY_SUMMARY_TIME
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return DEFAULT_DAILY_SUMMARY_TIME
    return f"{hour:02d}:{minute:02d}"


def _parse_recipients(value: object) -> tuple[UUID, ...]:
    if not isinstance(value, list):
        return ()

    recipients: list[UUID] = []
    seen: set[UUID] = set()
    for item in value:
        try:
            user_id = UUID(str(item))
        except (TypeError, ValueError):
            continue
        if user_id in seen:
            continue
        recipients.append(user_id)
        seen.add(user_id)
    return tuple(recipients)
