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
        self.assertEqual(response.context["dates"], DATES)  # all three, in order
        for d in DATES:
            self.assertIn(d.strftime("%d %b"), body)

    def test_the_status_is_one_dropdown_with_a_split_day_and_a_save_button(self):
        body = self._get().content.decode()
        self.assertIn('id="crpb-choice"', body)
        for value in (
            "full_present",
            "absent",
            "paid_leave",
            "unpaid_leave",
            "holiday",
            "week_off",
            "split",
        ):
            self.assertIn(f'value="{value}"', body)
        # A split replaces the two half-day buttons, and brings its two halves.
        self.assertNotIn('value="half_present"', body)
        self.assertNotIn('value="half_absent"', body)
        self.assertIn('id="crp-split-a"', body)
        self.assertIn('id="crp-split-b"', body)
        self.assertIn("msCalBulkSave()", body)
        self.assertNotIn("crpb-mark-btn", body)

    def _with_overtime(self, dates=DATES):
        for d in dates:
            make_attendance(
                employee=self.employee, attendance_date=d, overtime_second=3600
            )
        Attendance.objects.filter(
            employee_id=self.employee, attendance_date__in=dates
        ).update(attendance_overtime_approve=False)

    def test_approve_overtime_is_a_button_beside_save_when_a_day_has_overtime(self):
        self._with_overtime()
        body = self._get().content.decode()
        self.assertIn('id="crpb-approve-ot"', body)
        self.assertIn("msCalBulkApproveOt(this)", body)
        self.assertIn("Approve Overtime", body)
        self.assertNotIn('<option value="approve_ot"', body)

    def test_the_approve_button_is_left_out_when_no_selected_day_has_overtime(self):
        make_attendance(
            employee=self.employee, attendance_date=DATES[0], overtime_second=0
        )
        body = self._get().content.decode()
        self.assertNotIn('id="crpb-approve-ot"', body)

    def test_the_approve_button_is_left_out_once_the_overtime_is_approved(self):
        self._with_overtime()
        Attendance.objects.filter(employee_id=self.employee).update(
            attendance_overtime_approve=True
        )
        self.assertNotIn('id="crpb-approve-ot"', self._get().content.decode())

    def test_save_starts_off_until_a_status_is_chosen(self):
        body = self._get().content.decode()
        self.assertIn('id="crpb-save" disabled', body)
        self.assertIn('<option value="" data-color="#e5e7eb" selected>', body)

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

    def test_a_split_day_is_applied_to_every_selected_date(self):
        response = self._post("split:P+A")
        self.assertEqual(response.status_code, 200)

        saved = set(
            AttendanceConflictResolution.objects.filter(
                employee_id=self.employee, date__in=DATES
            ).values_list("date", "resolution")
        )
        self.assertEqual(saved, {(d, "split:P+A") for d in DATES})

    def test_a_bad_split_is_refused_and_nothing_is_saved(self):
        self._post("split:P+Z")
        self.assertFalse(
            AttendanceConflictResolution.objects.filter(
                employee_id=self.employee
            ).exists()
        )

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

    def test_a_quiet_approval_answers_with_json_and_does_not_redraw_the_calendar(self):
        for d in DATES:
            make_attendance(
                employee=self.employee, attendance_date=d, overtime_second=3600
            )
        Attendance.objects.filter(employee_id=self.employee).update(
            attendance_overtime_approve=False
        )

        response = self.client.post(
            reverse("attendance-monthly-summary-conflict-bulk-resolve"),
            {
                "employee_id": self.employee.pk,
                "from_date": FROM_DATE,
                "to_date": TO_DATE,
                "resolution": "approve_ot",
                "quiet": "1",
                "dates": DATES,
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"approved": len(DATES)})
        self.assertTrue(
            Attendance.objects.filter(
                employee_id=self.employee, attendance_overtime_approve=True
            ).count()
            == len(DATES)
        )

    def test_approving_overtime_makes_no_resolution_row(self):
        for d in DATES:
            make_attendance(
                employee=self.employee, attendance_date=d, overtime_second=3600
            )
        self._post("approve_ot")
        self.assertFalse(
            AttendanceConflictResolution.objects.filter(
                employee_id=self.employee
            ).exists()
        )

    def test_an_empty_resolution_only_redraws_the_calendar(self):
        response = self._post("")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            AttendanceConflictResolution.objects.filter(
                employee_id=self.employee
            ).exists()
        )

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
