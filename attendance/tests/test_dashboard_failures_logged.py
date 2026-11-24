"""
A chart whose query fails stays empty rather than breaking the dashboard, but
an empty chart reads as "nothing happened": the logged error is the only
trace of the failure.
"""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from attendance.models import Attendance
from horilla.testkit.factories import make_company, make_employee, make_user

FAILED = RuntimeError("query failed")


class TestDashboardFailuresAreLogged(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = make_user("boss", is_superuser=True)
        make_employee(
            company=make_company("Logging Ltd"), email="boss@log.test", user=cls.boss
        )

    def assert_logged(self, url_name, message, params=None):
        self.client.force_login(self.boss)
        with self.assertLogs("attendance.dashboard", level="ERROR") as logs:
            response = self.client.get(reverse(url_name), params or {})
        self.assertEqual(response.status_code, 200)
        self.assertIn(message, logs.output[0])
        self.assertIn("RuntimeError: query failed", logs.output[0])

    def test_pending_overtime(self):
        real_filter = Attendance.objects.filter

        def fail_on_overtime(*args, **kwargs):
            if "overtime_second__gt" in kwargs:
                raise FAILED
            return real_filter(*args, **kwargs)

        with patch.object(Attendance.objects, "filter", side_effect=fail_on_overtime):
            self.assert_logged(
                "attendance-dashboard-kpi", "Pending overtime query failed"
            )

    def test_late_and_early(self):
        with patch("attendance.models.AttendanceLateComeEarlyOut.objects") as manager:
            manager.filter.side_effect = FAILED
            self.assert_logged(
                "attendance-dashboard-late-early", "Late and early query failed"
            )

    def test_hours_distribution(self):
        with patch("attendance.models.AttendanceOverTime.objects") as manager:
            manager.filter.side_effect = FAILED
            self.assert_logged(
                "attendance-dashboard-hours", "Hours distribution query failed"
            )

    def test_attendance_and_absence_percentage(self):
        with patch("attendance.dashboard._group_attendance_stats", side_effect=FAILED):
            for url_name in (
                "attendance-dashboard-percentage",
                "attendance-dashboard-absence-percentage",
            ):
                with self.subTest(url_name):
                    self.assert_logged(
                        url_name,
                        "Attendance rate by department query failed",
                        {"dimension": "department"},
                    )

    def test_average_working_hours(self):
        with patch("attendance.models.Attendance.objects") as manager:
            manager.filter.side_effect = FAILED
            self.assert_logged(
                "attendance-dashboard-avg-hours", "Average working hours query failed"
            )

    def test_top_absentees(self):
        with patch(
            "attendance.dashboard._expected_attendance_days", side_effect=FAILED
        ):
            self.assert_logged(
                "attendance-dashboard-absentees", "Top absentees query failed"
            )

    def test_overview(self):
        with patch("attendance.dashboard._scoped_employees", side_effect=FAILED):
            self.assert_logged(
                "attendance-dashboard-overview", "Attendance overview query failed"
            )
