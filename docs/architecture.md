# PyScheduler Architecture

## Overview

PyScheduler is structured as a set of loosely-coupled components, each with a single clear responsibility. The design emphasises readability and teachability over raw performance.

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│    CLI       │────▶│  Scheduler   │────▶│  WorkerPool  │
└─────────────┘     └──────┬───────┘     └──────┬───────┘
                           │                     │
                    ┌──────▼───────┐      ┌──────▼───────┐
                    │   Storage    │      │   Executor   │
                    └─────────────┘      └──────────────┘
                           │
                    ┌──────▼───────┐
                    │   EventBus   │
                    └─────────────┘
```

---

## Components

### Config (`scheduler/config.py`)

A Pydantic `BaseSettings` model that holds all runtime configuration:

| Field            | Default        | Env var                   |
|------------------|----------------|---------------------------|
| `db_path`        | `scheduler.db` | `SCHEDULER_DB_PATH`       |
| `poll_interval`  | `1.0` s        | `SCHEDULER_POLL_INTERVAL` |
| `max_workers`    | `4`            | `SCHEDULER_MAX_WORKERS`   |
| `log_level`      | `INFO`         | `SCHEDULER_LOG_LEVEL`     |
| `log_json`       | `False`        | `SCHEDULER_LOG_JSON`      |

Values can be overridden by environment variables (prefixed `SCHEDULER_`) or passed directly when constructing the object (e.g., from the CLI).

---

### Models (`scheduler/models.py`)

Two Pydantic models define the core data shapes:

- **`Job`** — represents a scheduled task with its identity, callable reference, schedule type, next run time, and current status.
- **`JobResult`** — records the outcome of a single execution attempt: success flag, captured stdout, error message, timestamp, and wall-clock duration.

`JobStatus` and `ScheduleType` are `str` enums so they serialise naturally to/from JSON.

---

### Storage (`scheduler/storage.py`)

`SQLiteStorage` provides a simple persistence layer backed by SQLite. Both `jobs` and `results` tables store rows as JSON blobs, keeping the schema trivially simple.

Key methods:
- `add_job` / `get_job` / `list_jobs` / `update_job` / `delete_job` — full CRUD on jobs.
- `get_due_jobs` — returns all `PENDING` jobs whose `next_run_time` is ≤ now.
- `save_result` / `get_results` — append-only result history, optionally filtered by job id.

The `_connect()` context manager handles connection lifecycle and commit/rollback automatically.

---

### Events (`scheduler/events.py`)

`EventBus` is a minimal publish/subscribe bus protected by a `threading.Lock`.

```
EventType.JOB_SCHEDULED
EventType.JOB_STARTED
EventType.JOB_COMPLETED
EventType.JOB_FAILED
EventType.SCHEDULER_STARTED
EventType.SCHEDULER_STOPPED
```

Any component can subscribe to any event type; handlers are called synchronously in the publisher's thread. This keeps the implementation straightforward while still allowing clean decoupling (e.g., a future metrics collector or webhook notifier).

---

### Job Registry (`scheduler/jobs.py`)

`JOB_REGISTRY` is a plain `dict[str, Callable]`. The `@register_job("name")` decorator populates it at import time.

`resolve_func(func_path)` first checks the registry, then falls back to a dynamic `importlib` import using the dotted path convention (`"mypackage.mymodule.my_function"`). This allows users to run arbitrary Python functions without pre-registration.

---

### Executor (`scheduler/executor.py`)

`execute_job(job, timeout)` runs a single job synchronously (from the caller's perspective) but in an inner `ThreadPoolExecutor(max_workers=1)` so that:

1. `stdout` can be captured via `contextlib.redirect_stdout`.
2. A wall-clock timeout can be enforced via `future.result(timeout=...)`.
3. All exceptions are caught and converted into a failed `JobResult` rather than propagating.

The function always returns a `JobResult`; it never raises.

---

### WorkerPool (`scheduler/worker.py`)

`WorkerPool` wraps a `ThreadPoolExecutor`. When `submit(job, callback)` is called:

1. It publishes a `JOB_STARTED` event.
2. Calls `execute_job` (which runs the user function).
3. Publishes `JOB_COMPLETED` or `JOB_FAILED`.
4. Calls the `callback` with the `JobResult`.

The callback is always invoked in the worker thread, not the asyncio event loop thread.

---

### Scheduler (`scheduler/scheduler.py`)

The `Scheduler` class owns the main control loop:

```
start() ──▶ [loop]
              ├── get_due_jobs()
              ├── for each due job not in-flight:
              │     └── _dispatch(job)
              │           ├── mark RUNNING in storage
              │           ├── add to _in_flight set
              │           └── submit to WorkerPool
              └── asyncio.sleep(poll_interval)

_on_result(result) [called from worker thread]
    ├── remove from _in_flight
    ├── update job status (COMPLETED / FAILED / PENDING for interval)
    ├── recalculate next_run_time for INTERVAL jobs
    ├── update_job() in storage
    └── save_result() in storage
```

The `_in_flight` set prevents the same job from being dispatched twice during a single execution.

---

### Logging Config (`scheduler/logging_config.py`)

`setup_logging(level, use_json)` configures the root Python logger with either:
- A human-readable format: `timestamp | LEVEL | logger.name | message`
- A single-line JSON format (useful for log aggregation pipelines)

---

### CLI (`cli/`)

Built with [Click](https://click.palletsprojects.com/):

| Command       | Description                                    |
|---------------|------------------------------------------------|
| `add`         | Schedule a new job                             |
| `list-jobs`   | Display all jobs in a formatted table          |
| `remove`      | Delete a job by id                             |
| `run`         | Start the scheduler daemon (blocks until Ctrl-C)|
| `history`     | Show recent execution results                  |

The top-level `cli` group resolves `Config` from options + env vars and stores it in Click's context object (`ctx.obj["config"]`), making it available to all sub-commands via `@click.pass_context`.

---

## Data Flow

```
User
 │
 ▼
CLI (add command)
 │  creates Job, calls storage.add_job()
 ▼
SQLiteStorage (jobs table, JSON blob)
 │
 ▼
Scheduler loop (asyncio)
 │  calls storage.get_due_jobs() every poll_interval seconds
 │  dispatches due jobs via WorkerPool.submit()
 ▼
WorkerPool (ThreadPoolExecutor)
 │  runs execute_job() in a worker thread
 ▼
Executor
 │  resolves callable, captures stdout, enforces timeout
 │  returns JobResult
 ▼
WorkerPool callback → Scheduler._on_result()
 │  updates Job status in storage
 │  saves JobResult in storage
 ▼
SQLiteStorage (results table)
 │
 ▼
CLI (history command) — reads results for display
```

---

## Event Flow

```
Scheduler.start()          ──▶ EventBus.publish(SCHEDULER_STARTED)
WorkerPool._task()         ──▶ EventBus.publish(JOB_STARTED)
WorkerPool._task()         ──▶ EventBus.publish(JOB_COMPLETED | JOB_FAILED)
Scheduler.start() [exit]   ──▶ EventBus.publish(SCHEDULER_STOPPED)
```

Subscribers (e.g., a metrics handler, a webhook notifier) register once at startup and receive all events asynchronously — but note handlers run synchronously in the publisher's thread in the current implementation.

---

## Threading Model

```
Main thread (asyncio event loop)
│
├── Scheduler.start() [async coroutine]
│     └── asyncio.sleep(poll_interval) — yields control each cycle
│
└── ThreadPoolExecutor (WorkerPool)
      ├── Worker thread 1 ── execute_job()
      │     └── Inner ThreadPoolExecutor(max_workers=1) for timeout enforcement
      ├── Worker thread 2 ── execute_job()
      └── …  (up to max_workers)
```

- The asyncio event loop lives on the **main thread** and handles only scheduling logic (polling, dispatching). It never blocks on I/O or CPU work.
- Each job runs in a **worker thread** managed by `WorkerPool`'s `ThreadPoolExecutor`. This keeps the scheduler loop responsive even if a job hangs.
- The executor spawns a second, short-lived `ThreadPoolExecutor(max_workers=1)` per job execution to enable `future.result(timeout=...)` for timeout enforcement.
- `_on_result` is called from a **worker thread**, but SQLite operations are safe here because each `_connect()` call opens and closes its own connection.
