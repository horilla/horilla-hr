"""
Half-day leave and attendance: when is it a conflict, and why.

A half-day leave leaves the other half of the day to work. Attendance clashes with it when it
reaches into the half on leave beyond a default grace (coming early on a first-half leave,
leaving late on a second-half one), or when the whole minimum hours were worked anyway.
"""

import datetime
from datetime import time

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from attendance.models import Attendance, AttendanceConflictResolution
from attendance.views.summary import (
    HALF_LEAVE_GRACE_SECS,
    _build_calendar_context,
    build_monthly_summary,
    half_leave_conflict,
)
from employee.models import Employee
from horilla.testkit import make_company, make_employee, make_user

DAY = datetime.date(2026, 9, 2)  # a Wednesday
SHIFT = (time(9, 0), time(18, 0))  # the halves split at 13:30
EIGHT_HOURS = 8 * 3600
SHIFT_TIMES = SHIFT


class RuleMatrixTests(SimpleTestCase):
    """The rule on its own, for a 09:00-18:00 shift (halves split at 13:30, 30 min grace)."""

    def clash(self, lead, cin, cout, worked=0, minimum=EIGHT_HOURS, shift=SHIFT):
        return half_leave_conflict(lead, cin, cout, shift, worked, minimum)

    def test_the_default_grace_is_thirty_minutes(self):
        self.assertEqual(HALF_LEAVE_GRACE_SECS, 30 * 60)

    # -- second half on leave -------------------------------------------------------------
    def test_second_leave_morning_only_is_fine(self):
        self.assertEqual(self.clash("second", time(9, 0), time(13, 30), 4 * 3600), "")
        self.assertEqual(self.clash("second", time(9, 0), time(12, 0), 3 * 3600), "")

    def test_second_leave_leaving_a_little_late_is_within_grace(self):
        self.assertEqual(self.clash("second", time(9, 0), time(13, 55), 4 * 3600), "")
        self.assertEqual(
            self.clash("second", time(9, 0), time(14, 0), 4 * 3600), ""
        )  # exactly the grace

    def test_second_leave_leaving_later_than_the_grace_clashes(self):
        why = self.clash("second", time(9, 0), time(14, 10), 5 * 3600)
        self.assertIn("Worked until 14:10", why)
        self.assertIn("starts at 13:30", why)
        self.assertIn("30 min late is allowed", why)

    def test_second_leave_afternoon_punch_clashes(self):
        self.assertTrue(self.clash("second", time(14, 0), time(18, 0), 4 * 3600))

    def test_second_leave_whole_day_punch_clashes(self):
        self.assertTrue(self.clash("second", time(9, 0), time(18, 0), 8 * 3600))

    # -- first half on leave --------------------------------------------------------------
    def test_first_leave_afternoon_only_is_fine(self):
        self.assertEqual(self.clash("first", time(13, 30), time(18, 0), 4 * 3600), "")
        self.assertEqual(self.clash("first", time(14, 0), time(18, 0), 4 * 3600), "")

    def test_first_leave_coming_a_little_early_is_within_grace(self):
        self.assertEqual(self.clash("first", time(13, 10), time(18, 0), 4 * 3600), "")
        self.assertEqual(
            self.clash("first", time(13, 0), time(18, 0), 4 * 3600), ""
        )  # exactly the grace

    def test_first_leave_coming_earlier_than_the_grace_clashes(self):
        why = self.clash("first", time(12, 50), time(18, 0), 5 * 3600)
        self.assertIn("Clocked in at 12:50", why)
        self.assertIn("runs until 13:30", why)
        self.assertIn("30 min early is allowed", why)

    def test_first_leave_morning_punch_clashes(self):
        self.assertTrue(self.clash("first", time(9, 0), time(12, 0), 3 * 3600))

    def test_first_leave_whole_day_punch_clashes(self):
        self.assertTrue(self.clash("first", time(9, 0), time(18, 0), 8 * 3600))

    # -- full minimum hours ---------------------------------------------------------------
    def test_working_the_full_minimum_hours_clashes_even_inside_the_other_half(self):
        why = self.clash("second", time(5, 0), time(13, 0), EIGHT_HOURS)
        self.assertIn("full 8h 00m", why)
        self.assertIn("only half was needed", why)

    def test_one_second_short_of_the_minimum_is_not_that_clash(self):
        self.assertEqual(
            self.clash("second", time(5, 0), time(13, 0), EIGHT_HOURS - 1), ""
        )

    def test_no_minimum_configured_never_triggers_the_hours_rule(self):
        self.assertEqual(
            self.clash("second", time(5, 0), time(13, 0), 9 * 3600, minimum=0), ""
        )

    # -- punches without a clock-out, no shift times, night shifts ---------------------------
    def test_an_open_punch_counts_at_its_clock_in(self):
        self.assertEqual(self.clash("second", time(9, 0), None), "")
        self.assertTrue(self.clash("second", time(15, 0), None))
        self.assertEqual(self.clash("first", time(15, 0), None), "")
        self.assertTrue(self.clash("first", time(9, 0), None))

    def test_no_attendance_is_never_a_clash(self):
        self.assertEqual(self.clash("second", None, None), "")

    def test_a_shift_without_times_splits_at_one_pm(self):
        self.assertTrue(
            half_leave_conflict("second", time(9, 0), time(13, 40), None, 0, 0)
        )
        self.assertEqual(
            half_leave_conflict("second", time(9, 0), time(13, 20), None, 0, 0), ""
        )
        self.assertTrue(
            half_leave_conflict("first", time(12, 20), time(18, 0), None, 0, 0)
        )
        self.assertEqual(
            half_leave_conflict("first", time(12, 40), time(18, 0), None, 0, 0), ""
        )

    def test_a_night_shift_is_judged_on_hours_alone(self):
        night = (time(22, 0), time(6, 0))
        self.assertEqual(
            half_leave_conflict(
                "second", time(22, 0), time(2, 0), night, 4 * 3600, EIGHT_HOURS
            ),
            "",
        )
        self.assertTrue(
            half_leave_conflict(
                "second", time(22, 0), time(6, 0), night, EIGHT_HOURS, EIGHT_HOURS
            )
        )

    def test_a_wider_grace_can_be_passed(self):
        self.assertTrue(
            half_leave_conflict(
                "second", time(9, 0), time(14, 10), SHIFT, 0, 0, grace=10 * 60
            )
        )
        self.assertEqual(
            half_leave_conflict(
                "second", time(9, 0), time(14, 10), SHIFT, 0, 0, grace=45 * 60
            ),
            "",
        )


class DayFixture(TestCase):
    def setUp(self):
        company = make_company("Half Clash Co")
        self.employee = make_employee(company=company, email="halfclash@test.horilla")

    def leave(self, breakdown="second_half", payment="paid"):
        from leave.models import LeaveRequest, LeaveType

        leave_type, _ = LeaveType.objects.get_or_create(
            name=f"Half {payment} {breakdown}", defaults={"payment": payment}
        )
        # bulk_create: saving a half-day request fires a signal that overflows a column.
        LeaveRequest.objects.bulk_create(
            [
                LeaveRequest(
                    employee_id=self.employee,
                    leave_type_id=leave_type,
                    start_date=DAY,
                    end_date=DAY,
                    start_date_breakdown=breakdown,
                    end_date_breakdown=breakdown,
                    requested_days=0.5,
                    description="Test",
                    status="approved",
                )
            ]
        )

    def punch(self, clock_in, clock_out, worked="04:00"):
        return Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=DAY,
            attendance_clock_in_date=DAY,
            attendance_clock_in=clock_in,
            attendance_clock_out_date=DAY if clock_out else None,
            attendance_clock_out=clock_out,
            attendance_worked_hour=worked,
            minimum_hour="08:00",
            attendance_validated=True,
        )

    def with_shift(self, start, end):
        from base.models import EmployeeShift, EmployeeShiftDay, EmployeeShiftSchedule

        shift = EmployeeShift.objects.create(
            employee_shift=f"Shift {start:%H%M}-{end:%H%M}"
        )
        day, _ = EmployeeShiftDay.objects.get_or_create(day="wednesday")
        EmployeeShiftSchedule.objects.create(
            day=day,
            shift_id=shift,
            minimum_working_hour="08:00",
            start_time=start,
            end_time=end,
        )
        self.employee.employee_work_info.shift_id = shift
        self.employee.employee_work_info.save()
        return shift

    def cell(self):
        context = _build_calendar_context(self.employee, DAY, DAY)
        return [
            c
            for m in context["months"]
            for w in m["weeks"]
            for c in w
            if c and c["status"] != "out_of_range"
        ][0]

    def conflicts_in_table(self):
        rows, _t, _x = build_monthly_summary(
            DAY, DAY, Employee.objects.filter(pk=self.employee.pk)
        )
        return rows[0]["conflict_days"]


class DayScenarioTests(DayFixture):
    """Calendar cell and table count agree, for each scenario. No shift is set up here, so the
    halves split at 13:00."""

    SCENARIOS = [
        # leave, clock in, clock out, worked, conflict?
        ("second_half", time(14, 0), time(18, 0), "04:00", True),
        ("second_half", time(9, 0), time(12, 30), "03:30", False),
        (
            "second_half",
            time(9, 0),
            time(13, 20),
            "04:20",
            False,
        ),  # leaving late, within grace
        ("second_half", time(9, 0), time(13, 40), "04:40", True),  # past the grace
        (
            "first_half",
            time(12, 40),
            time(18, 0),
            "05:20",
            False,
        ),  # coming early, within grace
        ("first_half", time(12, 20), time(18, 0), "05:40", True),  # past the grace
        ("first_half", time(13, 0), time(18, 0), "05:00", False),
        ("first_half", time(9, 0), time(12, 0), "03:00", True),
        (
            "second_half",
            time(5, 0),
            time(12, 59),
            "08:00",
            True,
        ),  # full minimum hours worked
        ("second_half", time(9, 0), None, "00:00", False),  # open punch in the morning
        (
            "second_half",
            time(15, 0),
            None,
            "00:00",
            True,
        ),  # open punch in the leave half
    ]

    def test_each_scenario(self):
        for i, (breakdown, cin, cout, worked, expected) in enumerate(self.SCENARIOS):
            with self.subTest(leave=breakdown, cin=cin, cout=cout, worked=worked):
                # A fresh employee each time: nothing to delete, nothing carried over.
                self.employee = make_employee(
                    company=self.employee.get_company(),
                    email=f"scenario{i}@test.horilla",
                )
                self.leave(breakdown)
                self.punch(cin, cout, worked)
                cell = self.cell()
                self.assertEqual(bool(cell["is_conflict"]), expected)
                self.assertEqual(self.conflicts_in_table(), 1 if expected else 0)
                self.assertEqual(bool(cell["conflict_reason"]), expected)

    def test_an_unpaid_half_leave_clashes_as_unpaid_leave(self):
        self.leave("second_half", payment="unpaid")
        self.punch(time(14, 0), time(18, 0))
        self.assertEqual(self.cell()["conflict_with"], "unpaid_leave")

    def test_no_attendance_is_no_conflict(self):
        self.leave()
        self.assertFalse(self.cell()["is_conflict"])
        self.assertEqual(self.conflicts_in_table(), 0)

    def test_full_day_leave_with_attendance_is_still_a_conflict(self):
        from leave.models import LeaveRequest, LeaveType

        leave_type = LeaveType.objects.create(name="Full", payment="paid")
        LeaveRequest.objects.bulk_create(
            [
                LeaveRequest(
                    employee_id=self.employee,
                    leave_type_id=leave_type,
                    start_date=DAY,
                    end_date=DAY,
                    start_date_breakdown="full_day",
                    end_date_breakdown="full_day",
                    requested_days=1,
                    description="Test",
                    status="approved",
                )
            ]
        )
        self.punch(time(9, 0), time(12, 0))
        self.assertTrue(self.cell()["is_conflict"])

    def test_the_clash_is_counted_once_in_the_strip(self):
        self.leave()
        self.punch(time(14, 0), time(18, 0))
        context = _build_calendar_context(self.employee, DAY, DAY)
        self.assertEqual(context["cal_summary"]["conflict"], 1)

    def test_resolving_clears_the_conflict_whichever_way_it_is_resolved(self):
        self.leave()
        self.punch(time(14, 0), time(18, 0))
        for resolution in ("attendance", "leave", "full_present", "paid_leave"):
            with self.subTest(resolution=resolution):
                AttendanceConflictResolution.objects.filter(
                    employee_id=self.employee
                ).delete()
                AttendanceConflictResolution.objects.create(
                    employee_id=self.employee, date=DAY, resolution=resolution
                )
                self.assertFalse(self.cell()["is_conflict"])


class ExplanationTests(DayFixture):
    """The reason is shown on the day: its tooltip, the resolve panel and the conflicts popover."""

    def setUp(self):
        super().setUp()
        self.user = make_user("clash-admin", is_superuser=True)
        make_employee(
            company=self.employee.get_company(),
            email="clash-admin@test.horilla",
            user=self.user,
        )
        self.client.force_login(self.user)
        self.with_shift(time(9, 0), time(18, 0))
        self.leave()
        self.punch(time(14, 0), time(18, 0))
        self.params = {
            "employee_id": self.employee.pk,
            "date": DAY.isoformat(),
            "from_date": DAY.isoformat(),
            "to_date": DAY.isoformat(),
        }

    def test_the_cell_carries_the_reason_in_its_tooltip(self):
        from django.template.loader import render_to_string

        html = render_to_string(
            "attendance/monthly_summary/calendar_modal.html",
            _build_calendar_context(self.employee, DAY, DAY),
        )
        self.assertIn("Second-half leave", html)
        self.assertIn("Worked until 18:00", html)

    def test_the_resolve_panel_explains_the_clash(self):
        response = self.client.get(
            reverse("attendance-monthly-summary-conflict-resolve"),
            self.params,
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Second-half leave (13:30 – 18:00)")
        self.assertContains(response, "You were at work")
        self.assertContains(response, "14:00 – 18:00")
        self.assertContains(
            response, "Worked until 18:00, but the leave half starts at 13:30"
        )

    def test_the_conflicts_popover_lists_the_day_with_its_reason(self):
        response = self.client.get(
            reverse("attendance-monthly-summary-detail"),
            {**self.params, "metric": "conflict"},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Second-half leave")
        self.assertContains(response, "Worked until 18:00")

    def test_the_label_names_the_half_and_when_it_runs(self):
        from attendance.views.summary import half_leave_label

        self.assertEqual(
            half_leave_label("second", SHIFT_TIMES), "Second-half leave (13:30 – 18:00)"
        )
        self.assertEqual(
            half_leave_label("first", SHIFT_TIMES), "First-half leave (09:00 – 13:30)"
        )
        self.assertEqual(half_leave_label("second"), "Second-half leave (after 13:00)")

    def test_a_day_without_a_clash_has_no_explanation(self):
        Attendance.objects.filter(employee_id=self.employee).update(
            attendance_clock_in=time(9, 0), attendance_clock_out=time(12, 0)
        )
        response = self.client.get(
            reverse("attendance-monthly-summary-conflict-resolve"),
            self.params,
            HTTP_HX_REQUEST="true",
        )
        self.assertNotContains(response, "You were at work")


class ShiftBasisTests(DayFixture):
    """The two halves follow the employee's shift hours, not a fixed time of day."""

    def test_a_late_shift_moves_where_the_day_is_cut(self):
        # 10:00-19:00: the halves split at 14:30. A first-half leave and a 13:50 clock-in:
        # fine on a 13:00 split, but 40 minutes before this shift's half, past the 30 min allowed.
        self.with_shift(time(10, 0), time(19, 0))
        self.leave("first_half")
        self.punch(time(13, 50), time(19, 0), "05:10")
        cell = self.cell()
        self.assertTrue(cell["is_conflict"])
        self.assertIn("First-half leave (10:00 – 14:30)", cell["conflict_reason"])
        self.assertIn("runs until 14:30", cell["conflict_reason"])

    def test_without_that_shift_the_same_punch_is_fine(self):
        self.leave("first_half")
        self.punch(time(13, 50), time(19, 0), "05:10")
        self.assertFalse(self.cell()["is_conflict"])

    def test_the_shift_a_day_was_worked_on_wins_over_the_current_one(self):
        # Worked on the 10:00-19:00 shift while the employee's own is 09:00-18:00.
        late = self.with_shift(time(10, 0), time(19, 0))
        self.with_shift(time(9, 0), time(18, 0))
        self.leave("first_half")
        attendance = self.punch(time(13, 50), time(19, 0), "05:10")
        Attendance.objects.filter(pk=attendance.pk).update(shift_id=late)
        self.assertTrue(self.cell()["is_conflict"])
        self.assertEqual(self.conflicts_in_table(), 1)

    def test_the_panel_shows_the_shift_hours_and_where_it_splits(self):
        from django.urls import reverse

        user = make_user("shift-admin", is_superuser=True)
        make_employee(
            company=self.employee.get_company(),
            email="shift-admin@test.horilla",
            user=user,
        )
        self.client.force_login(user)
        self.with_shift(time(9, 0), time(18, 0))
        self.leave("second_half")
        self.punch(time(14, 0), time(18, 0))
        response = self.client.get(
            reverse("attendance-monthly-summary-conflict-resolve"),
            {
                "employee_id": self.employee.pk,
                "date": DAY.isoformat(),
                "from_date": DAY.isoformat(),
                "to_date": DAY.isoformat(),
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "09:00 – 18:00, halves split at 13:30")

    def test_shift_hours_text(self):
        from attendance.views.summary import shift_hours_text

        self.assertEqual(
            shift_hours_text(SHIFT), "09:00 – 18:00, halves split at 13:30"
        )
        self.assertEqual(
            shift_hours_text(None), "No shift times set, halves split at 13:00"
        )
