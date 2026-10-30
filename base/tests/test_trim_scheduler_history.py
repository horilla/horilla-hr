"""
Old scheduler job-run history is deleted daily.

django_apscheduler records a DjangoJobExecution row for every run of every job
and never removes them; with jobs that run every minute, one install had
64,999 rows (17 MB) after three weeks.
"""

import importlib
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from django_apscheduler.models import DjangoJob, DjangoJobExecution

from horilla.scheduling import get_registered_jobs


class TrimSchedulerHistoryTests(TestCase):
    def setUp(self):
        self.job = DjangoJob.objects.create(id="every_minute", job_state=b"")

    def run_at(self, age, status=DjangoJobExecution.SUCCESS):
        return DjangoJobExecution.objects.create(
            job=self.job, status=status, run_time=timezone.now() - age
        )

    @override_settings(HORILLA_SCHEDULER_HISTORY_DAYS=7)
    def test_runs_older_than_the_retention_go(self):
        from base.scheduler import trim_scheduler_history

        old = [self.run_at(timedelta(days=30)), self.run_at(timedelta(days=7, hours=1))]
        kept = [self.run_at(timedelta(days=6, hours=23)), self.run_at(timedelta(0))]

        with self.assertLogs("base.scheduler", level="INFO") as logs:
            trim_scheduler_history()

        self.assertEqual(
            set(DjangoJobExecution.objects.values_list("id", flat=True)),
            {run.id for run in kept},
        )
        self.assertFalse(
            DjangoJobExecution.objects.filter(id__in=[r.id for r in old]).exists()
        )
        self.assertIn("Deleted 2 scheduler job runs older than 7 days", logs.output[0])

    @override_settings(HORILLA_SCHEDULER_HISTORY_DAYS=30)
    def test_the_retention_is_a_setting(self):
        from base.scheduler import trim_scheduler_history

        self.run_at(timedelta(days=10))
        trim_scheduler_history()
        self.assertEqual(DjangoJobExecution.objects.count(), 1)

    @override_settings(HORILLA_SCHEDULER_HISTORY_DAYS=0)
    def test_at_least_a_day_is_kept(self):
        from base.scheduler import trim_scheduler_history

        self.run_at(timedelta(days=2))
        recent = self.run_at(timedelta(hours=1))
        trim_scheduler_history()
        self.assertEqual(
            list(DjangoJobExecution.objects.values_list("id", flat=True)), [recent.id]
        )

    def test_metrics_report_the_retained_runs(self):
        from base.scheduler import trim_scheduler_history
        from horilla.observability import scheduler_metrics

        self.run_at(timedelta(days=30), status=DjangoJobExecution.ERROR)
        self.run_at(timedelta(hours=1))
        trim_scheduler_history()

        metrics = scheduler_metrics()
        self.assertIn(
            'horilla_scheduler_executions_total{status="Executed"} 1', metrics
        )
        self.assertNotIn('status="Error!"', metrics)
        self.assertIn("# TYPE horilla_scheduler_executions_total gauge", metrics)

    def test_it_runs_daily(self):
        importlib.import_module("base.scheduler")
        job = next(
            j for j in get_registered_jobs() if j.job_id == "trim_scheduler_history"
        )
        self.assertEqual(job.trigger, "cron")
        self.assertEqual((job.kwargs["hour"], job.kwargs["minute"]), (3, 15))

    def test_metrics_report_overdue_jobs(self):
        """next_run_time is a DateTimeField; comparing it with time.time() raised."""
        from horilla.observability import scheduler_metrics

        self.job.next_run_time = timezone.now() - timedelta(minutes=5)
        self.job.save()
        self.assertIn("horilla_scheduler_jobs_overdue 1", scheduler_metrics())
