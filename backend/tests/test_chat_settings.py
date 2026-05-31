from __future__ import annotations

from uuid import uuid4

from app.modules.chats.settings import DEFAULT_DAILY_SUMMARY_TIME, parse_chat_daily_summary_settings


def test_daily_summary_settings_defaults_are_disabled() -> None:
    settings = parse_chat_daily_summary_settings(None)

    assert settings.daily_summary_enabled is False
    assert settings.daily_summary_time == DEFAULT_DAILY_SUMMARY_TIME
    assert settings.daily_summary_recipients == ()


def test_daily_summary_settings_parse_enabled_time_and_recipients() -> None:
    first_user_id = uuid4()
    second_user_id = uuid4()

    settings = parse_chat_daily_summary_settings(
        {
            "daily_summary_enabled": True,
            "daily_summary_time": "8:05",
            "daily_summary_recipients": [
                str(first_user_id),
                str(second_user_id),
                str(first_user_id),
                "not-a-uuid",
            ],
        }
    )

    assert settings.daily_summary_enabled is True
    assert settings.daily_summary_time == "08:05"
    assert settings.daily_summary_recipients == (first_user_id, second_user_id)


def test_daily_summary_settings_fallback_to_default_time_for_invalid_value() -> None:
    settings = parse_chat_daily_summary_settings(
        {
            "daily_summary_enabled": True,
            "daily_summary_time": "25:99",
            "daily_summary_recipients": "not-a-list",
        }
    )

    assert settings.daily_summary_enabled is True
    assert settings.daily_summary_time == DEFAULT_DAILY_SUMMARY_TIME
    assert settings.daily_summary_recipients == ()
