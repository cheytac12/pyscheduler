"""
Job registry: maps string names to Python callables.
Supports both registry lookup and dynamic import by dotted path.
"""
import importlib
from typing import Callable

JOB_REGISTRY: dict[str, Callable] = {}


def register_job(name: str) -> Callable:
    """Decorator that registers a function in the global JOB_REGISTRY under *name*."""
    def decorator(func: Callable) -> Callable:
        JOB_REGISTRY[name] = func
        return func
    return decorator


def resolve_func(func_path: str) -> Callable:
    """
    Resolve a callable by name.
    First checks JOB_REGISTRY, then attempts a dotted-path import (e.g. 'mymodule.myfunc').
    """
    if func_path in JOB_REGISTRY:
        return JOB_REGISTRY[func_path]
    module_path, _, func_name = func_path.rpartition(".")
    if not module_path:
        raise ImportError(f"Cannot resolve '{func_path}': not in registry and no module path given.")
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def list_registered_jobs() -> list[str]:
    """Return a sorted list of all registered job names."""
    return sorted(JOB_REGISTRY.keys())
