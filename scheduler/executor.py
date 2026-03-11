"""
Executes a single Job in an isolated manner:
- Captures stdout
- Enforces a timeout
- Measures wall-clock duration
- Returns a JobResult regardless of success or failure
"""
import contextlib
import io
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone

from .jobs import resolve_func
from .models import Job, JobResult


def execute_job(job: Job, timeout: float = 30.0) -> JobResult:
    """Run *job* and return a JobResult capturing output, errors and timing."""
    executed_at = datetime.now(timezone.utc)
    start = time.monotonic()

    def _run() -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            func = resolve_func(job.func_path)
            func(*job.args, **job.kwargs)
        return buf.getvalue()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run)
            output = future.result(timeout=timeout)
        duration = time.monotonic() - start
        return JobResult(
            job_id=job.id,
            success=True,
            output=output,
            executed_at=executed_at,
            duration_seconds=duration,
        )
    except FuturesTimeoutError:
        duration = time.monotonic() - start
        return JobResult(
            job_id=job.id,
            success=False,
            error=f"Job timed out after {timeout}s",
            executed_at=executed_at,
            duration_seconds=duration,
        )
    except Exception as exc:  # noqa: BLE001
        duration = time.monotonic() - start
        return JobResult(
            job_id=job.id,
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            executed_at=executed_at,
            duration_seconds=duration,
        )
