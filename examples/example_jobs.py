"""
Example jobs demonstrating how to write and register custom job functions.
Each function is decorated with @register_job to make it discoverable by the scheduler.
"""
import random
import time
from datetime import datetime, timezone

from scheduler.jobs import register_job


@register_job("greet")
def greet(name: str = "World") -> None:
    """Print a friendly greeting."""
    print(f"Hello, {name}! The time is {datetime.now(timezone.utc).isoformat()}")


@register_job("random_number")
def random_number(low: int = 1, high: int = 100) -> None:
    """Generate and print a random number within [low, high]."""
    number = random.randint(low, high)
    print(f"Random number between {low} and {high}: {number}")


@register_job("write_timestamp")
def write_timestamp(filepath: str = "timestamps.txt") -> None:
    """Append the current UTC timestamp to a file."""
    ts = datetime.now(timezone.utc).isoformat()
    with open(filepath, "a") as fh:
        fh.write(ts + "\n")
    print(f"Wrote timestamp {ts} to {filepath}")


@register_job("slow_job")
def slow_job(seconds: float = 5.0) -> None:
    """Sleep for *seconds* seconds — useful for testing timeouts and concurrency."""
    print(f"Sleeping for {seconds}s…")
    time.sleep(seconds)
    print("Done sleeping.")
