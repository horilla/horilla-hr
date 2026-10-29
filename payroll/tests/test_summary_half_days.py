"""
What payroll pays when a day is only part worked: half-day leave, a clock half day,
Half Day / Half Absent set by HR, and split days -- read through the attendance
summary exactly as the batch run reads it.
"""

import datetime

from django.test import TestCase

from attendance.methods.utils import get_employee_attendance_summary
from attendance.models import Attendance, AttendanceConflictResolution
from horilla.testkit import make_company, make_employee
from leave.models import LeaveRequest, LeaveType
from payroll.methods import batch_run
from payroll.methods.methods import compute_salary_on_period
from payroll.models.models import Contract

WEDNESDAY = datetime.date(2026, 9, 2)
DAY_WAGE = 1000.0


class HalfDayPayrollTests(TestCase):
    def setUp(self):
        company = make_company("Half Pay Co")
        self.employee = make_employee(company=company, email="halfpay@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        Contract.objects.create(
            contract_name="Daily",
            employee_id=self.employee,
            contract_start_date=datetime.date(2026, 1, 1),
            wage_type="daily",
            wage=DAY_WAGE,
            contract_status="active",
            deduct_leave_from_basic_pay=True,
            calculate_daily_leave_amount=True,
            deduction_for_one_leave_amount=0,
        )

    def _leave(self, payment, breakdown="second_half", name="Leave"):
        # bulk_create: saving a half-day request fires a signal that overflows a column.
        leave_type = LeaveType.objects.create(name=name, payment=payment)
        LeaveRequest.objects.bulk_create(
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
        )

    def _attend(
        self, worked, clock_in=datetime.time(9, 0), clock_out=datetime.time(18, 0)
    ):
        """
        A punch pair. On a day with half-day leave it has to be the half that is worked: with no
        shift times the halves split at 13:00, so a second-half leave is worked 09:00-13:00 and a
        first-half leave 13:00-17:00. Punching a whole day on top of a half-day leave is a conflict
        (see the conflict tests below), not a normal day.
        """
        Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=WEDNESDAY,
            attendance_clock_in_date=WEDNESDAY,
            attendance_clock_in=clock_in,
            attendance_clock_out_date=WEDNESDAY,
            attendance_clock_out=clock_out,
            attendance_worked_hour=worked,
            minimum_hour="08:00",
            attendance_validated=True,
        )

    def _resolve(self, resolution):
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=WEDNESDAY, resolution=resolution
        )

    def _pay(self):
        """(unpaid days, paid days, loss of pay) for the day, as payroll reads the summary."""
        summary = get_employee_attendance_summary([self.employee], WEDNESDAY, WEDNESDAY)
        row = summary[self.employee.pk]
        data = compute_salary_on_period(
            self.employee, WEDNESDAY, WEDNESDAY, month_summary=row
        )
        return data["unpaid_days"], data["paid_days"], data["loss_of_pay"]

    def test_half_paid_leave_with_nothing_else_loses_the_absent_half(self):
        self._leave("paid")
        self.assertEqual(self._pay(), (0.5, 0.5, 500.0))

    def test_half_paid_leave_with_attendance_loses_nothing(self):
        self._leave("paid")
        self._attend("04:00", clock_out=datetime.time(13, 0))
        self.assertEqual(self._pay(), (0, 1.0, 0))

    def test_half_paid_first_half_leave_with_the_second_half_worked_loses_nothing(self):
        self._leave("paid", breakdown="first_half")
        self._attend(
            "04:00", clock_in=datetime.time(13, 0), clock_out=datetime.time(17, 0)
        )
        self.assertEqual(self._pay(), (0, 1.0, 0))

    def test_half_unpaid_leave_with_attendance_loses_the_leave_half(self):
        self._leave("unpaid")
        self._attend("04:00", clock_out=datetime.time(13, 0))
        self.assertEqual(self._pay(), (0.5, 0.5, 500.0))

    def test_half_paid_leave_with_hours_too_short_loses_the_other_half(self):
        self._leave("paid")
        self._attend("01:00", clock_out=datetime.time(10, 0))
        self.assertEqual(self._pay(), (0.5, 0.5, 500.0))

    # -- a day worked on top of a half-day leave is a conflict until HR resolves it ----------

    def _summary_row(self):
        return get_employee_attendance_summary([self.employee], WEDNESDAY, WEDNESDAY)[
            self.employee.pk
        ]

    def test_a_punch_slightly_into_the_leave_half_is_within_the_grace(self):
        self._leave("paid")
        self._attend("04:20", clock_out=datetime.time(13, 20))
        self.assertEqual(self._summary_row()["unresolved_conflicts"], 0)
        self.assertEqual(self._pay(), (0, 1.0, 0))

    def test_a_punch_well_into_the_leave_half_is_a_conflict(self):
        self._leave("paid")
        self._attend("06:00", clock_out=datetime.time(15, 0))
        self.assertEqual(self._summary_row()["unresolved_conflicts"], 1)

    def test_a_full_day_worked_on_a_half_leave_is_a_conflict_that_blocks_the_payroll_run(
        self,
    ):
        self._leave("paid")
        self._attend(
            "08:00"
        )  # 09:00-18:00: the whole day on top of half a day of leave
        self.assertEqual(self._summary_row()["unresolved_conflicts"], 1)
        # The payroll rule for any unresolved conflict is unchanged (the day is unpaid), but the
        # batch run refuses to generate it: it is flagged for HR instead of silently deducted.
        result = batch_run.review([self.employee], WEDNESDAY, WEDNESDAY)
        self.assertEqual(result["blocked_count"], 1)
        self.assertIn("unresolved", str(result["rows"][0]["problems"][0][1]))

    def test_resolving_that_conflict_pays_the_day_and_unblocks_the_run(self):
        self._leave("paid")
        self._attend("08:00")
        self._resolve("split:PL+P")
        self.assertEqual(self._summary_row()["unresolved_conflicts"], 0)
        self.assertEqual(self._pay(), (0, 1.0, 0))
        self.assertEqual(
            batch_run.review([self.employee], WEDNESDAY, WEDNESDAY)["blocked_count"], 0
        )

    def test_a_clock_half_day_loses_the_short_half(self):
        self._attend("04:30")
        self.assertEqual(self._pay(), (0.5, 0.5, 500.0))

    def test_a_short_day_loses_the_whole_day(self):
        self._attend("01:00")
        self.assertEqual(self._pay(), (1.0, 0, 1000.0))

    def test_a_half_day_set_by_hr_is_paid_in_full(self):
        self._resolve("half_present")
        self.assertEqual(self._pay(), (0, 1.0, 0))

    def test_half_absent_loses_the_absent_half(self):
        self._resolve("half_absent")
        self.assertEqual(self._pay(), (0.5, 0.5, 500.0))

    def test_split_present_and_unpaid_loses_the_unpaid_half(self):
        self._resolve("split:P+UL")
        self.assertEqual(self._pay(), (0.5, 0.5, 500.0))

    def test_split_present_and_paid_loses_nothing(self):
        self._resolve("split:PL+P")
        self.assertEqual(self._pay(), (0, 1.0, 0))

    def test_split_absent_and_absent_loses_the_day(self):
        self._resolve("split:A+A")
        self.assertEqual(self._pay(), (1.0, 0, 1000.0))
