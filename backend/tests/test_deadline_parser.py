from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.modules.tasks.deadline_parser import (
    DEFAULT_DEADLINE_HOUR,
    DEFAULT_DEADLINE_MINUTE,
    DEFAULT_TIMEZONE,
    DeadlineParseResult,
    is_future_task_deadline,
    local_day_bounds_utc,
    parse_deadline,
)


def dt(year: int, month: int, day: int, hour: int, minute: int, tz_name: str = "UTC") -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz_name))


def assert_deadline(result: DeadlineParseResult, expected: datetime, *, raw_text: str, rule: str) -> None:
    assert result.deadline_at == expected
    assert result.raw_text == raw_text
    assert result.matched_rule == rule
    assert result.confidence > 0
    assert result.needs_clarification is False


def assert_deadline_utc(result: DeadlineParseResult, expected: datetime) -> None:
    assert result.deadline_at is not None
    assert result.deadline_at.astimezone(timezone.utc) == expected


@pytest.mark.parametrize(
    ("text", "expected", "raw_text", "rule"),
    [
        (
            "сегодня",
            dt(2026, 5, 20, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
            "сегодня",
            "relative_day_сегодня",
        ),
        (
            "завтра",
            dt(2026, 5, 21, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
            "завтра",
            "relative_day_завтра",
        ),
        (
            "послезавтра",
            dt(2026, 5, 22, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
            "послезавтра",
            "relative_day_послезавтра",
        ),
        (
            "до вечера",
            dt(2026, 5, 20, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
            "до вечера",
            "end_of_day",
        ),
        (
            "до конца дня",
            dt(2026, 5, 20, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
            "до конца дня",
            "end_of_day",
        ),
        (
            "до пятницы",
            dt(2026, 5, 22, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
            "до пятницы",
            "weekday",
        ),
        (
            "к пятнице",
            dt(2026, 5, 22, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
            "к пятнице",
            "weekday",
        ),
        (
            "25 мая",
            dt(2026, 5, 25, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
            "25 мая",
            "month_name_date",
        ),
        (
            "20.05",
            dt(2026, 5, 20, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
            "20.05",
            "numeric_date",
        ),
        (
            "20.05.2026",
            dt(2026, 5, 20, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
            "20.05.2026",
            "numeric_date",
        ),
        (
            "в 15:00",
            dt(2026, 5, 20, 15, 0),
            "в 15:00",
            "time_only",
        ),
        (
            "завтра в 15:00",
            dt(2026, 5, 21, 15, 0),
            "завтра в 15:00",
            "relative_day_завтра",
        ),
        (
            "завтра 15:00",
            dt(2026, 5, 21, 15, 0),
            "завтра 15:00",
            "relative_day_завтра",
        ),
        (
            "завтра до 18:00",
            dt(2026, 5, 21, 18, 0),
            "завтра до 18:00",
            "relative_day_завтра",
        ),
    ],
)
def test_parse_deadline_supported_expressions(
    text: str,
    expected: datetime,
    raw_text: str,
    rule: str,
) -> None:
    now = dt(2026, 5, 20, 10, 0)

    result = parse_deadline(f"сделать {text}", now, "UTC")

    assert_deadline(result, expected, raw_text=raw_text, rule=rule)


def test_parse_deadline_relative_minutes() -> None:
    now = dt(2026, 5, 20, 10, 0)

    result = parse_deadline("через 30 минут", now, "UTC")

    assert_deadline(
        result,
        now + timedelta(minutes=30),
        raw_text="через 30 минут",
        rule="relative_delta",
    )


def test_parse_deadline_relative_hours() -> None:
    now = dt(2026, 5, 20, 10, 0)

    result = parse_deadline("через 2 часа", now, "UTC")

    assert_deadline(
        result,
        now + timedelta(hours=2),
        raw_text="через 2 часа",
        rule="relative_delta",
    )


@pytest.mark.parametrize(
    ("text", "expected_local", "raw_text"),
    [
        ("через час", dt(2026, 5, 29, 18, 20, DEFAULT_TIMEZONE), "через час"),
        ("сегодня через час", dt(2026, 5, 29, 18, 20, DEFAULT_TIMEZONE), "сегодня через час"),
        ("через 1 час", dt(2026, 5, 29, 18, 20, DEFAULT_TIMEZONE), "через 1 час"),
        ("через 2 часа", dt(2026, 5, 29, 19, 20, DEFAULT_TIMEZONE), "через 2 часа"),
        ("сегодня через 2 часа", dt(2026, 5, 29, 19, 20, DEFAULT_TIMEZONE), "сегодня через 2 часа"),
        ("через 5 часов", dt(2026, 5, 29, 22, 20, DEFAULT_TIMEZONE), "через 5 часов"),
        ("через 30 минут", dt(2026, 5, 29, 17, 50, DEFAULT_TIMEZONE), "через 30 минут"),
        ("сегодня через 30 минут", dt(2026, 5, 29, 17, 50, DEFAULT_TIMEZONE), "сегодня через 30 минут"),
        ("через 1 минуту", dt(2026, 5, 29, 17, 21, DEFAULT_TIMEZONE), "через 1 минуту"),
        ("через полчаса", dt(2026, 5, 29, 17, 50, DEFAULT_TIMEZONE), "через полчаса"),
    ],
)
def test_parse_deadline_relative_expressions_have_priority_over_day_default_time(
    text: str,
    expected_local: datetime,
    raw_text: str,
) -> None:
    now = dt(2026, 5, 29, 17, 20, DEFAULT_TIMEZONE)

    result = parse_deadline(text, now, DEFAULT_TIMEZONE)

    assert_deadline(result, expected_local, raw_text=raw_text, rule="relative_delta")


def test_parse_deadline_relative_expressions_are_stored_as_utc() -> None:
    now = dt(2026, 5, 29, 17, 20, DEFAULT_TIMEZONE)

    result = parse_deadline("сегодня через час", now, DEFAULT_TIMEZONE)

    assert_deadline_utc(result, datetime(2026, 5, 29, 13, 20, tzinfo=timezone.utc))


@pytest.mark.parametrize("text", ["завтра через час", "завтра через 2 часа", "послезавтра через 30 минут"])
def test_parse_deadline_conflicting_future_day_and_relative_delta_needs_clarification(text: str) -> None:
    now = dt(2026, 5, 29, 17, 20, DEFAULT_TIMEZONE)

    result = parse_deadline(text, now, DEFAULT_TIMEZONE)

    assert result.deadline_at is None
    assert result.needs_clarification is True
    assert result.matched_rule is None


def test_parse_deadline_weekday_rolls_to_next_week_when_day_has_passed() -> None:
    now = dt(2026, 5, 23, 10, 0)

    result = parse_deadline("до пятницы", now, "UTC")

    assert_deadline(
        result,
        dt(2026, 5, 29, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
        raw_text="до пятницы",
        rule="weekday",
    )


def test_parse_deadline_uses_requested_timezone_for_local_date_and_time() -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)

    result = parse_deadline("сегодня", now, "Europe/Moscow")

    assert_deadline(
        result,
        dt(2026, 5, 20, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE, "Europe/Moscow"),
        raw_text="сегодня",
        rule="relative_day_сегодня",
    )
    assert result.deadline_at is not None
    assert result.deadline_at.utcoffset() == timedelta(hours=3)


def test_parse_deadline_uses_project_timezone_for_midnight_today() -> None:
    now = datetime(2026, 5, 26, 19, 13, tzinfo=timezone.utc)

    result = parse_deadline("сегодня 00:11", now, DEFAULT_TIMEZONE)

    assert_deadline_utc(result, datetime(2026, 5, 26, 19, 11, tzinfo=timezone.utc))
    assert result.raw_text == "сегодня 00:11"
    assert result.matched_rule == "relative_day_сегодня"


def test_parse_deadline_understands_today_until_midnight_time_in_project_timezone() -> None:
    now = datetime(2026, 5, 26, 19, 13, tzinfo=timezone.utc)

    result = parse_deadline("сегодня до 00:11", now, DEFAULT_TIMEZONE)

    assert_deadline_utc(result, datetime(2026, 5, 26, 19, 11, tzinfo=timezone.utc))
    assert result.raw_text == "сегодня до 00:11"


def test_parse_deadline_tomorrow_time_is_project_local_time() -> None:
    now = datetime(2026, 5, 26, 19, 13, tzinfo=timezone.utc)

    result = parse_deadline("завтра 15:00", now, DEFAULT_TIMEZONE)

    assert_deadline_utc(result, datetime(2026, 5, 28, 10, 0, tzinfo=timezone.utc))


def test_parse_deadline_time_only_until_uses_project_local_day_near_midnight() -> None:
    now = datetime(2026, 5, 26, 19, 13, tzinfo=timezone.utc)

    result = parse_deadline("до 01:00", now, DEFAULT_TIMEZONE)

    assert_deadline_utc(result, datetime(2026, 5, 26, 20, 0, tzinfo=timezone.utc))
    assert result.raw_text == "до 01:00"


def test_overdue_comparison_works_with_project_local_midnight_deadline() -> None:
    now = datetime(2026, 5, 26, 19, 13, tzinfo=timezone.utc)

    result = parse_deadline("сегодня 00:11", now, DEFAULT_TIMEZONE)

    assert result.deadline_at is not None
    assert result.deadline_at.astimezone(timezone.utc) < now


def test_local_day_bounds_use_project_timezone() -> None:
    now = datetime(2026, 5, 26, 19, 13, tzinfo=timezone.utc)

    today_start, today_end = local_day_bounds_utc(now)

    assert today_start == datetime(2026, 5, 26, 19, 0, tzinfo=timezone.utc)
    assert today_end == datetime(2026, 5, 27, 19, 0, tzinfo=timezone.utc)


def test_parse_deadline_time_only_rolls_to_tomorrow_when_time_has_passed() -> None:
    now = dt(2026, 5, 20, 16, 0)

    result = parse_deadline("в 15:00", now, "UTC")

    assert_deadline(
        result,
        dt(2026, 5, 21, 15, 0),
        raw_text="в 15:00",
        rule="time_only",
    )


def test_parse_deadline_rolls_short_date_to_next_year_when_date_has_passed() -> None:
    now = dt(2026, 5, 21, 10, 0)

    result = parse_deadline("20.05", now, "UTC")

    assert_deadline(
        result,
        dt(2027, 5, 20, DEFAULT_DEADLINE_HOUR, DEFAULT_DEADLINE_MINUTE),
        raw_text="20.05",
        rule="numeric_date",
    )


def test_parse_deadline_returns_clarification_for_invalid_text() -> None:
    result = parse_deadline("сделать когда-нибудь потом", dt(2026, 5, 20, 10, 0), "UTC")

    assert result.deadline_at is None
    assert result.raw_text is None
    assert result.confidence == 0
    assert result.matched_rule is None
    assert result.needs_clarification is True


def test_future_deadline_validation_rejects_project_local_past() -> None:
    now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
    deadline = datetime(2026, 5, 29, 16, 59, tzinfo=ZoneInfo(DEFAULT_TIMEZONE))

    assert is_future_task_deadline(deadline, now=now) is False


def test_future_deadline_validation_allows_project_local_future() -> None:
    now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
    deadline = datetime(2026, 5, 29, 17, 2, tzinfo=ZoneInfo(DEFAULT_TIMEZONE))

    assert is_future_task_deadline(deadline, now=now) is True


def test_future_deadline_validation_rejects_less_than_one_minute() -> None:
    now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)

    assert is_future_task_deadline(now, now=now) is False
    assert is_future_task_deadline(now + timedelta(seconds=59), now=now) is False
    assert is_future_task_deadline(now + timedelta(minutes=1), now=now) is True
