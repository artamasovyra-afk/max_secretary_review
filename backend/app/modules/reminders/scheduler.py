from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timezone
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import Settings, get_settings
from app.modules.reminders.jobs import (
    mark_overdue_tasks,
    run_daily_manager_summaries,
    run_daily_summary,
    run_due_reminders,
    run_due_scheduled_tasks,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReminderSchedulerConfig:
    reminders_enabled: bool = True
    poll_interval_seconds: int = 60
    daily_summary_time: str = "09:00"

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ReminderSchedulerConfig":
        settings = settings or get_settings()
        return cls(
            reminders_enabled=settings.reminders_enabled,
            poll_interval_seconds=settings.reminder_poll_interval_seconds,
            daily_summary_time=settings.daily_summary_time,
        )


def build_reminder_scheduler(config: ReminderSchedulerConfig) -> AsyncIOScheduler:
    poll_interval_seconds = _validate_poll_interval(config.poll_interval_seconds)
    daily_summary_hour, daily_summary_minute = parse_daily_summary_time(config.daily_summary_time)
    scheduler = AsyncIOScheduler(
        timezone=timezone.utc,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": max(60, poll_interval_seconds),
        },
    )
    scheduler.add_job(
        mark_overdue_tasks,
        "interval",
        seconds=poll_interval_seconds,
        id="mark_overdue_tasks",
        replace_existing=True,
    )
    scheduler.add_job(
        run_due_reminders,
        "interval",
        seconds=poll_interval_seconds,
        id="run_due_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        run_due_scheduled_tasks,
        "interval",
        seconds=poll_interval_seconds,
        id="run_due_scheduled_tasks",
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_summary,
        "cron",
        hour=daily_summary_hour,
        minute=daily_summary_minute,
        id="run_daily_summary",
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_manager_summaries,
        "cron",
        hour=daily_summary_hour,
        minute=daily_summary_minute,
        id="run_daily_manager_summaries",
        replace_existing=True,
    )
    return scheduler


async def run_reminder_scheduler(
    config: ReminderSchedulerConfig | None = None,
    *,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    config = config or ReminderSchedulerConfig.from_settings()
    if not config.reminders_enabled:
        logger.info("Reminder scheduler disabled by REMINDERS_ENABLED=false")
        await wait_for_shutdown_signal(shutdown_event=shutdown_event)
        return

    scheduler = build_reminder_scheduler(config)
    scheduler.start()
    logger.info(
        "Reminder scheduler started",
        extra={
            "poll_interval_seconds": config.poll_interval_seconds,
            "daily_summary_time": config.daily_summary_time,
        },
    )
    try:
        await wait_for_shutdown_signal(shutdown_event=shutdown_event)
    finally:
        scheduler.shutdown(wait=True)
        logger.info("Reminder scheduler stopped")


async def wait_for_shutdown_signal(*, shutdown_event: asyncio.Event | None = None) -> None:
    if shutdown_event is not None:
        await shutdown_event.wait()
        return

    event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_number, event.set)
        except NotImplementedError:
            signal.signal(signal_number, lambda _signum, _frame: loop.call_soon_threadsafe(event.set))

    await event.wait()


def parse_daily_summary_time(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("DAILY_SUMMARY_TIME must use HH:MM format")

    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError("DAILY_SUMMARY_TIME must use numeric HH:MM format") from exc

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("DAILY_SUMMARY_TIME must be a valid 24-hour time")

    return hour, minute


def _validate_poll_interval(value: int) -> int:
    if value <= 0:
        raise ValueError("REMINDER_POLL_INTERVAL_SECONDS must be greater than 0")
    return value
