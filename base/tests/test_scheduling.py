"""
Scheduled jobs must be registered, not started at import.

The bug this guards: every ``<app>/scheduler.py`` used to build its own
BackgroundScheduler and call ``.start()`` at import time via AppConfig.ready().
gunicorn runs up to 8 workers with preload_app=False, so each worker started its
own copy of every job -- payroll generation and database backups ran up to 8
times per interval.
"""

from io import StringIO

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

    def test_run_scheduler_list_prints_jobs_and_starts_nothing(self):
        # --list must be safe to run anywhere, including a deploy shell.
        from unittest.mock import patch

        job = ScheduledJob(
            func=lambda: None,
            trigger="interval",
            job_id="fake_job",
            kwargs={"hours": 1},
        )
        out = StringIO()
        with (
            patch(
                "base.management.commands.run_scheduler.get_registered_jobs",
                return_value=[job],
            ),
            patch("base.management.commands.run_scheduler.Command._load_job_modules"),
            patch(
                "base.management.commands.run_scheduler.BlockingScheduler"
            ) as scheduler_cls,
        ):
            call_command("run_scheduler", "--list", stdout=out)

        scheduler_cls.assert_not_called()
        self.assertIn("fake_job", out.getvalue())


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

        import yaml
        from django.conf import settings

        class ComposeLoader(yaml.SafeLoader):
            """Compose merge tags (!override, !reset) wrap plain values."""

        def _untag(loader, tag_suffix, node):
            if isinstance(node, yaml.MappingNode):
                return loader.construct_mapping(node, deep=True)
            if isinstance(node, yaml.SequenceNode):
                return loader.construct_sequence(node, deep=True)
            return loader.construct_scalar(node)

        ComposeLoader.add_multi_constructor("!", _untag)
        text = (Path(settings.BASE_DIR) / name).read_text(encoding="utf-8")
        return yaml.load(text, Loader=ComposeLoader)

    def _scheduler_env(self, compose):
        env = compose["services"]["scheduler"]["environment"]
        if isinstance(env, list):
            env = dict(item.split("=", 1) for item in env)
        return env

    def test_compose_files_launch_a_single_scheduler_that_skips_release_tasks(self):
        dev = self._compose("docker-compose.yml")
        prod = self._compose("docker-compose.prod.yml")

        # Something must actually launch the runner (prod inherits the command
        # from the dev file it overlays).
        self.assertIn("run_scheduler", str(dev["services"]["scheduler"]["command"]))
        self.assertIn("scheduler", prod["services"])

        # Both containers would otherwise race migrate, and
        # collectstatic --clear would wipe STATIC_ROOT under the live web
        # container.
        for name, compose in (("dev", dev), ("prod", prod)):
            with self.subTest(compose=name):
                self.assertEqual(
                    str(self._scheduler_env(compose)["HORILLA_SKIP_RELEASE_TASKS"]),
                    "1",
                )

        # Two schedulers reintroduce the duplicate-run problem.
        self.assertEqual(prod["services"]["scheduler"]["deploy"]["replicas"], 1)

    def test_runner_reports_job_failures(self):
        """APScheduler swallows job exceptions into its own logger, so a
        failing job paged nobody. The runner must attach the error listener."""
        from unittest.mock import patch

        from apscheduler.events import EVENT_JOB_ERROR

        from base.management.commands.run_scheduler import log_job_error

        job = ScheduledJob(
            func=lambda: None,
            trigger="interval",
            job_id="fake_job",
            kwargs={"hours": 1},
        )
        target = "base.management.commands.run_scheduler"
        with (
            patch(f"{target}.get_registered_jobs", return_value=[job]),
            patch(f"{target}.Command._load_job_modules"),
            patch(f"{target}.BlockingScheduler") as scheduler_cls,
            patch(f"{target}.DjangoJobStore"),
            patch(f"{target}.signal.signal"),
        ):
            call_command("run_scheduler", stdout=StringIO())

        scheduler = scheduler_cls.return_value
        scheduler.add_listener.assert_any_call(log_job_error, EVENT_JOB_ERROR)
        scheduler.start.assert_called_once()

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
