"""
Unit tests for the Scheduler: next-run calculation and result-handling logic.
Uses unittest.mock to avoid requiring a real database or worker pool.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from scheduler.config import Config
from scheduler.events import EventBus
from scheduler.models import Job, JobResult, JobStatus, ScheduleType
from scheduler.scheduler import Scheduler


def make_scheduler() -> Scheduler:
    config = Config(db_path=":memory:", poll_interval=0.1)
    storage = MagicMock()
    worker_pool = MagicMock()
    event_bus = EventBus()
    return Scheduler(config=config, storage=storage, worker_pool=worker_pool, event_bus=event_bus)


def make_interval_job(interval_seconds: float = 60.0) -> Job:
    return Job(
        name="interval-job",
        func_path="greet",
        schedule_type=ScheduleType.INTERVAL,
        interval_seconds=interval_seconds,
        next_run_time=datetime.now(timezone.utc),
    )


def make_once_job() -> Job:
    return Job(
        name="once-job",
        func_path="greet",
        schedule_type=ScheduleType.ONCE,
        next_run_time=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# _calculate_next_run
# ---------------------------------------------------------------------------


def test_calculate_next_run_uses_interval():
    scheduler = make_scheduler()
    job = make_interval_job(interval_seconds=120.0)
    before = datetime.now(timezone.utc)
    next_run = scheduler._calculate_next_run(job)
    after = datetime.now(timezone.utc)
    assert before + timedelta(seconds=120.0) <= next_run <= after + timedelta(seconds=120.0)


# ---------------------------------------------------------------------------
# _on_result — ONCE job
# ---------------------------------------------------------------------------


def test_on_result_once_job_completed():
    scheduler = make_scheduler()
    job = make_once_job()
    scheduler._storage.get_job.return_value = job

    result = JobResult(
        job_id=job.id,
        success=True,
        executed_at=datetime.now(timezone.utc),
        duration_seconds=0.1,
    )
    scheduler._on_result(result)

    assert job.status == JobStatus.COMPLETED
    scheduler._storage.update_job.assert_called_once_with(job)
    scheduler._storage.save_result.assert_called_once_with(result)


def test_on_result_once_job_failed():
    scheduler = make_scheduler()
    job = make_once_job()
    scheduler._storage.get_job.return_value = job

    result = JobResult(
        job_id=job.id,
        success=False,
        error="something went wrong",
        executed_at=datetime.now(timezone.utc),
        duration_seconds=0.2,
    )
    scheduler._on_result(result)

    assert job.status == JobStatus.FAILED


# ---------------------------------------------------------------------------
# _on_result — INTERVAL job
# ---------------------------------------------------------------------------


def test_on_result_interval_job_rescheduled():
    scheduler = make_scheduler()
    job = make_interval_job(interval_seconds=30.0)
    scheduler._storage.get_job.return_value = job

    result = JobResult(
        job_id=job.id,
        success=True,
        executed_at=datetime.now(timezone.utc),
        duration_seconds=0.05,
    )
    before = datetime.now(timezone.utc)
    scheduler._on_result(result)
    after = datetime.now(timezone.utc)

    assert job.status == JobStatus.PENDING
    assert before + timedelta(seconds=30.0) <= job.next_run_time <= after + timedelta(seconds=30.0)


def test_on_result_unknown_job_id():
    """Should log a warning and not crash when job_id doesn't exist in storage."""
    scheduler = make_scheduler()
    scheduler._storage.get_job.return_value = None

    result = JobResult(
        job_id="ghost-id",
        success=True,
        executed_at=datetime.now(timezone.utc),
        duration_seconds=0.0,
    )
    # Should not raise
    scheduler._on_result(result)
    scheduler._storage.update_job.assert_not_called()
