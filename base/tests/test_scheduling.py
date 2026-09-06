"""
Scheduled jobs must be registered, not started at import.

The bug this guards: every ``<app>/scheduler.py`` used to build its own
BackgroundScheduler and call ``.start()`` at import time via AppConfig.ready().
gunicorn runs up to 8 workers with preload_app=False, so each worker started its
own copy of every job -- payroll generation and database backups ran up to 8
times per interval.
"""

from django.core.management import call_command
from django.test import SimpleTestCase
from django.utils.module_loading import module_has_submodule

from horilla.scheduling import (
    ScheduledJob,
    clear_registry,
    get_registered_jobs,
    register_job,
)

# Reconfigured at runtime rather than statically registered, so they still own a
# live scheduler. See the ponytail: comments in those modules.
RUNTIME_CONFIGURED = {"horilla_backup", "pg_backup"}


class RegistryTests(SimpleTestCase):
    def setUp(self):
        self._saved = get_registered_jobs()
        clear_registry()

    def tearDown(self):
        clear_registry()
        for job in self._saved:
            register_job(job.func, job.trigger, job_id=job.job_id, **job.kwargs)

    def test_register_job_records_trigger_and_kwargs(self):
        def dummy():
            pass

        register_job(dummy, "interval", hours=4)
        jobs = get_registered_jobs()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].trigger, "interval")
        self.assertEqual(jobs[0].kwargs, {"hours": 4})

    def test_job_id_defaults_to_module_qualified_name(self):
        def dummy():
            pass

        register_job(dummy, "interval", hours=1)
        # Stable across restarts, so the jobstore replaces rather than
        # accumulating a duplicate row on every boot.
        self.assertEqual(get_registered_jobs()[0].job_id, f"{dummy.__module__}.dummy")

    def test_same_callable_may_register_under_distinct_ids(self):
        def dummy():
            pass

        register_job(dummy, "interval", minutes=30)
        register_job(dummy, "cron", job_id="dummy_daily", hour=0)

        self.assertEqual(len(get_registered_jobs()), 2)

    def test_clashing_job_id_raises_rather_than_silently_overwriting(self):
        def one():
            pass

        def two():
            pass

        register_job(one, "interval", job_id="shared", hours=1)
        with self.assertRaises(ValueError):
            register_job(two, "interval", job_id="shared", hours=1)


class NoSchedulerStartsAtImportTests(SimpleTestCase):
    """
    Importing an app's scheduler module must not start a scheduler.

    Asserted structurally rather than by importing and inspecting threads: a
    started scheduler is a side effect that would already have happened by the
    time this test runs.
    """

    def test_app_schedulers_do_not_call_start_at_import(self):
        from django.apps import apps

        offenders = []
        for config in apps.get_app_configs():
            if config.label in RUNTIME_CONFIGURED:
                continue
            if not module_has_submodule(config.module, "scheduler"):
                continue
            path = f"{config.path}/scheduler.py"
            with open(path) as handle:
                source = handle.read()
            for lineno, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if ".start()" in stripped and "scheduler" in stripped:
                    offenders.append(f"{path}:{lineno}")

        self.assertEqual(
            offenders,
            [],
            "Scheduler started at import time -- this runs once per gunicorn "
            "worker. Register the job with horilla.scheduling.register_job "
            "instead; run_scheduler owns execution.",
        )

    def test_every_registered_job_is_discoverable(self):
        jobs = get_registered_jobs()
        self.assertTrue(jobs, "No jobs registered -- scheduler modules not imported?")
        for job in jobs:
            self.assertIsInstance(job, ScheduledJob)
            self.assertTrue(callable(job.func))
            self.assertTrue(job.job_id)

    def test_run_scheduler_list_does_not_start_anything(self):
        # --list must be safe to run anywhere, including a deploy shell.
        call_command("run_scheduler", "--list")


class DeploymentWiringTests(SimpleTestCase):
    """
    The scheduler refactor moved jobs out of gunicorn workers into one
    process, but nothing started that process: run_scheduler appeared in no
    compose file, so every registered job ran zero times on the shipped
    stack. These pin the wiring, since a correct runner nothing launches is
    indistinguishable from no runner.
    """

    def _compose(self, name):
        from pathlib import Path

        from django.conf import settings

        return (Path(settings.BASE_DIR) / name).read_text(encoding="utf-8")

    def test_dev_compose_defines_a_scheduler_service(self):
        body = self._compose("docker-compose.yml")
        self.assertIn("scheduler:", body)
        self.assertIn("run_scheduler", body)

    def test_prod_compose_defines_a_scheduler_service(self):
        body = self._compose("docker-compose.prod.yml")
        self.assertIn("scheduler:", body)

    def test_scheduler_skips_release_tasks(self):
        """Both containers would otherwise race migrate, and
        collectstatic --clear would wipe STATIC_ROOT under the live web
        container."""
        for name in ("docker-compose.yml", "docker-compose.prod.yml"):
            with self.subTest(compose=name):
                self.assertIn("HORILLA_SKIP_RELEASE_TASKS", self._compose(name))

    def test_prod_scheduler_is_single_replica(self):
        """Two schedulers reintroduce the duplicate-run problem."""
        self.assertIn("replicas: 1", self._compose("docker-compose.prod.yml"))

    def test_ci_does_not_override_the_coverage_floor(self):
        """The Makefile's floor is the gate; passing a lower value at the
        call site re-created the very anti-pattern its comment condemns."""
        from pathlib import Path

        from django.conf import settings

        workflow = (
            Path(settings.BASE_DIR) / ".github/workflows/unit-tests.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("COV_FAIL_UNDER=5", workflow)

    def test_runner_reports_job_failures(self):
        """APScheduler swallows job exceptions into its own logger, so a
        failing job paged nobody."""
        import inspect

        from base.management.commands import run_scheduler

        source = inspect.getsource(run_scheduler)
        self.assertIn("EVENT_JOB_ERROR", source)
        self.assertIn("add_listener", source)

    def test_biometric_does_not_start_a_scheduler_at_import(self):
        """Import runs once per gunicorn worker, so a scheduler started here
        polled every device once per worker."""
        import inspect

        from biometric import views

        source = inspect.getsource(views)
        module_level = [
            line
            for line in source.splitlines()
            if line.startswith("    scheduler.start()") or line == "scheduler.start()"
        ]
        self.assertFalse(
            module_level,
            "biometric/views.py starts a scheduler outside a function",
        )
        self.assertIn("register_job(", source)


class RuffConfigTests(SimpleTestCase):
    """
    Ruff's rule set is deliberately narrow. The full E,F,B set reports ~4,500
    findings here, dominated by line-length and star-import usage -- a gate
    that fails on 4,500 issues gets disabled rather than fixed, which is the
    same trap .coveragerc records about the coverage floor.

    So the enabled rules are ones the codebase passes today, and the config
    documents the follow-up set. These tests guard both halves: that the gate
    is wired, and that the follow-up list has not been quietly deleted
    instead of worked through.
    """

    def _pyproject(self):
        from pathlib import Path

        from django.conf import settings

        return (Path(settings.BASE_DIR) / "pyproject.toml").read_text(encoding="utf-8")

    def test_ruff_is_configured(self):
        body = self._pyproject()
        self.assertIn("[tool.ruff]", body)
        self.assertIn("[tool.ruff.lint]", body)

    def test_migrations_and_vendored_code_are_excluded(self):
        """Migrations are generated, and notifications is vendored."""
        body = self._pyproject()
        self.assertIn("*/migrations/*", body)
        self.assertIn("notifications", body)

    def test_ci_runs_ruff_over_the_whole_repo(self):
        """Black and isort cover two paths; ruff has to cover everything or
        it adds nothing the pre-commit hook did not already."""
        from pathlib import Path

        from django.conf import settings

        workflow = (
            Path(settings.BASE_DIR) / ".github/workflows/quality.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("ruff check .", workflow)
        # Pinned, like the other two linters, so a new release cannot turn a
        # green branch red without a deliberate bump.
        self.assertIn('"ruff==', workflow)

    def test_precommit_runs_ruff(self):
        from pathlib import Path

        from django.conf import settings

        config = (Path(settings.BASE_DIR) / ".pre-commit-config.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("ruff-pre-commit", config)

    def test_followup_rules_are_still_documented(self):
        """The 93 known defects are listed in the config as the next pass.
        If someone widens the rule set they should be removing entries from
        that list, not the list itself."""
        body = self._pyproject()
        for rule in ("F811", "B023", "F821", "E722", "B006"):
            with self.subTest(rule=rule):
                self.assertIn(rule, body)
