"""
Data models for Jobs and JobResults using Pydantic for validation and serialization.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ScheduleType(str, Enum):
    ONCE = "once"
    INTERVAL = "interval"


class Job(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    func_path: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    schedule_type: ScheduleType
    interval_seconds: float | None = None
    next_run_time: datetime
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_run_at: datetime | None = None


class JobResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    success: bool
    output: str | None = None
    error: str | None = None
    executed_at: datetime
    duration_seconds: float
