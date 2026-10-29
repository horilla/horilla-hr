"""
The last regularisation of a day is the one shown (summary, calendar, work records), and a leave
whose type excludes holidays / week-offs does not take those days as leave.
"""

import datetime
from datetime import time
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from attendance.methods.leave_days import excluded_dates
from attendance.methods.work_record_sync import record_spec
from attendance.models import Attendance, AttendanceConflictResolution, WorkRecords
from attendance.views.summary import _build_calendar_context, build_monthly_summary
from employee.models import Employee
from horilla.testkit import make_company, make_employee

D = datetime.date
SEP_START, SEP_END = D(2026, 9, 1), D(2026, 9, 30)
SATURDAYS = [D(2026, 9, 5), D(2026, 9, 12), D(2026, 9, 19), D(2026, 9, 26)]
SUNDAYS = [D(2026, 9, 6), D(2026, 9, 13), D(2026, 9, 20), D(2026, 9, 27)]


class Base(TestCase):
    def setUp(self):
        company = make_company("Regularise Co")
        self.employee = make_employee(company=company, email="regularise@test.horilla")

    def punch(self, day, clock_in=time(9, 0), clock_out=time(18, 0), worked="09:00"):
        return Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=day,
            attendance_clock_in_date=day,
            attendance_clock_in=clock_in,
            attendance_clock_out_date=day,
            attendance_clock_out=clock_out,
            attendance_worked_hour=worked,
            minimum_hour="08:00",
            attendance_validated=True,
        )

    def regularise(self, day, resolution):
        row, _ = AttendanceConflictResolution._base_manager.update_or_create(
            employee_id=self.employee,
            date=day,
            defaults={"resolution": resolution},
        )
        return row

    def record(self, day):
        return WorkRecords._base_manager.filter(
            employee_id=self.employee, date=day
        ).first()


class RecordSpecTests(SimpleTestCase):
    def test_each_resolution_maps_to_what_the_work_record_draws(self):
        cases = {
            "full_present": ("FDP", 1.0, False),
            "attendance": ("FDP", 1.0, False),
            "half_present": ("HDP", 0.5, False),
            "half_absent": ("HDP", 0.5, False),
            "partial_hours": ("HDP", 0.5, False),
            "absent": ("DFT", 0.0, False),
            "paid_leave": ("ABS", 0.0, True),
            "unpaid_leave": ("ABS", 0.0, True),
            "holiday": ("HD", 0.0, False),
            "week_off": ("HD", 0.0, False),
        }
        for resolution, (kind, pct, leave) in cases.items():
            with self.subTest(resolution=resolution):
                spec = record_spec(resolution)
                self.assertEqual((spec[0], spec[2], spec[3]), (kind, pct, leave))

    def test_a_split_day_follows_how_many_halves_are_present(self):
        self.assertEqual(record_spec("split:P+P")[:1], ("FDP",))
        self.assertEqual(record_spec("split:P+A")[:1], ("HDP",))
        self.assertEqual(record_spec("split:A+PL")[:1], ("DFT",))
        self.assertEqual(record_spec("split:PL+UL")[:1], ("ABS",))

    def test_approving_overtime_changes_nothing(self):
        self.assertIsNone(record_spec("approve_ot"))


class LastRegularisationWinsTests(Base):
    DAY = D(2026, 9, 2)

    def row_for(self):
        rows, _t, _x = build_monthly_summary(
            SEP_START, SEP_END, Employee.objects.filter(pk=self.employee.pk)
        )
        return rows[0]

    def cell(self):
        context = _build_calendar_context(self.employee, SEP_START, SEP_END)
        return [
            c
            for m in context["months"]
            for w in m["weeks"]
            for c in w
            if c and c.get("date") == self.DAY
        ][0]

    def test_regularising_again_replaces_the_earlier_one_in_the_summary_and_calendar(
        self,
    ):
        self.punch(self.DAY)
        self.regularise(self.DAY, "absent")
        self.assertEqual(self.cell()["status"], "absent")
        self.regularise(self.DAY, "full_present")
        self.assertEqual(self.cell()["status"], "present")
        self.assertEqual(
            AttendanceConflictResolution._base_manager.filter(
                employee_id=self.employee, date=self.DAY
            ).count(),
            1,
        )

    def test_the_summary_counts_the_last_regularisation(self):
        self.regularise(self.DAY, "absent")
        absent = self.row_for()["absent"]
        self.regularise(self.DAY, "full_present")
        row = self.row_for()
        self.assertEqual(row["present"], 1)
        self.assertEqual(row["absent"], absent - 1)

    def test_the_work_record_follows_the_last_regularisation(self):
        self.punch(self.DAY)
        self.assertEqual(self.record(self.DAY).work_record_type, "FDP")
        self.regularise(self.DAY, "absent")
        self.assertEqual(
            (self.record(self.DAY).work_record_type, self.record(self.DAY).message),
            ("DFT", "Regularised: Absent"),
        )
        self.regularise(self.DAY, "half_present")
        self.assertEqual(
            (
                self.record(self.DAY).work_record_type,
                self.record(self.DAY).day_percentage,
            ),
            ("HDP", 0.5),
        )
        self.regularise(self.DAY, "full_present")
        self.assertEqual(
            (self.record(self.DAY).work_record_type, self.record(self.DAY).message),
            ("FDP", "Regularised: Present"),
        )

    def test_a_regularisation_makes_the_work_record_when_the_day_has_none(self):
        self.assertIsNone(self.record(self.DAY))
        self.regularise(self.DAY, "full_present")
        self.assertEqual(self.record(self.DAY).work_record_type, "FDP")

    def test_a_later_attendance_save_does_not_undo_the_regularisation(self):
        attendance = self.punch(self.DAY)
        self.regularise(self.DAY, "absent")
        attendance.attendance_worked_hour = "08:30"
        attendance.save()
        self.assertEqual(self.record(self.DAY).work_record_type, "DFT")

    def test_undoing_the_regularisation_puts_the_attendance_back(self):
        self.punch(self.DAY)
        row = self.regularise(self.DAY, "absent")
        row.delete()
        self.assertEqual(
            (self.record(self.DAY).work_record_type, self.record(self.DAY).message),
            ("FDP", "Present"),
        )

    def test_undoing_a_regularisation_that_made_the_record_removes_it(self):
        row = self.regularise(self.DAY, "full_present")
        row.delete()
        self.assertIsNone(self.record(self.DAY))

    def test_a_leave_approved_after_a_regularisation_does_not_replace_it(self):
        from leave.models import LeaveRequest, LeaveType
        from leave.signals import leaverequest_pre_save

        self.regularise(self.DAY, "full_present")
        leave_type = LeaveType.objects.create(name="After Reg", payment="paid")
        leave = LeaveRequest.objects.bulk_create(
            [
                LeaveRequest(
                    employee_id=self.employee,
                    leave_type_id=leave_type,
                    start_date=self.DAY,
                    end_date=self.DAY,
                    start_date_breakdown="full_day",
                    end_date_breakdown="full_day",
                    requested_days=1,
                    description="Test",
                    status="approved",
                )
            ]
        )[0]
        leaverequest_pre_save(LeaveRequest, leave)
        record = self.record(self.DAY)
        self.assertEqual(
            (record.work_record_type, record.is_leave_record), ("FDP", False)
        )

    def test_an_approve_overtime_resolution_leaves_the_work_record_alone(self):
        self.punch(self.DAY)
        before = self.record(self.DAY).work_record_type
        self.regularise(self.DAY, "approve_ot")
        self.assertEqual(self.record(self.DAY).work_record_type, before)


class LeaveExclusionTests(Base):
    """A leave takes the holidays and week-offs its type does not exclude, and not those it does."""

    LEAVE_START, LEAVE_END = D(2026, 9, 4), D(
        2026, 9, 8
    )  # Fri to Tue: Sat 5th, Sun 6th, holiday Mon 7th
    HOLIDAY = D(2026, 9, 7)

    def setUp(self):
        super().setUp()
        from base.models import Holidays

        Holidays.objects.create(
            name="Exclusion Holiday", start_date=self.HOLIDAY, end_date=self.HOLIDAY
        )

    def patched(self):
        weekend = SATURDAYS + SUNDAYS
        return (
            patch(
                "attendance.views.summary.get_company_leave_dates", return_value=weekend
            ),
            patch(
                "attendance.methods.leave_days.get_company_leave_dates",
                return_value=weekend,
            ),
        )

    def leave(self, exclude_company="no", exclude_holiday="no", name=None):
        from leave.models import LeaveRequest, LeaveType

        leave_type = LeaveType.objects.create(
            name=name or f"Excl {exclude_company}/{exclude_holiday}",
            payment="paid",
            exclude_company_leave=exclude_company,
            exclude_holiday=exclude_holiday,
        )
        return LeaveRequest.objects.bulk_create(
            [
                LeaveRequest(
                    employee_id=self.employee,
                    leave_type_id=leave_type,
                    start_date=self.LEAVE_START,
                    end_date=self.LEAVE_END,
                    start_date_breakdown="full_day",
                    end_date_breakdown="full_day",
                    requested_days=5,
                    description="Test",
                    status="approved",
                )
            ]
        )[0]

    def table(self):
        first, second = self.patched()
        with first, second:
            rows, _t, _x = build_monthly_summary(
                SEP_START, SEP_END, Employee.objects.filter(pk=self.employee.pk)
            )
        return rows[0]

    def cells(self):
        first, second = self.patched()
        with first, second:
            context = _build_calendar_context(self.employee, SEP_START, SEP_END)
        return {
            c["date"]: c["status"]
            for m in context["months"]
            for w in m["weeks"]
            for c in w
            if c and c.get("date")
        }

    def counted(self, leave):
        from attendance.methods.leave_days import leave_counted_dates

        first, second = self.patched()
        with first, second:
            return leave_counted_dates(leave)

    # -- the rule on its own
    def test_excluded_dates_follow_the_type_flags(self):
        class T:
            def __init__(self, c, h):
                self.exclude_company_leave, self.exclude_holiday = c, h

        holidays, week_offs = {D(2026, 9, 7)}, {D(2026, 9, 5), D(2026, 9, 6)}
        self.assertEqual(excluded_dates(T("no", "no"), holidays, week_offs), set())
        self.assertEqual(excluded_dates(T("yes", "no"), holidays, week_offs), week_offs)
        self.assertEqual(excluded_dates(T("no", "yes"), holidays, week_offs), holidays)
        self.assertEqual(
            excluded_dates(T("yes", "yes"), holidays, week_offs), holidays | week_offs
        )

    # -- the summary table
    def test_a_type_that_excludes_both_takes_only_the_working_days(self):
        self.leave("yes", "yes")
        row = self.table()
        # The month has eight weekend days; the leave takes none of them, nor the holiday.
        self.assertEqual(
            (row["paid_leave"], row["week_off"], row["holiday"]), (2, 8, 1)
        )

    def test_a_type_that_excludes_nothing_takes_every_day_as_leave(self):
        self.leave("no", "no")
        row = self.table()
        # The leave takes the weekend (so six of the eight weekend days are left) and the holiday.
        self.assertEqual(
            (row["paid_leave"], row["week_off"], row["holiday"]), (5, 6, 0)
        )

    def test_excluding_only_holidays_leaves_the_holiday_a_holiday(self):
        self.leave("no", "yes")
        row = self.table()
        # The weekend counts as leave (six weekend days left), the holiday stays a holiday.
        self.assertEqual(
            (row["paid_leave"], row["week_off"], row["holiday"]), (4, 6, 1)
        )

    def test_excluding_only_company_week_offs_leaves_the_weekend_a_week_off(self):
        self.leave("yes", "no")
        row = self.table()
        # The weekend stays week-off (all eight); the holiday is taken as leave: the 4th, 7th, 8th.
        self.assertEqual(
            (row["paid_leave"], row["week_off"], row["holiday"]), (3, 8, 0)
        )

    # -- the calendar and the grid
    def test_the_calendar_shows_the_excluded_days_as_what_they_are(self):
        self.leave("yes", "yes")
        cells = self.cells()
        self.assertEqual(cells[D(2026, 9, 4)], "paid_leave")
        self.assertEqual(cells[D(2026, 9, 5)], "week_off")
        self.assertEqual(cells[D(2026, 9, 6)], "week_off")
        self.assertEqual(cells[D(2026, 9, 7)], "holiday")
        self.assertEqual(cells[D(2026, 9, 8)], "paid_leave")

    def test_the_calendar_shows_every_day_as_leave_when_nothing_is_excluded(self):
        self.leave("no", "no")
        cells = self.cells()
        for day in range(4, 9):
            self.assertEqual(cells[D(2026, 9, day)], "paid_leave", day)

    # -- the employee's own week-offs (their roster) decide what is excluded
    def test_a_roster_decides_which_days_a_leave_excludes(self):
        from base.models import Department, Roster

        department = Department.objects.create(department="Exclusion Roster")
        # Rostered 4th to 8th; only the 6th is a day off, so the company's Saturday the 5th is worked.
        for day in range(4, 9):
            Roster.objects.create(
                employee=self.employee,
                date=D(2026, 9, day),
                department=department,
                is_off=(day == 6),
            )
        leave = self.leave("yes", "yes")
        counted = self.counted(leave)
        self.assertIn(D(2026, 9, 5), counted)  # a worked Saturday: leave
        self.assertNotIn(D(2026, 9, 6), counted)  # the roster's day off: excluded
        self.assertNotIn(D(2026, 9, 7), counted)  # the holiday: excluded
        self.assertEqual(self.table()["paid_leave"], 3)  # the 4th, 5th and 8th

    # -- the work records
    def test_no_leave_work_record_is_made_for_an_excluded_day(self):
        from leave.models import LeaveRequest
        from leave.signals import leaverequest_pre_save

        leave = self.leave("yes", "yes")
        first, second = self.patched()
        with first, second:
            leaverequest_pre_save(LeaveRequest, leave)
        made = {
            r.date
            for r in WorkRecords._base_manager.filter(
                employee_id=self.employee, is_leave_record=True
            )
        }
        self.assertEqual(made, {D(2026, 9, 4), D(2026, 9, 8)})

    def test_every_day_gets_a_leave_work_record_when_nothing_is_excluded(self):
        from leave.models import LeaveRequest
        from leave.signals import leaverequest_pre_save

        leave = self.leave("no", "no")
        first, second = self.patched()
        with first, second:
            leaverequest_pre_save(LeaveRequest, leave)
        made = {
            r.date
            for r in WorkRecords._base_manager.filter(
                employee_id=self.employee, is_leave_record=True
            )
        }
        self.assertEqual(made, {D(2026, 9, d) for d in range(4, 9)})

    def test_saving_the_leave_again_after_the_type_changes_drops_the_records_it_no_longer_counts(
        self,
    ):
        from leave.models import LeaveRequest
        from leave.signals import leaverequest_pre_save

        leave = self.leave("no", "no")
        first, second = self.patched()
        with first, second:
            leaverequest_pre_save(LeaveRequest, leave)
            leave.leave_type_id.exclude_company_leave = "yes"
            leave.leave_type_id.exclude_holiday = "yes"
            leave.leave_type_id.save()
            leaverequest_pre_save(LeaveRequest, leave)
        made = {
            r.date
            for r in WorkRecords._base_manager.filter(
                employee_id=self.employee, is_leave_record=True
            )
        }
        self.assertEqual(made, {D(2026, 9, 4), D(2026, 9, 8)})
