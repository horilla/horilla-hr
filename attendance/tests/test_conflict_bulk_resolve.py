"""
Bulk-regularising a Ctrl/Shift-click day selection from the calendar popover.

A single-day decision already existed (attendance_monthly_summary_conflict_resolve).
This is its multi-day sibling: apply one status to every date in the
selection at once, instead of clicking through them one at a time.
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from attendance.models import Attendance, AttendanceConflictResolution
from horilla.testkit import make_company, make_employee, make_user
from horilla.testkit.factories import make_attendance

FROM_DATE = datetime.date(2026, 9, 1)
TO_DATE = datetime.date(2026, 9, 30)

DATES = [
    datetime.date(2026, 9, 3),
    datetime.date(2026, 9, 4),
    datetime.date(2026, 9, 7),
]


class Fixture(TestCase):
    def setUp(self):
        self.user = make_user("bulkadmin", is_superuser=True)
        self.company = make_company("Bulk Co")
        make_employee(
            company=self.company, email="bulkadmin@test.horilla", user=self.user
        )
        self.client.force_login(self.user)

        self.employee = make_employee(
            company=self.company, email="bulkworker@test.horilla"
        )

    def _get(self, dates=DATES):
        params = [
            ("employee_id", self.employee.pk),
            ("from_date", FROM_DATE),
            ("to_date", TO_DATE),
        ]
        params += [("dates", d) for d in dates]
        query = "&".join(f"{k}={v}" for k, v in params)
        return self.client.get(
            reverse("attendance-monthly-summary-conflict-bulk-resolve") + "?" + query,
            HTTP_HX_REQUEST="true",
        )

    def _post(self, resolution, dates=DATES):
        data = {
            "employee_id": self.employee.pk,
            "from_date": FROM_DATE,
            "to_date": TO_DATE,
            "resolution": resolution,
            "dates": dates,
        }
        return self.client.post(
            reverse("attendance-monthly-summary-conflict-bulk-resolve"),
            data,
            HTTP_HX_REQUEST="true",
        )


class GetPanelTests(Fixture):
    def test_it_renders_the_count_and_every_selected_date(self):
        response = self._get()
        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("3", body)
        for d in DATES:
            self.assertIn(d.strftime("%d %b"), body)

    def test_no_dates_is_handled_without_a_server_error(self):
        response = self._get(dates=[])
        self.assertEqual(response.status_code, 200)
        self.assertIn("No days selected", response.content.decode())

    def test_a_missing_employee_is_handled_without_a_server_error(self):
        response = self.client.get(
            reverse("attendance-monthly-summary-conflict-bulk-resolve")
            + f"?employee_id=999999&from_date={FROM_DATE}&to_date={TO_DATE}&dates={DATES[0]}",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("not found", response.content.decode().lower())


class PostResolveTests(Fixture):
    def test_it_applies_the_resolution_to_every_selected_date(self):
        response = self._post("paid_leave")
        self.assertEqual(response.status_code, 200)

        saved = set(
            AttendanceConflictResolution.objects.filter(
                employee_id=self.employee, date__in=DATES
            ).values_list("date", "resolution")
        )
        self.assertEqual(saved, {(d, "paid_leave") for d in DATES})

    def test_it_reuses_the_single_day_bucket_so_the_calendar_recomputes_consistently(
        self,
    ):
        # Same resolution string, same AttendanceConflictResolution row shape
        # as the single-day path — build_monthly_summary's _RES_BUCKET lookup
        # doesn't need to know this came from a bulk action.
        self._post("absent")
        row = AttendanceConflictResolution.objects.get(
            employee_id=self.employee, date=DATES[0]
        )
        self.assertEqual(row.resolution, "absent")
        self.assertEqual(row.conflict_type, "")

    def test_approve_ot_flips_the_flag_on_every_selected_date_with_attendance(self):
        for d in DATES:
            make_attendance(
                employee=self.employee, attendance_date=d, overtime_second=3600
            )
        Attendance.objects.filter(
            employee_id=self.employee, attendance_date__in=DATES
        ).update(attendance_overtime_approve=False)

        self._post("approve_ot")

        approved = set(
            Attendance.objects.filter(
                employee_id=self.employee, attendance_date__in=DATES
            ).values_list("attendance_date", "attendance_overtime_approve")
        )
        self.assertEqual(approved, {(d, True) for d in DATES})

    def test_an_invalid_resolution_is_silently_ignored_rather_than_applied(self):
        response = self._post("not-a-real-status")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            AttendanceConflictResolution.objects.filter(
                employee_id=self.employee, date__in=DATES
            ).exists()
        )

    def test_partial_hours_is_rejected_since_it_has_no_per_day_target(self):
        # Unlike the single-day resolve view, bulk deliberately doesn't expose
        # partial_hours — a single target duration isn't meaningful applied
        # identically across a heterogeneous multi-day selection.
        response = self._post("partial_hours")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            AttendanceConflictResolution.objects.filter(
                employee_id=self.employee, date__in=DATES
            ).exists()
        )

    def test_it_rerenders_the_full_calendar_so_counts_refresh_immediately(self):
        response = self._post("holiday")
        self.assertIn('id="cal-data"', response.content.decode())
