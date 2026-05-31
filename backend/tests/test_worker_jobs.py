from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import time

import pytest

from app.modules.reminders.scheduler import ReminderSchedulerConfig
from app.workers.jobs import is_worker_heartbeat_fresh, run_worker, write_worker_heartbeat


@pytest.mark.anyio
async def test_worker_logs_disabled_reminders_and_stops(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    shutdown_event = asyncio.Event()
    shutdown_event.set()
    heartbeat_file = tmp_path / "worker-heartbeat"
    caplog.set_level(logging.INFO, logger="app.workers.jobs")

    await run_worker(
        ReminderSchedulerConfig(reminders_enabled=False),
        shutdown_event=shutdown_event,
        heartbeat_file=heartbeat_file,
    )

    assert "worker started" in caplog.text
    assert "reminders disabled" in caplog.text
    assert "worker stopping" in caplog.text
    assert is_worker_heartbeat_fresh(heartbeat_file)


@pytest.mark.anyio
async def test_worker_logs_enabled_reminders_and_stops(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    shutdown_event = asyncio.Event()
    shutdown_event.set()
    heartbeat_file = tmp_path / "worker-heartbeat"
    caplog.set_level(logging.INFO, logger="app.workers.jobs")

    await run_worker(
        ReminderSchedulerConfig(
            reminders_enabled=True,
            poll_interval_seconds=60,
            daily_summary_time="09:00",
        ),
        shutdown_event=shutdown_event,
        heartbeat_file=heartbeat_file,
    )

    assert "worker started" in caplog.text
    assert "reminders enabled" in caplog.text
    assert "worker stopping" in caplog.text
    assert is_worker_heartbeat_fresh(heartbeat_file)


def test_worker_heartbeat_freshness(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "worker-heartbeat"

    assert not is_worker_heartbeat_fresh(heartbeat_file)

    write_worker_heartbeat(heartbeat_file)
    assert is_worker_heartbeat_fresh(heartbeat_file)

    stale_time = time.time() - 300
    os.utime(heartbeat_file, (stale_time, stale_time))

    assert not is_worker_heartbeat_fresh(heartbeat_file, max_age_seconds=120)
