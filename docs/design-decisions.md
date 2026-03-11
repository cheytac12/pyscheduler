# Design Decisions

This document explains the rationale behind the key technology and design choices made in PyScheduler.

---

## Python 3.10+

PyScheduler targets Python 3.10 as its minimum version for several reasons:

- **Union types with `|`** — `str | None` is clearer and shorter than `Optional[str]`. This syntax was introduced in Python 3.10.
- **`match` statements** — structural pattern matching is available for future expansion of command dispatch or result handling logic.
- **`ParamSpec` and improved typing** — 3.10 polished several typing features that make annotated, educational code easier to read.

Requiring a recent Python version also avoids the maintenance burden of compatibility shims, keeping the codebase clean and focused on the educational goal.

---

## Pydantic v2

[Pydantic](https://docs.pydantic.dev/) v2 is used for the `Job` and `JobResult` models because:

- **Validation** — fields are automatically coerced and validated on construction. A `Job` created with a bad `schedule_type` value raises an error immediately, not silently at execution time.
- **Serialisation** — `model_dump_json()` and `model_validate_json()` provide round-trip JSON serialisation with correct handling of `datetime`, `UUID`, and `Enum` fields. This is how jobs and results are stored in SQLite.
- **Type hints as documentation** — Pydantic models double as living documentation of the data schema. Readers can understand the full shape of a `Job` just by reading `models.py`.
- **v2 performance** — Pydantic v2's Rust-based core is significantly faster than v1, though performance is not the primary concern here.

---

## pydantic-settings

[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) provides `BaseSettings`, which extends a Pydantic model with automatic environment variable parsing.

- Configuration can be supplied via env vars (`SCHEDULER_DB_PATH=...`), a `.env` file, or direct constructor arguments — all with the same validation guarantees as any other Pydantic model.
- This makes the scheduler easy to configure in different environments (development, CI, containers) without changing code.
- It avoids a custom `argparse`/`os.environ` config layer, keeping `config.py` to ~10 lines.

---

## SQLite

SQLite was chosen as the persistence backend because:

- **Zero additional dependencies** — it ships with Python's standard library (`sqlite3`). No database server, no Docker container, no connection string to configure.
- **Simplicity** — the schema is two tables (`jobs`, `results`), each with a primary key and a single `TEXT` column storing a JSON blob. New fields can be added to models without a schema migration.
- **Portability** — the database is a single file. Developers can inspect or copy it trivially.
- **Educational clarity** — readers can follow the storage layer without knowledge of any ORM or external database system.

For a production scheduler, you might replace `SQLiteStorage` with a PostgreSQL-backed implementation behind the same interface.

---

## asyncio (Scheduler Loop)

The main scheduler loop uses `asyncio` for several reasons:

- **Non-blocking sleep** — `await asyncio.sleep(poll_interval)` releases the event loop between poll cycles, allowing future expansion with async I/O (e.g., an HTTP API) without restructuring the loop.
- **Clean cancellation** — asyncio coroutines have well-defined cancellation semantics. The `KeyboardInterrupt` path in the CLI calls `scheduler.stop()`, which sets `_running = False` and lets the loop exit cleanly on its next iteration.
- **Familiarity** — asyncio is the standard Python async framework, and its patterns (`async def`, `await`, `asyncio.run()`) are widely documented.

Note that the scheduler loop itself is lightweight — all actual work happens in threads. asyncio is used for the *structure* of the loop, not for async I/O.

---

## ThreadPoolExecutor (Job Isolation)

Jobs are executed in a `ThreadPoolExecutor` rather than in the asyncio event loop for several reasons:

- **Blocking code** — most real-world job functions are synchronous and may block (network calls, file I/O, `time.sleep`). Blocking the event loop would stall the scheduler.
- **Stdout capture** — `contextlib.redirect_stdout` is thread-local, so each job can independently capture its output.
- **Timeout enforcement** — `concurrent.futures.Future.result(timeout=N)` provides a straightforward way to enforce wall-clock timeouts on blocking code.
- **Concurrency** — multiple jobs can run simultaneously up to `max_workers`, which is configurable.

`ProcessPoolExecutor` was considered but rejected: spawning processes is heavier, requires pickleable callables, and complicates stdout capture. For an educational project, threads are the right trade-off.

---

## Click (CLI)

[Click](https://click.palletsprojects.com/) was chosen over `argparse` because:

- **Decorator-based API** — commands are plain functions decorated with `@click.command` and `@click.option`. This is easy to read and extend.
- **Composability** — `@click.group()` nests commands cleanly. Shared state (the `Config` object) is passed through Click's context object without global variables.
- **Built-in help generation** — every command and option automatically gets a `--help` page.
- **Widely used** — Click is one of the most popular Python CLI libraries. Readers are likely already familiar with it.

---

## Event Bus Pattern

The `EventBus` is intentionally minimal (< 40 lines), but it demonstrates an important architectural pattern:

- **Decoupling** — the `Scheduler` and `WorkerPool` publish events without knowing who (if anyone) is listening. A metrics collector, a webhook notifier, or a test spy can subscribe without modifying the scheduler.
- **Observability** — lifecycle events (`JOB_STARTED`, `JOB_COMPLETED`, `JOB_FAILED`, etc.) provide hooks for monitoring and alerting without polluting the core logic.
- **Testability** — tests can subscribe to the event bus to assert that specific events were published, rather than inspecting internal state.

The current implementation calls handlers synchronously in the publisher's thread, which keeps the code simple. A production system might use an async or queued dispatch strategy.
