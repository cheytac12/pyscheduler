"""
SQLite-backed storage for Jobs and JobResults.
All data is serialized as JSON blobs, keeping the schema simple and flexible.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from .models import Job, JobResult, JobStatus


class SQLiteStorage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._create_tables()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _create_tables(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    next_run_time TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)

    def add_job(self, job: Job) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id, status, next_run_time, data) VALUES (?, ?, ?, ?)",
                (job.id, job.status.value, job.next_run_time.isoformat(), job.model_dump_json()),
            )

    def get_job(self, job_id: str) -> Job | None:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return Job.model_validate_json(row["data"]) if row else None

    def list_jobs(self) -> list[Job]:
        with self._connect() as conn:
            rows = conn.execute("SELECT data FROM jobs").fetchall()
        return [Job.model_validate_json(row["data"]) for row in rows]

    def update_job(self, job: Job) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, next_run_time = ?, data = ? WHERE id = ?",
                (job.status.value, job.next_run_time.isoformat(), job.model_dump_json(), job.id),
            )

    def delete_job(self, job_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def get_due_jobs(self) -> list[Job]:
        """Return all PENDING jobs whose next_run_time is at or before now."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data FROM jobs WHERE status = ? AND next_run_time <= ?",
                (JobStatus.PENDING.value, now_iso),
            ).fetchall()
        return [Job.model_validate_json(row["data"]) for row in rows]

    def save_result(self, result: JobResult) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO results (id, job_id, data) VALUES (?, ?, ?)",
                (result.id, result.job_id, result.model_dump_json()),
            )

    def get_results(self, job_id: str | None = None, limit: int = 100) -> list[JobResult]:
        with self._connect() as conn:
            if job_id:
                rows = conn.execute(
                    "SELECT data FROM results WHERE job_id = ? ORDER BY rowid DESC LIMIT ?",
                    (job_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT data FROM results ORDER BY rowid DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [JobResult.model_validate_json(row["data"]) for row in rows]
