"""
Configuration for the scheduler, loaded from environment variables or defaults.
Uses pydantic-settings for automatic env-var parsing.
"""
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    db_path: str = "scheduler.db"
    poll_interval: float = 1.0
    max_workers: int = 4
    log_level: str = "INFO"
    log_json: bool = False

    model_config = {"env_prefix": "SCHEDULER_"}
