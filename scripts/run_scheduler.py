"""
Convenience script: start the PyScheduler daemon with default settings.
Equivalent to running `pyscheduler run` from the command line.
"""
import sys

from cli.main import cli

if __name__ == "__main__":
    sys.exit(cli(["run"], standalone_mode=False) or 0)
