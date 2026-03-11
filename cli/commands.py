"""
CLI commands for managing and running the scheduler.
Each command is a Click command that operates on the shared Config object.
"""
import asyncio
import json
from datetime import datetime, timezone

import click

from scheduler.events import EventBus
from scheduler.models import Job, ScheduleType
from scheduler.scheduler import Scheduler
from scheduler.storage import SQLiteStorage
from scheduler.worker import WorkerPool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _storage(ctx: click.Context) -> SQLiteStorage:
    config = ctx.obj["config"]
    return SQLiteStorage(db_path=config.db_path)


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@click.command("add")
@click.option("--name", required=True, help="Human-readable job name.")
@click.option("--func-path", required=True, help="Registered job name or dotted import path.")
@click.option(
    "--schedule-type",
    type=click.Choice(["once", "interval"], case_sensitive=False),
    default="once",
    show_default=True,
)
@click.option("--interval", type=float, default=None, help="Interval in seconds (for 'interval' schedule).")
@click.option("--run-at", default=None, help="ISO 8601 datetime for first run (defaults to now).")
@click.option("--args", "args_json", default="[]", help="JSON array of positional arguments.")
@click.option("--kwargs", "kwargs_json", default="{}", help="JSON object of keyword arguments.")
@click.pass_context
def add(
    ctx: click.Context,
    name: str,
    func_path: str,
    schedule_type: str,
    interval: float | None,
    run_at: str | None,
    args_json: str,
    kwargs_json: str,
) -> None:
    """Schedule a new job."""
    storage = _storage(ctx)

    if run_at:
        next_run_time = datetime.fromisoformat(run_at)
        if next_run_time.tzinfo is None:
            next_run_time = next_run_time.replace(tzinfo=timezone.utc)
    else:
        next_run_time = datetime.now(timezone.utc)

    job = Job(
        name=name,
        func_path=func_path,
        args=json.loads(args_json),
        kwargs=json.loads(kwargs_json),
        schedule_type=ScheduleType(schedule_type),
        interval_seconds=interval,
        next_run_time=next_run_time,
    )
    storage.add_job(job)
    click.echo(f"✔ Job '{name}' scheduled with id {job.id}")


@click.command("list-jobs")
@click.pass_context
def list_jobs(ctx: click.Context) -> None:
    """List all scheduled jobs."""
    storage = _storage(ctx)
    jobs = storage.list_jobs()

    if not jobs:
        click.echo("No jobs found.")
        return

    col_widths = {"id": 36, "name": 20, "func": 30, "schedule": 10, "status": 10, "next_run": 20}
    header = (
        f"{'ID':<{col_widths['id']}}  "
        f"{'Name':<{col_widths['name']}}  "
        f"{'Func':<{col_widths['func']}}  "
        f"{'Schedule':<{col_widths['schedule']}}  "
        f"{'Status':<{col_widths['status']}}  "
        f"{'Next Run':<{col_widths['next_run']}}"
    )
    click.echo(header)
    click.echo("-" * len(header))
    for job in jobs:
        click.echo(
            f"{job.id:<{col_widths['id']}}  "
            f"{job.name:<{col_widths['name']}}  "
            f"{job.func_path:<{col_widths['func']}}  "
            f"{job.schedule_type.value:<{col_widths['schedule']}}  "
            f"{job.status.value:<{col_widths['status']}}  "
            f"{_fmt_dt(job.next_run_time):<{col_widths['next_run']}}"
        )


@click.command("remove")
@click.argument("job_id")
@click.pass_context
def remove(ctx: click.Context, job_id: str) -> None:
    """Remove a job by JOB_ID."""
    storage = _storage(ctx)
    job = storage.get_job(job_id)
    if job is None:
        click.echo(f"No job found with id '{job_id}'.", err=True)
        raise SystemExit(1)
    storage.delete_job(job_id)
    click.echo(f"✔ Job '{job.name}' ({job_id}) removed.")


@click.command("run")
@click.pass_context
def run(ctx: click.Context) -> None:
    """Start the scheduler daemon."""
    config = ctx.obj["config"]
    storage = SQLiteStorage(db_path=config.db_path)
    event_bus = EventBus()
    worker_pool = WorkerPool(max_workers=config.max_workers, event_bus=event_bus)
    scheduler = Scheduler(
        config=config,
        storage=storage,
        worker_pool=worker_pool,
        event_bus=event_bus,
    )
    click.echo("Starting scheduler… (Ctrl-C to stop)")
    try:
        asyncio.run(scheduler.start())
    except KeyboardInterrupt:
        scheduler.stop()
        click.echo("\nScheduler stopped.")


@click.command("history")
@click.option("--job-id", default=None, help="Filter results for a specific job id.")
@click.option("--limit", default=20, show_default=True, help="Maximum number of results to show.")
@click.pass_context
def history(ctx: click.Context, job_id: str | None, limit: int) -> None:
    """Show execution history."""
    storage = _storage(ctx)
    results = storage.get_results(job_id=job_id, limit=limit)

    if not results:
        click.echo("No results found.")
        return

    col_widths = {"id": 36, "job_id": 36, "success": 8, "duration": 10, "executed_at": 20}
    header = (
        f"{'Result ID':<{col_widths['id']}}  "
        f"{'Job ID':<{col_widths['job_id']}}  "
        f"{'OK':<{col_widths['success']}}  "
        f"{'Duration':<{col_widths['duration']}}  "
        f"{'Executed At':<{col_widths['executed_at']}}"
    )
    click.echo(header)
    click.echo("-" * len(header))
    for r in results:
        click.echo(
            f"{r.id:<{col_widths['id']}}  "
            f"{r.job_id:<{col_widths['job_id']}}  "
            f"{'yes' if r.success else 'no':<{col_widths['success']}}  "
            f"{r.duration_seconds:<{col_widths['duration']}.3f}  "
            f"{_fmt_dt(r.executed_at):<{col_widths['executed_at']}}"
        )
