# PyScheduler

> An educational Python job scheduler — clear, readable, and fully type-annotated.

PyScheduler is a self-contained job scheduling library and CLI built to demonstrate how a real-world scheduler works under the hood. Every design decision is explained, every module has a docstring, and the code is written to be read as much as run.

---

## Features

- **Schedule jobs once or on a repeating interval**
- **CLI interface** — add, list, remove, run, and inspect history from the terminal
- **SQLite persistence** — no external database required
- **Concurrent execution** — configurable thread pool runs multiple jobs simultaneously
- **Timeout enforcement** — jobs that hang are killed after a configurable deadline
- **stdout capture** — job output is saved to the result history
- **Event bus** — publish/subscribe lifecycle events for extensibility
- **JSON logging** — structured log output for log aggregation pipelines
- **Environment-variable configuration** — all settings overridable via `SCHEDULER_*` env vars
- **Fully type-annotated** — every function and class uses Python 3.10+ type hints

---

## Installation

**Requirements:** Python 3.10+

```bash
# Clone the repo
git clone https://github.com/your-org/pyscheduler.git
cd pyscheduler

# Install with pip (editable mode recommended for development)
pip install -e ".[dev]"
```

This installs the `pyscheduler` CLI entry point and all dependencies.

---

## Quick Start

### 1. Schedule a job (run once, immediately)

```bash
pyscheduler add --name "say-hello" --func-path greet
```

### 2. Schedule a repeating job every 30 seconds

```bash
pyscheduler add \
  --name "tick" \
  --func-path greet \
  --schedule-type interval \
  --interval 30
```

### 3. Schedule a job with arguments

```bash
pyscheduler add \
  --name "greet-alice" \
  --func-path greet \
  --kwargs '{"name": "Alice"}'
```

### 4. Schedule a job at a specific time

```bash
pyscheduler add \
  --name "future-job" \
  --func-path greet \
  --run-at "2025-12-31T23:59:00"
```

### 5. List scheduled jobs

```bash
pyscheduler list-jobs
```

```
ID                                    Name                  Func                            Schedule    Status      Next Run
------------------------------------------------------------------------------------------------------------------------------------
3f2e1d0c-...                          say-hello             greet                           once        pending     2025-01-01 00:00:00
```

### 6. Start the scheduler daemon

```bash
pyscheduler run
# Starting scheduler… (Ctrl-C to stop)
```

### 7. View execution history

```bash
pyscheduler history --limit 10
```

### 8. Remove a job

```bash
pyscheduler remove 3f2e1d0c-...
```

---

## Configuration

All settings can be provided via environment variables (prefix: `SCHEDULER_`):

| Variable                    | Default        | Description                          |
|-----------------------------|----------------|--------------------------------------|
| `SCHEDULER_DB_PATH`         | `scheduler.db` | Path to the SQLite database file     |
| `SCHEDULER_POLL_INTERVAL`   | `1.0`          | Seconds between scheduler poll cycles|
| `SCHEDULER_MAX_WORKERS`     | `4`            | Maximum concurrent job threads       |
| `SCHEDULER_LOG_LEVEL`       | `INFO`         | Logging level                        |
| `SCHEDULER_LOG_JSON`        | `false`        | Output logs as JSON                  |

CLI flags `--db-path` and `--log-level` override env vars.

---

## Adding Custom Jobs

Define your job function and decorate it with `@register_job`:

```python
# my_jobs.py
from scheduler.jobs import register_job

@register_job("send_report")
def send_report(email: str) -> None:
    """Send a daily report to the given email address."""
    print(f"Sending report to {email}…")
    # … your logic here
```

Import your module before starting the scheduler (so the decorator runs), then schedule by name:

```bash
python -c "import my_jobs"  # registers the job
pyscheduler add --name "daily-report" --func-path send_report --kwargs '{"email": "ops@example.com"}'
```

Alternatively, use the full dotted import path without pre-registration:

```bash
pyscheduler add --name "daily-report" --func-path my_jobs.send_report --kwargs '{"email": "ops@example.com"}'
```

See [`examples/example_jobs.py`](examples/example_jobs.py) for four ready-to-use example jobs: `greet`, `random_number`, `write_timestamp`, and `slow_job`.

---

## Architecture Overview

PyScheduler is composed of nine focused modules:

| Module                     | Responsibility                                      |
|----------------------------|-----------------------------------------------------|
| `scheduler/config.py`      | Runtime configuration via pydantic-settings         |
| `scheduler/models.py`      | `Job` and `JobResult` Pydantic models               |
| `scheduler/storage.py`     | SQLite-backed persistence                           |
| `scheduler/events.py`      | Thread-safe publish/subscribe event bus             |
| `scheduler/jobs.py`        | Job registry and callable resolver                  |
| `scheduler/executor.py`    | Single-job execution with timeout and stdout capture|
| `scheduler/worker.py`      | Thread pool for concurrent job execution            |
| `scheduler/scheduler.py`   | Core asyncio polling loop                           |
| `scheduler/logging_config.py` | Human-readable and JSON log formatting           |

For a detailed description of each component and how they interact, see [`docs/architecture.md`](docs/architecture.md).

For the rationale behind every major technology choice, see [`docs/design-decisions.md`](docs/design-decisions.md).

For Mermaid flowcharts and component diagrams, see [`docs/scheduler-diagram.md`](docs/scheduler-diagram.md).

---

## Running the Tests

```bash
pytest tests/ -v
```

The test suite covers:

- `tests/test_storage.py` — CRUD operations, due-job filtering, result persistence
- `tests/test_scheduler.py` — next-run calculation, result handling for ONCE and INTERVAL jobs, unknown job id guard

---

## Project Structure

```
pyscheduler/
├── scheduler/          # Core library
│   ├── config.py
│   ├── events.py
│   ├── executor.py
│   ├── jobs.py
│   ├── logging_config.py
│   ├── models.py
│   ├── scheduler.py
│   ├── storage.py
│   └── worker.py
├── cli/                # Click-based CLI
│   ├── commands.py
│   └── main.py
├── examples/           # Example job functions
│   └── example_jobs.py
├── tests/              # pytest test suite
│   ├── test_storage.py
│   └── test_scheduler.py
├── scripts/            # Convenience scripts
│   └── run_scheduler.py
├── docs/               # Architecture and design documentation
│   ├── architecture.md
│   ├── design-decisions.md
│   └── scheduler-diagram.md
├── pyproject.toml
└── requirements.txt
```
