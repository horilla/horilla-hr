"""Dashboard role resolver, prefs migration, and Phase 5/6 guards."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from base.dashboard import _normalize_dashboard_chart_prefs
from base.dashboard_roles import (
    DEMOTED_BY_DEFAULT,
    ROLE_DEFAULT_VISIBLE,
    can_see_analytics_home,
    resolve_home_role,
    role_default_prefs,
)
from base.views import _charts_use_modern_prefs


class ResolveHomeRoleTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, user, **get):
        request = self.factory.get("/dashboard/", get)
        request.user = user
        request.session = {}
        return request

    def test_superuser_is_leadership(self):
        user = SimpleNamespace(
            is_superuser=True,
            is_staff=False,
            has_perm=lambda p: False,
            employee_get=None,
        )
        self.assertEqual(resolve_home_role(self._request(user)), "leadership")

    def test_employee_leave_recruitment_is_leadership(self):
        perms = {
            "employee.view_employee",
            "leave.view_leaverequest",
            "recruitment.view_recruitment",
        }
        user = SimpleNamespace(
            is_superuser=False,
            is_staff=False,
            has_perm=lambda p: p in perms,
            employee_get=None,
        )
        self.assertEqual(resolve_home_role(self._request(user)), "leadership")

    def test_employee_leave_is_hr(self):
        perms = {"employee.view_employee", "leave.view_leaverequest"}
        user = SimpleNamespace(
            is_superuser=False,
            is_staff=False,
            has_perm=lambda p: p in perms,
            employee_get=None,
        )
        with patch("base.dashboard_roles._is_reporting_manager", return_value=False):
            self.assertEqual(resolve_home_role(self._request(user)), "hr")

    def test_reporting_manager_is_manager(self):
        user = SimpleNamespace(
            is_superuser=False,
            is_staff=False,
            has_perm=lambda p: False,
            employee_get=object(),
        )
        with patch("base.dashboard_roles._is_reporting_manager", return_value=True):
            self.assertEqual(resolve_home_role(self._request(user)), "manager")

    def test_pure_employee(self):
        user = SimpleNamespace(
            is_superuser=False,
            is_staff=False,
            has_perm=lambda p: False,
            employee_get=None,
        )
        with patch("base.dashboard_roles._is_reporting_manager", return_value=False):
            self.assertEqual(resolve_home_role(self._request(user)), "employee")
            self.assertFalse(can_see_analytics_home("employee"))


class RoleDefaultPrefsTests(SimpleTestCase):
    def test_manager_default_visible_at_most_six(self):
        prefs = role_default_prefs("manager")
        visible = [p["id"] for p in prefs if p["visible"]]
        self.assertLessEqual(len(visible), 6)
        for demoted in DEMOTED_BY_DEFAULT:
            self.assertNotIn(demoted, visible)
        for expected in ROLE_DEFAULT_VISIBLE["manager"]:
            self.assertIn(expected, visible)

    def test_hr_includes_turnover_not_payroll(self):
        prefs = role_default_prefs("hr")
        visible = {p["id"] for p in prefs if p["visible"]}
        self.assertIn("employee_turnover", visible)
        self.assertNotIn("payroll_summary", visible)
        self.assertNotIn("gender_distribution", visible)


class PrefsMigrationTests(SimpleTestCase):
    def test_legacy_string_list_normalizes_empty(self):
        self.assertEqual(
            _normalize_dashboard_chart_prefs(["gender_chart", "employees_chart"]),
            [],
        )

    def test_modern_prefs_preserved(self):
        modern = [
            {"id": "attendance_trend", "visible": True},
            {"id": "gender_distribution", "visible": False},
        ]
        self.assertEqual(_normalize_dashboard_chart_prefs(modern), modern)

    def test_modern_prefs_guard_helper(self):
        self.assertTrue(
            _charts_use_modern_prefs([{"id": "attendance_trend", "visible": True}])
        )
        self.assertFalse(_charts_use_modern_prefs(["gender_chart"]))
        self.assertFalse(_charts_use_modern_prefs([]))


class ModernDashboardFetchInventoryTests(SimpleTestCase):
    def test_dashboard_template_avoids_legacy_module_chart_urls(self):
        from pathlib import Path

        text = Path("templates/dashboard.html").read_text(encoding="utf-8")
        banned = (
            "department-overtime-chart",
            "leave-over-period",
            "overall-leave",
            "department-leave-chart",
            "url 'recruitment-pipeline'",
            "/employee/dashboard-employee",
            "url 'dashboard-attendance'",
            "url 'dashboard-hiring'",
        )
        for token in banned:
            self.assertNotIn(token, text, msg=f"legacy fetch still present: {token}")
        for required in (
            "dashboard-employee-status",
            "dashboard-attendance-overview",
            "dashboard-department-overtime",
            "dashboard-leave-trends",
            "dashboard-leave-by-department",
            "dashboard-department-leave-days",
            "dashboard-hiring-timeline",
            "dashboard-recruitment-by-stage",
        ):
            self.assertIn(required, text)

    def test_kpi_clickthroughs_use_destination_filters(self):
        from pathlib import Path

        text = Path("templates/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("status=approved&today_leave=true&filter_applied=on", text)
        # Present Today drills into the employee directory -- the people who
        # have an attendance record today -- not into attendance-view's
        # per-record list.
        self.assertIn(
            "present_on={% now 'Y-m-d' %}&is_active=True&filter_applied=on", text
        )
        self.assertIn(
            "expected_to_check_in={% now 'Y-m-d' %}&is_active=True&filter_applied=on",
            text,
        )
        self.assertIn("is_active=True&filter_applied=on", text)
        self.assertIn("closed=false&filter_applied=on", text)
        self.assertIn("asset_request_status=Requested&filter_applied=1", text)
        self.assertIn(
            "view-reimbursement' %}?open_tab=1&status=requested&type=reimbursement&filter_applied=1",
            text,
        )
        self.assertIn(
            "shift-request-view' %}?open_tab=1&status=requested&filter_applied=1", text
        )
        self.assertIn(
            "work-type-request-view' %}?status=requested&filter_applied=1", text
        )
        self.assertIn("request-view' %}?status=requested&filter_applied=1", text)
        self.assertIn("request-attendance-view' %}?open_tab=1", text)
        self.assertNotIn("approval_status=pending", text)
        self.assertNotIn("request-attendance-view' %}?approved=false", text)
        self.assertNotIn("approved=false&canceled=false", text)
        self.assertNotIn("is_validate_request=true", text)
        self.assertNotIn("dashboard-compliance-strip", text)
        # Attendance Overview bars drill into the employee directory too,
        # carrying department + date + how they attended. The statuses are
        # indexed positionally because data.labels is gettext'd, so matching
        # on its text would break under any non-English locale.
        self.assertIn("['on_time', 'late_come', 'early_out']", text)
        self.assertIn("attendance_status: status", text)
        self.assertIn("employee_work_info__department_id: deptId", text)
        # Both former attendance destinations are gone from the dashboard.
        self.assertNotIn("late-come-early-out-view", text)
        self.assertNotIn("url 'attendance-view'", text)

        # Home no longer surfaces report pin / suggested pack UI
        for removed in (
            "standard-report-suggested-pack",
            "standard-report-dashboard-pins",
            "standard-report-pin-recommended",
            "md-std-pins",
            "md-suggested",
            "md-compliance-strip",
        ):
            self.assertNotIn(removed, text)
