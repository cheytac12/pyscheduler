"""
A simple thread-safe event bus for decoupled communication between scheduler components.
"""
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class EventType(str, Enum):
    JOB_SCHEDULED = "job_scheduled"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    SCHEDULER_STARTED = "scheduler_started"
    SCHEDULER_STOPPED = "scheduler_stopped"


@dataclass
class Event:
    type: EventType
    job_id: str | None = None
    data: dict = field(default_factory=dict)


class EventBus:
    """Publish/subscribe event bus. Handlers are called synchronously in the publisher's thread."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Callable[[Event], None]]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._handlers[event_type].append(handler)

    def publish(self, event: Event) -> None:
        with self._lock:
            handlers = list(self._handlers[event.type])
        for handler in handlers:
            handler(event)
