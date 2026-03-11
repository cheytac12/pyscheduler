"""
Tests for SQLiteStorage: CRUD operations on jobs and results, plus due-job filtering.
"""
from datetime import datetime, timedelta, timezone

import pytest

from scheduler.models import Job, JobResult, JobStatus, ScheduleType
from scheduler.storage import SQLiteStorage


def make_job(*, minutes_offset: float = -1.0, status: JobStatus = JobStatus.PENDING) -> Job:
    """Helper: create a Job due *minutes_offset* minutes from now."""
    return Job(
        name="test-job",
        func_path="greet",
        schedule_type=ScheduleType.ONCE,
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=minutes_offset),
        status=status,
    )


@pytest.fixture()
def storage(tmp_path):
    return SQLiteStorage(db_path=str(tmp_path / "test.db"))


def test_add_and_get_job(storage):
    job = make_job()
    storage.add_job(job)
    fetched = storage.get_job(job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.name == job.name


def test_get_job_missing(storage):
    assert storage.get_job("nonexistent") is None


def test_list_jobs(storage):
    j1, j2 = make_job(), make_job()
    storage.add_job(j1)
    storage.add_job(j2)
    jobs = storage.list_jobs()
    ids = {j.id for j in jobs}
    assert j1.id in ids
    assert j2.id in ids


def test_update_job(storage):
    job = make_job()
    storage.add_job(job)
    job.status = JobStatus.COMPLETED
    storage.update_job(job)
    fetched = storage.get_job(job.id)
    assert fetched.status == JobStatus.COMPLETED


def test_delete_job(storage):
    job = make_job()
    storage.add_job(job)
    storage.delete_job(job.id)
    assert storage.get_job(job.id) is None


def test_get_due_jobs_past(storage):
    job = make_job(minutes_offset=-5.0)  # due 5 minutes ago
    storage.add_job(job)
    due = storage.get_due_jobs()
    assert any(j.id == job.id for j in due)


def test_get_due_jobs_future(storage):
    job = make_job(minutes_offset=10.0)  # due 10 minutes from now
    storage.add_job(job)
    due = storage.get_due_jobs()
    assert not any(j.id == job.id for j in due)


def test_save_and_get_results(storage):
    job = make_job()
    storage.add_job(job)
    result = JobResult(
        job_id=job.id,
        success=True,
        output="ok",
        executed_at=datetime.now(timezone.utc),
        duration_seconds=0.1,
    )
    storage.save_result(result)
    results = storage.get_results(job_id=job.id)
    assert len(results) == 1
    assert results[0].job_id == job.id
    assert results[0].success is True


def test_get_results_no_filter(storage):
    job = make_job()
    storage.add_job(job)
    for _ in range(3):
        storage.save_result(
            JobResult(
                job_id=job.id,
                success=True,
                executed_at=datetime.now(timezone.utc),
                duration_seconds=0.05,
            )
        )
    assert len(storage.get_results()) == 3
