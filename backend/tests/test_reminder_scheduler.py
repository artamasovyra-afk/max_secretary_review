from __future__ import annotations

import asyncio
import logging

import pytest

from app.modules.reminders.scheduler import (
    ReminderSchedulerConfig,
    build_reminder_scheduler,
    parse_daily_summary_time,
    run_reminder_scheduler,
)


def test_parse_daily_summary_time() -> None:
    assert parse_daily_summary_time("09:00") == (9, 0)
    assert parse_daily_summary_time("23:59") == (23, 59)


@pytest.mark.parametrize("value", ["9", "24:00", "10:60", "aa:bb"])
def test_parse_daily_summary_time_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_daily_summary_time(value)


def test_build_reminder_scheduler_registers_jobs() -> None:
    scheduler = build_reminder_scheduler(
        ReminderSchedulerConfig(
            reminders_enabled=True,
            poll_interval_seconds=60,
            daily_summary_time="09:30",
        )
    )

    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert set(jobs) == {
        "mark_overdue_tasks",
        "run_due_reminders",
        "run_due_scheduled_tasks",
        "run_daily_summary",
        "run_daily_manager_summaries",
    }
    assert str(jobs["mark_overdue_tasks"].trigger) == "interval[0:01:00]"
    assert str(jobs["run_due_reminders"].trigger) == "interval[0:01:00]"
    assert str(jobs["run_due_scheduled_tasks"].trigger) == "interval[0:01:00]"
    assert "hour='9'" in str(jobs["run_daily_summary"].trigger)
    assert "minute='30'" in str(jobs["run_daily_summary"].trigger)
    assert "hour='9'" in str(jobs["run_daily_manager_summaries"].trigger)
    assert "minute='30'" in str(jobs["run_daily_manager_summaries"].trigger)


def test_build_reminder_scheduler_rejects_invalid_poll_interval() -> None:
    with pytest.raises(ValueError, match="REMINDER_POLL_INTERVAL_SECONDS"):
        build_reminder_scheduler(
            ReminderSchedulerConfig(
                reminders_enabled=True,
                poll_interval_seconds=0,
                daily_summary_time="09:00",
            )
        )


@pytest.mark.anyio
async def test_disabled_reminder_scheduler_does_not_start(caplog: pytest.LogCaptureFixture) -> None:
    shutdown_event = asyncio.Event()
    shutdown_event.set()
    caplog.set_level(logging.INFO, logger="app.modules.reminders.scheduler")

    await run_reminder_scheduler(
        ReminderSchedulerConfig(reminders_enabled=False),
        shutdown_event=shutdown_event,
    )

    assert "Reminder scheduler disabled" in caplog.text


@pytest.mark.anyio
async def test_enabled_reminder_scheduler_starts_and_stops(caplog: pytest.LogCaptureFixture) -> None:
    shutdown_event = asyncio.Event()
    shutdown_event.set()
    caplog.set_level(logging.INFO, logger="app.modules.reminders.scheduler")

    await run_reminder_scheduler(
        ReminderSchedulerConfig(
            reminders_enabled=True,
            poll_interval_seconds=60,
            daily_summary_time="09:00",
        ),
        shutdown_event=shutdown_event,
    )

    assert "Reminder scheduler started" in caplog.text
    assert "Reminder scheduler stopped" in caplog.text
