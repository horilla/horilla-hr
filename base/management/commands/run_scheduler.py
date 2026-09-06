"""
Run Horilla's background jobs in one dedicated process.

Deploy this as its own service with **exactly one replica**. Jobs used to start
inside every gunicorn worker (see ``horilla.scheduling``), so payroll runs and
database backups fired once per worker per interval.

    python manage.py run_scheduler

Jobs are stored in ``DjangoJobStore``, so schedules survive a restart instead of
resetting their interval clock, and ``max_instances=1`` keeps a slow run from
overlapping itself.
"""

import logging
import signal

import pytz
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.schedulers.blocking import BlockingScheduler
from django.conf import settings
from django.core.management.base import BaseCommand
from django_apscheduler.jobstores import DjangoJobStore

from horilla.scheduling import get_registered_jobs

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run all registered background jobs in a single dedicated process."

    def add_arguments(self, parser):
        parser.add_argument(
            "--list",
            action="store_true",
            help="Print the registered jobs and exit without running anything.",
        )

    def handle(self, *args, **options):
        # Importing the app schedulers is what populates the registry. This is
        # deliberately here and not in AppConfig.ready(): ready() runs in every
        # process, which is the duplication this command exists to remove.
        self._load_job_modules()

        jobs = get_registered_jobs()
        if not jobs:
            self.stderr.write(self.style.WARNING("No scheduled jobs registered."))
            return

        if options["list"]:
            for job in jobs:
                self.stdout.write(f"{job.job_id}  {job.trigger}  {job.kwargs}")
            return

        # attendance's cron jobs fire at a wall-clock time (00:30), so the
        # scheduler must use the project timezone rather than the container's.
        scheduler = BlockingScheduler(timezone=pytz.timezone(settings.TIME_ZONE))
        scheduler.add_jobstore(DjangoJobStore(), "default")

        for job in jobs:
            scheduler.add_job(
                job.func,
                job.trigger,
                id=job.job_id,
                # A job whose previous run is still going must not stack a
                # second copy; coalesce collapses a backlog after downtime into
                # one run instead of replaying every missed interval.
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                **job.kwargs,
            )
            logger.info("Scheduled %s (%s, %s)", job.job_id, job.trigger, job.kwargs)

        # APScheduler catches per-job exceptions and logs them to its own
        # `apscheduler.executors` logger, so a failing job did not surface
        # anywhere a person or Sentry would see. Re-raise it through our
        # logger instead: logger.exception is what the Sentry integration
        # reports on, and it names the job so the alert is actionable.
        def _on_job_error(event):
            logger.error(
                "Scheduled job %s raised %s",
                event.job_id,
                type(event.exception).__name__,
                exc_info=(
                    type(event.exception),
                    event.exception,
                    event.traceback,
                ),
            )

        def _on_job_missed(event):
            # A missed run means the scheduler was busy or down past the
            # grace time; silent misses are how "payroll did not run" goes
            # unnoticed until someone asks.
            logger.warning(
                "Scheduled job %s missed its run time (%s)",
                event.job_id,
                event.scheduled_run_time,
            )

        scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
        scheduler.add_listener(_on_job_missed, EVENT_JOB_MISSED)

        self.stdout.write(self.style.SUCCESS(f"Running {len(jobs)} scheduled job(s)."))

        # BlockingScheduler ignores SIGTERM by default, so a container stop
        # would kill it mid-job instead of letting it shut down cleanly.
        def _shutdown(signum, frame):
            logger.info("Received signal %s, shutting down scheduler.", signum)
            scheduler.shutdown(wait=True)

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown(wait=True)

    def _load_job_modules(self):
        """Import every installed app's scheduler module to populate the registry."""
        from django.apps import apps
        from django.utils.module_loading import module_has_submodule

        for config in apps.get_app_configs():
            if module_has_submodule(config.module, "scheduler"):
                __import__(f"{config.name}.scheduler")
