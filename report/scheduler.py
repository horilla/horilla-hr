"""
Standard report subscription job.

Registered with horilla.scheduling; executed by `manage.py run_scheduler`.
"""

from __future__ import annotations

import logging

from horilla.scheduling import register_job

logger = logging.getLogger(__name__)


def run_report_subscriptions():
    """Hourly poll entrypoint used by APScheduler."""
    from report.delivery import run_due_subscriptions

    results = run_due_subscriptions()
    sent = sum(1 for r in results if r.ok)
    skipped = sum(1 for r in results if r.status in ("skipped", "inactive"))
    failed = sum(
        1 for r in results if not r.ok and r.status not in ("skipped", "inactive")
    )
    if results:
        logger.info(
            "Report subscriptions poll: %s sent, %s skipped, %s failed/denied",
            sent,
            skipped,
            failed,
        )


register_job(
    run_report_subscriptions,
    "interval",
    job_id="report_subscriptions",
    hours=1,
)
