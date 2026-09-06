"""
Central registry for Horilla's background jobs.

Why this exists
---------------
Every ``<app>/scheduler.py`` used to build its own ``BackgroundScheduler()``
and call ``.start()`` at import time, reached via ``AppConfig.ready()``. Import
time is once *per process*, and gunicorn runs ``workers = cpu*2+1`` capped at 8
with ``preload_app = False``, so each worker started its own copy of every job:
payroll generation, database backups and shift rotation all ran up to 8 times
per interval, with no lock to make the duplicates harmless.

Jobs now register themselves here instead of starting a scheduler, and exactly
one process -- ``manage.py run_scheduler`` -- owns execution.

Registering a job
-----------------
In ``<app>/scheduler.py``, replace the ``BackgroundScheduler()`` block with::

    from horilla.scheduling import register_job

    register_job(my_job, "interval", hours=4)

The callable is resolved lazily by ``run_scheduler`` so importing this module
never touches the database or starts a thread.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduledJob:
    """One registered job: what to run, how often, and under what id."""

    func: Callable
    trigger: str
    job_id: str
    kwargs: dict[str, Any] = field(default_factory=dict)


_REGISTRY: dict[str, ScheduledJob] = {}


def register_job(func: Callable, trigger: str = "interval", *, job_id=None, **kwargs):
    """
    Register ``func`` to run on ``trigger``.

    ``job_id`` defaults to ``<module>.<name>``, which is stable across restarts
    so APScheduler's jobstore replaces the existing row rather than accumulating
    a duplicate on every boot. A clashing id is a programming error -- two jobs
    would silently collapse into one -- so it raises rather than overwriting.
    """
    resolved_id = job_id or f"{func.__module__}.{func.__name__}"

    existing = _REGISTRY.get(resolved_id)
    if existing is not None and existing.func is not func:
        raise ValueError(
            f"Duplicate scheduled job id {resolved_id!r}: already registered by "
            f"{existing.func.__module__}.{existing.func.__name__}. Pass an "
            f"explicit job_id= to disambiguate."
        )

    _REGISTRY[resolved_id] = ScheduledJob(
        func=func, trigger=trigger, job_id=resolved_id, kwargs=kwargs
    )
    logger.debug("Registered scheduled job %s (%s, %s)", resolved_id, trigger, kwargs)
    return func


def get_registered_jobs() -> list[ScheduledJob]:
    """Every registered job, ordered by id so listings are deterministic."""
    return [_REGISTRY[key] for key in sorted(_REGISTRY)]


def clear_registry() -> None:
    """Drop all registrations. For tests only."""
    _REGISTRY.clear()
