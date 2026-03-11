"""
Entry point for the pyscheduler CLI.
Defines the top-level Click group and shared options.
"""
import click

from scheduler.config import Config
from scheduler.logging_config import setup_logging
from . import commands


@click.group()
@click.option("--db-path", default=None, help="Path to the SQLite database file.")
@click.option("--log-level", default=None, help="Logging level (DEBUG, INFO, WARNING, ERROR).")
@click.pass_context
def cli(ctx: click.Context, db_path: str | None, log_level: str | None) -> None:
    """PyScheduler — a simple educational job scheduler."""
    ctx.ensure_object(dict)
    overrides: dict = {}
    if db_path:
        overrides["db_path"] = db_path
    if log_level:
        overrides["log_level"] = log_level
    config = Config(**overrides)
    setup_logging(level=config.log_level, use_json=config.log_json)
    ctx.obj["config"] = config


cli.add_command(commands.add)
cli.add_command(commands.list_jobs)
cli.add_command(commands.remove)
cli.add_command(commands.run)
cli.add_command(commands.history)
