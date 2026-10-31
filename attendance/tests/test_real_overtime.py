import datetime

from django.test import SimpleTestCase, TestCase

from attendance.methods.utils import real_overtime_seconds
from attendance.models import (
    Attendance,
    AttendanceConflictResolution,
    AttendanceValidationCondition,
)
from attendance.views.summary import approve_overtime_if_eligible, ot_counts
from horilla.testkit import make_company, make_employee


class RealOvertimeTests(SimpleTestCase):
    """Overtime is what was worked beyond the minimum hours, never more than the stored figure."""

    def test_short_day_has_no_overtime_even_if_one_is_stored(self):
        self.assertEqual(real_overtime_seconds(25500, "08:00", 3600), 0)

    def test_overtime_is_held_to_the_hours_beyond_the_minimum(self):
        self.assertEqual(real_overtime_seconds(30000, "08:00", 3600), 1200)

    def test_stored_overtime_is_kept_when_it_is_really_worked(self):
        self.assertEqual(real_overtime_seconds(32400, "08:00", 3600), 3600)

    def test_no_minimum_means_all_worked_hours_are_overtime(self):
        self.assertEqual(real_overtime_seconds(7200, "00:00", 7200), 7200)

    def test_nothing_stored_is_nothing(self):
        self.assertEqual(real_overtime_seconds(32400, "08:00", 0), 0)


class OvertimeCountsTests(SimpleTestCase):
    def test_approved_counts(self):
        self.assertTrue(ot_counts(True, None))

    def test_unapproved_does_not(self):
        self.assertFalse(ot_counts(False, None))

    def test_regularized_or_approved_by_hr_counts(self):
        self.assertTrue(ot_counts(False, "full_present"))
        self.assertTrue(ot_counts(False, "approve_ot"))


class ApproveOvertimeTests(TestCase):
    """Overtime is approved only when it reaches the validation rule's minimum."""

    DAY = datetime.date(2026, 9, 2)  # a Wednesday

    def setUp(self):
        company = make_company("Approve OT Co")
        self.employee = make_employee(company=company, email="approve-ot@test.horilla")
        AttendanceValidationCondition.objects.all().delete()
        AttendanceValidationCondition.objects.create(
            validation_at_work="09:00",
            minimum_overtime_to_approve="00:30",
            overtime_cutoff="02:00",
            auto_approve_ot=False,
        )

    def _attendance(self, worked):
        return Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=self.DAY,
            attendance_clock_in_date=self.DAY,
            attendance_clock_in=datetime.time(9, 0),
            attendance_clock_out_date=self.DAY,
            attendance_clock_out=datetime.time(18, 0),
            attendance_worked_hour=worked,
            minimum_hour="08:00",
            attendance_validated=True,
        )

    def _approved(self):
        return Attendance.objects.get(
            employee_id=self.employee, attendance_date=self.DAY
        ).attendance_overtime_approve

    def test_overtime_at_the_minimum_is_approved(self):
        self._attendance("08:30")
        approve_overtime_if_eligible(self.employee, [self.DAY])
        self.assertTrue(self._approved())

    def test_overtime_below_the_minimum_is_not_approved(self):
        self._attendance("08:15")
        approve_overtime_if_eligible(self.employee, [self.DAY])
        self.assertFalse(self._approved())

    def test_a_day_without_overtime_is_not_approved(self):
        self._attendance("07:30")
        approve_overtime_if_eligible(self.employee, [self.DAY])
        self.assertFalse(self._approved())

    def test_not_eligible_leaves_no_approve_mark_behind(self):
        self._attendance("08:15")
        AttendanceConflictResolution.objects.create(
            employee_id=self.employee, date=self.DAY, resolution="approve_ot"
        )
        approve_overtime_if_eligible(self.employee, [self.DAY])
        self.assertFalse(
            AttendanceConflictResolution.objects.filter(
                employee_id=self.employee, date=self.DAY, resolution="approve_ot"
            ).exists()
        )
