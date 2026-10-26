"""
A regularised half day is half present and half absent.

The summary counted the present half and dropped the other, so the day came out
0.5 paid and 0.5 nowhere: paid days plus unpaid days fell short of the month and
the missing half was never taken off pay. A half day that came from the clock
already counted its other half as absent; this makes the regularised one agree.
"""

import datetime

from django.test import TestCase

from attendance.models import AttendanceConflictResolution
from attendance.views.summary import build_monthly_summary
from employee.models import Employee
from horilla.testkit import make_company, make_employee

WEDNESDAY = datetime.date(2026, 9, 2)


class HalfDayResolutionTests(TestCase):
    def setUp(self):
        company = make_company("Half Day Co")
        self.employee = make_employee(company=company, email="half@test.horilla")

    def _row(self, resolution):
        AttendanceConflictResolution.objects.filter(employee_id=self.employee).delete()
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=WEDNESDAY, resolution=resolution
        )
        rows, _total, _totals = build_monthly_summary(
            WEDNESDAY, WEDNESDAY, Employee.objects.filter(pk=self.employee.pk)
        )
        return rows[0]

    def test_a_half_day_is_half_present_and_half_paid_leave(self):
        row = self._row("half_present")
        self.assertEqual(row["present"], 0.5)
        self.assertEqual(row["paid_leave"], 0.5)
        self.assertEqual(row["absent"], 0)

    def test_a_full_day_has_nothing_absent(self):
        row = self._row("full_present")
        self.assertEqual(row["present"], 1.0)
        self.assertEqual(row["absent"], 0.0)


class HalfAbsentResolutionTests(HalfDayResolutionTests):
    """Half Absent: half the day absent, half present -- its own status, the same arithmetic."""

    def test_half_absent_is_half_present_and_half_absent(self):
        row = self._row("half_absent")
        self.assertEqual(row["present"], 0.5)
        self.assertEqual(row["absent"], 0.5)

    def test_it_shows_on_the_calendar_as_its_own_status_and_is_counted_apart_from_half_day(
        self,
    ):
        from attendance.views.summary import _build_calendar_context

        self._row("half_absent")
        context = _build_calendar_context(self.employee, WEDNESDAY, WEDNESDAY)
        cells = [
            c
            for m in context["months"]
            for w in m["weeks"]
            for c in w
            if c and c["status"] != "out_of_range"
        ]
        self.assertEqual([c["status"] for c in cells], ["half_absent"])
        self.assertEqual(context["cal_summary"]["half_absent"], 1)
        self.assertEqual(context["cal_summary"]["half_present"], 0)

    def test_it_is_a_choice_on_the_resolution_and_is_accepted_by_the_resolve_view(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("hr-half", is_superuser=True)
        make_employee(
            company=self.employee.employee_work_info.company_id,
            email="hr@half.test",
            user=user,
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse("attendance-monthly-summary-conflict-resolve"),
            {
                "employee_id": self.employee.pk,
                "date": WEDNESDAY.isoformat(),
                "from_date": WEDNESDAY.isoformat(),
                "to_date": WEDNESDAY.isoformat(),
                "resolution": "half_absent",
                "conflict_type": "",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        saved = AttendanceConflictResolution.objects.get(
            employee_id=self.employee, date=WEDNESDAY
        )
        self.assertEqual(saved.resolution, "half_absent")
        self.assertIn(
            "Half Absent", response.content.decode()
        )  # the calendar's legend / summary

    def test_the_day_popover_keeps_its_head_outside_the_scrolling_part(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("hr-half2", is_superuser=True)
        make_employee(
            company=self.employee.employee_work_info.company_id,
            email="hr2@half.test",
            user=user,
        )
        self.client.force_login(user)
        html = self.client.get(
            reverse("attendance-monthly-summary-conflict-resolve"),
            {
                "employee_id": self.employee.pk,
                "date": WEDNESDAY.isoformat(),
                "from_date": WEDNESDAY.isoformat(),
                "to_date": WEDNESDAY.isoformat(),
            },
            HTTP_HX_REQUEST="true",
        ).content.decode()
        self.assertNotIn(
            "msCalResolvePost('half_absent'", html
        )  # Split the day covers it
        self.assertIn("crp-shell", html)
        self.assertLess(html.index("crp-head"), html.index("crp-scroll"))
        self.assertNotIn("position:sticky", html)


class SplitDayTests(HalfDayResolutionTests):
    """A day cut in two: each half is present, absent, paid leave or unpaid leave."""

    def test_the_halves_are_parsed_and_anything_else_is_refused(self):
        from attendance.views.summary import parse_split

        self.assertEqual(parse_split("split:P+A"), ("P", "A"))
        self.assertEqual(parse_split("split:UL+PL"), ("UL", "PL"))
        for bad in ("split:P", "split:P+X", "split:P+A+A", "half_present", "", None):
            self.assertIsNone(parse_split(bad))

    def test_each_half_counts_half_a_day_in_its_own_bucket(self):
        for res, expected in {
            "split:P+A": {"present": 0.5, "absent": 0.5},
            "split:PL+A": {"paid_leave": 0.5, "absent": 0.5},
            "split:P+UL": {"present": 0.5, "unpaid_leave": 0.5},
            "split:PL+PL": {"paid_leave": 1.0},
        }.items():
            row = self._row(res)
            for bucket in ("present", "absent", "paid_leave", "unpaid_leave"):
                self.assertEqual(row[bucket], expected.get(bucket, 0.0), (res, bucket))

    def test_the_calendar_colours_the_cell_by_its_two_halves(self):
        from attendance.views.summary import _build_calendar_context

        self._row("split:PL+A")
        context = _build_calendar_context(self.employee, WEDNESDAY, WEDNESDAY)
        cell = next(
            c
            for m in context["months"]
            for w in m["weeks"]
            for c in w
            if c and c["status"] != "out_of_range"
        )
        self.assertEqual(cell["status"], "split")
        self.assertEqual(
            cell["split_style"], "--h1:#93c5fd;--h2:#fca5a5"
        )  # paid leave blue, absent red
        self.assertEqual(cell["split_label"], "Half Paid Leave + Half Absent")
        self.assertEqual(context["cal_summary"]["split"], 1)

    def test_the_resolve_view_saves_a_valid_split_and_refuses_a_bad_one(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("hr-split", is_superuser=True)
        make_employee(
            company=self.employee.employee_work_info.company_id,
            email="hr@split.test",
            user=user,
        )
        self.client.force_login(user)
        url = reverse("attendance-monthly-summary-conflict-resolve")

        def post(resolution):
            return self.client.post(
                url,
                {
                    "employee_id": self.employee.pk,
                    "date": WEDNESDAY.isoformat(),
                    "from_date": WEDNESDAY.isoformat(),
                    "to_date": WEDNESDAY.isoformat(),
                    "resolution": resolution,
                    "conflict_type": "",
                },
                HTTP_HX_REQUEST="true",
            )

        post("split:X+Q")
        self.assertFalse(
            AttendanceConflictResolution.objects.filter(
                employee_id=self.employee, date=WEDNESDAY
            ).exists()
        )
        post("split:P+UL")
        saved = AttendanceConflictResolution.objects.get(
            employee_id=self.employee, date=WEDNESDAY
        )
        self.assertEqual(saved.resolution, "split:P+UL")

    def test_the_popover_has_the_split_controls_with_the_current_halves_chosen(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        self._row("split:UL+A")
        user = make_user("hr-split2", is_superuser=True)
        make_employee(
            company=self.employee.employee_work_info.company_id,
            email="hr2@split.test",
            user=user,
        )
        self.client.force_login(user)
        html = self.client.get(
            reverse("attendance-monthly-summary-conflict-resolve"),
            {
                "employee_id": self.employee.pk,
                "date": WEDNESDAY.isoformat(),
                "from_date": WEDNESDAY.isoformat(),
                "to_date": WEDNESDAY.isoformat(),
            },
            HTTP_HX_REQUEST="true",
        ).content.decode()
        self.assertIn("msCalSaveDay(", html)
        self.assertIn('id="crp-choice"', html)
        self.assertIn('<option value="UL" data-color="#fdba74" selected>', html)
        self.assertIn('<option value="A" data-color="#fca5a5" selected>', html)
        self.assertIn(
            "Half Unpaid Leave + Half Absent", html
        )  # named in the banner/history
        self.assertIn("crp-mark-grid--3", html)  # the away buttons share a row

    def test_a_split_with_a_present_half_counts_as_a_worked_day_for_payroll_overtime(
        self,
    ):
        self._row("split:A+P")
        from django.db.models import Q

        worked = AttendanceConflictResolution.objects.filter(
            Q(resolution__in=("full_present", "half_present", "half_absent"))
            | Q(resolution__regex=r"^split:(P\+|.+\+P$)"),
            employee_id=self.employee,
        )
        self.assertEqual(worked.count(), 1)
        AttendanceConflictResolution.objects.filter(employee_id=self.employee).update(
            resolution="split:A+UL"
        )
        self.assertEqual(worked.count(), 0)


class HalfDayLeaveNaturalTests(TestCase):
    """Half-day leave with no regularisation: the rest of the day follows the attendance."""

    def setUp(self):
        company = make_company("Natural Half Co")
        self.employee = make_employee(company=company, email="natural@test.horilla")

    def _leave(self, payment="paid", breakdown="second_half", name="Half Leave"):
        from leave.models import LeaveRequest, LeaveType

        leave_type = LeaveType.objects.create(name=name, payment=payment)
        # bulk_create: saving a half-day request fires a signal that overflows a column.
        return LeaveRequest.objects.bulk_create(
            [
                LeaveRequest(
                    employee_id=self.employee,
                    leave_type_id=leave_type,
                    start_date=WEDNESDAY,
                    end_date=WEDNESDAY,
                    start_date_breakdown=breakdown,
                    end_date_breakdown=breakdown,
                    requested_days=0.5,
                    description="Test",
                    status="approved",
                )
            ]
        )[0]

    def _attend(self, worked="08:00"):
        from attendance.models import Attendance

        return Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=WEDNESDAY,
            attendance_clock_in_date=WEDNESDAY,
            attendance_clock_in=datetime.time(9, 0),
            attendance_clock_out_date=WEDNESDAY,
            attendance_clock_out=datetime.time(18, 0),
            attendance_worked_hour=worked,
            minimum_hour="08:00",
            attendance_validated=True,
        )

    def _row(self):
        rows, _total, _totals = build_monthly_summary(
            WEDNESDAY, WEDNESDAY, Employee.objects.filter(pk=self.employee.pk)
        )
        return rows[0]

    def _cell(self):
        from attendance.views.summary import _build_calendar_context

        context = _build_calendar_context(self.employee, WEDNESDAY, WEDNESDAY)
        cells = [
            c
            for m in context["months"]
            for w in m["weeks"]
            for c in w
            if c and c["status"] != "out_of_range"
        ]
        return cells[0]

    def test_half_leave_without_attendance_is_half_leave_and_half_absent(self):
        self._leave()
        row = self._row()
        self.assertEqual(
            (row["paid_leave"], row["present"], row["absent"]), (0.5, 0, 0.5)
        )

    def test_unpaid_half_leave_without_attendance_is_half_unpaid_and_half_absent(self):
        self._leave(payment="unpaid")
        row = self._row()
        self.assertEqual(
            (row["unpaid_leave"], row["present"], row["absent"]), (0.5, 0, 0.5)
        )

    def test_half_leave_with_attendance_is_half_leave_and_half_present_and_no_clash(
        self,
    ):
        self._leave()
        self._attend("08:00")
        row = self._row()
        self.assertEqual(
            (row["paid_leave"], row["present"], row["absent"]), (0.5, 0.5, 0)
        )
        self.assertEqual(row["conflict_days"], 0)

    def test_half_leave_with_hours_too_short_leaves_the_other_half_absent(self):
        self._leave()
        self._attend("01:00")
        row = self._row()
        self.assertEqual(
            (row["paid_leave"], row["present"], row["absent"]), (0.5, 0, 0.5)
        )
        self.assertEqual(row["conflict_days"], 0)

    def test_half_paid_plus_half_unpaid_fills_the_day(self):
        self._leave(breakdown="first_half", name="Paid One")
        self._leave(payment="unpaid", breakdown="second_half", name="Unpaid One")
        row = self._row()
        self.assertEqual(
            (row["paid_leave"], row["unpaid_leave"], row["absent"]), (0.5, 0.5, 0)
        )

    def test_full_leave_with_attendance_is_still_a_clash(self):
        from leave.models import LeaveRequest, LeaveType

        LeaveRequest.objects.create(
            employee_id=self.employee,
            leave_type_id=LeaveType.objects.create(name="Full", payment="paid"),
            start_date=WEDNESDAY,
            end_date=WEDNESDAY,
            requested_days=1,
            description="Test",
            status="approved",
        )
        self._attend("08:00")
        self.assertEqual(self._row()["conflict_days"], 1)

    def test_a_half_day_of_attendance_is_half_present_and_half_short_and_unpaid(self):
        self._attend("04:00")
        row = self._row()
        self.assertEqual(
            (row["present"], row["paid_leave"], row["absent"]), (0.5, 0, 0.5)
        )

    def test_calendar_colours_the_leave_half_and_the_absent_half(self):
        self._leave(breakdown="second_half")
        cell = self._cell()
        self.assertEqual(cell["status"], "split")
        # Leave is the second half, so the absent half comes first.
        self.assertEqual(cell["split_style"], "--h1:#fca5a5;--h2:#93c5fd")

    def test_calendar_shows_present_half_when_attendance_is_found(self):
        self._leave(breakdown="first_half")
        self._attend("08:00")
        cell = self._cell()
        self.assertEqual(cell["status"], "split")
        self.assertEqual(cell["split_style"], "--h1:#93c5fd;--h2:#86efac")
        self.assertFalse(cell["is_conflict"])

    def test_absent_popover_lists_the_half_absent_day(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        self._leave()
        user = make_user("hr-natural", is_superuser=True)
        make_employee(
            company=self.employee.employee_work_info.company_id,
            email="hr@natural.test",
            user=user,
        )
        self.client.force_login(user)
        response = self.client.get(
            reverse("attendance-monthly-summary-detail"),
            {
                "employee_id": self.employee.pk,
                "from_date": WEDNESDAY.isoformat(),
                "to_date": WEDNESDAY.isoformat(),
                "metric": "absent",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Wed, 02 Sep 2026")
        self.assertContains(response, ">Half<")


class CalendarStripTests(HalfDayLeaveNaturalTests):
    """The strip above the calendar counts the halves too."""

    def _strip(self):
        from attendance.views.summary import _build_calendar_context

        return _build_calendar_context(self.employee, WEDNESDAY, WEDNESDAY)[
            "cal_summary"
        ]

    def test_split_day_halves_go_to_their_own_tiles(self):
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=WEDNESDAY, resolution="split:P+UL"
        )
        strip = self._strip()
        self.assertEqual(
            (strip["unpaid_leave"], strip["paid_leave"], strip["absent"]), (0.5, 0, 0)
        )

    def test_half_absent_is_half_present_and_half_absent_and_half_day_half_paid_leave(
        self,
    ):
        for resolution, bucket in (
            ("half_absent", "absent"),
            ("half_present", "paid_leave"),
        ):
            AttendanceConflictResolution.objects.filter(
                employee_id=self.employee
            ).delete()
            AttendanceConflictResolution.objects.create(
                employee_id=self.employee, date=WEDNESDAY, resolution=resolution
            )
            strip = self._strip()
            self.assertEqual((strip["present"], strip[bucket]), (0.5, 0.5))

    def test_the_chips_add_up_to_the_days(self):
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=WEDNESDAY, resolution="split:P+PL"
        )
        strip = self._strip()
        self.assertEqual(
            strip["present"]
            + strip["paid_leave"]
            + strip["unpaid_leave"]
            + strip["absent"],
            1,
        )

    def test_half_leave_without_attendance_counts_leave_and_absent_halves(self):
        self._leave()
        strip = self._strip()
        self.assertEqual((strip["paid_leave"], strip["absent"]), (0.5, 0.5))


class PopoverStatusTests(HalfDayLeaveNaturalTests):
    """The day popover says what the day is, in the colours of its halves."""

    def _panel(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        if not getattr(self, "_hr_logged_in", False):
            user = make_user("hr-status", is_superuser=True)
            make_employee(
                company=self.employee.employee_work_info.company_id,
                email="hr@status.test",
                user=user,
            )
            self.client.force_login(user)
            self._hr_logged_in = True
        return self.client.get(
            reverse("attendance-monthly-summary-conflict-resolve"),
            {
                "employee_id": self.employee.pk,
                "date": WEDNESDAY.isoformat(),
                "from_date": WEDNESDAY.isoformat(),
                "to_date": WEDNESDAY.isoformat(),
            },
            HTTP_HX_REQUEST="true",
        ).content.decode()

    def test_half_leave_without_attendance_is_named_with_both_halves(self):
        self._leave(breakdown="second_half")
        html = self._panel()
        self.assertIn("Half Absent + Half Paid Leave", html)
        self.assertIn("linear-gradient(90deg,#fee2e2 50%,#dbeafe 50%)", html)

    def test_half_leave_with_attendance_is_not_shown_as_a_clash(self):
        self._leave(breakdown="first_half")
        self._attend("08:00")
        html = self._panel()
        self.assertIn("Day status", html)
        self.assertIn("Half Paid Leave + Half Present", html)

    def test_a_saved_split_shows_its_halves_in_colour(self):
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=WEDNESDAY, resolution="split:P+UL"
        )
        self.assertIn("linear-gradient(90deg,#d1fae5 50%,#ffedd5 50%)", self._panel())


class ShortHalfTests(HalfDayLeaveNaturalTests):
    """Half the shift or more, not all of it: half present and half short hours, as it happened."""

    def test_the_calendar_splits_the_day_into_present_and_short(self):
        self._attend("04:30")
        cell = self._cell()
        self.assertEqual(cell["status"], "split")
        self.assertEqual(cell["split_style"], "--h1:#86efac;--h2:#fca5a5")

    def test_the_strip_counts_a_present_half_and_a_short_half(self):
        from attendance.views.summary import _build_calendar_context

        self._attend("04:30")
        strip = _build_calendar_context(self.employee, WEDNESDAY, WEDNESDAY)[
            "cal_summary"
        ]
        self.assertEqual(
            (strip["present"], strip["absent"], strip["paid_leave"]), (0.5, 0.5, 0)
        )

    def test_under_half_the_shift_is_still_a_short_day(self):
        self._attend("01:00")
        self.assertEqual(self._cell()["status"], "short")

    def test_partial_hours_is_no_longer_offered_and_short_hours_are_not_changed(self):
        from django.urls import reverse

        from horilla.testkit import make_user

        user = make_user("hr-short", is_superuser=True)
        make_employee(
            company=self.employee.employee_work_info.company_id,
            email="hr@short.test",
            user=user,
        )
        self.client.force_login(user)

        def panel():
            return self.client.get(
                reverse("attendance-monthly-summary-conflict-resolve"),
                {
                    "employee_id": self.employee.pk,
                    "date": WEDNESDAY.isoformat(),
                    "from_date": WEDNESDAY.isoformat(),
                    "to_date": WEDNESDAY.isoformat(),
                },
                HTTP_HX_REQUEST="true",
            ).content.decode()

        attendance = self._attend("04:30")
        self.assertNotIn("msCalResolvePost('partial_hours'", panel())
        self.assertIn("Half Present + Half Short Hours", panel())
        attendance.delete()
        self._attend("01:00")
        self.assertNotIn("msCalResolvePost('partial_hours'", panel())

    def test_an_existing_partial_hours_resolution_still_counts_as_before(self):
        self._attend("04:00")
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=WEDNESDAY, resolution="partial_hours"
        )
        row = self._row()
        # Present in proportion to the hours worked: 4h of an 8h day.
        self.assertEqual((row["present"], row["absent"]), (0.5, 0.5))


class StatusChoiceDefaultTests(PopoverStatusTests):
    """The status choice opens on what the day actually is."""

    def test_a_worked_day_opens_on_full_present(self):
        self._attend("08:00")
        self.assertIn('data-initial="full_present"', self._panel())

    def test_a_day_with_nothing_opens_on_absent(self):
        self.assertIn('data-initial="absent"', self._panel())

    def test_a_short_day_opens_on_absent(self):
        self._attend("01:00")
        self.assertIn('data-initial="absent"', self._panel())

    def test_a_clock_half_day_opens_on_a_split_of_present_and_unpaid(self):
        self._attend("04:30")
        html = self._panel()
        self.assertIn('data-initial="split"', html)
        self.assertIn('data-initial-a="P" data-initial-b="A"', html)

    def test_half_leave_opens_on_the_split_it_makes(self):
        self._leave(breakdown="second_half")
        html = self._panel()
        self.assertIn('data-initial="split"', html)
        self.assertIn('data-initial-a="A" data-initial-b="PL"', html)

    def test_a_saved_override_wins(self):
        self._attend("08:00")
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=WEDNESDAY, resolution="paid_leave"
        )
        self.assertIn('data-initial="paid_leave"', self._panel())

    def test_an_old_half_day_opens_as_present_plus_paid_leave(self):
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=WEDNESDAY, resolution="half_present"
        )
        html = self._panel()
        self.assertIn('data-initial="split"', html)
        self.assertIn('data-initial-a="P" data-initial-b="PL"', html)

    def test_an_old_half_absent_opens_as_present_plus_absent(self):
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=WEDNESDAY, resolution="half_absent"
        )
        html = self._panel()
        self.assertIn('data-initial="split"', html)
        self.assertIn('data-initial-a="P" data-initial-b="A"', html)


class DayHistoryTests(PopoverStatusTests):
    """The popover's history lists every change to the day, in an accordion."""

    def _post(self, resolution):
        from django.urls import reverse

        return self.client.post(
            reverse("attendance-monthly-summary-conflict-resolve"),
            {
                "employee_id": self.employee.pk,
                "date": WEDNESDAY.isoformat(),
                "from_date": WEDNESDAY.isoformat(),
                "to_date": WEDNESDAY.isoformat(),
                "resolution": resolution,
                "conflict_type": "",
            },
            HTTP_HX_REQUEST="true",
        )

    def test_every_change_is_listed_newest_first(self):
        self._panel()  # logs the HR user in
        self._post("paid_leave")
        self._post("split:P+UL")
        self._post("clear")
        html = self._panel()
        self.assertIn('<details class="crp-hist">', html)
        self.assertIn("Regularized as", html)
        self.assertIn("Changed", html)
        self.assertIn("Override cleared", html)
        self.assertEqual(html.count('class="crp-hist-item"'), 3)
        # Newest first: the clear comes before the first regularisation.
        self.assertLess(html.index("Override cleared"), html.index("Regularized as"))

    def test_a_day_nobody_touched_has_no_history(self):
        self.assertNotIn('class="crp-hist"', self._panel())

    def test_the_audit_trail_covers_the_two_models(self):
        from horilla_audit.registry import DEFAULT_TRACKED_MODELS

        self.assertIn(
            ("attendance", "AttendanceConflictResolution"), DEFAULT_TRACKED_MODELS
        )
        self.assertIn(("attendance", "AttendanceDailyHours"), DEFAULT_TRACKED_MODELS)


class DayHoursSaveTests(PopoverStatusTests):
    """Hours are always editable in the popover and saved by its one Save button."""

    def _hours(self, raw):
        from django.urls import reverse

        self._panel()  # logs the HR user in
        return self.client.post(
            reverse("attendance-monthly-summary-daily-hours-edit"),
            {
                "employee_id": self.employee.pk,
                "date": WEDNESDAY.isoformat(),
                "from_date": WEDNESDAY.isoformat(),
                "to_date": WEDNESDAY.isoformat(),
                "hours": raw,
                "computed_sec": "0",
                "panel": "1",
            },
            HTTP_HX_REQUEST="true",
        )

    def test_the_panel_has_an_always_editable_hours_input_and_one_save_button(self):
        self._attend("08:00")
        html = self._panel()
        self.assertIn('id="crp-hours-input"', html)
        self.assertIn('data-initial="8:00"', html)
        self.assertIn('id="crp-save"', html)
        self.assertIn(">Save<", html)
        self.assertNotIn("msCalHoursEdit(", html)
        self.assertNotIn('id="crp-choice-go"', html)
        # The Save button sits after the scrolling body, at the foot of the panel.
        self.assertLess(html.index('class="crp-scroll"'), html.index('id="crp-save"'))

    def test_hours_up_to_24_are_saved(self):
        from attendance.models import AttendanceDailyHours

        for raw, seconds in (("8:30", 30600), ("16:00", 57600), ("24:00", 86400)):
            response = self._hours(raw)
            self.assertEqual(response.status_code, 200, raw)
            saved = AttendanceDailyHours.objects.get(
                employee_id=self.employee, date=WEDNESDAY
            )
            self.assertEqual(saved.hours_second, seconds)

    def test_more_than_24_hours_is_refused_and_nothing_is_saved(self):
        from attendance.models import AttendanceDailyHours

        for raw in ("24:01", "25:00", "30"):
            response = self._hours(raw)
            self.assertEqual(response.status_code, 400, raw)
            self.assertIn("24 hours", response.content.decode())
        self.assertFalse(
            AttendanceDailyHours.objects.filter(employee_id=self.employee).exists()
        )

    def test_unreadable_hours_are_refused(self):
        for raw in ("abc", "8:75", ""):
            self.assertEqual(self._hours(raw).status_code, 400, raw)

    def test_the_page_carries_the_15_hour_confirmation_text(self):
        html = self._panel()
        self.assertIn('data-warn-title="More than 15 hours in a day"', html)
        self.assertIn('data-over24="A day cannot have more than 24 hours."', html)

    def test_the_hours_card_carries_what_the_live_breakdown_needs(self):
        self._attend("09:00")
        html = self._panel()
        for field in ("crp-calc-reg", "crp-calc-ot", "crp-calc-total"):
            self.assertIn('id="%s" disabled' % field, html)
        self.assertIn('data-eff-min="28800"', html)
        self.assertIn('data-is-ot-day="0"', html)

    def test_the_hours_card_names_the_shift_and_its_minimum_and_explains_the_cap(self):
        self._attend("09:00")
        html = self._panel()
        self.assertIn('id="crp-min-required" disabled value="8:00"', html)
        self.assertIn("How the minimum hours count", html)
        self.assertIn("stop at the minimum required hours of the shift, 8:00", html)

    def test_a_day_without_a_record_says_where_its_minimum_comes_from(self):
        html = self._panel()
        # Nothing on that day and no shift set up: the 8h default is assumed and says so.
        self.assertIn("no shift minimum is set, so 8:00 is assumed", html)

    def test_a_short_day_counts_with_absent_in_the_strip_and_has_no_chip_of_its_own(
        self,
    ):
        from attendance.views.summary import _build_calendar_context

        self._attend("01:00")
        context = _build_calendar_context(self.employee, WEDNESDAY, WEDNESDAY)
        self.assertEqual(context["cal_summary"]["absent"], 1)
        self.assertNotIn("short", context["cal_summary"])

    def test_the_absent_popover_lists_short_hours_days_with_what_was_worked(self):
        from django.urls import reverse

        self._attend("01:00")
        self._panel()  # logs the HR user in
        response = self.client.get(
            reverse("attendance-monthly-summary-detail"),
            {
                "employee_id": self.employee.pk,
                "from_date": WEDNESDAY.isoformat(),
                "to_date": WEDNESDAY.isoformat(),
                "metric": "absent",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Wed, 02 Sep 2026")
        self.assertContains(response, "Short hours 1h 00m / 8h 00m")

    def test_a_half_day_of_hours_is_not_listed_as_a_short_day(self):
        from django.urls import reverse

        self._attend("06:00")
        self._panel()
        response = self.client.get(
            reverse("attendance-monthly-summary-detail"),
            {
                "employee_id": self.employee.pk,
                "from_date": WEDNESDAY.isoformat(),
                "to_date": WEDNESDAY.isoformat(),
                "metric": "absent",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertNotContains(response, "Short hours")


class ChipHoverGroupTests(HalfDayLeaveNaturalTests):
    """Each day knows which summary chips it counts in, for the hover highlight."""

    def test_groups_for_each_kind_of_day(self):
        from attendance.views.summary import cell_groups

        self.assertEqual(cell_groups("present", None, None), "present")
        self.assertEqual(cell_groups("absent", None, None), "absent")
        self.assertEqual(cell_groups("short", None, None), "absent")
        self.assertEqual(cell_groups("paid_leave", None, None), "paid_leave")
        self.assertEqual(cell_groups("unpaid_leave", None, None), "unpaid_leave")
        self.assertEqual(cell_groups("week_off", None, None), "week_off")
        self.assertEqual(cell_groups("holiday", None, None), "holiday")
        self.assertEqual(cell_groups("future", None, None), "")

    def test_a_half_day_and_a_split_belong_to_both_of_their_chips(self):
        from attendance.views.summary import cell_groups

        self.assertEqual(cell_groups("half_present", None, None), "paid_leave present")
        self.assertEqual(cell_groups("half_absent", None, None), "absent present")
        self.assertEqual(
            cell_groups("split", ("P", "UL"), None), "present unpaid_leave"
        )
        self.assertEqual(cell_groups("split", ("P", "SH"), None), "absent present")
        self.assertIn("conflict", cell_groups("present", None, "paid_leave"))

    def test_the_calendar_carries_the_groups_and_the_chips_name_theirs(self):
        from django.template.loader import render_to_string

        from attendance.views.summary import _build_calendar_context

        self._leave(breakdown="second_half")
        context = _build_calendar_context(self.employee, WEDNESDAY, WEDNESDAY)
        html = render_to_string(
            "attendance/monthly_summary/calendar_modal.html", context
        )
        self.assertIn('data-groups="absent paid_leave"', html)
        for group in (
            "present",
            "absent",
            "paid_leave",
            "unpaid_leave",
            "week_off",
            "holiday",
        ):
            self.assertIn('data-group="%s"' % group, html)

    def test_two_half_days_carry_their_halves_in_drawing_order(self):
        from attendance.views.summary import cell_halves_data

        self.assertEqual(
            cell_halves_data("split", ("P", "PL")), "present|#86efac,paid_leave|#93c5fd"
        )
        self.assertEqual(
            cell_halves_data("split", ("A", "PL")), "absent|#fca5a5,paid_leave|#93c5fd"
        )
        self.assertEqual(
            cell_halves_data("half_present", None), "present|#86efac,paid_leave|#93c5fd"
        )
        self.assertEqual(
            cell_halves_data("half_absent", None), "absent|#fca5a5,present|#86efac"
        )
        self.assertEqual(cell_halves_data("present", None), "")
