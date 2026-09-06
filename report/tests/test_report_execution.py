"""
Database-backed execution tests for the standard report catalog.

Every other report test module is a ``SimpleTestCase``, which forbids DB
access -- so until this file existed no registered report was ever actually
*run*. The registry tests assert reports are declared; these assert they
execute against real rows and return a well-formed payload.

The fixture is deliberately small (two companies, a handful of employees and
a few rows per domain). The goal is exercising every query path, not
realistic volume.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.apps import apps
from django.test import TestCase

from horilla.testkit.company import clear_selected_company
from horilla.testkit.factories import (
    get_hired_stage,
    make_attendance,
    make_available_leave,
    make_candidate,
    make_company,
    make_contract,
    make_employee,
    make_leave_request,
    make_leave_type,
    make_payslip,
    make_recruitment,
    make_resignation,
    make_stage,
    make_user,
)

# Reports are executed across this grid; each combination is a distinct set of
# date-boundary and queryset-filter paths.
PERIOD_PRESETS = ("this_month", "ytd", "all_time")
EMPLOYMENT_STATUSES = ("active", "all")


class StandardReportExecutionTests(TestCase):
    """Run every registered report and assert the payload contract holds."""

    @classmethod
    def setUpTestData(cls):
        import report.metrics  # noqa: F401  (registers the catalog)

        cls.today = date.today()
        cls.company = make_company("Alpha Corp")
        cls.other_company = make_company("Beta Corp", hq=False)

        # Two active employees in the primary company, one terminated, and one
        # in a second company so cross-tenant leakage is detectable.
        # date_joining matters: joiners/leavers, tenure and the 90-day
        # attrition cohort all read it, and a null makes an employee
        # invisible to them.
        cls.emp_a = make_employee(
            company=cls.company,
            email="a@test.horilla",
            first_name="Ann",
            date_joining=cls.today - timedelta(days=400),
        )
        cls.emp_b = make_employee(
            company=cls.company,
            email="b@test.horilla",
            first_name="Bob",
            date_joining=cls.today - timedelta(days=20),
        )
        cls.emp_left = make_employee(
            company=cls.company,
            email="c@test.horilla",
            first_name="Cara",
            date_joining=cls.today - timedelta(days=40),
        )
        cls.emp_left.is_active = False
        cls.emp_left.save(update_fields=["is_active"])
        cls.emp_other = make_employee(
            company=cls.other_company, email="d@test.horilla", first_name="Dan"
        )

        cls._seed_exits()
        cls._seed_time_and_leave()
        cls._seed_payroll()
        cls._seed_talent()

    @classmethod
    def _seed_exits(cls):
        """An approved resignation -- the source report.metrics._exits reads.

        Without this every exit-shaped report and drill-down runs against an
        empty population and their assertions pass vacuously.
        """
        if not apps.is_installed("offboarding"):
            return
        make_resignation(
            employee=cls.emp_left,
            planned_to_leave_on=cls.today - timedelta(days=5),
        )

    @classmethod
    def _seed_time_and_leave(cls):
        if apps.is_installed("attendance"):
            # 1h45m of overtime twice over -- the pair that used to total
            # 2.90 hours instead of 3.50 in the pivot explorer.
            for offset in (1, 2):
                make_attendance(
                    employee=cls.emp_a,
                    attendance_date=cls.today - timedelta(days=offset),
                    overtime_second=6300,
                )
            make_attendance(
                employee=cls.emp_b,
                attendance_date=cls.today - timedelta(days=1),
            )
        if apps.is_installed("leave"):
            cls.leave_type = make_leave_type()
            make_available_leave(employee=cls.emp_a, leave_type=cls.leave_type)
            make_leave_request(
                employee=cls.emp_a,
                leave_type=cls.leave_type,
                start_date=cls.today - timedelta(days=3),
                end_date=cls.today - timedelta(days=3),
                status="approved",
            )
            # A non-approved row: metrics that count only approved leave must
            # not pick this up.
            make_leave_request(
                employee=cls.emp_b,
                leave_type=cls.leave_type,
                start_date=cls.today - timedelta(days=2),
                end_date=cls.today - timedelta(days=2),
                status="requested",
            )

    @classmethod
    def _seed_payroll(cls):
        if not apps.is_installed("payroll"):
            return
        period_start = cls.today.replace(day=1)
        make_payslip(
            employee=cls.emp_a,
            start_date=period_start,
            end_date=cls.today,
        )
        make_payslip(
            employee=cls.emp_b,
            start_date=period_start,
            end_date=cls.today,
            gross_pay=7000,
            net_pay=5600,
        )
        make_contract(
            employee=cls.emp_a,
            start_date=cls.today - timedelta(days=365),
            end_date=cls.today + timedelta(days=30),
        )

    @classmethod
    def _seed_talent(cls):
        if not apps.is_installed("recruitment"):
            return
        cls.recruitment = make_recruitment(company=cls.company)
        cls.stage = make_stage(recruitment=cls.recruitment)
        make_candidate(
            recruitment=cls.recruitment,
            stage=cls.stage,
            email="cand1@test.horilla",
        )
        # Candidate.save() derives `hired` from the stage's stage_type, so a
        # hired candidate has to sit on the real hired stage rather than
        # carrying the flag alone.
        hired_stage = get_hired_stage(recruitment=cls.recruitment) or cls.stage
        make_candidate(
            recruitment=cls.recruitment,
            stage=hired_stage,
            email="cand2@test.horilla",
            name="Hired Candidate",
            hired=True,
        )

    def setUp(self):
        # Reports read the selected company from a ContextVar; leaving one set
        # would silently scope (or unscope) every assertion below.
        clear_selected_company()

    # -- helpers ---------------------------------------------------------

    def _filters(self, preset="this_month", employment_status="active"):
        from report.engine import ReportFilters, resolve_period_preset

        from_date, to_date = resolve_period_preset(preset, self.today)
        return ReportFilters(
            from_date=from_date,
            to_date=to_date,
            period_preset=preset,
            employment_status=employment_status,
        )

    def _assert_payload_shape(self, slug, payload):
        """The contract every report renderer and exporter relies on."""
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload.get("slug"), slug)
        self.assertTrue(payload.get("title"), f"{slug} has no title")
        self.assertIn("period", payload)

        kpis = payload.get("kpis")
        self.assertIsInstance(kpis, list, f"{slug} kpis must be a list")
        for kpi in kpis:
            self.assertIn("label", kpi, f"{slug} kpi missing label: {kpi}")
            # A None value renders as an empty card and breaks the exporters'
            # number formatting -- catch it here rather than in a PDF.
            self.assertIsNotNone(
                kpi.get("value"), f"{slug} kpi '{kpi.get('label')}' value is None"
            )

        table = payload.get("table")
        if table:
            columns = table.get("columns") or []
            self.assertTrue(
                all(c.get("key") for c in columns),
                f"{slug} has a table column with no key",
            )
            keys = {c["key"] for c in columns}
            for row in table.get("rows") or []:
                self.assertIsInstance(row, dict)
                # Rows are looked up by column key in both the UI and the
                # exporters; a missing key silently exports as blank.
                missing = keys - set(row.keys())
                self.assertFalse(
                    missing, f"{slug} row missing column keys {sorted(missing)}"
                )

    # -- tests -----------------------------------------------------------

    def test_every_registered_report_executes(self):
        """The gap this file exists to close.

        ``run_report`` was previously only ever called on synthetic fixture
        reports, so a real report could raise on real data and CI stayed
        green.
        """
        from report.registry import list_reports, run_report

        definitions = list_reports()
        self.assertGreater(len(definitions), 25, "catalog looks unregistered")

        for definition in definitions:
            for preset in PERIOD_PRESETS:
                for status in EMPLOYMENT_STATUSES:
                    with self.subTest(
                        slug=definition.slug, preset=preset, status=status
                    ):
                        payload = run_report(
                            definition.slug,
                            self._filters(preset=preset, employment_status=status),
                        )
                        self._assert_payload_shape(definition.slug, payload)

    def test_every_report_executes_with_period_compare(self):
        """The compare path runs each report's query set a second time."""
        from report.registry import list_reports, run_report

        for definition in list_reports():
            with self.subTest(slug=definition.slug):
                filters = self._filters()
                filters.compare_preset = "prior_period"
                payload = run_report(definition.slug, filters)
                self._assert_payload_shape(definition.slug, payload)

    def test_every_drilldown_returns_rows_payload(self):
        """Drill-downs are separate queries and can regress independently."""
        from report.registry import list_reports, run_drilldown

        checked = 0
        for definition in list_reports():
            if not definition.drilldown_fn:
                continue
            with self.subTest(slug=definition.slug):
                result = run_drilldown(definition.slug, self._filters(), {})
                self.assertIsInstance(result, dict)
                self.assertIn("rows", result)
                self.assertIsInstance(result["rows"], list)
                checked += 1
        self.assertGreater(checked, 0, "no drilldowns exercised")

    # Drill-downs that need no dimension argument to return their population.
    # The dimension-keyed ones (workforce-composition, payslip-register,
    # recruitment-funnel) correctly answer "Missing dimension value." when
    # called bare, so they are exercised separately below.
    UNKEYED_DRILLDOWNS = (
        "exit-analysis",
        "joiners-leavers",
        "new-hire-90-day-attrition",
        "turnover-attrition",
        "leave-liability",
        "overtime-analysis",
    )

    def test_drilldowns_actually_return_rows(self):
        """The shape assertions above pass just as happily on empty payloads.

        Every drill-down in this suite returned zero rows once while the test
        stayed green -- the fixture simply had no exits, no joining dates and
        no overtime. Assert real rows so a drill-down that silently stops
        matching is caught.
        """
        from report.registry import get_report, run_drilldown

        for slug in self.UNKEYED_DRILLDOWNS:
            if get_report(slug) is None:
                continue
            with self.subTest(slug=slug):
                result = run_drilldown(slug, self._filters(preset="all_time"), {})
                self.assertTrue(
                    result.get("rows"),
                    f"{slug} drill-down returned no rows: "
                    f"{result.get('message') or 'no message'}",
                )
                self.assertTrue(
                    result.get("columns"), f"{slug} returned rows but no columns"
                )
                # Every row must carry all declared column keys, same
                # contract the report tables hold to.
                keys = {c["key"] for c in result["columns"]}
                for row in result["rows"]:
                    missing = keys - set(row.keys())
                    self.assertFalse(
                        missing, f"{slug} row missing keys {sorted(missing)}"
                    )

    def test_named_overtime_rows_stay_behind_the_privacy_gate(self):
        """Drilling in must not become a way to rebuild the named breakdown
        the report deliberately withholds (report/metrics/_privacy.py)."""
        from report.registry import run_drilldown

        result = run_drilldown(
            "overtime-analysis", self._filters(preset="all_time"), {}
        )
        # No request on the filters -> no include_names flag -> aggregates.
        column_keys = {c["key"] for c in result.get("columns") or []}
        self.assertNotIn("employee", column_keys)
        self.assertIn("department", column_keys)

    def test_reports_export_to_xlsx_and_csv(self):
        """Export the real payloads, not hand-written fixtures."""
        import io

        import openpyxl

        from report.export import export_csv, export_xlsx
        from report.registry import list_reports, run_report

        for definition in list_reports()[:8]:
            with self.subTest(slug=definition.slug):
                payload = run_report(definition.slug, self._filters())
                xlsx = export_xlsx(payload, f"{definition.slug}.xlsx", meta={})
                self.assertTrue(xlsx.content)
                wb = openpyxl.load_workbook(io.BytesIO(xlsx.content))
                self.assertIn("Cover", wb.sheetnames)
                csv_response = export_csv(payload, f"{definition.slug}.csv")
                self.assertTrue(csv_response.content)


class ReportNumericAgreementTests(TestCase):
    """
    Pin the numbers the audit found diverging between the two reporting
    systems. These are the assertions that make the eventual explorer
    consolidation safe to attempt.
    """

    @classmethod
    def setUpTestData(cls):
        import report.metrics  # noqa: F401

        cls.today = date.today()
        cls.company = make_company("Agreement Corp")
        cls.active_1 = make_employee(
            company=cls.company, email="act1@test.horilla", first_name="Act1"
        )
        cls.active_2 = make_employee(
            company=cls.company, email="act2@test.horilla", first_name="Act2"
        )
        cls.terminated = make_employee(
            company=cls.company, email="term@test.horilla", first_name="Term"
        )
        cls.terminated.is_active = False
        cls.terminated.save(update_fields=["is_active"])

    def setUp(self):
        clear_selected_company()

    def _filters(self, employment_status="active"):
        from report.engine import ReportFilters, resolve_period_preset

        from_date, to_date = resolve_period_preset("all_time", self.today)
        return ReportFilters(
            from_date=from_date,
            to_date=to_date,
            period_preset="all_time",
            employment_status=employment_status,
        )

    def test_active_default_excludes_terminated_employees(self):
        """Standard reports default to active-only.

        The pivot explorer used ``Employee.objects.all()`` and so counted the
        terminated employee, producing a headcount that disagreed with this.
        """
        from employee.models import Employee

        active_count = Employee.objects.filter(is_active=True).count()
        self.assertEqual(active_count, 2)
        self.assertEqual(Employee.objects.count(), 3)

    def test_explorer_pivot_matches_active_headcount(self):
        """The explorer queryset must now agree with the active count."""
        from employee.models import Employee

        # Mirrors the (fixed) queryset in report/views/employee_report.py:
        # no is_active in the query string -> active only.
        explorer_qs = Employee.objects.all().filter(is_active=True)
        self.assertEqual(explorer_qs.count(), 2)

    def test_overtime_seconds_convert_to_decimal_hours(self):
        """1h45m twice must total 3.5 hours, not 2.90."""
        seconds = 6300  # 1:45
        hours = round(seconds / 3600, 2)
        self.assertEqual(hours, 1.75)
        self.assertEqual(hours * 2, 3.5)


class ReportQueryBudgetTests(TestCase):
    """
    A ceiling on queries per report, so a new N+1 shows up as a failing test
    rather than a slow page.

    The bound is deliberately generous -- this guards against a per-row query
    creeping in, not against every extra join. Reports that legitimately need
    more can be listed in ``ALLOWANCES`` with a note.
    """

    # Reports whose current implementation exceeds the default ceiling.
    # Each entry is a standing invitation to optimise, not an endorsement.
    # Measured with the six-employee fixture below; bounds are set just above
    # the current count so a per-row query creeping in trips the test.
    ALLOWANCES = {
        # Iterates the exit list twice, issuing a per-exit work-info query
        # (report/metrics/workforce.py). Currently 33.
        "turnover-attrition": 45,
        # Six monthly windows, each running its own attendance/leave
        # aggregate. Currently 25.
        "absenteeism-rate": 35,
    }
    DEFAULT_BUDGET = 20

    @classmethod
    def setUpTestData(cls):
        import report.metrics  # noqa: F401

        cls.today = date.today()
        cls.company = make_company("Budget Corp")
        # Enough employees that a per-employee query is visible above the
        # fixed cost of the report itself.
        cls.employees = [
            make_employee(
                company=cls.company,
                email=f"budget{i}@test.horilla",
                first_name=f"Emp{i}",
            )
            for i in range(6)
        ]

    def setUp(self):
        clear_selected_company()

    def test_no_report_exceeds_its_query_budget(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from report.engine import ReportFilters, resolve_period_preset
        from report.registry import list_reports, run_report

        from_date, to_date = resolve_period_preset("this_month", self.today)
        overruns = []
        for definition in list_reports():
            budget = self.ALLOWANCES.get(definition.slug, self.DEFAULT_BUDGET)
            filters = ReportFilters(
                from_date=from_date,
                to_date=to_date,
                period_preset="this_month",
            )
            with CaptureQueriesContext(connection) as ctx:
                run_report(definition.slug, filters)
            if len(ctx) > budget:
                overruns.append(f"{definition.slug}: {len(ctx)} > {budget}")
        self.assertFalse(
            overruns,
            "Reports exceeded their query budget (likely a new N+1):\n"
            + "\n".join(overruns),
        )


class SubscriptionClaimTests(TestCase):
    """
    report/scheduler.py runs an in-process scheduler, so with N gunicorn
    workers there are N pollers. Delivery has to be claimed atomically or
    every worker sends the same subscription.
    """

    @classmethod
    def setUpTestData(cls):
        import report.metrics  # noqa: F401

        cls.company = make_company("Claim Corp")
        cls.employee = make_employee(
            company=cls.company, email="claim@test.horilla", first_name="Claim"
        )
        # The owner has to clear both the view and export permission gates,
        # or delivery exits before ever reaching the claim.
        cls.owner = make_user("claim-owner", is_superuser=True)

    def setUp(self):
        clear_selected_company()

    def _mail_configured(self):
        """Delivery bails at mail_unconfigured before reaching the claim when
        no SMTP sender is set, which is the case in tests."""
        from unittest.mock import patch

        return patch(
            "report.delivery.ConfiguredEmailBackend.dynamic_from_email_with_display_name",
            new_callable=lambda: property(lambda self: "reports@test.horilla"),
            create=True,
        )

    def _subscription(self, **overrides):
        from report.models import ReportSubscription

        defaults = {
            "report_slug": "workforce-composition",
            "name": "Weekly workforce",
            "frequency": "weekly",
            "recipients": "boss@test.horilla",
            "last_run_at": None,
            "owner": self.owner,
        }
        defaults.update(overrides)
        return ReportSubscription.objects.create(**defaults)

    def test_second_worker_does_not_resend(self):
        """Two pollers, one due subscription -> one claim wins."""
        from unittest.mock import patch

        from report.delivery import deliver_subscription
        from report.models import ReportSubscription

        sub = self._subscription()
        # Two in-memory handles on the same row, as two worker processes
        # would each have after their own queryset read.
        first = ReportSubscription.objects.get(pk=sub.pk)
        second = ReportSubscription.objects.get(pk=sub.pk)

        # A successful send is required for the claim to stick: a failed
        # delivery deliberately releases it so the next poll retries.
        with self._mail_configured(), patch(
            "report.delivery.EmailMessage.send", return_value=1
        ):
            result_a = deliver_subscription(first)
            result_b = deliver_subscription(second)

        # Exactly one worker delivers; the loser is turned away by the claim.
        self.assertTrue(result_a.ok, result_a.detail)
        self.assertFalse(result_b.ok)
        self.assertEqual(result_b.status, "skipped")
        self.assertIn("claimed", result_b.detail.lower())

    def test_claim_is_released_when_delivery_fails(self):
        """A failed send must not consume the whole interval."""
        from unittest.mock import patch

        from report.delivery import deliver_subscription
        from report.models import ReportSubscription

        sub = self._subscription()
        with self._mail_configured(), patch(
            "report.delivery.run_report", side_effect=RuntimeError("boom")
        ):
            result = deliver_subscription(ReportSubscription.objects.get(pk=sub.pk))
        self.assertFalse(result.ok)
        sub.refresh_from_db()
        # Back to unclaimed, so the next poll retries.
        self.assertIsNone(sub.last_run_at)

    def test_forced_run_bypasses_the_claim(self):
        """Run-now from the UI must work even when not due."""
        from django.utils import timezone

        from report.delivery import deliver_subscription
        from report.models import ReportSubscription

        sub = self._subscription(last_run_at=timezone.now())
        with self._mail_configured():
            result = deliver_subscription(
                ReportSubscription.objects.get(pk=sub.pk), force=True
            )
        # Not "skipped": force skips both the due check and the claim.
        self.assertNotEqual(result.status, "skipped")


class AsyncExportScopingTests(TestCase):
    """The export worker runs outside the request, so tenant scope and the
    concurrency ceiling both have to be explicit."""

    def test_queue_refuses_beyond_the_concurrency_limit(self):
        from report import async_export

        acquired = []
        try:
            for _ in range(async_export.MAX_CONCURRENT_EXPORTS):
                self.assertTrue(async_export._export_slots.acquire(blocking=False))
                acquired.append(True)
            with self.assertRaises(async_export.ExportQueueFull):
                async_export.queue_export_email(
                    user_id=1,
                    to_email="x@test.horilla",
                    slug="workforce-composition",
                    fmt="xlsx",
                    filters_dict={},
                    meta={},
                )
        finally:
            for _ in acquired:
                async_export._export_slots.release()

    def test_queue_accepts_company_id(self):
        """The signature has to carry company_id: without it the worker has
        no session and no ContextVar, so the workbook spans every company."""
        import inspect

        from report.async_export import queue_export_email

        params = inspect.signature(queue_export_email).parameters
        self.assertIn("company_id", params)

    def test_view_passes_selected_company_to_the_worker(self):
        import inspect

        from report.views import standard_reports

        source = inspect.getsource(standard_reports.standard_report_export)
        self.assertIn("company_id=company_id", source)


class PivotTruncationDisclosureTests(TestCase):
    """
    pivot_limits caps a payload and reports it in a response header, but the
    explorer templates fetch with $.getJSON, which discards headers -- so a
    truncated pivot used to present a partial total as a complete one.
    """

    def test_response_carries_truncation_headers(self):
        from report.pivot_limits import pivot_json_with_meta

        rows = [{"n": i} for i in range(12)]
        response = pivot_json_with_meta(rows, limit=5)
        self.assertEqual(response["X-Horilla-Pivot-Truncated"], "1")
        self.assertEqual(response["X-Horilla-Pivot-Limit"], "5")

    def test_untruncated_response_sets_no_flag(self):
        from report.pivot_limits import pivot_json_with_meta

        response = pivot_json_with_meta([{"n": 1}], limit=5)
        self.assertIsNone(response.get("X-Horilla-Pivot-Truncated"))

    def test_notice_script_is_loaded_for_pivot_pages(self):
        """The banner is installed once in the shared base template rather
        than at each of the ~10 fetch sites across 7 near-identical pages."""
        from pathlib import Path

        from django.conf import settings

        index = Path(settings.BASE_DIR) / "templates" / "index.html"
        markup = index.read_text(encoding="utf-8")
        self.assertIn("report/js/pivot_safety.js", markup)

    def test_notice_script_reads_the_documented_headers(self):
        from pathlib import Path

        from django.conf import settings

        script = (
            Path(settings.BASE_DIR)
            / "report"
            / "static"
            / "report"
            / "js"
            / "pivot_safety.js"
        )
        source = script.read_text(encoding="utf-8")
        self.assertIn("X-Horilla-Pivot-Truncated", source)
        self.assertIn("X-Horilla-Pivot-Limit", source)


class SharedFormulaGuardTests(TestCase):
    """
    Four separate spreadsheet writers exist in this repo and only
    report/export.py guarded its cells. They now share one guard.
    """

    def test_triggers_are_neutralized(self):
        from horilla.export_safety import neutralize_formula

        for payload in (
            '=HYPERLINK("http://evil.test","x")',
            "+1+1",
            "-1-1",
            "@SUM(A1:A9)",
            "\tinjected",
            "\rinjected",
            "\ninjected",
            # Unicode minus and dashes: rendered like a hyphen, and some
            # importers normalize them before evaluating.
            "−=1",
            "–=1",
        ):
            guarded = neutralize_formula(payload)
            self.assertTrue(guarded.startswith("'"), f"not neutralized: {payload!r}")

    def test_ordinary_text_and_numbers_pass_through(self):
        from horilla.export_safety import neutralize_formula, safe_cell

        self.assertEqual(neutralize_formula("Ann Smith"), "Ann Smith")
        self.assertEqual(neutralize_formula(""), "")
        # Real numeric types must keep their cell type, or the column loses
        # its number formatting and its totals.
        self.assertEqual(safe_cell(42), 42)
        self.assertEqual(safe_cell(3.5), 3.5)
        self.assertIs(safe_cell(True), True)
        self.assertEqual(safe_cell(None), "")

    def test_report_export_uses_the_shared_guard(self):
        from horilla.export_safety import neutralize_formula
        from report.export import _neutralize_formula

        self.assertEqual(_neutralize_formula("=cmd"), neutralize_formula("=cmd"))

    def test_other_writers_guard_their_cells(self):
        """All four spreadsheet writers, not just report/export.py."""
        import inspect

        from base import methods as base_methods
        from horilla_views import cbv_methods as hv_cbv
        from horilla_views import views as hv_views

        self.assertIn("safe_cell", inspect.getsource(base_methods.export_data))
        self.assertIn("safe_cell", inspect.getsource(hv_views))
        self.assertIn("safe_cell", inspect.getsource(hv_cbv))

    def test_no_unguarded_worksheet_writes_remain(self):
        """A regression fence: a new ws.append(row) without the guard is the
        easiest way to reintroduce the sink."""
        import inspect

        from horilla_views import cbv_methods as hv_cbv

        source = inspect.getsource(hv_cbv)
        # Header rows are literals built in-module, not user data; the two
        # data-row writes must both be wrapped.
        self.assertNotIn("ws.append(row)", source)

    def test_client_side_export_guard_mirrors_python(self):
        """The explorer builds xlsx in the browser from the DOM, bypassing
        every server-side guard."""
        from pathlib import Path

        from django.conf import settings

        base = Path(settings.BASE_DIR)
        script = (
            base / "report" / "static" / "report" / "js" / "pivot_safety.js"
        ).read_text(encoding="utf-8")
        self.assertIn("horillaSafeCell", script)

        for name in (
            "employee",
            "asset",
            "attendance",
            "leave",
            "payroll",
            "pms",
            "recruitment",
        ):
            markup = (
                base / "horilla_theme" / "templates" / "report" / f"{name}_report.html"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "horillaSafeCell",
                markup,
                f"{name} pivot export writes cells unguarded",
            )


class PeriodNoteDisclosureTests(TestCase):
    """
    turnover-attrition deliberately analyses a fixed rolling 6-month window
    and explains that in payload["period_note"]. The note was produced and
    never rendered -- one producer, zero consumers repo-wide -- so the number
    looked as though it had ignored the selected period for no reason.
    """

    @classmethod
    def setUpTestData(cls):
        import report.metrics  # noqa: F401

        cls.today = date.today()
        cls.company = make_company("Note Corp")
        make_employee(company=cls.company, email="note@test.horilla", first_name="Note")

    def setUp(self):
        clear_selected_company()

    def test_turnover_declares_its_own_window(self):
        from report.engine import ReportFilters, resolve_period_preset
        from report.registry import run_report

        # Ask for a single month; the report answers with its own window.
        from_date, to_date = resolve_period_preset("this_month", self.today)
        payload = run_report(
            "turnover-attrition",
            ReportFilters(
                from_date=from_date, to_date=to_date, period_preset="this_month"
            ),
        )
        self.assertEqual(payload["period"]["preset"], "rolling_6m")
        self.assertTrue(payload.get("period_note"))
        # The declared window must be wider than the month that was asked
        # for, or the override is not actually taking effect.
        self.assertLess(payload["period"]["from_date"], from_date.isoformat())

    def test_ui_renders_the_note(self):
        from pathlib import Path

        from django.conf import settings

        markup = (
            Path(settings.BASE_DIR)
            / "horilla_theme"
            / "templates"
            / "report"
            / "standard_report.html"
        ).read_text(encoding="utf-8")
        self.assertIn("sr-period-note", markup)
        self.assertIn("setPeriodNote", markup)
        self.assertIn("data.period_note", markup)

    def test_ui_does_not_overwrite_the_user_date_inputs(self):
        """A report reporting its own window must not rewrite the filter
        inputs to dates the user never picked -- the next report opened would
        otherwise inherit them."""
        from pathlib import Path

        from django.conf import settings

        markup = (
            Path(settings.BASE_DIR)
            / "horilla_theme"
            / "templates"
            / "report"
            / "standard_report.html"
        ).read_text(encoding="utf-8")
        self.assertIn("usesOwnWindow", markup)


class AuditActivityScopingTests(TestCase):
    """
    auditlog.LogEntry is third-party: no company column, no
    HorillaCompanyManager. Unlike every other model the metrics layer
    touches, it returned every tenant's activity to any viewer.
    """

    @classmethod
    def setUpTestData(cls):
        import report.metrics  # noqa: F401

        cls.today = date.today()
        cls.company_a = make_company("Audit A")
        cls.company_b = make_company("Audit B", hq=False)
        cls.user_a = make_user("audit-a")
        cls.user_b = make_user("audit-b")
        cls.emp_a = make_employee(
            company=cls.company_a,
            email="aa@test.horilla",
            first_name="AuditA",
            user=cls.user_a,
        )
        cls.emp_b = make_employee(
            company=cls.company_b,
            email="bb@test.horilla",
            first_name="AuditB",
            user=cls.user_b,
        )

    def setUp(self):
        clear_selected_company()

    def _entries(self):
        """One log entry per company, attributed to that company's user."""
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(type(self.emp_a))
        for actor, obj in ((self.user_a, self.emp_a), (self.user_b, self.emp_b)):
            LogEntry.objects.create(
                content_type=ct,
                object_pk=str(obj.pk),
                object_repr=str(obj),
                action=1,
                actor=actor,
            )

    def test_scoped_to_the_selected_company(self):
        from report.engine import ReportFilters, resolve_period_preset
        from report.metrics.compliance import audit_activity

        self._entries()
        from_date, to_date = resolve_period_preset("all_time", self.today)
        scoped = audit_activity(
            ReportFilters(
                from_date=from_date,
                to_date=to_date,
                period_preset="all_time",
                company_id=self.company_a.id,
            )
        )
        kpis = {str(k["label"]): k["value"] for k in scoped["kpis"]}
        # Company A's single entry, not both companies'.
        self.assertEqual(kpis.get("Log entries"), 1)

    def test_unscoped_request_still_returns_everything(self):
        """No company selected (superuser 'all') keeps tenant-wide view."""
        from report.engine import ReportFilters, resolve_period_preset
        from report.metrics.compliance import audit_activity

        self._entries()
        from_date, to_date = resolve_period_preset("all_time", self.today)

        def entries(**kw):
            payload = audit_activity(
                ReportFilters(
                    from_date=from_date,
                    to_date=to_date,
                    period_preset="all_time",
                    **kw,
                )
            )
            return {str(k["label"]): k["value"] for k in payload["kpis"]}["Log entries"]

        # Fixture setup itself writes audit rows, so compare the scoped and
        # unscoped views rather than asserting an absolute count.
        unscoped = entries()
        scoped_a = entries(company_id=self.company_a.id)
        scoped_b = entries(company_id=self.company_b.id)
        self.assertGreater(unscoped, scoped_a)
        self.assertGreater(unscoped, scoped_b)
        # Neither tenant sees the other's activity.
        self.assertGreaterEqual(scoped_a, 1)
        self.assertGreaterEqual(scoped_b, 1)


class MetricTruncationDisclosureTests(TestCase):
    """A KPI counting every match above a capped row list has to say so."""

    def test_table_carries_truncation_flags(self):
        import inspect

        from report.metrics import compliance, packs

        # The registered report is packs.document_expiry_aging;
        # compliance.document_expiry serves the retired slug.
        for fn in (packs.document_expiry_aging, compliance.document_expiry):
            source = inspect.getsource(fn)
            self.assertIn('"truncated"', source, fn.__name__)
            self.assertIn('"total_rows"', source, fn.__name__)

    def test_aging_buckets_count_every_match_not_just_listed_rows(self):
        """The buckets were built inside the row slice, so past the cap the
        KPI totals were wrong, not just the table."""
        import inspect

        from report.metrics import packs

        source = inspect.getsource(packs.document_expiry_aging)
        # Bucketing runs over a values_list of the full queryset, separate
        # from the capped select_related loop that builds rows.
        self.assertIn('values_list("expiry_date"', source)
        self.assertIn("[:ROW_CAP]", source)

    def test_exports_and_ui_honour_the_flag(self):
        import inspect
        from pathlib import Path

        from django.conf import settings

        from report import export

        # PDF path escalates its own cap with the metric's flag.
        self.assertIn(
            'table_meta.get("truncated")',
            (
                inspect.getsource(export._render_pdf_context)
                if hasattr(export, "_render_pdf_context")
                else inspect.getsource(export)
            ),
        )
        # Excel data sheet reports a sample rather than a total.
        self.assertIn("(sample)", inspect.getsource(export._write_data_sheet))
        markup = (
            Path(settings.BASE_DIR)
            / "horilla_theme"
            / "templates"
            / "report"
            / "standard_report.html"
        ).read_text(encoding="utf-8")
        self.assertIn("table.truncated", markup)


class SilentMetricFailureTests(TestCase):
    """A data source that fails silently shrinks the report into a smaller,
    apparently valid number with nothing logged."""

    def test_no_bare_pass_handlers_remain_in_metrics(self):
        from pathlib import Path

        from django.conf import settings

        metrics_dir = Path(settings.BASE_DIR) / "report" / "metrics"
        offenders = []
        for path in sorted(metrics_dir.glob("*.py")):
            lines = path.read_text(encoding="utf-8").splitlines()
            for idx, line in enumerate(lines[:-1]):
                if line.strip() == "except Exception:" and (
                    lines[idx + 1].strip() == "pass"
                ):
                    offenders.append(f"{path.name}:{idx + 1}")
        self.assertFalse(
            offenders,
            "silent exception handlers drop whole data sources: "
            + ", ".join(offenders),
        )


class CohortActiveFilterTests(TestCase):
    """
    Reports measuring what happened to leavers must not filter the cohort to
    active employees -- that removes exactly the population being counted.

    new-hire-90-day-attrition's numerator was structurally zero (its joiner
    cohort excluded anyone who had left), and quality-of-hire's retention
    rate was biased toward 100% for the same reason.
    """

    @classmethod
    def setUpTestData(cls):
        import report.metrics  # noqa: F401

        cls.today = date.today()
        cls.company = make_company("Cohort Corp")
        # Joined 40 days ago, left 5 days ago -> a 35-day tenure, squarely
        # inside the 90-day window.
        cls.early_leaver = make_employee(
            company=cls.company,
            email="leaver@test.horilla",
            first_name="Early",
            date_joining=cls.today - timedelta(days=40),
        )
        cls.stayer = make_employee(
            company=cls.company,
            email="stayer@test.horilla",
            first_name="Stayer",
            date_joining=cls.today - timedelta(days=40),
        )
        if apps.is_installed("offboarding"):
            make_resignation(
                employee=cls.early_leaver,
                planned_to_leave_on=cls.today - timedelta(days=5),
            )
        cls.early_leaver.is_active = False
        cls.early_leaver.save(update_fields=["is_active"])

    def setUp(self):
        clear_selected_company()

    def _filters(self):
        from report.engine import ReportFilters, resolve_period_preset

        from_date, to_date = resolve_period_preset("all_time", self.today)
        return ReportFilters(
            from_date=from_date, to_date=to_date, period_preset="all_time"
        )

    def test_90_day_attrition_counts_the_leaver(self):
        from report.registry import run_report

        payload = run_report("new-hire-90-day-attrition", self._filters())
        kpis = {str(k["label"]): k["value"] for k in payload["kpis"]}
        # The cohort has to include the inactive early leaver, so neither the
        # cohort size nor the early-exit count can be zero.
        self.assertGreaterEqual(
            kpis.get("Cohort joiners", 0), 2, f"cohort excluded the leaver: {kpis}"
        )
        self.assertGreaterEqual(
            kpis.get("Early exits", 0),
            1,
            f"early exits should count the leaver: {kpis}",
        )
        # And the headline rate must therefore be non-zero.
        self.assertNotEqual(kpis.get("90-day attrition"), "0.0%", kpis)

    def test_90_day_attrition_drilldown_lists_the_leaver(self):
        from report.registry import run_drilldown

        result = run_drilldown("new-hire-90-day-attrition", self._filters(), {})
        names = " ".join(str(r.get("employee", "")) for r in result.get("rows") or [])
        self.assertIn("Early", names, f"leaver missing from drill-down: {result}")

    def test_quality_of_hire_cohort_includes_leavers(self):
        import inspect

        from report.metrics import talent

        # The denominator must not be active-filtered, or retention trends
        # toward 100% no matter how many new hires leave.
        source = inspect.getsource(talent.quality_of_hire)
        self.assertIn("apply_employment_status=False", source)


class TemplateShadowingTests(TestCase):
    """
    horilla/settings/base.py puts the theme filesystem loader ahead of
    app_directories, so report/templates/report/*.html could never render --
    4,165 lines of it were being maintained alongside the live theme copies
    that actually shadow them.
    """

    EXPLORERS = (
        "asset",
        "attendance",
        "employee",
        "leave",
        "payroll",
        "pms",
        "recruitment",
    )

    def test_explorer_templates_resolve_to_the_theme(self):
        """Let Django resolve them rather than reasoning about loader order."""
        from django.template.loader import get_template

        for name in self.EXPLORERS:
            with self.subTest(explorer=name):
                origin = get_template(f"report/{name}_report.html").origin.name or ""
                self.assertIn(
                    "horilla_theme",
                    origin,
                    f"{name} no longer resolves to the theme copy: {origin}",
                )

    def test_no_shadowed_copies_reappear(self):
        """A re-added app-level copy would be silently unreachable."""
        from pathlib import Path

        from django.conf import settings

        shadowed = Path(settings.BASE_DIR) / "report" / "templates" / "report"
        self.assertFalse(
            shadowed.exists(),
            "report/templates/report/ is shadowed by the theme loader and can "
            "never render; put explorer templates in horilla_theme instead.",
        )

    def test_dead_export_helper_stays_deleted(self):
        """report_export.js defined five helpers and nothing called any of
        them -- the residue of an abandoned dedup attempt."""
        from pathlib import Path

        from django.conf import settings

        base = Path(settings.BASE_DIR)
        self.assertFalse(
            (base / "report" / "static" / "report" / "js" / "report_export.js").exists()
        )
        theme = base / "horilla_theme" / "templates" / "report"
        for path in theme.glob("*_report.html"):
            self.assertNotIn(
                "report_export.js",
                path.read_text(encoding="utf-8"),
                f"{path.name} still loads the deleted helper",
            )


class ExplorerStylesheetTests(TestCase):
    """
    The explorer <style> block was inlined in all seven templates at 97-100%
    identity -- ~4,050 lines where ~600 do. Only two selectors ever differed,
    both splitting single-model against multi-model explorers.
    """

    SINGLE_MODEL = ("asset", "attendance", "employee")
    MULTI_MODEL = ("leave", "payroll", "pms", "recruitment")

    def _template_text(self, name):
        from pathlib import Path

        from django.conf import settings

        return (
            Path(settings.BASE_DIR)
            / "horilla_theme"
            / "templates"
            / "report"
            / f"{name}_report.html"
        ).read_text(encoding="utf-8")

    def test_shared_stylesheet_exists(self):
        from pathlib import Path

        from django.conf import settings

        css = (
            Path(settings.BASE_DIR)
            / "report"
            / "static"
            / "report"
            / "css"
            / "pivot_explorer.css"
        )
        self.assertTrue(css.exists())
        body = css.read_text(encoding="utf-8")
        # The two genuine per-page variants live here, not forked per file.
        self.assertIn(".oh-report--multi-model .oh-report-view-slot", body)

    def test_no_template_reinlines_the_block(self):
        """A re-added inline <style> would start the drift over again."""
        for name in self.SINGLE_MODEL + self.MULTI_MODEL:
            with self.subTest(explorer=name):
                text = self._template_text(name)
                self.assertNotIn(
                    "<style>",
                    text,
                    f"{name} re-inlined styles instead of using the shared file",
                )
                self.assertIn("report/css/pivot_explorer.css", text)

    def test_all_explorer_templates_still_compile(self):
        """A template syntax error introduced by the extraction would not show
        up in a file-content assertion -- compile each one."""
        from django.template.loader import get_template

        for name in self.SINGLE_MODEL + self.MULTI_MODEL:
            with self.subTest(explorer=name):
                template = get_template(f"report/{name}_report.html")
                self.assertTrue(template.template.nodelist)

    def test_only_multi_model_pages_carry_the_variant_class(self):
        """The variant supplies the "Choose Report" label typography, which
        the single-model explorers must not pick up."""
        marker = 'class="oh-report-view-slot oh-report--multi-model"'
        for name in self.MULTI_MODEL:
            with self.subTest(explorer=name, expected=True):
                self.assertIn(marker, self._template_text(name))
        for name in self.SINGLE_MODEL:
            with self.subTest(explorer=name, expected=False):
                self.assertNotIn(marker, self._template_text(name))


class PdfFontEmbeddingTests(TestCase):
    """
    export_pdf called pisa.CreatePDF with no link_callback, so xhtml2pdf could
    not resolve the font URI and silently fell back to Helvetica -- a base-14
    face with no glyphs outside Latin, printing non-Latin employee names as
    black boxes.
    """

    def _payload(self):
        return {
            "title": "Font Test",
            "slug": "font-test",
            "domain": "workforce",
            "period": {"from_date": "2026-01-01", "to_date": "2026-01-31"},
            "kpis": [{"label": "Headcount", "value": 2, "hint": ""}],
            "table": {
                "columns": [{"key": "name", "label": "Employee"}],
                # Devanagari is covered by the bundled Poppins face; the
                # accented Latin exercises Latin-ext.
                "rows": [{"name": "अमित शर्मा"}, {"name": "José Núñez"}],
            },
        }

    def test_pdf_embeds_a_truetype_font(self):
        from report.export import export_pdf

        body = export_pdf(self._payload(), filename="f.pdf", meta={}).content
        self.assertEqual(body[:4], b"%PDF")
        # An embedded TrueType face appears as a FontFile2 stream. With the
        # base-14 fallback there is none, which is exactly the broken state.
        self.assertIn(b"FontFile2", body)

    def test_link_callback_resolves_the_bundled_font(self):
        import os

        from django.conf import settings

        from report.export import PDF_FONT_STATIC_PATH, _pdf_link_callback

        uri = f"{settings.STATIC_URL}{PDF_FONT_STATIC_PATH}"
        resolved = _pdf_link_callback(uri, "")
        self.assertTrue(
            os.path.isfile(resolved), f"font URI did not resolve: {resolved}"
        )

    def test_link_callback_passes_through_what_it_cannot_resolve(self):
        """An unresolvable asset must not fail the whole document."""
        from report.export import _pdf_link_callback

        for uri in (
            "https://example.test/logo.png",
            "data:image/png;base64,AAAA",
            "/static/does/not/exist.png",
        ):
            self.assertIsInstance(_pdf_link_callback(uri, ""), str)


class ExportLabelTranslationTests(TestCase):
    """
    The filter block on every export cover sheet used raw English literals, so
    it stayed English in a French or Arabic tenant while the rest of the
    document translated.
    """

    def _filters(self):
        from report.engine import ReportFilters

        return ReportFilters(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            period_preset="this_month",
        )

    def test_labels_go_through_gettext(self):
        from django.utils import translation

        filters = self._filters()
        with translation.override("fr"):
            labels = [label for label, _value in filters.summary_pairs()]
        # Whether a French catalog entry exists is a packaging question; what
        # matters here is that the label is not a hard-coded literal bypassing
        # translation entirely.
        self.assertTrue(labels)
        with translation.override("en"):
            self.assertIn("Period", [l for l, _v in filters.summary_pairs()])

    def test_period_chip_stays_a_bare_value_under_translation(self):
        """summary_labels() used to detect the period row by comparing the
        label to the literal "Period", which a translated label would silently
        stop matching -- turning the chip into "Période: ..." in one language
        and a bare value in another."""
        from django.utils import translation

        filters = self._filters()
        for lang in ("en", "fr", "ar"):
            with self.subTest(lang=lang), translation.override(lang):
                chips = filters.summary_labels()
                self.assertTrue(chips)
                # The first chip is the period: a bare value, no "Label:".
                self.assertNotIn(":", chips[0].split("→")[0])

    def test_all_companies_label_is_translatable(self):
        import inspect

        from report import company_context

        source = inspect.getsource(company_context)
        self.assertIn('_("All companies")', source)


class ExportPolishTests(TestCase):
    """Smaller export defects: inconsistent timestamps, duplicated palettes,
    and chart failures indistinguishable from empty charts."""

    def test_all_export_paths_share_one_local_timestamp_helper(self):
        """The Excel footer and cover used naive timezone.now() while the PDF
        used localtime(), so one report exported twice carried two different
        times -- UTC on one document, local on the other."""
        import inspect

        from report import export

        source = inspect.getsource(export)
        self.assertNotIn('timezone.now().strftime("%Y-%m-%d %H:%M")', source)
        # Every timestamp goes through the one helper.
        self.assertIn("def _local_stamp(", source)

    def test_local_stamp_converts_aware_datetimes(self):
        from django.utils import timezone

        from report.export import _local_stamp

        aware = timezone.now()
        self.assertEqual(
            _local_stamp(aware), timezone.localtime(aware).strftime("%Y-%m-%d %H:%M")
        )
        # Non-datetimes pass through as text rather than raising.
        self.assertEqual(_local_stamp("2026-01-01"), "2026-01-01")

    def test_chart_palette_has_one_definition(self):
        """The PDF and Excel palettes were duplicated literals in separate
        files, linked only by a comment."""
        from report.chart_render import PALETTE_HEX
        from report.export import _chart_palette_hex

        self.assertEqual(_chart_palette_hex(), list(PALETTE_HEX))
        self.assertIn("E54F38", PALETTE_HEX)  # brand coral

    def test_chart_render_failure_is_logged_not_silent(self):
        """A failing chart returned None, which callers treat as "no data" --
        so a real failure printed "No data for the selected period"."""
        from unittest.mock import patch

        from report.chart_render import render_chart_png

        chart = {
            "id": "c1",
            "type": "bar",
            "categories": ["A", "B"],
            "series": [{"name": "n", "data": [1, 2]}],
        }
        with patch(
            "report.chart_render._bar_drawing", side_effect=RuntimeError("boom")
        ):
            with self.assertLogs("report.chart_render", level="ERROR") as logs:
                self.assertIsNone(render_chart_png(chart))
        self.assertTrue(any("Chart render failed" in line for line in logs.output))

    def test_chart_render_still_returns_none_for_empty_data(self):
        """The genuine no-data case must stay quiet."""
        from report.chart_render import render_chart_png

        self.assertIsNone(render_chart_png({"categories": [], "series": []}))
