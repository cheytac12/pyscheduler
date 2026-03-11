"""
Core scheduler loop: polls storage for due jobs, dispatches them to the WorkerPool,
and handles results (updating job status and scheduling next run).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .config import Config
from .events import Event, EventBus, EventType
from .models import Job, JobResult, JobStatus, ScheduleType
from .storage import SQLiteStorage
from .worker import WorkerPool

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(
        self,
        config: Config,
        storage: SQLiteStorage,
        worker_pool: WorkerPool,
        event_bus: EventBus,
    ) -> None:
        self._config = config
        self._storage = storage
        self._worker_pool = worker_pool
        self._event_bus = event_bus
        self._running = False
        # Track jobs currently being executed to avoid double-dispatch
        self._in_flight: set[str] = set()

    async def start(self) -> None:
        """Main scheduler loop. Runs until stop() is called."""
        self._running = True
        self._event_bus.publish(Event(type=EventType.SCHEDULER_STARTED))
        logger.info("Scheduler started (poll_interval=%.1fs).", self._config.poll_interval)

        while self._running:
            due_jobs = self._storage.get_due_jobs()
            for job in due_jobs:
                if job.id not in self._in_flight:
                    self._dispatch(job)
            await asyncio.sleep(self._config.poll_interval)

        self._worker_pool.shutdown()
        self._event_bus.publish(Event(type=EventType.SCHEDULER_STOPPED))
        logger.info("Scheduler stopped.")

    def stop(self) -> None:
        """Signal the scheduler to stop after the current poll cycle."""
        self._running = False

    def _dispatch(self, job: Job) -> None:
        """Mark a job as RUNNING and submit it to the worker pool."""
        job.status = JobStatus.RUNNING
        self._storage.update_job(job)
        self._in_flight.add(job.id)
        self._worker_pool.submit(job, callback=self._on_result)
        logger.info("Dispatched job '%s' (%s).", job.name, job.id)

    def _on_result(self, result: JobResult) -> None:
        """Callback invoked by the WorkerPool when a job finishes."""
        self._in_flight.discard(result.job_id)
        job = self._storage.get_job(result.job_id)
        if job is None:
            logger.warning("Received result for unknown job id '%s'.", result.job_id)
            return

        job.last_run_at = result.executed_at

        if result.success:
            if job.schedule_type == ScheduleType.INTERVAL:
                job.status = JobStatus.PENDING
                job.next_run_time = self._calculate_next_run(job)
                logger.info("Job '%s' completed; rescheduled in %.1fs.", job.name, job.interval_seconds)
            else:
                job.status = JobStatus.COMPLETED
                logger.info("Job '%s' completed (once).", job.name)
        else:
            job.status = JobStatus.FAILED
            logger.error("Job '%s' failed: %s", job.name, result.error)

        self._storage.update_job(job)
        self._storage.save_result(result)

    def _calculate_next_run(self, job: Job) -> datetime:
        """For INTERVAL jobs, compute the next run time from the current moment."""
        interval = job.interval_seconds or 0.0
        return datetime.now(timezone.utc) + timedelta(seconds=interval)
