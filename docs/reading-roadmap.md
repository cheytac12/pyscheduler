# PyScheduler — Code Reading Roadmap

This guide tells you **exactly which files to read, in which order, and what to look for** in each one. Follow it from top to bottom and you will have a complete mental model of how PyScheduler works before you touch a single line of code.

---

## Phase 1 — Orient yourself (big picture)

### Step 1 · `README.md`

**What it is:** The project overview.

**What to look for:**
- The features list — this tells you the scope of the project up front.
- The "Architecture Overview" table — nine modules, each with one job. Memorise the table; it is your map.
- The "Quick Start" commands — run them mentally so you know what user-visible behaviour you are about to implement.
- The configuration table — you will see these same keys again in `config.py`.

---

### Step 2 · `docs/architecture.md`

**What it is:** A prose description of every component and the data/event flows between them.

**What to look for:**
- The ASCII diagram at the top — it shows who calls whom at a glance.
- The "Data Flow" section — traces a job from `pyscheduler add` all the way to the results table.
- The "Event Flow" and "Threading Model" sections — these explain the two non-obvious design aspects (publish/subscribe and the asyncio + ThreadPoolExecutor combination). Read these carefully.

---

### Step 3 · `docs/scheduler-diagram.md`

**What it is:** Mermaid diagrams rendered from the same information as `architecture.md`.

**What to look for:**
- **Diagram 1 (Scheduler Loop Flowchart)** — step through it once. After you read `scheduler.py` you will come back here and it will click instantly.
- **Diagram 2 (Component Diagram)** — confirms the dependency edges you will see in the imports of each file.
- **Diagram 3 (Sequence Diagram)** — the most useful one. It shows the exact call sequence from `pyscheduler add` through to `save_result`. Keep this open while reading the core files.

---

### Step 4 · `docs/design-decisions.md`

**What it is:** The "why" behind every major technology choice.

**What to look for:**
- Why Pydantic v2 for models (validation + JSON round-trips + type documentation).
- Why SQLite (zero dependencies, single file, no migration needed).
- Why asyncio + ThreadPoolExecutor together (non-blocking loop + blocking job isolation).
- Why Click over argparse.
- Why the EventBus pattern (decoupling, testability).

You do not need to agree with every decision, but understanding them will prevent you from spending time wondering "why didn't they just…".

---

## Phase 2 — Core data types (no logic yet)

### Step 5 · `scheduler/config.py`

**Lines:** ~17  
**What it is:** The single source of truth for all runtime settings.

**What to look for:**
- `Config` is a `pydantic_settings.BaseSettings` subclass.
- `model_config = {"env_prefix": "SCHEDULER_"}` — this one line makes every field readable from `SCHEDULER_*` environment variables.
- The six fields and their defaults. You will see these fields referenced in almost every other file.

---

### Step 6 · `scheduler/models.py`

**Lines:** ~47  
**What it is:** The two core data shapes — `Job` and `JobResult`.

**What to look for:**
- `JobStatus` and `ScheduleType` are `str` enums — they serialise to plain strings in JSON and SQLite.
- `Job.id` defaults to a new UUID automatically (via `default_factory`).
- `Job.schedule_type` is either `ONCE` or `INTERVAL`. This single field controls the entire scheduling lifecycle.
- `Job.interval_seconds` is `None` for `ONCE` jobs — always check for `None` before using it.
- `JobResult` is **append-only** — it records what happened, nothing more.

---

## Phase 3 — Infrastructure layer (no business logic yet)

### Step 7 · `scheduler/logging_config.py`

**Lines:** ~38  
**What it is:** Configures the Python root logger.

**What to look for:**
- `_JsonFormatter.format` — builds a dict, calls `json.dumps`. Entirely self-contained.
- `setup_logging` — called once at startup (from `cli/main.py`). After that, every `logging.getLogger(__name__)` in every module just works.
- This file has no dependencies on any other module in the project. Read it first in this phase and never think about it again.

---

### Step 8 · `scheduler/events.py`

**Lines:** ~43  
**What it is:** A minimal publish/subscribe event bus.

**What to look for:**
- `EventType` — the six lifecycle events. You will see these published throughout the codebase.
- `EventBus._handlers` is a `defaultdict(list)`, so subscribing to a new event type never raises a `KeyError`.
- `EventBus._lock` — the lock is acquired in both `subscribe` and `publish`. Notice that in `publish`, the lock is released *before* calling the handlers. This means handlers run outside the lock, preventing deadlocks if a handler itself calls `publish`.
- No other module in `scheduler/` imports `events.py`. It is a leaf dependency.

---

### Step 9 · `scheduler/jobs.py`

**Lines:** ~36  
**What it is:** The job registry and callable resolver.

**What to look for:**
- `JOB_REGISTRY` is a plain module-level dict — simple and inspectable.
- `@register_job("name")` — a standard decorator factory. When `example_jobs.py` is imported, each decorated function is inserted into `JOB_REGISTRY` at import time.
- `resolve_func` — two strategies: registry lookup first, then `importlib` dynamic import by dotted path. This is why you can schedule both `"greet"` (registered) and `"mypackage.mymodule.my_function"` (not registered) without any code changes.

---

### Step 10 · `scheduler/storage.py`

**Lines:** ~104  
**What it is:** The SQLite persistence layer.

**What to look for:**
- `_connect()` is a `@contextmanager` — it opens a connection, yields it, commits, then always closes. No connection pooling; every call opens a fresh connection.
- The schema is just two tables with a JSON `TEXT` column (`data`). All Pydantic serialisation happens at the storage boundary: `model_dump_json()` going in, `model_validate_json()` coming out.
- `get_due_jobs()` — this is the hot path. It filters on `status = 'pending'` AND `next_run_time <= now`. The `now_iso` variable uses `.isoformat()` which produces an ISO 8601 string that sorts lexicographically, making the `<=` comparison on plain `TEXT` columns work correctly.
- `get_results` — sorted `ORDER BY rowid DESC` to return most recent first.

---

## Phase 4 — Execution pipeline (the "hot path")

### Step 11 · `scheduler/executor.py`

**Lines:** ~60  
**What it is:** Runs one job in isolation and always returns a `JobResult`.

**What to look for:**
- `_run()` is the inner function that is submitted to the inner `ThreadPoolExecutor`. Trace why the inner executor is needed: `contextlib.redirect_stdout` redirects in the *calling* thread's context; running in a new thread preserves that redirection. The inner `ThreadPoolExecutor(max_workers=1)` + `future.result(timeout=...)` is the timeout mechanism.
- The `try/except` structure: `FuturesTimeoutError` → timeout result; `Exception` → failure result; anything else → success result. The function **never raises**.
- `resolve_func(job.func_path)` is called inside `_run()`, after the thread is started. This means import errors also produce a failed `JobResult`.

---

### Step 12 · `scheduler/worker.py`

**Lines:** ~38  
**What it is:** Wraps a `ThreadPoolExecutor` and adds event publishing around each job execution.

**What to look for:**
- `WorkerPool.submit` creates an inner `_task` closure and submits it to the executor. The `job` and `callback` are captured by the closure.
- The event publish order: `JOB_STARTED` → `execute_job` → `JOB_COMPLETED` or `JOB_FAILED` → `callback(result)`.
- `callback` (which is `Scheduler._on_result`) is called in the **worker thread**, not the asyncio event loop thread. This matters for understanding thread safety in `_on_result`.
- `shutdown(wait=True)` blocks until all in-flight jobs finish — important for graceful shutdown.

---

### Step 13 · `scheduler/scheduler.py`

**Lines:** ~92  
**What it is:** The brain of the system. Owns the main loop and result handling.

**What to look for:**
- `start()` is an `async def`. The entire loop body is synchronous except for `await asyncio.sleep(...)`. The sleep is the only point where other coroutines could run (none exist here, but the pattern is future-proof).
- `_in_flight: set[str]` — the guard against double-dispatch. If the poll interval is shorter than a job's execution time, `get_due_jobs()` would return the same job again. The set prevents that.
- `_dispatch(job)` — three atomic steps: mark RUNNING in storage, add to `_in_flight`, submit to worker pool. The storage update happens first so that even if the process crashes, the job is not stuck in PENDING.
- `_on_result(result)` — called from a worker thread. Notice it calls `_storage.get_job(result.job_id)` to get the *current* state from the database, not a stale in-memory copy.
- The `INTERVAL` vs `ONCE` branching in `_on_result` — `INTERVAL` jobs are rescheduled by computing a new `next_run_time`; `ONCE` jobs move to `COMPLETED` and never run again.
- Cross-reference with **Diagram 1** from `scheduler-diagram.md` while reading this file.

---

## Phase 5 — Entry points

### Step 14 · `scheduler/__init__.py`

**Lines:** 1  
Just a docstring. Confirms the package boundary. Nothing to study here.

---

### Step 15 · `cli/main.py`

**Lines:** ~34  
**What it is:** The top-level Click group and shared initialisation.

**What to look for:**
- `@click.group()` — makes `cli` the root command. All sub-commands are attached at the bottom with `cli.add_command(...)`.
- `@click.pass_context` + `ctx.obj["config"] = config` — the standard Click pattern for sharing state between a group and its sub-commands.
- `Config(**overrides)` — note that `overrides` only contains keys that were explicitly set by CLI flags. pydantic-settings fills in anything else from env vars or defaults. This is the correct way to layer CLI > env var > default.

---

### Step 16 · `cli/commands.py`

**Lines:** ~185  
**What it is:** The five CLI commands: `add`, `list-jobs`, `remove`, `run`, `history`.

**What to look for:**
- `_storage(ctx)` helper — creates a new `SQLiteStorage` from the config in context. Keeps command functions clean.
- `add` — validates `--run-at`, handles missing timezone by defaulting to UTC, then constructs and persists a `Job`. Everything is explicit.
- `list-jobs` and `history` — pure display logic. Notice the use of f-string padding for column alignment.
- `remove` — looks up the job first; exits with code `1` if it does not exist (good CLI hygiene).
- `run` — this is where all the pieces are assembled. Read it carefully: `SQLiteStorage` → `EventBus` → `WorkerPool` → `Scheduler` → `asyncio.run(scheduler.start())`. The `KeyboardInterrupt` handler calls `scheduler.stop()` which sets `_running = False` and lets the next loop iteration exit cleanly.

---

### Step 17 · `examples/example_jobs.py`

**Lines:** ~40  
**What it is:** Four concrete job functions showing how `@register_job` is used.

**What to look for:**
- `@register_job("greet")` — the decorator is the only registration needed. Import the module and the job is ready.
- `slow_job` — deliberately sleeps. Combined with `SCHEDULER_JOB_TIMEOUT`, this is how you test the timeout path in `executor.py`.
- `write_timestamp` — shows a job that has side effects (file I/O) and is not just `print`.

---

### Step 18 · `scripts/run_scheduler.py`

**Lines:** ~10  
**What it is:** A convenience script for running the daemon without installing the package.

**What to look for:**
- Calls `cli(["run"], standalone_mode=False)` — passes the `run` sub-command name programmatically.
- `standalone_mode=False` prevents Click from calling `sys.exit()` itself; the script handles the return code.
- This pattern is useful when you want to embed the CLI inside a larger application.

---

## Phase 6 — Tests

### Step 19 · `tests/test_storage.py`

**What it is:** Unit tests for `SQLiteStorage`.

**What to look for:**
- The `tmp_path` fixture from pytest — creates an isolated temporary directory per test, so tests never share a database file.
- Which CRUD operations are tested and which edge cases are covered (e.g., `get_due_jobs` respecting `next_run_time` and `status`).
- These tests are a second specification of the storage layer's behaviour. If you are unsure what `get_due_jobs` should return, read the test.

---

### Step 20 · `tests/test_scheduler.py`

**What it is:** Unit tests for `Scheduler` logic.

**What to look for:**
- How dependencies (`SQLiteStorage`, `WorkerPool`, `EventBus`) are assembled for test: they use real objects, not mocks, with in-memory or temp databases.
- Tests for `_calculate_next_run`, result handling for `ONCE` vs `INTERVAL` jobs, and the guard for unknown job ids.
- The test structure mirrors the structure of `scheduler.py` — each logical unit in the scheduler has a corresponding test.

---

## Reading Order Summary

| # | File | Phase |
|---|------|-------|
| 1 | `README.md` | Orient |
| 2 | `docs/architecture.md` | Orient |
| 3 | `docs/scheduler-diagram.md` | Orient |
| 4 | `docs/design-decisions.md` | Orient |
| 5 | `scheduler/config.py` | Core data |
| 6 | `scheduler/models.py` | Core data |
| 7 | `scheduler/logging_config.py` | Infrastructure |
| 8 | `scheduler/events.py` | Infrastructure |
| 9 | `scheduler/jobs.py` | Infrastructure |
| 10 | `scheduler/storage.py` | Infrastructure |
| 11 | `scheduler/executor.py` | Execution pipeline |
| 12 | `scheduler/worker.py` | Execution pipeline |
| 13 | `scheduler/scheduler.py` | Execution pipeline |
| 14 | `scheduler/__init__.py` | Entry points |
| 15 | `cli/main.py` | Entry points |
| 16 | `cli/commands.py` | Entry points |
| 17 | `examples/example_jobs.py` | Entry points |
| 18 | `scripts/run_scheduler.py` | Entry points |
| 19 | `tests/test_storage.py` | Tests |
| 20 | `tests/test_scheduler.py` | Tests |

---

## After the first read-through

Once you have read everything once, try these exercises in order:

1. **Trace a full job lifecycle by hand.** Pick `example_jobs.greet`, schedule it with `pyscheduler add`, and trace every function call from the CLI all the way to `storage.save_result()` using the sequence diagram in `docs/scheduler-diagram.md` as your guide.

2. **Add a new event type.** Add `JOB_RETRIED` to `EventType` in `events.py`, subscribe to it in a test, and publish it from `_on_result` when a job fails. This touches `events.py`, `scheduler.py`, and the tests.

3. **Add a new CLI command.** Write `pyscheduler pause <job_id>` that sets a job's status to `PAUSED`. `JobStatus.PAUSED` already exists in `models.py`. You will need to modify `storage.py` (a `pause_job` method) and add the command in `commands.py`.

4. **Replace the storage backend.** Write an `InMemoryStorage` class with the same interface as `SQLiteStorage`. Because all types are defined in `models.py` and the storage interface is used polymorphically, you can drop it in with zero changes to the rest of the codebase.
