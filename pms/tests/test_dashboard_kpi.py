"""The PMS dashboard KPI endpoint.

/pms/dashboard/api/kpi/ is the JSON feed behind the dashboard cards. It
aggregates across three models, divides to produce a completion rate, and
filters everything through a period window taken from query parameters --
none of which was covered.

These pin the arithmetic and the window, including the edge cases where a
division or an empty aggregate could raise.
"""

from datetime import date

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from pms.models import EmployeeKeyResult, EmployeeObjective, KeyResult, Objective

URL = "/pms/dashboard/api/kpi/"

# A window wide enough to contain every fixture row below, so tests that are
# not about the period filter are not accidentally filtered.
WIDE = {"from_date": "2026-01-01", "to_date": "2026-12-31"}


class DashboardKpiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("KPI Test Co")
        cls.user = make_user("kpi_user", password="secret123")
        cls.employee = make_employee(
            company=company, email="kpi@test.horilla", user=cls.user
        )
        cls.user.user_permissions.add(
            Permission.objects.get(
                codename="view_employeeobjective", content_type__app_label="pms"
            )
        )
        cls.company = company

    def setUp(self):
        self.client.force_login(self.user)

    _seq = 0

    def _objective(
        self, *, status="On Track", start=date(2026, 2, 1), days=28, archive=False
    ):
        """Create one EmployeeObjective.

        Each gets its own parent Objective: EmployeeObjective declares
        unique_together on (employee_id, objective_id), so one employee
        cannot hold two against the same parent.

        end_date is deliberately not passed. EmployeeObjective.save()
        derives it on create from the parent's duration and duration_unit,
        discarding anything supplied -- so the window is set through `days`.
        """
        type(self)._seq += 1
        objective = Objective.objects.create(
            title=f"Objective {type(self)._seq}",
            description="d",
            duration=days,
            duration_unit="days",
            company_id=self.company,
        )
        return EmployeeObjective.objects.create(
            objective_id=objective,
            employee_id=self.employee,
            start_date=start,
            status=status,
            archive=archive,
        )

    def _key_result(self, emp_obj, *, current, target, title="KR"):
        kr = KeyResult.objects.create(
            title=title, description="d", target_value=target, duration=30
        )
        return EmployeeKeyResult.objects.create(
            employee_objective_id=emp_obj,
            key_result_id=kr,
            start_value=0,
            current_value=current,
            target_value=target,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 3, 1),
        )

    def test_empty_database_does_not_divide_by_zero(self):
        """completion_rate guards total_objectives > 0, and avg_progress
        relies on Coalesce to turn an empty Avg into 0.0."""
        response = self.client.get(URL, WIDE)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_objectives"], 0)
        self.assertEqual(body["completion_rate"], 0)
        self.assertEqual(body["avg_progress"], 0.0)

    def test_completion_rate_is_closed_over_total(self):
        self._objective(status="Closed")
        self._objective(status="Closed")
        self._objective(status="On Track")
        self._objective(status="On Track")

        body = self.client.get(URL, WIDE).json()

        self.assertEqual(body["total_objectives"], 4)
        self.assertEqual(body["closed"], 2)
        self.assertEqual(body["completion_rate"], 50.0)

    def test_completion_rate_is_rounded_to_one_decimal(self):
        """1 of 3 closed is 33.333...; the view rounds to 33.3."""
        self._objective(status="Closed")
        self._objective(status="On Track")
        self._objective(status="On Track")

        body = self.client.get(URL, WIDE).json()

        self.assertEqual(body["completion_rate"], 33.3)

    def test_at_risk_counts_only_that_status(self):
        self._objective(status="At Risk")
        self._objective(status="On Track")

        body = self.client.get(URL, WIDE).json()

        self.assertEqual(body["at_risk"], 1)

    def test_archived_objectives_are_excluded(self):
        self._objective(status="On Track")
        self._objective(status="On Track", archive=True)

        body = self.client.get(URL, WIDE).json()

        self.assertEqual(body["total_objectives"], 1)

    def test_avg_progress_averages_key_results_not_objectives(self):
        """The card reports the mean across key results.

        Two key results at 20% and 80% average to 50, regardless of how the
        objective's own progress_percentage rolls up -- a different
        aggregation, as the view's comment notes.
        """
        obj = self._objective()
        self._key_result(obj, current=2, target=10, title="KR low")
        self._key_result(obj, current=8, target=10, title="KR high")

        body = self.client.get(URL, WIDE).json()

        self.assertEqual(body["total_key_results"], 2)
        self.assertEqual(body["avg_progress"], 50.0)

    def test_period_window_excludes_rows_outside_it(self):
        """A row overlaps when start <= to_date and end >= from_date."""
        self._objective(start=date(2026, 2, 1), days=28)
        self._objective(start=date(2026, 8, 1), days=28)

        body = self.client.get(
            URL, {"from_date": "2026-01-01", "to_date": "2026-04-01"}
        ).json()

        self.assertEqual(body["total_objectives"], 1)

    def test_a_row_straddling_the_window_is_included(self):
        """Overlap, not containment: a row spanning the whole window counts."""
        self._objective(start=date(2026, 1, 1), days=364)

        body = self.client.get(
            URL, {"from_date": "2026-06-01", "to_date": "2026-06-30"}
        ).json()

        self.assertEqual(body["total_objectives"], 1)

    def test_unparseable_dates_fall_back_to_the_current_month(self):
        """_parse_period catches ValueError/TypeError rather than 500ing."""
        response = self.client.get(URL, {"from_date": "not-a-date", "to_date": "//"})

        self.assertEqual(response.status_code, 200)

    def test_endpoint_requires_the_objective_view_permission(self):
        other = make_user("kpi_nobody", password="secret123")
        make_employee(
            company=make_company("KPI Other Co", hq=False),
            email="kpi_nobody@test.horilla",
            user=other,
        )
        self.client.force_login(other)

        response = self.client.get(URL, WIDE)

        self.assertNotEqual(
            response.status_code, 200, "KPI data served without the permission"
        )
