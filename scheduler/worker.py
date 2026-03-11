"""
WorkerPool: manages a pool of threads for concurrent job execution.
Publishes lifecycle events via the EventBus.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .events import Event, EventBus, EventType
from .executor import execute_job
from .models import Job, JobResult

logger = logging.getLogger(__name__)


class WorkerPool:
    def __init__(self, max_workers: int, event_bus: EventBus) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._event_bus = event_bus

    def submit(self, job: Job, callback: Callable[[JobResult], None]) -> None:
        """Submit *job* for execution. *callback* is called with the JobResult when done."""
        def _task() -> None:
            self._event_bus.publish(Event(type=EventType.JOB_STARTED, job_id=job.id))
            result = execute_job(job)
            event_type = EventType.JOB_COMPLETED if result.success else EventType.JOB_FAILED
            self._event_bus.publish(Event(type=event_type, job_id=job.id, data={"success": result.success}))
            callback(result)

        self._executor.submit(_task)
        logger.debug("Submitted job '%s' (%s) to worker pool.", job.name, job.id)

    def shutdown(self) -> None:
        """Wait for all running jobs to finish, then shut down."""
        self._executor.shutdown(wait=True)
        logger.info("Worker pool shut down.")
