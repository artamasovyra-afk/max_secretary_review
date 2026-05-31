from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
import os
from pathlib import Path
import sys
import time

from app.core.logging import configure_logging
from app.modules.reminders.jobs import (
    mark_overdue_tasks,
    run_daily_summary,
    run_due_reminders,
    run_due_scheduled_tasks,
)
from app.modules.reminders.scheduler import ReminderSchedulerConfig, run_reminder_scheduler

logger = logging.getLogger(__name__)
DEFAULT_WORKER_HEARTBEAT_FILE = "/tmp/max_secretary_worker_heartbeat"
DEFAULT_WORKER_HEARTBEAT_INTERVAL_SECONDS = 10
DEFAULT_WORKER_HEARTBEAT_MAX_AGE_SECONDS = 120

__all__ = [
    "is_worker_heartbeat_fresh",
    "mark_overdue_tasks",
    "run_daily_summary",
    "run_due_reminders",
    "run_due_scheduled_tasks",
    "run_worker",
    "write_worker_heartbeat",
]


async def run_worker(
    config: ReminderSchedulerConfig | None = None,
    *,
    shutdown_event: asyncio.Event | None = None,
    heartbeat_file: str | Path | None = None,
    heartbeat_interval_seconds: float = DEFAULT_WORKER_HEARTBEAT_INTERVAL_SECONDS,
) -> None:
    config = config or ReminderSchedulerConfig.from_settings()
    heartbeat_path = Path(heartbeat_file or _worker_heartbeat_file_from_env())
    write_worker_heartbeat(heartbeat_path)
    heartbeat_task = asyncio.create_task(
        run_worker_heartbeat(
            heartbeat_path,
            interval_seconds=heartbeat_interval_seconds,
        )
    )
    logger.info("worker started")
    if config.reminders_enabled:
        logger.info(
            "reminders enabled",
            extra={
                "poll_interval_seconds": config.poll_interval_seconds,
                "daily_summary_time": config.daily_summary_time,
            },
        )
    else:
        logger.info("reminders disabled")

    try:
        await run_reminder_scheduler(config, shutdown_event=shutdown_event)
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        logger.info("worker stopping")


async def run_worker_heartbeat(
    heartbeat_file: str | Path,
    *,
    interval_seconds: float = DEFAULT_WORKER_HEARTBEAT_INTERVAL_SECONDS,
) -> None:
    heartbeat_path = Path(heartbeat_file)
    while True:
        write_worker_heartbeat(heartbeat_path)
        await asyncio.sleep(interval_seconds)


def write_worker_heartbeat(heartbeat_file: str | Path) -> None:
    heartbeat_path = Path(heartbeat_file)
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.write_text(str(time.time()), encoding="utf-8")


def is_worker_heartbeat_fresh(
    heartbeat_file: str | Path | None = None,
    *,
    max_age_seconds: float | None = None,
) -> bool:
    heartbeat_path = Path(heartbeat_file or _worker_heartbeat_file_from_env())
    max_age = max_age_seconds if max_age_seconds is not None else _worker_heartbeat_max_age_from_env()
    try:
        heartbeat_mtime = heartbeat_path.stat().st_mtime
    except FileNotFoundError:
        return False
    return time.time() - heartbeat_mtime <= max_age


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    argv = argv if argv is not None else sys.argv[1:]
    if "--healthcheck" in argv:
        raise SystemExit(0 if is_worker_heartbeat_fresh() else 1)
    asyncio.run(run_worker())


def _worker_heartbeat_file_from_env() -> str:
    return os.getenv("WORKER_HEARTBEAT_FILE", DEFAULT_WORKER_HEARTBEAT_FILE)


def _worker_heartbeat_max_age_from_env() -> int:
    raw_value = os.getenv("WORKER_HEARTBEAT_MAX_AGE_SECONDS")
    if not raw_value:
        return DEFAULT_WORKER_HEARTBEAT_MAX_AGE_SECONDS
    try:
        return int(raw_value)
    except ValueError:
        return DEFAULT_WORKER_HEARTBEAT_MAX_AGE_SECONDS


if __name__ == "__main__":
    main()
